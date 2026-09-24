from contextlib import closing
import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path
from detector import Config, Detector, SITE


def event(i, seconds=0, **extra):
    row = dict(id=i, site_id=SITE, event_type='landing', ip_address='8.8.4.4',
               ip_resolution_version='3', ip_confidence='trusted_proxy',
               received_at=1800000000+seconds, gclid='C' + str(i).zfill(30),
               metadata={'fresh_ads_entry': True, 'navigation_type': 'navigate'})
    row.update(extra)
    return row


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name)/'source.db'
        self.state = Path(self.tmp.name)/'state.db'
        with closing(sqlite3.connect(self.source, isolation_level=None)) as db:
            db.execute('CREATE TABLE ads_click_events(id INTEGER PRIMARY KEY)')
        self.d = Detector(self.state, Config(enabled=True))
        self.d.bootstrap(self.source)

    def test_boundary(self):
        self.assertIsNone(self.d.process_event(event(1)))
        self.assertIsNone(self.d.process_event(event(2, 60)))
        self.assertIsNotNone(self.d.process_event(event(3, 119.999)))

    def test_restart_duplicate_unblock(self):
        self.d.process_event(event(1))
        self.d = Detector(self.state, Config(enabled=True))
        self.assertIsNone(self.d.process_event(event(2, 1, gclid=event(1)['gclid'])))
        self.assertIsNotNone(self.d.process_event(event(3, 2)))
        self.assertEqual(self.d.unblock('8.8.4.4', 'operator correction'), 1)
        self.assertIsNone(self.d.process_event(event(4, 3, gclid=event(3)['gclid'])))
        self.assertIsNone(self.d.process_event(event(1)))
        self.assertEqual(self.d.active_decisions(), [])
        self.assertIsNone(self.d.process_event(event(5, 4)))
        self.assertIsNotNone(self.d.process_event(event(6, 5)))

    def test_unblock_rejects_delayed_old_ids(self):
        self.d.process_event(event(1))
        self.d.process_event(event(10, 1))
        self.d.unblock('8.8.4.4', 'reset window')
        self.assertIsNone(self.d.process_event(event(5, 2)))
        self.assertIsNone(self.d.process_event(event(11, 3)))
        self.assertIsNotNone(self.d.process_event(event(12, 4)))

    def test_guards(self):
        cases = [dict(metadata={}), dict(metadata={'fresh_ads_entry': True, 'navigation_type':'reload'}),
                 dict(metadata={'fresh_ads_entry':True,'navigation_type':'back_forward'}),
                 dict(event_type='page_view'), dict(ip_confidence='unverified_proxy'),
                 dict(ip_resolution_version='2'), dict(ip_address='192.168.1.1'),
                 dict(gclid='test'+'x'*30), dict(gclid='',gbraid='x'*30),
                 dict(utm_campaign='qa_test_campaign'), dict(site_id='other.com')]
        for i, extra in enumerate(cases, 1):
            self.assertIsNone(self.d.process_event(event(i, **extra)))
        self.assertIsNone(self.d.process_event(event(99)))

    def test_repeated_non_ads_visits_never_create_a_block(self):
        non_ads = [
            dict(gclid=None, metadata={'navigation_type': 'navigate'}),
            dict(gclid='', metadata={'signal': 'not_fresh_ads_entry', 'navigation_type': 'navigate'}),
            dict(gclid=None, metadata={'signal': 'fresh_ads_entry', 'navigation_type': 'navigate'}),
            dict(gclid='C' + '9' * 30, metadata={'signal': 'not_fresh_ads_entry', 'navigation_type': 'navigate'}),
            dict(gclid='C' + '8' * 30, metadata={'signal': 'fresh_ads_entry', 'navigation_type': 'reload'}),
            dict(gclid='C' + '7' * 30, metadata={'signal': 'fresh_ads_entry', 'navigation_type': 'back_forward'}),
        ]
        for i in range(1, 25):
            self.assertIsNone(self.d.process_event(event(i, i, **non_ads[(i - 1) % len(non_ads)])))
        self.assertEqual(self.d.active_decisions(), [])
        with self.d.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM clicks').fetchone()[0], 0)

    def test_allow_protected_and_kill(self):
        for cfg in [Config(), Config(enabled=True,allowlist=('8.8.4.4',)),
                    Config(enabled=True,protected_ranges=('8.8.4.0/24',))]:
            self.assertIsNone(Detector(self.state,cfg).eligible(event(1)))

    def test_legacy_signal_without_boolean(self):
        self.assertIsNotNone(self.d.eligible(event(1, metadata={'signal':'fresh_ads_entry','navigation_type':'navigate'})))
        for metadata in [
            {'signal':'fresh_ads_entry','fresh_ads_entry':False,'navigation_type':'navigate'},
            {'signal':'fresh_ads_entry','fresh_ads_entry':None,'navigation_type':'navigate'},
            {'signal':'fresh_ads_entry','navigation_type':'reload'},
            {'signal':'fresh_ads_entry','navigation_type':'back_forward'},
            {'signal':'carryover','navigation_type':'navigate'},
            {'navigation_type':'navigate'},
        ]:
            self.assertIsNone(self.d.eligible(event(1, metadata=metadata)))

    def test_no_history(self):
        path=Path(self.tmp.name)/'new.db'
        with closing(sqlite3.connect(self.source, isolation_level=None)) as db:db.execute('INSERT INTO ads_click_events VALUES(50)')
        d=Detector(path,Config(enabled=True));d.bootstrap(self.source)
        self.assertIsNone(d.process_event(event(49)))
        self.assertIsNone(d.process_event(event(50)))
        self.assertIsNone(d.process_event(event(51)))
        self.assertIsNotNone(d.process_event(event(52, 1)))

    def test_concurrent_out_of_order(self):
        def run(i):return Detector(self.state,Config(enabled=True)).process_event(event(i, 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(run, [8,7,6,5,4,3,2,1]*2))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertEqual(len(self.d.active_decisions()),1)
        with self.d.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM clicks').fetchone()[0],8)


if __name__ == '__main__':
    unittest.main()
