"""One-time recovery from a server-to-Europe network ban; run on trusted operator host."""
import json
import subprocess
import tempfile
import time
from pathlib import Path

from manual_sync import reconcile
from worker import request


def remote_file(path):
    return subprocess.check_output(['ssh', 'gearbox', 'cat ' + path], timeout=20)


def main():
    config = json.loads(remote_file('/etc/ead-access/config.json'))
    original = json.loads(remote_file('/var/lib/ead-access/manual-sync.json'))
    desired = {ip for ip, row in original['origins']['iran'].items() if row['active']}
    count = 0

    def paced(origin, action, ip, decision_id):
        nonlocal count
        if origin['name'] == 'eu':
            time.sleep(4)
            count += 1
        return request(origin, action, ip, decision_id)

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'state.json'
        path.write_text(json.dumps(original))
        result = reconcile(config, path, desired, paced, limit_per_origin=None)
        subprocess.run(['scp', str(path), 'gearbox:/var/lib/ead-access/manual-sync.json'], check=True, timeout=30)
    print(json.dumps({'attempted_eu': count, 'result': result}, separators=(',', ':')))
    if result['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
