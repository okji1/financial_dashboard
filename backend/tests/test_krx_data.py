"""KRX authentication, real schema, dates, caching and query isolation."""
import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from fastapi.testclient import TestClient
from asgi import app, api, get_store
from krx_data import KRXDailyCache, KRXUnavailable, parse_daily
from shared_store import LeaseLost, section, utc_now
from snapshot_collector import SnapshotCollector
from test_fastapi_migration import MemoryStore

# Schema verified against the official API. Values here are synthetic test data.
ROW = {'BAS_DD': '20261111', 'ISU_CD': '04020000', 'ISU_NM': '금 99.99_1kg',
    'TDD_CLSPRC': '100,000', 'CMPPREVDD_PRC': '-1000', 'FLUC_RT': '-0.99',
    'TDD_OPNPRC': '101000', 'TDD_HGPRC': '102000', 'TDD_LWPRC': '99000',
    'ACC_TRDVOL': '2000', 'ACC_TRDVAL': '200000000'}
NOW = datetime.datetime(2026, 11, 12, 8, tzinfo=datetime.timezone.utc)


def response(rows=None, status=200):
    return Mock(status_code=status, json=Mock(return_value={'OutBlock_1': rows if rows is not None else [ROW]}))


class KRXDataTests(unittest.TestCase):
    def test_schema_keeps_units_negative_changes_and_valid_zero(self):
        row = {**ROW, 'ACC_TRDVOL': '0', 'ACC_TRDVAL': '0', 'FLUC_RT': '0', 'CMPPREVDD_PRC': '0'}
        item = parse_daily({'OutBlock_1': [row]}, '20261111')[0]
        self.assertEqual(item['close'], 100000)
        self.assertEqual(item['volume_grams'], 0)
        self.assertEqual(item['change_rate'], 0)
        self.assertEqual(parse_daily({'OutBlock_1': [ROW]}, '20261111')[0]['change'], -1000)
        row['TDD_CLSPRC'] = '-'
        self.assertIsNone(parse_daily({'OutBlock_1': [row]}, '20261111')[0]['close'])

    def test_malformed_dates_duplicate_rows_and_numbers_fail_closed(self):
        bad = [None, {}, {'OutBlock_1': 'error'}, {'OutBlock_1': [ROW, ROW]},
            {'OutBlock_1': [{**ROW, 'BAS_DD': '20261110'}]},
            {'OutBlock_1': [{**ROW, 'TDD_CLSPRC': 'NaN'}]},
            {'OutBlock_1': [{**ROW, 'ACC_TRDVOL': '-1'}]},
            {'OutBlock_1': [{**ROW, 'ACC_TRDVOL': '1.5'}]},
            {'OutBlock_1': [{**ROW, 'TDD_CLSPRC': '1,,000'}]}]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(KRXUnavailable):
                parse_daily(payload, '20261111')

    @patch('krx_data.utc_now', return_value=NOW)
    def test_blank_today_falls_back_and_hourly_cache_avoids_provider_calls(self, _):
        cache = KRXDailyCache('test-key'); renew = Mock()
        with patch('krx_data.time.monotonic', return_value=100), patch('krx_data.requests.get', side_effect=[response([]), response()]) as get:
            first = cache.get(renew)
            second = cache.get(renew)
            self.assertEqual(first['data'], second['data'])
        self.assertEqual(first['data']['trade_date'], '2026-11-11')
        self.assertEqual(first['data']['refresh_state'], 'ok')
        self.assertEqual(get.call_count, 2)
        self.assertEqual(renew.call_count, 2)
        self.assertEqual(get.call_args.kwargs['headers'], {'AUTH_KEY': 'test-key'})
        self.assertFalse(get.call_args.kwargs['allow_redirects'])
        self.assertEqual(get.call_args.kwargs['params'], {'basDd': '20261111'})

    def test_kst_date_boundary_and_weekend_are_not_utc_business_days(self):
        # Sunday UTC, already Monday KST. Monday empty, then skip Sat/Sun.
        now = datetime.datetime(2026, 11, 15, 16, tzinfo=datetime.timezone.utc)
        friday = {**ROW, 'BAS_DD': '20261113'}
        with patch('krx_data.utc_now', return_value=now), patch('krx_data.requests.get', side_effect=[response([]), response([friday])]) as get:
            result = KRXDailyCache('test').get()
        self.assertEqual([c.kwargs['params']['basDd'] for c in get.call_args_list], ['20261116', '20261113'])
        self.assertEqual(result['data']['trade_date'], '2026-11-13')

    @patch('krx_data.utc_now', return_value=NOW)
    def test_auth_failure_does_not_scan_old_dates_or_echo_credentials(self, _):
        cache = KRXDailyCache('test-secret')
        with patch('krx_data.time.monotonic', return_value=100), patch('krx_data.requests.get', return_value=response(status=401)) as get:
            self.assertEqual(cache.get()['state'], 'unavailable')
            cache.get()
        get.assert_called_once()

    @patch('krx_data.utc_now', return_value=NOW)
    def test_holiday_search_is_bounded_and_errors_preserve_original_fetch_time(self, _):
        cache = KRXDailyCache('test')
        with patch('krx_data.requests.get', return_value=response([])) as get:
            self.assertEqual(cache.get()['state'], 'unavailable')
        self.assertEqual(get.call_count, 10)
        cache.next_check = 0
        with patch('krx_data.requests.get', side_effect=[response([]), response()]):
            success = cache.get()['data']
        cache.next_check = 0
        with patch('krx_data.requests.get', return_value=response(status=403)):
            delayed = cache.get()['data']
        self.assertEqual(delayed['trade_date'], success['trade_date'])
        self.assertEqual(delayed['fetched_at'], success['fetched_at'])
        self.assertEqual(delayed['refresh_state'], 'delayed')

    def test_no_key_and_lost_lease_never_call_provider(self):
        with patch('krx_data.requests.get') as get:
            self.assertEqual(KRXDailyCache('').get()['state'], 'unavailable')
            with self.assertRaises(LeaseLost):
                KRXDailyCache('test').get(renew=Mock(side_effect=LeaseLost()))
        get.assert_not_called()

    def test_collector_publishes_krx_even_when_futures_master_is_unavailable(self):
        store = Mock(); master = Mock(); master.get.side_effect = LeaseLost()
        cache = Mock(); cache.get.return_value = section({'test': 'krx'})
        with patch('snapshot_collector._collect_gold_premium_data', return_value=None):
            payload = SnapshotCollector(store, master, krx=cache).collect_once()
        self.assertEqual(payload['krx_daily']['data'], {'test': 'krx'})
        store.publish.assert_called_once()

    def test_api_reads_daily_data_without_provider_calls_and_with_cors(self):
        store = MemoryStore()
        store.payload['krx_daily'] = section({'source': 'KRX_OPEN_API', 'trade_date': '2026-11-11',
            'fetched_at': utc_now().isoformat(), 'refresh_state': 'ok',
            'items': parse_daily({'OutBlock_1': [ROW]}, '20261111')})
        api.dependency_overrides[get_store] = lambda: store
        try:
            with TestClient(app, raise_server_exceptions=False) as client, patch('krx_data.requests.get', side_effect=AssertionError('provider called')):
                r = client.get('/api/krx-gold-daily', headers={'Origin': 'https://financial-dashboard-six-chi.vercel.app'})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()['items'][0]['volume_grams'], 2000)
                self.assertEqual(r.headers['access-control-allow-origin'], 'https://financial-dashboard-six-chi.vercel.app')
                store.payload['krx_daily'] = section(state='unavailable')
                self.assertEqual(client.get('/api/krx-gold-daily').status_code, 503)
                store.payload.pop('krx_daily')
                self.assertEqual(client.get('/api/krx-gold-daily').status_code, 503)
        finally:
            api.dependency_overrides.clear()
