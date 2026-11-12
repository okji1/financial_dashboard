"""Contract parity and request isolation, without external API or database calls."""
import concurrent.futures
import copy
import datetime
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from asgi import app as fastapi_app, api, get_store
from app import app as flask_app
from shared_store import section, utc_now, StoreUnavailable
from test_data_integrity import QUOTE


class MemoryStore:
    def __init__(self):
        self.quote = {**QUOTE, 'timestamp': utc_now().isoformat()}
        self.candidates = [{'symbol':'A88611','description':'금 F 202611','year':2026,'month':11,'expiry_date':None}]
        self.active = {**self.candidates[0], 'current_price':170000.0,'volume':56,'open_interest':100,
            'expiry_year':2026,'expiry_month':11,'updated_at':utc_now().isoformat()}
        self.book = {'symbol':'A88611','contract_name':'금 F 202611','current_price':'170000',
            'volume':'56','prev_day_price':'169000','price_change':'1000','change_rate':'0.59',
            'buy_pressure_pct':50.0,'sell_pressure_pct':50.0,'pressure_ratio':1.0,'pressure_signal':'균형',
            'total_bid_quantity':10,'total_ask_quantity':10,'orderbook':{'bid_prices':['170000'],'ask_prices':['170010']},
            'last_update_time':'153000'}
        self.payload = {'gold':section(self.quote),
            'candidates':section({'candidates':self.candidates,'count':1}),
            'active_contract':section(self.active),'orderbooks':{'A88611':section(self.book)}}
        self.refreshes = 0

    def read(self):
        return {'generation':'test-generation','collected_at':utc_now().isoformat(),'payload':copy.deepcopy(self.payload)}

    def token_status(self):
        return {'cache_hit':True}

    def request_refresh(self):
        self.refreshes += 1


class FastAPIMigrationTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        api.dependency_overrides[get_store] = lambda: self.store
        self.client = TestClient(fastapi_app, raise_server_exceptions=False)
        self.addCleanup(api.dependency_overrides.clear)
        self.addCleanup(self.client.close)

    def test_gold_endpoints_match_existing_flask_contracts(self):
        with patch('gold_data.get_gold_premium_data',return_value=self.store.quote):
            old = flask_app.test_client()
            for path in ['gold-premium','investment-strategy','gold-analysis']:
                previous = old.get('/api/'+path)
                response = self.client.get('/api/'+path)
                self.assertEqual(response.status_code, previous.status_code)
                self.assertEqual(response.json(), previous.json)

    def test_futures_endpoints_preserve_fields_and_values(self):
        with patch('futures_api.find_active_gold_contract',return_value=self.store.active),patch('futures_api.generate_gold_futures_candidates',return_value=self.store.candidates),patch('futures_api.get_domestic_futures_orderbook',return_value=self.store.book):
            old = flask_app.test_client()
            for path in ['futures-candidates','active-contract','pressure-signal','orderbook-analysis']:
                previous = old.get('/api/'+path).json
                response = self.client.get('/api/'+path)
                self.assertEqual(response.status_code,200)
                current = response.json()
                for volatile in ['timestamp','analysis_time']:
                    previous.pop(volatile,None);current.pop(volatile,None)
                self.assertEqual(current,previous)

    def test_requests_do_not_collect_prices_issue_tokens_or_query_orderbooks(self):
        with patch('gold_data._collect_gold_premium_data',side_effect=AssertionError('provider called')),patch('futures_api.get_domestic_futures_data',side_effect=AssertionError('provider called')),patch('futures_api.get_domestic_futures_orderbook',side_effect=AssertionError('provider called')),patch('kis_auth.get_access_token',side_effect=AssertionError('token issuance called')):
            for path in ['gold-premium','investment-strategy','gold-analysis','futures-candidates','active-contract','pressure-signal','orderbook-analysis','token-status']:
                self.assertEqual(self.client.get('/api/'+path).status_code,200,path)
            self.assertEqual(self.client.post('/api/update-active-contract').status_code,200)
            self.assertEqual(self.store.refreshes,1)

    def test_unavailable_and_stale_quotes_cannot_generate_signals(self):
        for field in ['unavailable','expired']:
            if field=='unavailable':self.store.payload['gold']=section(state='unavailable')
            else:self.store.payload['gold']={'state':'ok','data':self.store.quote,'collected_at':(utc_now()-datetime.timedelta(seconds=91)).isoformat()}
            for path in ['gold-premium','investment-strategy','gold-analysis']:
                response=self.client.get('/api/'+path)
                self.assertEqual(response.status_code,503)
                self.assertNotIn('signals',response.json())

    def test_empty_book_and_upstream_failure_are_distinct(self):
        self.store.payload['orderbooks']['A88611']=section(state='empty')
        self.assertEqual(self.client.get('/api/pressure-signal').status_code,404)
        self.store.payload['orderbooks']['A88611']=section(state='unavailable')
        self.assertEqual(self.client.get('/api/pressure-signal').status_code,503)
        self.assertEqual(self.client.get('/api/pressure-signal?symbol=NOTREAL').status_code,404)
        self.assertEqual(self.client.get('/api/pressure-signal?symbol=bad!').status_code,422)

    def test_cors_including_errors_and_untrusted_suffix(self):
        for origin in ['http://127.0.0.1:3000','https://financial-dashboard-six-chi.vercel.app','https://financial-dashboard-8s2zdjlqt-kim-juins-projects.vercel.app']:
            response=self.client.get('/api/pressure-signal?symbol=NOTREAL',headers={'Origin':origin})
            self.assertEqual(response.headers.get('Access-Control-Allow-Origin'),origin)
            self.assertIn('Server-Timing',response.headers)
        response=self.client.get('/api/gold-premium',headers={'Origin':'https://financial-dashboard-evil-kim-juins-projects.vercel.app.evil.org'})
        self.assertNotIn('Access-Control-Allow-Origin',response.headers)

    def test_invalid_numeric_response_is_rejected_and_secret_errors_are_sanitized(self):
        self.store.payload['active_contract']['data']['current_price']='not a price'
        self.assertEqual(self.client.get('/api/active-contract').status_code,502)
        with patch.object(self.store,'read',side_effect=StoreUnavailable('SENSITIVE-EXAMPLE')):
            response=self.client.get('/api/gold-premium')
            self.assertEqual(response.status_code,503)
            self.assertNotIn('SENSITIVE',response.text)

    def test_token_response_cannot_include_a_bearer_token(self):
        with patch.object(self.store,'token_status',return_value={'cache_hit':True,'access_token':'test-secret'}):
            self.assertEqual(self.client.get('/api/token-status').json(),{'cache_hit':True})

    def test_blocking_database_read_does_not_block_the_asgi_event_loop(self):
        started,release=threading.Event(),threading.Event()
        original=self.store.read
        def blocked():
            started.set();release.wait(5);return original()
        with TestClient(fastapi_app) as client,patch.object(self.store,'read',side_effect=blocked),concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            pending=executor.submit(client.get,'/api/gold-premium')
            self.assertTrue(started.wait(3))
            try:
                health=executor.submit(client.get,'/health').result(timeout=3)
                self.assertEqual(health.json()['framework'],'fastapi')
            finally:release.set()
            self.assertEqual(pending.result(timeout=3).status_code,200)

    def test_openapi_exposes_explicit_response_models(self):
        spec=api.openapi()
        self.assertIn('Premium',spec['components']['schemas'])
        self.assertIn('/api/update-active-contract',spec['paths'])
