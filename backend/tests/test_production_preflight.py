import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
from preflight_production import api_call, ManagementError, jwt_role, find_service, preflight, TABLES


class ProductionPreflightTests(unittest.TestCase):
    def test_error_response_cannot_expose_admin_key_or_response_body(self):
        session = Mock()
        session.request.return_value = Mock(ok=False, status_code=403, text='SECRET-TOKEN-EXAMPLE')
        with self.assertRaises(ManagementError) as error:
            api_call(session, 'GET', 'https://api.render.com/v1/services', 'SECRET-TOKEN-EXAMPLE')
        self.assertNotIn('SECRET', str(error.exception))

    def test_ambiguous_target_prevents_any_followup_actions(self):
        service = {'id': 'test', 'serviceDetails': {'url': 'https://backend.example.org'}}
        with patch('preflight_production.api_call', return_value=[{'service': service}]*2):
            with self.assertRaises(ManagementError): find_service(Mock(), 'test', 'https://backend.example.org')

    @patch.dict('os.environ', {'RENDER_API_KEY':'test', 'SUPABASE_ACCESS_TOKEN':'test', 'SUPABASE_URL':'https://expected.supabase.co'})
    def test_wrong_backend_project_stops_before_sql(self):
        with patch('preflight_production.find_service', return_value={'id':'test'}), patch('preflight_production.api_call', return_value=[{'envVar': {'key':'SUPABASE_URL', 'value':'https://different.supabase.co'}}]) as call:
            with self.assertRaises(ManagementError): preflight(Mock(), 'https://backend.example.org')
            self.assertEqual(call.call_count, 1)

    @patch.dict('os.environ', {'RENDER_API_KEY':'test', 'SUPABASE_ACCESS_TOKEN':'test', 'SUPABASE_URL':'https://expected.supabase.co'})
    def test_output_contains_names_and_role_claim_but_no_keys(self):
        secret='header.'+base64.urlsafe_b64encode(json.dumps({'role':'service_role'}).encode()).decode().rstrip('=')+'.signature'
        env=[{'envVar':{'key':'SUPABASE_URL','value':'https://expected.supabase.co'}},{'envVar':{'key':'SUPABASE_SERVICE_ROLE_KEY','value':secret}}]
        tables=[{'table_name':name} for name in TABLES]
        with patch('preflight_production.find_service', return_value={'id':'test','name':'backend'}), patch('preflight_production.api_call', side_effect=[env,tables]):
            result=preflight(Mock(),'https://backend.example.org')
        self.assertNotIn(secret,json.dumps(result))
        self.assertEqual(result['effective_key_role_claim'],'service_role')
