import copy
import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared_store import SharedStore, StoreUnavailable, LeaseLost, utc_now
from snapshot_collector import SnapshotCollector, MasterCache
from futures_api import FuturesUnavailable
from test_fastapi_migration import MemoryStore
import kis_auth


class SharedPipelineTests(unittest.TestCase):
    def test_expired_global_snapshot_cannot_be_read(self):
        store=SharedStore('https://test.supabase.co','test-only')
        row={'generation':'test','payload':{},'collected_at':utc_now().isoformat(),
             'expires_at':(utc_now()-datetime.timedelta(seconds=1)).isoformat()}
        with patch.object(store,'_request',return_value=[row]):
            with self.assertRaises(StoreUnavailable):store.read()

    def test_cache_single_flight_preserves_expiry_and_isolation(self):
        store=SharedStore('https://test.supabase.co','test-only',read_cache_seconds=15)
        now=utc_now()
        row={'generation':'test','payload':{'value':1},'collected_at':now.isoformat(),
             'expires_at':(now+datetime.timedelta(seconds=5)).isoformat()}
        with patch.object(store,'_request',return_value=[row]) as request:
            result=store.read();result['payload']['value']=2
            self.assertEqual(store.read()['payload']['value'],1)
            request.assert_called_once()
            with patch('shared_store.utc_now',return_value=now+datetime.timedelta(seconds=6)):
                with self.assertRaises(StoreUnavailable):store.read()

    def test_unowned_writer_is_not_treated_as_success(self):
        store=SharedStore('https://test.supabase.co','test-only')
        with patch.object(store,'_request',return_value=False):
            with self.assertRaises(LeaseLost):store.publish('owner','generation',{})
        with patch.object(store,'_request',return_value={'acquired':False}):
            with self.assertRaises(LeaseLost):store.claim('owner')

    def test_missing_lease_prevents_any_collection(self):
        store=Mock();store.claim.side_effect=LeaseLost()
        with patch('snapshot_collector._collect_gold_premium_data') as collect:
            with self.assertRaises(LeaseLost):SnapshotCollector(store,Mock()).collect_once()
            collect.assert_not_called();store.publish.assert_not_called()

    def test_atomic_bundle_contains_validated_master_and_actual_book(self):
        fixture=MemoryStore();store=Mock();master=Mock();master.get.return_value=fixture.candidates
        with patch('snapshot_collector._collect_gold_premium_data',return_value=fixture.quote),patch('snapshot_collector.get_domestic_futures_data',return_value=fixture.active),patch('snapshot_collector.get_domestic_futures_orderbook',return_value=fixture.book):
            payload=SnapshotCollector(store,master,owner='test-owner').collect_once()
        store.publish.assert_called_once()
        self.assertEqual(payload['active_contract']['data']['volume'],56)
        self.assertEqual(payload['orderbooks']['A88611']['data']['buy_pressure_pct'],50.0)
        self.assertEqual(payload['active_contract']['data']['expiry_month'],11)

    def test_price_error_cannot_hide_higher_volume_or_make_zero_signal(self):
        fixture=MemoryStore();store=Mock();master=Mock();master.get.return_value=fixture.candidates
        with patch('snapshot_collector._collect_gold_premium_data',return_value=None),patch('snapshot_collector.get_domestic_futures_data',side_effect=FuturesUnavailable()),patch('snapshot_collector.get_domestic_futures_orderbook',return_value=None):
            payload=SnapshotCollector(store,master).collect_once()
        self.assertEqual(payload['gold']['state'],'unavailable')
        self.assertEqual(payload['active_contract']['state'],'unavailable')
        self.assertIsNone(payload['active_contract']['data'])
        self.assertEqual(payload['orderbooks']['A88611']['state'],'empty')

    def test_master_failure_replaces_instead_of_reusing_old_signals(self):
        store=Mock();master=Mock();master.get.side_effect=StoreUnavailable()
        with patch('snapshot_collector._collect_gold_premium_data',return_value=None),patch('snapshot_collector.get_domestic_futures_data') as prices:
            payload=SnapshotCollector(store,master).collect_once()
        prices.assert_not_called();store.publish.assert_called_once()
        self.assertEqual(payload['candidates']['state'],'unavailable')

    def test_master_beyond_36_hours_is_not_used_after_refresh_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            master=MasterCache(directory);master.candidates=[{'symbol':'test-only'}]
            master.fetched_at=utc_now()-datetime.timedelta(hours=37)
            with patch('snapshot_collector.requests.get',side_effect=StoreUnavailable()):
                with self.assertRaises(StoreUnavailable):master.get()

    def test_lease_is_rechecked_immediately_before_token_issuance(self):
        kis_auth.clear_memory_cache();kis_auth.set_issuance_guard(Mock(side_effect=LeaseLost()))
        try:
            with patch('kis_auth.get_cached_token',return_value=None),patch('kis_auth.get_kis_token') as issue:
                self.assertIsNone(kis_auth.get_access_token());issue.assert_not_called()
        finally:
            kis_auth.set_issuance_guard(None);kis_auth.clear_memory_cache()
