"""Local-only, fail-closed eligibility detector. No network or enforcement.

Call bootstrap(source_path) before poll(). First bootstrap skips historical rows.
process_event() is the ordered-event integration API; IDs must be monotonic.
All transitions and cursor updates serialize through BEGIN IMMEDIATE.
"""
from contextlib import contextmanager, closing
import datetime as dt
import ipaddress
import json
import re
import sqlite3
from dataclasses import dataclass

SITE = "modirankhodro-emdad.com"


@dataclass(frozen=True)
class Config:
    enabled: bool = False
    allowlist: tuple = ()
    protected_ranges: tuple = ()


class Detector:
    def __init__(self, state_path, config=Config()):
        self.path, self.config = str(state_path), config
        self.allow = {ipaddress.ip_address(x) for x in config.allowlist}
        self.protected = tuple(ipaddress.ip_network(x, strict=False) for x in config.protected_ranges)
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS cursor(singleton INTEGER PRIMARY KEY CHECK(singleton=1), value INTEGER);
              CREATE TABLE IF NOT EXISTS bootstrap_floor(singleton INTEGER PRIMARY KEY, value INTEGER);
              CREATE TABLE IF NOT EXISTS processed(event_id INTEGER PRIMARY KEY);
              CREATE TABLE IF NOT EXISTS unblock_floor(site TEXT, ip TEXT, event_id INTEGER, PRIMARY KEY(site,ip));
              CREATE TABLE IF NOT EXISTS clicks(site TEXT, ip TEXT, gclid TEXT, received REAL, event_id INTEGER,
                PRIMARY KEY(site,ip,gclid));
              CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, site TEXT, ip TEXT, first_click TEXT,
                second_click TEXT, received REAL, active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(site,ip,first_click,second_click));
              CREATE UNIQUE INDEX IF NOT EXISTS active_ip ON decisions(site,ip) WHERE active=1;
              CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT DEFAULT CURRENT_TIMESTAMP,
                action TEXT, site TEXT, ip TEXT, detail TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def bootstrap(self, source_path):
        with closing(sqlite3.connect('file:' + str(source_path) + '?mode=ro', uri=True)) as source:
            maximum = source.execute('SELECT COALESCE(MAX(id),0) FROM ads_click_events').fetchone()[0]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO cursor VALUES(1,?)', (maximum,))
            db.execute('INSERT OR IGNORE INTO bootstrap_floor VALUES(1,?)', (maximum,))
            db.commit()

    def poll(self, source_path, limit=1000):
        self.bootstrap(source_path)
        with self.connect() as db:
            cursor = db.execute('SELECT value FROM cursor').fetchone()[0]
        with closing(sqlite3.connect('file:' + str(source_path) + '?mode=ro', uri=True)) as source:
            source.row_factory = sqlite3.Row
            events = source.execute('SELECT * FROM ads_click_events WHERE id>? ORDER BY id LIMIT ?',
                                    (cursor, limit)).fetchall()
        return [decision for event in events if (decision := self.process_event(dict(event))) is not None]

    def eligible(self, event):
        if not self.config.enabled or event.get('site_id') != SITE or event.get('event_type') != 'landing':
            return None
        if str(event.get('ip_resolution_version')) != '3' or event.get('ip_confidence') not in ('trusted_proxy', 'direct_peer'):
            return None
        try:
            ip = ipaddress.ip_address(event.get('ip_address', ''))
            if not ip.is_global or ip in self.allow or any(ip in net for net in self.protected):
                return None
            meta = event.get('metadata')
            if meta is None:
                meta = json.loads(event.get('metadata_json') or '{}')
            if not isinstance(meta, dict):
                return None
            fresh = meta.get('fresh_ads_entry') is True if 'fresh_ads_entry' in meta else meta.get('signal') == 'fresh_ads_entry'
            if not fresh:
                return None
            if meta.get('navigation_type') != 'navigate':
                return None
            if meta.get('purpose') in ('healthcheck', 'diagnostic', 'test', 'qa') or meta.get('synthetic'):
                return None
            campaign = str(event.get('utm_campaign') or '') + ' ' + str(event.get('utm_source') or '')
            if re.search(r'(?i)(?:^|[^a-z])(qa|test|synthetic|diagnostic|healthcheck)(?:$|[^a-z])', campaign):
                return None
            click = event.get('gclid') or ''
            if not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', click) or re.match(r'(?i)(test|fake|synthetic|qa|health|diagnostic)', click):
                return None
            stamp = event['received_at']
            if isinstance(stamp, (float, int)):
                received = float(stamp)
            else:
                parsed = dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.timezone.utc)
                received = parsed.timestamp()
            if not (0 <= received < 253402300800):
                return None
            return str(ip), click, received
        except (ValueError, TypeError, KeyError):
            return None

    def process_event(self, event):
        event_id = int(event['id'])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cursor = db.execute('SELECT value FROM cursor').fetchone()
            if cursor is None:
                raise RuntimeError('bootstrap required; historical events must not trigger blocks')
            floor = db.execute('SELECT value FROM bootstrap_floor').fetchone()[0]
            if event_id <= floor or db.execute('SELECT 1 FROM processed WHERE event_id=?', (event_id,)).fetchone():
                db.rollback()
                return None
            db.execute('INSERT INTO processed VALUES(?)', (event_id,))
            db.execute('UPDATE cursor SET value=MAX(value,?)', (event_id,))
            eligible = self.eligible(event)
            if eligible is None:
                db.commit()
                return None
            ip, click, received = eligible
            reset = db.execute('SELECT event_id FROM unblock_floor WHERE site=? AND ip=?', (SITE, ip)).fetchone()
            reset_id = reset[0] if reset else 0
            if event_id <= reset_id:
                db.commit()
                return None
            inserted = db.execute('INSERT OR IGNORE INTO clicks VALUES(?,?,?,?,?)',
                                  (SITE, ip, click, received, event_id)).rowcount
            decision = None
            if inserted and not db.execute('SELECT 1 FROM decisions WHERE site=? AND ip=? AND active=1', (SITE, ip)).fetchone():
                prior = db.execute('SELECT gclid FROM clicks WHERE site=? AND ip=? AND gclid<>? '
                                   'AND ABS(received-?)<60 AND event_id>? ORDER BY received DESC LIMIT 1',
                                   (SITE, ip, click, received, reset_id)).fetchone()
                if prior:
                    row = db.execute('INSERT OR IGNORE INTO decisions(site,ip,first_click,second_click,received) VALUES(?,?,?,?,?)',
                                     (SITE, ip, prior[0], click, received))
                    if row.rowcount:
                        decision = dict(id=row.lastrowid, site=SITE, ip=ip, first_click=prior[0], second_click=click,
                                        received=received, permanent=True)
                        db.execute('INSERT INTO audit(action,site,ip,detail) VALUES(?,?,?,?)',
                                   ('block_decision', SITE, ip, json.dumps(decision)))
            db.commit()
            return decision

    def active_decisions(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute('SELECT * FROM decisions WHERE active=1 ORDER BY id')]

    def unblock(self, ip, reason):
        if not reason or not reason.strip():
            raise ValueError('audit reason required')
        ip = str(ipaddress.ip_address(ip))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute('UPDATE decisions SET active=0 WHERE site=? AND ip=? AND active=1', (SITE, ip)).rowcount
            floor = db.execute('SELECT COALESCE(MAX(value),0) FROM cursor').fetchone()[0]
            db.execute('INSERT INTO unblock_floor VALUES(?,?,?) ON CONFLICT(site,ip) DO UPDATE SET event_id=MAX(event_id,excluded.event_id)',
                       (SITE, ip, floor))
            # Seen click IDs remain forever, preventing a replay of the old pair.
            db.execute('INSERT INTO audit(action,site,ip,detail) VALUES(?,?,?,?)', ('unblock', SITE, ip, reason))
            db.commit()
            return count
