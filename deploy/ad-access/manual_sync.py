"""Mirror the WordPress IP block list to both authenticated site origins.

The WordPress plugin protects the Iran origin directly. This reconciler also
protects the Europe origin and keeps both in sync after manual unblock/reblock.
It never removes an existing ban when WordPress cannot be reached.
"""
import ipaddress
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

from worker import request


FETCH_CODE = """
import json
from seo_brain.db.engine import get_engine
from seo_brain.integrations.wordpress.security import WordPressSecurityService, resolve_site_by_domain
engine = get_engine()
site = resolve_site_by_domain(engine, 'modirankhodro-emdad.com')
result = WordPressSecurityService(engine).list_blocked(site)
if not result.get('connected'):
    raise RuntimeError(result.get('code', 'wordpress_unavailable'))
print(json.dumps([item['ip'] for item in result['items']]))
"""


def fetch_wordpress_ips():
    result = subprocess.run(
        ['docker', 'exec', '-i', 'seo-brain-backend-1', 'python', '-c', FETCH_CODE],
        capture_output=True, text=True, check=True, timeout=45,
    )
    items = json.loads(result.stdout)
    if not isinstance(items, list):
        raise ValueError('invalid WordPress block list')
    return {str(ipaddress.ip_address(ip)) for ip in items}


def save_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as out:
            json.dump(payload, out, separators=(',', ':'))
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def reconcile(config, state_path, desired, transport=request, limit_per_origin=3):
    path = Path(state_path)
    state = json.loads(path.read_text()) if path.exists() else {'origins': {}}
    errors = []
    protected_ips = set(config.get('protected_ips', []))
    protected_ranges = [ipaddress.ip_network(x) for x in config.get('protected_ranges', [])]
    safe_desired = set()
    for ip in desired:
        address = ipaddress.ip_address(ip)
        if not address.is_global or ip in protected_ips or any(address in network for network in protected_ranges):
            errors.append('protected_ip_skipped')
        else:
            safe_desired.add(ip)

    for origin in config['origins']:
        name = origin['name']
        records = state['origins'].setdefault(name, {})
        attempted = 0
        for ip in sorted(safe_desired | set(records)):
            record = records.get(ip)
            if ip in safe_desired and record and record['active']:
                continue
            if ip not in safe_desired and not record:
                continue
            if limit_per_origin is not None and attempted >= limit_per_origin:
                continue
            if name == 'eu' and attempted:
                time.sleep(4)
            attempted += 1
            if ip in safe_desired and not record:
                # Persist the ID before delivery. A retry cannot create an
                # untracked second owner if the origin applied the first call.
                record = {'id': 'wpmanual_' + secrets.token_hex(16), 'active': False}
                records[ip] = record
                save_json(path, state)
            action = 'block' if ip in safe_desired else 'unblock'
            try:
                result = transport(origin, action, ip, record['id'])
                if (result.get('ip') != ip or result.get('decision_id') != record['id']
                        or result.get('active') is not (action == 'block')
                        or not result.get('htaccess_sha256')):
                    raise RuntimeError('origin acknowledgement mismatch')
                if action == 'block':
                    record['active'] = True
                else:
                    del records[ip]
                save_json(path, state)
            except Exception as exc:
                errors.append(name + ':' + type(exc).__name__)
    return {'desired_count': len(safe_desired),
            'applied': {name: sum(bool(r['active']) for r in records.values())
                        for name, records in state['origins'].items()},
            'errors': errors, 'checked_at': time.time()}


def main():
    config = json.loads(Path('/etc/ead-access/config.json').read_text())
    state_path = '/var/lib/ead-access/manual-sync.json'
    status_path = '/var/lib/ead-access/manual-sync-status.json'
    try:
        desired = fetch_wordpress_ips()
        result = reconcile(config, state_path, desired)
    except Exception as exc:
        # A failed fetch must never trigger unblocks.
        result = {'errors': ['fetch:' + type(exc).__name__], 'checked_at': time.time()}
    save_json(status_path, result)
    print(json.dumps(result, separators=(',', ':')))
    if result['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
