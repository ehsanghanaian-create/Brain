from contextlib import closing
from datetime import datetime, timezone
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import threshold_worker as rule


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.origin, self.ads, self.state = root/'origin.db', root/'ads.db', root/'state.db'
        with closing(sqlite3.connect(self.origin)) as db:
            db.execute('CREATE TABLE ads_click_events(site_id TEXT,ip_address TEXT,received_at REAL,gclid TEXT,utm_campaign TEXT,origin TEXT)')
        with closing(sqlite3.connect(self.ads)) as db:
            db.execute('CREATE TABLE ads_click_events(site_id TEXT,event_type TEXT,event_uuid TEXT,gclid TEXT,received_at TEXT,session_id TEXT,utm_source TEXT,utm_medium TEXT,utm_campaign TEXT,metadata_json TEXT,visitor_id TEXT)')
        self.cfg = dict(entry_source_db=str(self.origin), ads_source_db=str(self.ads), state_db=str(self.state),
                        api_url='http://backend/api/v1', wordpress_site_id='site', minimum_count=3,
                        window_seconds=86400, protected_ips=[], protected_ranges=[])
        self.now = 1_800_000_000

    def origin_entry(self, click, ip='8.8.4.4', campaign='real', received=None):
        with closing(sqlite3.connect(self.origin)) as db:
            db.execute('INSERT INTO ads_click_events VALUES(?,?,?,?,?,?)',(rule.SITE,ip,self.now-10 if received is None else received,click,campaign,'iran'));db.commit()

    def landing(self, click, visitor, received=None, metadata=None):
        stamp = self.now-10 if received is None else received
        iso = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
        meta = metadata if metadata is not None else {'signal':'fresh_ads_entry','navigation_type':'navigate'}
        with closing(sqlite3.connect(self.ads)) as db:
            db.execute('INSERT INTO ads_click_events(site_id,event_type,event_uuid,gclid,received_at,session_id,utm_source,utm_medium,utm_campaign,metadata_json,visitor_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (rule.SITE,'landing','landing-'+click+visitor,click,iso,visitor,'google','cpc','real',json.dumps(meta),visitor));db.commit()

    def tel(self, click, event, session='fresh', received='2027-01-15T07:59:55Z', campaign='real'):
        with closing(sqlite3.connect(self.ads)) as db:
            db.execute('INSERT INTO ads_click_events(site_id,event_type,event_uuid,gclid,received_at,session_id,utm_source,utm_medium,utm_campaign,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?)',(rule.SITE,'tel_click',event,click,received,session,'google','cpc',campaign,'{}'))
            db.execute('INSERT INTO ads_click_events(site_id,event_type,event_uuid,gclid,received_at,session_id,utm_source,utm_medium,utm_campaign,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?)',(rule.SITE,'landing','landing-'+event,click,'2027-01-15T07:59:50Z',session,'google','cpc',campaign,'{"signal":"fresh_ads_entry"}'));db.commit()

    def test_three_fresh_ads_entries_trigger(self):
        for x in 'ABC': self.origin_entry(x*30)
        got=rule.collect_candidates(self.cfg,self.now)
        self.assertEqual([(x['ip'],x['ads_entries'],x['ads_tel_clicks']) for x in got],[('8.8.4.4',3,0)])

    def test_second_distinct_entry_by_same_visitor_blocks_latest_origin_ip(self):
        self.cfg['visitor_rule_start']=self.now-20
        first, second='A'*30,'B'*30
        self.origin_entry(first,received=self.now-3*86400);self.landing(first,'visitor-one',self.now-3*86400)
        self.assertEqual(rule.collect_candidates(self.cfg,self.now),[])
        self.origin_entry(second,ip='1.1.1.1');self.landing(second,'visitor-one')
        got=rule.collect_candidates(self.cfg,self.now)
        self.assertEqual([(x['ip'],x['repeat_visitor']) for x in got],[('1.1.1.1',True)])

    def test_shared_ip_different_visitors_and_reloads_do_not_block(self):
        self.cfg['visitor_rule_start']=self.now-20
        for click, visitor in [('A'*30,'visitor-one'),('B'*30,'visitor-two')]:
            self.origin_entry(click);self.landing(click,visitor)
        self.landing('A'*30,'visitor-one',metadata={'signal':'not_fresh_ads_entry','navigation_type':'reload'})
        self.assertEqual(rule.collect_candidates(self.cfg,self.now),[])

    def test_pre_activation_repeat_does_not_back_block(self):
        self.cfg['visitor_rule_start']=self.now-20
        for click, age in [('A'*30,100),('B'*30,50)]:
            self.origin_entry(click,received=self.now-age);self.landing(click,'visitor-one',self.now-age)
        self.assertEqual(rule.collect_candidates(self.cfg,self.now),[])

    def test_ambiguous_second_click_ip_cannot_block_visitor(self):
        self.cfg['visitor_rule_start']=self.now-20
        first, second='A'*30,'B'*30
        self.origin_entry(first);self.landing(first,'visitor-one')
        self.origin_entry(second);self.origin_entry(second,ip='1.1.1.1')
        self.landing(second,'visitor-one')
        self.assertEqual(rule.collect_candidates(self.cfg,self.now),[])

    def test_three_ads_phone_clicks_trigger_but_direct_never_does(self):
        click='G'*30;self.origin_entry(click)
        for i in range(3): self.tel(click,f'ad-{i}')
        with closing(sqlite3.connect(self.ads)) as db:
            for i in range(20):db.execute('INSERT INTO ads_click_events(site_id,event_type,event_uuid,gclid,received_at,session_id,utm_source,utm_medium,utm_campaign,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?)',(rule.SITE,'tel_click',f'direct-{i}',None,'2027-01-15T07:59:55Z','direct','','','','{}'))
            db.commit()
        got=rule.collect_candidates(self.cfg,self.now)
        self.assertEqual([(x['ip'],x['ads_entries'],x['ads_tel_clicks']) for x in got],[('8.8.4.4',1,3)])

    def test_duplicate_origin_and_ambiguous_ip_do_not_inflate(self):
        for x in 'AB':
            self.origin_entry(x*30);self.origin_entry(x*30)
        self.origin_entry('C'*30);self.origin_entry('C'*30,ip='1.1.1.1')
        self.assertEqual(rule.collect_candidates(self.cfg,self.now),[])

    def test_qa_old_private_and_two_do_not_trigger(self):
        for x in 'AB': self.origin_entry(x*30)
        self.origin_entry('Q'*30,campaign='qa validation')
        self.origin_entry('P'*30,ip='192.168.1.1')
        self.assertEqual(rule.collect_candidates(self.cfg,self.now),[])

    def test_carried_attribution_future_and_test_gclid_never_trigger(self):
        click='G'*30;self.origin_entry(click)
        with closing(sqlite3.connect(self.ads)) as db:
            for i in range(3):
                db.execute('INSERT INTO ads_click_events(site_id,event_type,event_uuid,gclid,received_at,session_id,utm_source,utm_medium,utm_campaign,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?)',(rule.SITE,'tel_click',f'carried-{i}',click,'2027-01-15T07:59:55Z','carried','google','cpc','real','{}'))
            db.commit()
        self.assertEqual(rule.collect_candidates(self.cfg,self.now),[])
        future='F'*30
        with closing(sqlite3.connect(self.origin)) as db:
            for x in 'ABC': db.execute('INSERT INTO ads_click_events VALUES(?,?,?,?,?,?)',(rule.SITE,'8.8.8.8',self.now+10,x*30,'real','iran'))
            db.commit()
        self.origin_entry('test'+'x'*30)
        self.assertEqual(rule.collect_candidates(self.cfg,self.now),[])

    def test_success_is_durable_and_failure_retries(self):
        for x in 'ABC': self.origin_entry(x*30)
        calls=[]
        def ok(config,candidate):calls.append(candidate['ip']);return {'success':True,'ip':candidate['ip'],'status':'blocked'}
        self.assertEqual(rule.iteration(self.cfg,self.now,ok),[]);rule.iteration(self.cfg,self.now+10,ok)
        self.assertEqual(calls,['8.8.4.4'])
        with closing(sqlite3.connect(self.state)) as db:self.assertEqual(db.execute("SELECT status FROM automatic_blocks").fetchone()[0],'blocked')

    def test_request_uses_authenticated_wordpress_route(self):
        candidate={'ip':'8.8.4.4','ads_entries':3,'ads_tel_clicks':0}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'{"success":true,"ip":"8.8.4.4","status":"blocked"}'
        seen={}
        def opener(request,timeout):seen.update(url=request.full_url,token=request.headers['X-api-token'],body=request.data,timeout=timeout);return Response()
        with patch.dict(os.environ,{'SEO_BRAIN_API_TOKEN':'secret'}):rule.request_block(self.cfg,candidate,opener)
        self.assertTrue(seen['url'].endswith('/sites/site/security/block'));self.assertEqual(seen['token'],'secret');self.assertNotIn(b'secret',seen['body'])


if __name__ == '__main__': unittest.main()
