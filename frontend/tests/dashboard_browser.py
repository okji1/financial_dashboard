"""Dashboard UI regression: valid/empty/stale/error data, themes and mobile.

Run a production frontend locally on port 3000, then run this script with Python
Playwright. All API responses here are explicit test fixtures, never production
writes or invented historical charts.
"""
import copy
import datetime
import json
import os
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright, expect, Error

ROOT = Path(__file__).resolve().parents[2]
code = '''
import json,sys
from unittest.mock import patch
sys.path[:0]=['backend','backend/tests']
from app import app
from test_data_integrity import QUOTE
with patch('gold_data.get_gold_premium_data',return_value=QUOTE):
 print(json.dumps({p:app.test_client().get('/api/'+p).json for p in ['gold-premium','investment-strategy','gold-analysis']}))
'''
fixtures=json.loads(subprocess.check_output([str(ROOT/'backend/venv/bin/python'),'-c',code],cwd=ROOT,text=True))
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    mode={'gold':'ok'};pending=[]
    clock={'now':datetime.datetime.now(datetime.timezone.utc)}
    def route_api(route):
        path=route.request.url.rsplit('/',1)[-1];status=200;payload=copy.deepcopy(fixtures.get(path))
        if isinstance(payload,dict) and path in ['gold-premium','gold-analysis']:
            payload['timestamp']=clock['now'].isoformat()
        if path=='gold-premium':
            if mode['gold']=='timeout':pending.append(route);return
            if mode['gold']=='network':route.abort();return
            if mode['gold']=='error':status,payload=500,{'error':'test failure'}
            elif mode['gold']=='malformed':payload={'london_gold_usd':'invalid'}
            elif mode['gold']=='zero':payload['premium_percentage']=0
            elif mode['gold']=='stale':payload['timestamp']=(clock['now']-datetime.timedelta(seconds=120)).isoformat()
        elif path=='futures-candidates':payload={'candidates':[],'count':0}
        elif path in ['active-contract','pressure-signal']:status,payload=404,{'error':'no contract'}
        route.fulfill(status=status,content_type='application/json',body=json.dumps(payload),headers={'Access-Control-Allow-Origin':'*'})
    def settled():
        # A visible error can precede the other five responses. Finish that batch
        # before advancing into the next poll; the app intentionally coalesces it.
        expect(page.get_by_role('button',name='새로 고침',exact=True)).to_be_enabled()
    def advance(milliseconds=30001, wait_previous=True):
        if wait_previous:settled()
        clock['now']+=datetime.timedelta(milliseconds=milliseconds)
        page.clock.fast_forward(milliseconds)
    page.route('http://127.0.0.1:5000/api/**',route_api)
    page.clock.install(time=clock['now'])
    page.goto(os.getenv('FRONTEND_URL','http://127.0.0.1:3000'))
    expect(page.get_by_test_id('metric-international')).to_contain_text('2,000.00')
    expect(page.get_by_text('현재 조회 가능한 금선물 계약이 없습니다.',exact=True)).to_be_visible()
    expect(page.locator('#sources')).to_contain_text('거래 기준 시각 미제공')
    expect(page.locator('#sources')).to_contain_text('장 운영 상태·기준일은 추정해 표시하지 않습니다.')
    print('PASS: truthful prices, empty futures and missing source metadata')
    mode['gold']='zero';advance()
    expect(page.get_by_test_id('metric-premium')).to_contain_text('0.00')
    mode['gold']='stale';advance()
    expect(page.get_by_text('새로운 시세를 확인한 뒤 해석을 표시합니다.',exact=True)).to_be_visible()
    print('PASS: zero is valid; stale prices do not produce fresh interpretation')
    mode['gold']='error';advance()
    expect(page.get_by_test_id('market-error')).to_contain_text('데이터 서버 오류입니다.')
    expect(page.get_by_test_id('metric-international')).to_contain_text('—')
    mode['gold']='ok';advance()
    expect(page.get_by_test_id('metric-international')).to_contain_text('2,000.00')
    expect(page.get_by_test_id('market-error')).to_have_count(0)
    print('PASS: polling recovers from a failed request and removes its error')
    mode['gold']='malformed';advance()
    expect(page.get_by_test_id('market-error')).to_contain_text('서버 응답 데이터 형식이 올바르지 않습니다.')
    mode['gold']='network';advance()
    expect(page.get_by_test_id('market-error')).to_contain_text('서버에 연결할 수 없습니다.')
    mode['gold']='timeout'
    with page.expect_request('**/api/gold-premium'):advance()
    page.wait_for_timeout(100);advance(20001,wait_previous=False)
    expect(page.get_by_test_id('market-error')).to_contain_text('응답 시간이 초과되었습니다.')
    for route in pending:
        try:route.fulfill(status=504,body='{}',content_type='application/json')
        except Error:pass
    mode['gold']='ok';advance()
    expect(page.get_by_test_id('metric-international')).to_contain_text('2,000.00')
    print('PASS: malformed JSON, network errors and timeout are visible')
    for width in [1440,1024,768,390,320]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'Horizontal overflow at {width}'
    page.set_viewport_size({'width':1440,'height':1000})
    page.screenshot(path='/tmp/fd-design-dark-fixture.png',full_page=True)
    page.get_by_role('button',name='밝은 테마로 전환').click()
    expect(page.locator('html')).not_to_have_class('dark')
    page.screenshot(path='/tmp/fd-design-light-fixture.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path='/tmp/fd-design-mobile-fixture.png',full_page=True)
    assert not errors,errors
    print('PASS: dark/light switch, five viewport sizes and no JavaScript errors')
    page.unroute_all(behavior='ignoreErrors');browser.close()
