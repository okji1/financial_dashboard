"""Browser regression checks against a running production frontend.

Requires Python playwright and Chromium. Run from repo root:
python frontend/tests/dashboard_browser.py
Only localhost API routes are replaced by deterministic Flask response fixtures.
"""
import json
import os
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright, expect, Error

ROOT = Path(__file__).resolve().parents[2]
# Generate fixtures through the real Flask endpoints, never external services.
code = '''
import json, sys
from unittest.mock import patch
sys.path[:0] = ['backend', 'backend/tests']
from app import app
from test_data_integrity import QUOTE
with patch('gold_data.get_gold_premium_data', return_value=QUOTE):
 print(json.dumps({p: app.test_client().get('/api/'+p).json for p in ['gold-premium','investment-strategy','gold-analysis']}))
'''
fixtures = json.loads(subprocess.check_output([str(ROOT / 'backend/venv/bin/python'), '-c', code], cwd=ROOT, text=True))
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH', '/usr/bin/chromium'), args=['--no-sandbox'])
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    mode = {'gold': 'ok'}
    pending = []

    def route_api(route):
        path = route.request.url.rsplit('/', 1)[-1]
        status = 200
        payload = fixtures.get(path)
        if path == 'gold-premium' and mode['gold'] == 'timeout':
            pending.append(route)
            return
        if path == 'gold-premium' and mode['gold'] == 'error':
            status, payload = 500, {'error': 'test failure'}
        elif path == 'gold-premium' and mode['gold'] == 'malformed':
            payload = {'london_gold_usd': 'not a number'}
        elif path == 'gold-premium' and mode['gold'] == 'network':
            route.abort(); return
        elif path == 'futures-candidates':
            payload = {'candidates': [], 'count': 0}
        elif path in ['active-contract', 'pressure-signal']:
            status, payload = 404, {'error': 'no contract'}
        route.fulfill(status=status, content_type='application/json', body=json.dumps(payload), headers={'Access-Control-Allow-Origin': '*'})

    page.route('http://127.0.0.1:5000/api/**', route_api)
    page.clock.install()
    page.goto('http://127.0.0.1:3000')
    expect(page.get_by_text('$2000.00', exact=True)).to_be_visible()
    expect(page.get_by_text('현재 조회 가능한 금선물 계약이 없습니다.', exact=True)).to_be_visible()
    expect(page.get_by_text('COMEX 금 선물 (USD)', exact=True)).to_be_visible()
    print('PASS: successful Flask contracts render; empty futures is a normal state')

    mode['gold'] = 'error'
    page.clock.fast_forward(300001)
    expect(page.get_by_text('Error: 데이터 서버 오류입니다. 잠시 후 다시 시도해 주세요.', exact=True)).to_be_visible()
    mode['gold'] = 'ok'
    page.clock.fast_forward(300001)
    expect(page.get_by_text('$2000.00', exact=True)).to_be_visible()
    expect(page.get_by_text('Error: 데이터 서버 오류입니다. 잠시 후 다시 시도해 주세요.', exact=True)).to_have_count(0)
    print('PASS: 500 failure followed by successful polling clears old error')
    mode['gold'] = 'malformed'
    page.clock.fast_forward(300001)
    expect(page.get_by_text('Error: 서버 응답 데이터 형식이 올바르지 않습니다.', exact=True)).to_be_visible()
    mode['gold'] = 'network'
    page.clock.fast_forward(300001)
    expect(page.get_by_text('Error: 서버에 연결할 수 없습니다. 네트워크 또는 접근 설정을 확인해 주세요.', exact=True)).to_be_visible()
    mode['gold'] = 'timeout'
    with page.expect_request('**/api/gold-premium'):
        page.clock.fast_forward(300001)
    page.wait_for_timeout(100)
    page.clock.fast_forward(20001)
    expect(page.get_by_text('Error: 응답 시간이 초과되었습니다. 다시 시도해 주세요.', exact=True)).to_be_visible()
    print('PASS: delayed API request displays timeout')
    assert not errors, errors
    print('PASS: malformed 200 and network failures display errors without render exceptions')
    for route in pending:
        try:
            route.fulfill(status=504, body='{}', content_type='application/json')
        except Error:
            pass  # Browser already cancelled this timed-out request.
    page.unroute_all(behavior="ignoreErrors")
    browser.close()
