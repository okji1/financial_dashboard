"""Offline regression tests: no real credentials or writes are used."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import api_utils
import gold_data
from app import app


QUOTE = {
    'international_price_usd_oz': 2000., 'domestic_price_krw_g': 100000.,
    'usd_krw_rate': 1300., 'converted_intl_price_krw_g': 83591.87,
    'premium_percentage': 19.63, 'premium_grade': '매우높음',
    'timestamp': '2026-11-12T00:00:00+00:00',
}


class DataIntegrityTests(unittest.TestCase):
    def setUp(self):
        api_utils._exchange_value = None
        api_utils._exchange_until = 0
        gold_data._gold_cache = None
        gold_data._gold_cache_until = 0
        self.client = app.test_client()

    def tearDown(self):
        self.setUp()

    @patch('api_utils.EXCHANGE_RATE_API_KEY', 'test-only')
    def test_exchange_failure_stops_lookback_and_is_negative_cached(self):
        with patch('api_utils.api_call', return_value=None) as call:
            self.assertIsNone(api_utils.get_exchange_rate())
            self.assertIsNone(api_utils.get_exchange_rate())
        call.assert_called_once()

    @patch('api_utils.EXCHANGE_RATE_API_KEY', 'test-only')
    def test_exchange_empty_holiday_falls_back_and_caches_valid_quote(self):
        with patch('api_utils.api_call', side_effect=[[], [{'result': 1, 'cur_unit': 'USD', 'deal_bas_r': '1,300.50'}]]) as call:
            self.assertEqual(api_utils.get_exchange_rate(), 1300.5)
            self.assertEqual(api_utils.get_exchange_rate(), 1300.5)
            self.assertEqual(call.call_count, 2)

    def test_failed_collection_is_shared_without_fake_price(self):
        with patch('gold_data._collect_gold_premium_data', return_value=None) as collect:
            for _ in range(3):
                self.assertIsNone(gold_data.get_gold_premium_data())
            collect.assert_called_once()

    def test_missing_fx_does_not_generate_premium(self):
        with patch('gold_data.get_exchange_rate', return_value=None), patch('gold_data.get_naver_gold_price', return_value=2000), patch('gold_data.get_domestic_gold_price', return_value=100000):
            self.assertIsNone(gold_data._collect_gold_premium_data())

    def test_dashboard_endpoints_have_matching_contracts(self):
        with patch('gold_data.get_gold_premium_data', return_value=QUOTE):
            premium = self.client.get('/api/gold-premium')
            strategy = self.client.get('/api/investment-strategy')
            analysis = self.client.get('/api/gold-analysis')
        for response in [premium, strategy, analysis]:
            self.assertEqual(response.status_code, 200)
            self.assertIn('Server-Timing', response.headers)
        self.assertEqual(premium.json['london_gold_usd'], 2000.)
        self.assertIsInstance(strategy.json['signals'], list)
        self.assertEqual(analysis.json['market_overview']['premium_percentage'], 19.63)
        self.assertIsNone(analysis.json['risk_assessment']['liquidity_score'])

    def test_unavailable_prices_do_not_return_successful_signals(self):
        with patch('gold_data.get_gold_premium_data', return_value=None):
            for path in ['gold-premium', 'investment-strategy', 'gold-analysis']:
                response = self.client.get('/api/' + path)
                self.assertGreaterEqual(response.status_code, 400)
                self.assertNotIn('signals', response.json)

    def test_token_status_never_contains_partial_or_complete_token(self):
        with patch('app.get_cached_token', return_value='sensitive-test-bearer-token'):
            response = self.client.get('/api/token-status')
        self.assertEqual(response.json, {'cache_hit': True})
        self.assertNotIn('sensitive', response.text)

    def test_local_and_reported_preview_cors(self):
        for origin in ['http://127.0.0.1:3000', 'https://financial-dashboard-8s2zdjlqt-kim-juins-projects.vercel.app']:
            response = self.client.get('/api/futures-candidates', headers={'Origin': origin})
            self.assertEqual(response.headers['Access-Control-Allow-Origin'], origin)
        response = self.client.get('/api/futures-candidates', headers={'Origin': 'https://financial-dashboard-evil-kim-juins-projects.vercel.app.evil.org'})
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)

    @patch.dict('os.environ', {'ENABLE_BACKGROUND_UPDATES': '0'})
    def test_default_web_requests_do_not_start_collector(self):
        with patch('app.start_background_updates') as start:
            self.client.get('/health')
            start.assert_not_called()

    @patch.dict('os.environ', {'KIS_GOLD_FUTURES_SYMBOLS': ''})
    def test_no_contract_is_a_real_404_and_no_pressure_signal(self):
        for path in ['active-contract', 'pressure-signal']:
            response = self.client.get('/api/' + path)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn('buy_pressure', response.json)


class OrderbookIntegrityTests(unittest.TestCase):
    def test_missing_or_negative_quantities_never_create_pressure(self):
        import futures_api
        from unittest.mock import Mock
        for quantities in [{}, {'total_askp_rsqn': '-1', 'total_bidp_rsqn': '10'}, {'total_askp_rsqn': '0', 'total_bidp_rsqn': '0'}]:
            response = Mock(status_code=200)
            response.json.return_value = {'rt_cd': '0', 'output1': {}, 'output2': quantities}
            with patch('kis_auth.get_access_token', return_value='test-only'), patch('requests.get', return_value=response) as get:
                self.assertIsNone(futures_api.get_domestic_futures_orderbook('TEST123'))
                self.assertEqual(get.call_args.kwargs['timeout'], (3, 8))

    def test_valid_orderbook_computes_real_ratios(self):
        import futures_api
        from unittest.mock import Mock
        response = Mock(status_code=200)
        response.json.return_value = {'rt_cd': '0', 'output1': {}, 'output2': {'total_askp_rsqn': '25', 'total_bidp_rsqn': '75'}}
        with patch('kis_auth.get_access_token', return_value='test-only'), patch('requests.get', return_value=response):
            result = futures_api.get_domestic_futures_orderbook('TEST123')
        self.assertEqual(result['buy_pressure_pct'], 75.)
        self.assertEqual(result['sell_pressure_pct'], 25.)
