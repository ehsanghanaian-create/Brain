import json
import tempfile
import unittest
from pathlib import Path

from manual_sync import reconcile


class ManualSyncTests(unittest.TestCase):
    def test_limits_new_deliveries_per_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            config = {'origins': [{'name': 'iran'}], 'protected_ips': [], 'protected_ranges': []}
            desired = {'8.8.4.4', '8.8.8.8', '1.1.1.1', '9.9.9.9'}

            def transport(origin, action, ip, decision_id):
                return {'ip': ip, 'decision_id': decision_id, 'active': action == 'block', 'htaccess_sha256': 'hash'}

            self.assertEqual(reconcile(config, state, desired, transport)['applied']['iran'], 3)
            self.assertEqual(reconcile(config, state, desired, transport)['applied']['iran'], 4)

    def test_block_retry_unblock_and_reblock(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            config = {'origins': [{'name': 'iran'}, {'name': 'eu'}], 'protected_ips': [], 'protected_ranges': []}
            calls = []
            failed = {'eu'}

            def transport(origin, action, ip, decision_id):
                calls.append((origin['name'], action, ip, decision_id))
                if origin['name'] in failed:
                    raise TimeoutError()
                return {'ip': ip, 'decision_id': decision_id, 'active': action == 'block', 'htaccess_sha256': 'hash'}

            ip = '8.8.4.4'
            first = reconcile(config, state, {ip}, transport)
            self.assertEqual(first['applied'], {'iran': 1, 'eu': 0})
            pending_id = json.loads(state.read_text())['origins']['eu'][ip]['id']
            failed.clear()
            second = reconcile(config, state, {ip}, transport)
            self.assertEqual(second['applied'], {'iran': 1, 'eu': 1})
            self.assertEqual(calls[-1][3], pending_id)
            reconcile(config, state, set(), transport)
            self.assertEqual(json.loads(state.read_text())['origins'], {'iran': {}, 'eu': {}})
            reconcile(config, state, {ip}, transport)
            self.assertNotEqual(calls[-1][3], pending_id)


if __name__ == '__main__':
    unittest.main()
