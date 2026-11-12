import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import futures_api
from app import app


class FuturesUnavailableTests(unittest.TestCase):
    def test_api_error_is_503_instead_of_a_missing_contract_404(self):
        with patch('futures_api.find_active_gold_contract',side_effect=futures_api.FuturesUnavailable('test-only failure')):
            for endpoint in ['active-contract','pressure-signal','orderbook-analysis']:
                response=app.test_client().get('/api/'+endpoint)
                self.assertEqual(response.status_code,503)
                self.assertNotIn('test-only failure',response.text)

    def test_failed_quote_request_never_becomes_zero_activity(self):
        with patch('kis_auth.get_access_token',return_value='test-only'), patch('futures_api.api_call',return_value=None):
            with self.assertRaises(futures_api.FuturesUnavailable):
                futures_api.get_domestic_futures_data('A88612')

    def test_rejected_quote_never_becomes_zero_activity(self):
        with patch('kis_auth.get_access_token',return_value='test-only'), patch('futures_api.api_call',return_value={'rt_cd':'1','msg_cd':'REJECTED'}):
            with self.assertRaises(futures_api.FuturesUnavailable):
                futures_api.get_domestic_futures_data('A88612')

    def test_http_orderbook_failure_is_unavailable(self):
        with patch('kis_auth.get_access_token',return_value='test-only'),patch('requests.get',return_value=Mock(status_code=503)):
            with self.assertRaises(futures_api.FuturesUnavailable):
                futures_api.get_domestic_futures_orderbook('A88612')

    def test_valid_zero_quote_is_not_a_fabricated_active_contract(self):
        payload={'rt_cd':'0','msg_cd':'OK','output1':{'futs_prpr':'0','acml_vol':'0'}}
        with patch('kis_auth.get_access_token',return_value='test-only'),patch('futures_api.api_call',return_value=payload):
            self.assertIsNone(futures_api.get_domestic_futures_data('A88612'))
