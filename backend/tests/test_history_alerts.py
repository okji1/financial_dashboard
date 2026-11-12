import datetime
from pathlib import Path
import sys
import unittest
import concurrent.futures
import threading
from unittest.mock import Mock, patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from fastapi.testclient import TestClient
from asgi import api,app,get_store
from history_alerts import HistoryAlertsStore,ArchiveWorker,monitor_states
from shared_store import SharedStore,StoreUnavailable,LeaseLost,section,utc_now
from test_fastapi_migration import MemoryStore
from test_krx_data import ROW
from krx_data import parse_daily,KRXUnavailable


class HistoryAlertsTests(unittest.TestCase):
    def test_no_trades_are_not_an_outage_but_stale_provider_data_is(self):
        payload=MemoryStore().payload
        payload['krx_daily']=section({'trade_date':'2020-01-01','refresh_state':'ok','fetched_at':utc_now().isoformat()})
        payload['active_contract']=section(state='empty')
        self.assertEqual(set(monitor_states(payload).values()),{'ok'})
        payload['krx_daily']['data']['fetched_at']=(utc_now()-datetime.timedelta(hours=3)).isoformat()
        self.assertEqual(monitor_states(payload)['krx'],'error')
        payload['orderbooks']['A88611']=section(state='unavailable')
        self.assertEqual(monitor_states(payload)['futures'],'error')

    def test_archive_is_idempotent_and_only_marks_day_after_rows_are_saved(self):
        store=Mock();archive=HistoryAlertsStore(store)
        day=datetime.date(2026,11,11);items=parse_daily({'OutBlock_1':[ROW]},'20261111')
        archive.archive(day,items,utc_now().isoformat())
        calls=store._request.call_args_list
        self.assertEqual([c.args[1] for c in calls],['krx_gold_history','krx_gold_days'])
        self.assertEqual(calls[0].kwargs['params']['on_conflict'],'trade_date,symbol')
        self.assertTrue(calls[1].kwargs['json']['has_data'])
        store.reset_mock();store._request.side_effect=StoreUnavailable()
        with self.assertRaises(StoreUnavailable):archive.archive(day,items,utc_now().isoformat())
        self.assertEqual(store._request.call_count,1)

    def test_empty_holiday_is_remembered_without_fake_prices(self):
        store=Mock();HistoryAlertsStore(store).archive(datetime.date(2026,11,11),[],utc_now().isoformat())
        store._request.assert_called_once()
        self.assertFalse(store._request.call_args.kwargs['json']['has_data'])

    def test_history_is_bounded_sorted_and_product_filtered(self):
        store=Mock();items=parse_daily({'OutBlock_1':[ROW]},'20261111')
        store._request.return_value={'items':[{**items[0],'trade_date':'2026-11-11'}]}
        result=HistoryAlertsStore(store).history('04020000',90)
        self.assertEqual(result['items'][0]['trade_date'],'2026-11-11')
        store._request.assert_called_once_with('POST','rpc/dashboard_read_krx_history',json={'p_symbol':'04020000','p_days':90})

    def test_backfill_makes_only_one_provider_request_after_publication(self):
        archive=Mock();archive.checked_days.return_value=[]
        worker=ArchiveWorker(archive,'test-key');renew=Mock()
        with patch('history_alerts.fetch_daily',return_value=[]) as fetch:
            worker.run_once(section(state='unavailable'),renew)
            worker.run_once(section(state='unavailable'),renew)
        fetch.assert_called_once();archive.archive.assert_called_once()
        self.assertEqual(renew.call_count,2)

    def test_backfill_respects_lease_and_does_not_mark_failed_dates_complete(self):
        archive=Mock();archive.checked_days.return_value=[]
        with patch('history_alerts.fetch_daily',side_effect=KRXUnavailable()):
            ArchiveWorker(archive,'test').run_once(section(state='unavailable'),Mock())
        archive.archive.assert_not_called()
        with patch('history_alerts.fetch_daily') as fetch:
            with self.assertRaises(LeaseLost):ArchiveWorker(archive,'test').run_once(section(state='unavailable'),Mock(side_effect=LeaseLost()))
        fetch.assert_not_called()

    def test_stopped_collector_can_be_reported_without_a_live_snapshot(self):
        store=Mock();last=utc_now()-datetime.timedelta(seconds=120)
        store._request.return_value={'events':[],'collected_at':last.isoformat(),'collector_status':'ok'}
        result=HistoryAlertsStore(store).alerts()
        self.assertEqual(len(result['events']),1)
        self.assertEqual(result['events'][0]['id'],'collector-error-'+str(int((last+datetime.timedelta(seconds=90)).timestamp())))
        self.assertEqual(result['events'][0]['status'],'error')
        self.assertGreater(result['snapshot_age_seconds'],90)

    def test_existing_failure_does_not_gain_a_duplicate_synthetic_event(self):
        store=Mock();last=utc_now()-datetime.timedelta(seconds=120)
        store._request.return_value={'events':[{'id':'existing','source':'collector','status':'error','occurred_at':last.isoformat()}],'collected_at':last.isoformat(),'collector_status':'error'}
        self.assertEqual(len(HistoryAlertsStore(store).alerts()['events']),1)

    def test_monitor_requires_current_lease(self):
        store=Mock();store._request.return_value=False
        with self.assertRaises(LeaseLost):HistoryAlertsStore(store).monitor('test',{'gold':'ok'})

    def test_query_cache_shares_work_without_aliasing_mutable_rows(self):
        store=SharedStore('https://test.supabase.co','test');loader=Mock(return_value={'items':[1]})
        first=store.cached_read(('test',),loader);first['items'].append(2)
        self.assertEqual(store.cached_read(('test',),loader),{'items':[1]})
        loader.assert_called_once()

    def test_slow_history_does_not_block_operational_alerts(self):
        store=SharedStore('https://test.supabase.co','test');started=threading.Event();release=threading.Event()
        def slow():started.set();release.wait(5);return {'history':[]}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            history=executor.submit(store.cached_read,('history',),slow)
            self.assertTrue(started.wait(2))
            try:
                alerts=executor.submit(store.cached_read,('alerts',),lambda:{'events':[]})
                self.assertEqual(alerts.result(timeout=2),{'events':[]})
            finally:release.set()
            history.result(timeout=2)

    def test_http_ranges_and_symbols_are_validated_without_calling_providers(self):
        store=Mock();store.cached_read.side_effect=lambda key,loader:loader()
        def request(method,path,**kwargs):
            if path=='rpc/dashboard_read_krx_history':return {'source':'KRX_OPEN_API','symbol':kwargs['json']['p_symbol'],'days':kwargs['json']['p_days'],'checked_days':0,'total_days':64,'items':[]}
            if path=='rpc/dashboard_read_system_alerts':return {'events':[],'collected_at':utc_now().isoformat(),'collector_status':'ok'}
            raise AssertionError(path)
        store._request.side_effect=request
        api.dependency_overrides[get_store]=lambda:store
        try:
            with TestClient(app,raise_server_exceptions=False) as client,patch('history_alerts.fetch_daily',side_effect=AssertionError('provider called')):
                for days in (30,90):self.assertEqual(client.get(f'/api/krx-gold-history?days={days}').status_code,200)
                for query in ('days=45','days=1000','symbol=INVALID'):
                    self.assertEqual(client.get('/api/krx-gold-history?'+query).status_code,422)
                self.assertEqual(client.get('/api/system-alerts').status_code,200)
        finally:api.dependency_overrides.clear()
