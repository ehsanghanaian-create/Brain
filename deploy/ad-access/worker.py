"""Prospective detector and authenticated delivery to both website origins."""
from contextlib import contextmanager
import os
import ipaddress
import tempfile
from contextlib import closing
import argparse
import hashlib
import hmac
import http.client
import json
import logging
import secrets
import socket
import sqlite3
import ssl
import time
from pathlib import Path
from detector import Config, Detector, SITE


class OriginConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=5, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


_origin_cooldown = {}


def request(origin, action, ip=None, decision_id=None, since=None):
    name = origin['name']
    if time.time() < _origin_cooldown.get(name, 0):
        raise TimeoutError('origin network cooldown')
    payload = dict(site=SITE, action=action, ts=int(time.time()), nonce=secrets.token_hex(16))
    if ip is not None:
        payload.update(ip=ip, decision_id=decision_id)
    if since is not None:
        payload['since'] = since
    raw = json.dumps(payload, separators=(',', ':')).encode()
    signature = hmac.new(origin['secret'].encode(), raw, hashlib.sha256).hexdigest()
    conn = OriginConnection(SITE, origin['address'])
    try:
        conn.request('POST', '/_ead_access.php', raw, {
            'Content-Type': 'application/json', 'X-EAD-Signature': signature,
            'Cache-Control': 'no-store',
        })
        response = conn.getresponse()
        data = json.loads(response.read(1048576))
        if response.status != 200:
            raise RuntimeError(f"origin {origin['name']} HTTP {response.status}: {data.get('error','invalid_response')}")
        if action in ('status', 'entries'):
            if data.get('site') != SITE:
                raise RuntimeError('origin site mismatch')
        elif data.get('decision_id') != decision_id or data.get('ip') != ip:
            raise RuntimeError('origin acknowledgement mismatch')
        return data
    except (TimeoutError, OSError):
        # Avoid hammering an origin that temporarily filters this controller's
        # IP. The other origin continues to receive decisions meanwhile.
        _origin_cooldown[name] = time.time() + 180
        raise
    finally:
        conn.close()


def detector(config):
    return Detector(config['state_db'], Config(enabled=config.get('enabled') is True,
        allowlist=tuple(config.get('protected_ips', [])), protected_ranges=tuple(config.get('protected_ranges', []))))


@contextmanager
def delivery_lock(config):
    # Shared by the service iteration and manual unblock, including outbound I/O.
    with open(str(config['state_db']) + '.delivery.lock', 'a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def setup(d):
    with d.connect() as cx:
        cx.execute('CREATE TABLE IF NOT EXISTS deliveries (decision INTEGER, origin TEXT, '
                   'active INTEGER, hash TEXT, checked REAL, PRIMARY KEY(decision,origin))')
        cx.execute('CREATE TABLE IF NOT EXISTS origin_health (origin TEXT PRIMARY KEY, hash TEXT, checked REAL)')


def entry_source(path):
    with closing(sqlite3.connect(path)) as cx:
        cx.executescript('''
          CREATE TABLE IF NOT EXISTS ads_click_events(id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id TEXT,event_type TEXT,ip_address TEXT,ip_resolution_version TEXT,
            ip_confidence TEXT,received_at REAL,gclid TEXT,metadata_json TEXT,utm_campaign TEXT,
            origin TEXT,entry_id INTEGER, UNIQUE(origin,entry_id));
          CREATE TABLE IF NOT EXISTS entry_cursors(origin TEXT PRIMARY KEY,last_id INTEGER);
          CREATE INDEX IF NOT EXISTS entry_click_ip ON ads_click_events(gclid,ip_address);
        ''')


def ingest_entries(config, transport):
    """Authenticated origin journals only; each origin starts prospectively."""
    path=config['entry_source_db'];errors=[]
    for origin in config['origins']:
        try:
            with closing(sqlite3.connect(path)) as lookup:
                known=lookup.execute('SELECT last_id FROM entry_cursors WHERE origin=?',(origin['name'],)).fetchone()
            result=transport(origin,'entries',since=known[0] if known else None)
            last=result.get('last_id'); entries=result.get('entries')
            if result.get('site')!=SITE or type(last) is not int or last<0 or not isinstance(entries,list) or len(entries)>1000:
                raise RuntimeError('invalid origin journal')
            with closing(sqlite3.connect(path, timeout=30)) as cx:
                cx.execute('BEGIN IMMEDIATE')
                cursor=cx.execute('SELECT last_id FROM entry_cursors WHERE origin=?',(origin['name'],)).fetchone()
                if cursor is None:
                    cx.execute('INSERT INTO entry_cursors VALUES(?,?)',(origin['name'],last));cx.commit();continue
                if last<cursor[0]:
                    # A reset journal cannot safely reuse entry IDs.
                    raise RuntimeError('origin journal reset; operator reconciliation required')
                pending=[x for x in entries if type(x.get('id')) is int and cursor[0]<x['id']<=last]
                pending.sort(key=lambda x:x['id'])
                if last>cursor[0] and (not pending or pending[0]['id']!=cursor[0]+1 or pending[-1]['id']!=last or len(pending)!=last-cursor[0]):
                    # Drop a lost window instead of constructing cross-gap pairs.
                    cx.execute('UPDATE entry_cursors SET last_id=? WHERE origin=?',(last,origin['name']));cx.commit()
                    raise RuntimeError('origin journal gap skipped; increase polling frequency')
                for item in pending:
                    ip=str(ipaddress.ip_address(item['ip_address']))
                    if not ipaddress.ip_address(ip).is_global or not isinstance(item.get('gclid'),str) or type(item.get('received_at')) not in (float,int):
                        raise RuntimeError('invalid journal entry')
                    cx.execute('INSERT OR IGNORE INTO ads_click_events(site_id,event_type,ip_address,ip_resolution_version,ip_confidence,received_at,gclid,metadata_json,utm_campaign,origin,entry_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (SITE,'landing',ip,'3','direct_peer',item['received_at'],item['gclid'],json.dumps({'signal':'fresh_ads_entry','navigation_type':'navigate'}),item.get('utm_campaign',''),origin['name'],item['id']))
                cx.execute('UPDATE entry_cursors SET last_id=? WHERE origin=?',(last,origin['name']));cx.commit()
        except Exception as exc:
            errors.append((origin['name'],str(exc)))
            if str(exc) != 'origin network cooldown':
                logging.error('entry ingest failed origin=%s: %s',origin['name'],exc)
    return errors


def sync_locked(config, d, transport, now, unblocks_only=False):
    errors = []
    with d.connect() as cx:
        decisions = [dict(row) for row in cx.execute('SELECT * FROM decisions ORDER BY id')]
    for origin in config['origins']:
        try:
            with d.connect() as cx:
                health = cx.execute('SELECT * FROM origin_health WHERE origin=?', (origin['name'],)).fetchone()
            force = False
            current_hash = health['hash'] if health else None
            checked = health['checked'] if health else 0
            if health is None or now - checked >= 30:
                status = transport(origin, 'status')
                if status.get('site') != SITE or status.get('enforcement_enabled') is not True:
                    raise RuntimeError('origin not enabled or identity mismatch')
                force = health is not None and status.get('htaccess_sha256') != current_hash
                current_hash = status.get('htaccess_sha256')
                checked = now
            for decision in decisions:
                # Re-read immediately before delivery. The CLI shares this lock.
                with d.connect() as cx:
                    live = cx.execute('SELECT active FROM decisions WHERE id=?', (decision['id'],)).fetchone()
                    sent = cx.execute('SELECT active FROM deliveries WHERE decision=? AND origin=?',
                                      (decision['id'], origin['name'])).fetchone()
                active = live['active']
                if unblocks_only and active:
                    continue
                if not force and sent and sent['active'] == active:
                    continue
                action = 'block' if active else 'unblock'
                key = config['decision_prefix'] + str(decision['id']).zfill(16)
                result = transport(origin, action, decision['ip'], key)
                if result.get('decision_id') != key or result.get('ip') != decision['ip'] or result.get('active') is not bool(active) or not result.get('htaccess_sha256'):
                    raise RuntimeError('origin acknowledgement mismatch')
                current_hash = result['htaccess_sha256']
                with d.connect() as cx:
                    cx.execute('INSERT OR REPLACE INTO deliveries VALUES(?,?,?,?,?)',
                               (decision['id'], origin['name'], active, current_hash, now))
            with d.connect() as cx:
                cx.execute('INSERT OR REPLACE INTO origin_health VALUES(?,?,?)', (origin['name'], current_hash, checked))
        except Exception as exc:
            errors.append((origin['name'], str(exc)))
            if str(exc) != 'origin network cooldown':
                logging.error('origin=%s failed; remaining origins still attempted: %s', origin['name'], exc)
    return errors


def export_snapshot(config, d, errors, now):
    """Sanitized dashboard data only. Never export origin configuration/secrets."""
    destination=config.get('dashboard_snapshot')
    if not destination:
        return
    names=[o['name'] for o in config['origins']]
    failed={name for name,_ in errors}
    with d.connect() as cx:
        decisions=[dict(r) for r in cx.execute('SELECT * FROM decisions WHERE active=1 ORDER BY id')]
        deliveries={(r['decision'],r['origin']):dict(r) for r in cx.execute('SELECT * FROM deliveries')}
        health={r['origin']:dict(r) for r in cx.execute('SELECT * FROM origin_health')}
    items=[]
    unique_click_ips={}
    if config.get('entry_source_db') and decisions:
        with closing(sqlite3.connect('file:'+config['entry_source_db']+'?mode=ro',uri=True)) as source:
            candidates=list({d[k] for d in decisions for k in ('first_click','second_click')})
            for start in range(0,len(candidates),400):
                batch=candidates[start:start+400]
                unique_click_ips.update({r[0]:r[1] for r in source.execute(
                    "SELECT gclid,MIN(ip_address) FROM ads_click_events WHERE gclid IN ("+','.join('?' for _ in batch)+") GROUP BY gclid HAVING COUNT(DISTINCT ip_address)=1",batch)})
    for decision in decisions:
        origins={}
        for name in names:
            sent=deliveries.get((decision['id'],name)); h=health.get(name)
            healthy=bool(h and 0<=now-h['checked']<=35 and name not in failed)
            origins[name]={'active':bool(sent['active']) if sent else None,
                           'checked':sent['checked'] if sent else None,
                           'health_checked':h['checked'] if h else None,'healthy':healthy}
        ack=bool(names) and all(x['active'] is True for x in origins.values())
        healthy=bool(names) and all(x['healthy'] for x in origins.values())
        state='blocked' if ack and healthy else ('unknown' if failed or ack else 'pending')
        match_gclids=[click for click in (decision['first_click'],decision['second_click']) if unique_click_ips.get(click)==decision['ip']]
        items.append({'decision_id':decision['id'],'ip':decision['ip'],'match_gclids':match_gclids,
                      'received':decision['received'],'status':state,
                      'origins':[{'name':name,'acknowledged':value['active'] is True,'checked':value['checked'],
                                  'healthy':value['healthy']} for name,value in origins.items()]})
    overall=bool(names) and not failed and all(name in health and 0<=now-health[name]['checked']<=35 for name in names)
    payload={'generated_at':now,'enabled':config.get('enabled') is True,'site':SITE,'items':items,
             'healthy':overall,'errors':[name+':source_or_origin_unavailable' for name,_ in errors],
             'semantics':'blocked means recent host acknowledgement, not an independent visitor HTTP probe'}
    path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True);os.chmod(path.parent,0o755)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf8',dir=path.parent,delete=False) as out:
            temporary=out.name;json.dump(payload,out,separators=(',',':'));out.flush();os.fsync(out.fileno())
        os.chmod(temporary,0o644);os.replace(temporary,path);temporary=None
    finally:
        if temporary and os.path.exists(temporary):os.unlink(temporary)


def safe_export(config,d,errors,now):
    try:export_snapshot(config,d,errors,now)
    except Exception:logging.exception('dashboard snapshot export failed; enforcement continues')


def iteration(config, transport=request, now=None):
    now = time.time() if now is None else now
    with delivery_lock(config):
        d = detector(config); setup(d)
        ingest_errors=[]
        if config.get('entry_source_db'):
            entry_source(config['entry_source_db'])
            d.bootstrap(config['entry_source_db'])
            ingest_errors=ingest_entries(config, transport)
            d.poll(config['entry_source_db'])
        else:
            d.poll(config['source_db'])
        # Kill switch stops new detection AND outbound writes; existing bans persist.
        if config.get('enabled') is not True:
            safe_export(config,d,ingest_errors,now)
            return ingest_errors
        errors=ingest_errors + sync_locked(config, d, transport, now)
        safe_export(config,d,errors,time.time() if now is None else now)
        return errors


def unblock(config, ip, reason, transport=request, now=None):
    ip = str(ipaddress.ip_address(ip))
    with delivery_lock(config):
        d = detector(config); setup(d)
        count = d.unblock(ip, reason)
        # Operator removal is allowed even with detection disabled. Failures remain
        # pending in durable inactive decisions for subsequent retry.
        errors = sync_locked(config, d, transport, time.time() if now is None else now, unblocks_only=True)
        safe_export(config,d,errors,time.time() if now is None else now)
        return {'unblocked_decisions': count, 'errors': errors}


def run(config_path):
    while True:
        try:
            config = json.loads(Path(config_path).read_text())
            iteration(config)
        except Exception:
            logging.exception('access rule iteration failed; will retry')
        time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('command', choices=['run', 'status', 'unblock'])
    ap.add_argument('--ip')
    ap.add_argument('--reason')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.command == 'run':
        return run(args.config)
    cfg = json.loads(Path(args.config).read_text())
    d = detector(cfg)
    if args.command == 'status':
        print(json.dumps({'enabled': cfg.get('enabled') is True, 'active_decisions': d.active_decisions(),
            'origins': {o['name']: request(o, 'status') for o in cfg['origins']}}, indent=2))
    else:
        if not args.ip or not args.reason:
            ap.error('--ip and --reason required')
        print(json.dumps(unblock(cfg, args.ip, args.reason)))



if __name__ == '__main__':
    main()
