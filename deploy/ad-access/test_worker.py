from contextlib import closing
import concurrent.futures
import sqlite3
import tempfile
import threading
import json
import unittest
from pathlib import Path
import worker
from test_detector import event


class Transport:
    def __init__(self):
        self.calls=[]; self.fail=set(); self.hashes={'a':'initial','b':'initial'}
        self.bad_ack=False
    def __call__(self, origin, action, ip=None, decision_id=None):
        name=origin['name'];self.calls.append((name,action))
        if name in self.fail:raise RuntimeError('offline')
        if action=='status':return dict(site=worker.SITE,enforcement_enabled=True,htaccess_sha256=self.hashes[name])
        self.hashes[name]=name+action+decision_id
        return dict(ip=ip,decision_id=decision_id,active=(action=='block') if not self.bad_ack else None,htaccess_sha256=self.hashes[name])


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name)
        self.cfg=dict(state_db=str(p/'state.db'),source_db=str(p/'source.db'),enabled=True,
                      origins=[dict(name='a'),dict(name='b')],decision_prefix='decision_')
        with closing(sqlite3.connect(self.cfg['source_db'])) as cx:
            cx.execute('CREATE TABLE ads_click_events(id INTEGER PRIMARY KEY)');cx.commit()
        self.d=worker.detector(self.cfg);self.d.bootstrap(self.cfg['source_db'])
        self.d.process_event(event(1));self.d.process_event(event(2,1));self.t=Transport()
    def test_failed_origin_does_not_starve_and_retries(self):
        self.t.fail={'a'};self.assertEqual(len(worker.iteration(self.cfg,self.t,100)),1)
        self.assertIn(('b','block'),self.t.calls)
        self.t.fail.clear();self.t.calls=[];worker.iteration(self.cfg,self.t,101)
        self.assertIn(('a','block'),self.t.calls);self.assertNotIn(('b','block'),self.t.calls)
    def test_persistent_ack_skips_restart(self):
        worker.iteration(self.cfg,self.t,100);self.t.calls=[]
        worker.iteration(dict(self.cfg),self.t,101);self.assertEqual(self.t.calls,[])
    def test_drift_reconciles_at_30_seconds(self):
        worker.iteration(self.cfg,self.t,100);self.t.calls=[];self.t.hashes['a']='externally edited'
        worker.iteration(self.cfg,self.t,129);self.assertEqual(self.t.calls,[])
        worker.iteration(self.cfg,self.t,130);self.assertIn(('a','block'),self.t.calls);self.assertNotIn(('b','block'),self.t.calls)
    def test_default_kill_switch_no_network(self):
        del self.cfg['enabled'];worker.iteration(self.cfg,self.t,100);self.assertEqual(self.t.calls,[])
    def test_invalid_ack_never_persisted(self):
        self.t.bad_ack=True;self.assertEqual(len(worker.iteration(self.cfg,self.t,100)),2)
        with self.d.connect() as cx:self.assertEqual(cx.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0],0)
    def test_unblock_serializes_with_iteration(self):
        started=threading.Event();release=threading.Event();base=self.t
        def slow(*args):
            if args[1]=='block' and not started.is_set():started.set();release.wait(5)
            return base(*args)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(worker.iteration,self.cfg,slow,100);self.assertTrue(started.wait(2))
            second=pool.submit(worker.unblock,self.cfg,'8.8.4.4','operator',base,101)
            release.set();first.result();self.assertEqual(second.result()['errors'],[])
        for name in ['a','b']:
            actions=[a for n,a in base.calls if n==name and a!='status'];self.assertEqual(actions[-1],'unblock')
        self.assertEqual(self.d.active_decisions(),[])
    def test_unblock_retry_after_partial_failure(self):
        worker.iteration(self.cfg,self.t,100);self.t.fail={'a'}
        self.assertEqual(len(worker.unblock(self.cfg,'8.8.4.4','operator',self.t,101)['errors']),1)
        self.t.fail.clear();self.t.calls=[];worker.unblock(self.cfg,'8.8.4.4','retry',self.t,102)
        self.assertIn(('a','unblock'),self.t.calls)

    def test_origin_ingest_prospective_dedup_restart(self):
        self.cfg['entry_source_db']=str(Path(self.tmp.name)/'entry.db')
        worker.entry_source(self.cfg['entry_source_db'])
        journal={'a':[], 'b':[]};calls=[]
        def transport(origin, action, since=None):
            n=origin['name'];calls.append((n,since));items=journal[n]
            return dict(site=worker.SITE,last_id=len(items),entries=[] if since is None else items[since:])
        def entry(i,click):return dict(id=i,ip_address='8.8.4.4',gclid=click,received_at=1800000000+i,utm_campaign='')
        journal['a']=[entry(1,'C'*30)]
        self.assertEqual(worker.ingest_entries(self.cfg,transport),[])
        journal['a'].append(entry(2,'D'*30));journal['b'].append(entry(1,'D'*30))
        self.assertEqual(worker.ingest_entries(self.cfg,transport),[])
        self.assertEqual(worker.ingest_entries(self.cfg,transport),[])
        with closing(sqlite3.connect(self.cfg['entry_source_db'])) as cx:
            self.assertEqual(cx.execute('SELECT COUNT(*) FROM ads_click_events').fetchone()[0],2)
        self.assertEqual(calls[-2:],[('a',2),('b',1)])

    def test_snapshot_ack_failure_staleness_and_sanitization(self):
        self.cfg['dashboard_snapshot']=str(Path(self.tmp.name)/'dashboard/status.json')
        self.cfg['origins'][0]['secret']='never-export-me'
        worker.iteration(self.cfg,self.t,100)
        path=Path(self.cfg['dashboard_snapshot']);data=json.loads(path.read_text())
        self.assertTrue(data['healthy']);self.assertEqual(data['items'][0]['status'],'blocked')
        self.assertNotIn('never-export-me',path.read_text())
        worker.export_snapshot(self.cfg,self.d,[('a','never-export-me')],101)
        data=json.loads(path.read_text());self.assertFalse(data['healthy']);self.assertEqual(data['items'][0]['status'],'unknown')
        self.assertNotIn('never-export-me',path.read_text())
        worker.export_snapshot(self.cfg,self.d,[],140)
        self.assertEqual(json.loads(path.read_text())['items'][0]['status'],'unknown')
        worker.unblock(self.cfg,'8.8.4.4','operator',self.t,141)
        self.assertEqual(json.loads(path.read_text())['items'],[])

    def test_snapshot_click_correlation_ambiguity(self):
        self.cfg['entry_source_db']=str(Path(self.tmp.name)/'entries.db');worker.entry_source(self.cfg['entry_source_db'])
        self.cfg['dashboard_snapshot']=str(Path(self.tmp.name)/'dashboard/status.json');worker.setup(self.d)
        with closing(sqlite3.connect(self.cfg['entry_source_db'])) as cx:
            for ip,click in [('8.8.4.4',event(1)['gclid']),('8.8.4.4',event(2)['gclid']),('1.1.1.1',event(2)['gclid'])]:
                cx.execute('INSERT INTO ads_click_events(ip_address,gclid) VALUES(?,?)',(ip,click))
            cx.commit()
        worker.export_snapshot(self.cfg,self.d,[],100)
        data=json.loads(Path(self.cfg['dashboard_snapshot']).read_text())
        self.assertEqual(data['items'][0]['match_gclids'],[event(1)['gclid']])


if __name__=='__main__':unittest.main()
