"""Browser integration for persisted rules, real chart semantics and recovery.

Explicit synthetic fixtures only. No production writes or external messages.
"""
import copy
import datetime
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[2]
code='''
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
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    clock={'now':datetime.datetime.now(datetime.timezone.utc)}
    mode={'price':100000,'premium':1,'stale':False,'system':'ok','history_error':False}
    def handle(route):
        url=urlsplit(route.request.url);path=url.path.rsplit('/',1)[-1];status=200
        payload=copy.deepcopy(fixtures.get(path))
        if isinstance(payload,dict) and path in ['gold-premium','gold-analysis']:payload['timestamp']=clock['now'].isoformat()
        if path=='gold-premium':
            payload.update(domestic_gold_price=mode['price'],premium_percentage=mode['premium'])
            if mode['stale']:payload['timestamp']=(clock['now']-datetime.timedelta(seconds=120)).isoformat()
        elif path=='futures-candidates':payload={'candidates':[],'count':0}
        elif path in ['active-contract','pressure-signal','krx-gold-daily']:status,payload=404,{'error':'no fixture'}
        elif path=='system-alerts':
            events=[]
            if mode['system'] in ['error','recovered']:
                events=[{'id':'krx-error-test','source':'krx','status':'error','occurred_at':clock['now'].isoformat(),'message':'KRX 일별 자료 수집 실패 또는 데이터 지연이 감지됐습니다.'}]
            if mode['system']=='recovered':events.append({'id':'krx-recovered-test','source':'krx','status':'recovered','occurred_at':clock['now'].isoformat(),'message':'KRX 일별 자료 수집이 정상으로 복구됐습니다.'})
            payload={'events':events,'snapshot_age_seconds':1,'checked_at':clock['now'].isoformat()}
            if mode['system']=='network':status,payload=503,{'error':'connection test'}
        elif path=='krx-gold-history':
            params=parse_qs(url.query);symbol=params['symbol'][0];days=int(params['days'][0]);base=100000 if symbol=='04020000' else 200000
            dates=['2026-11-04','2026-11-05','2026-11-06','2026-11-09']
            items=[{'symbol':symbol,'name':'test gold','trade_date':day,'close':None if i==2 else base+i*1000,
                    'change':0,'change_rate':0,'open':base,'high':base+3000,'low':base,'volume_grams':i*1000,'trading_value_krw':i*100000000} for i,day in enumerate(dates)]
            payload={'source':'KRX_OPEN_API','symbol':symbol,'days':days,'checked_days':10,'total_days':22 if days==30 else 64,'items':items}
            if mode['history_error']:status,payload=503,{'error':'history unavailable'}
        route.fulfill(status=status,content_type='application/json',body=json.dumps(payload),headers={'Access-Control-Allow-Origin':'*'})
    def settled():expect(page.get_by_role('button',name='새로 고침',exact=True)).to_be_enabled()
    def advance(ms=30001):
        settled();clock['now']+=datetime.timedelta(milliseconds=ms);page.clock.fast_forward(ms)
        settled()
    page.route('http://127.0.0.1:5000/api/**',handle)
    page.clock.install(time=clock['now'])
    page.goto('http://127.0.0.1:3000');settled();advance(1001)
    expect(page.get_by_test_id('history-change')).to_have_text('+3.00%')
    assert page.locator('.chart-price').get_attribute('d').count('M')==2,'Missing prices must break the line'
    page.get_by_label('차트 거래일 탐색').fill('0')
    expect(page.get_by_test_id('history-selection')).to_contain_text('2026-11-04')
    expect(page.get_by_test_id('history-selection')).to_contain_text('100,000 원/g')
    page.get_by_role('button',name='미니금 100g',exact=True).click()
    expect(page.get_by_test_id('history-change')).to_have_text('+1.50%')
    page.get_by_role('button',name='30일',exact=True).click()
    expect(page.locator('#history .panel-meta')).to_contain_text('10/22')
    page.get_by_text('거래일별 원자료 보기',exact=True).click()
    expect(page.locator('#history tbody tr')).to_have_count(4)
    expect(page.locator('#history tbody tr').nth(2)).to_contain_text('—')
    mode['history_error']=True;page.get_by_role('button',name='90일',exact=True).click()
    expect(page.locator('#history [role="alert"]')).to_be_visible()
    mode['history_error']=False;page.get_by_role('button',name='30일',exact=True).click()
    expect(page.get_by_test_id('history-change')).to_be_visible()
    print('PASS: date selection, product/range switch, missing-price gaps, raw table and history recovery')
    page.get_by_label('알림 기준값').fill('100000');page.get_by_role('button',name='조건 추가',exact=True).click()
    page.get_by_role('button',name='가격 조건',exact=True).click()
    expect(page.get_by_test_id('inbox-event')).to_have_count(1)
    expect(page.get_by_role('link',name='알림함, 읽지 않은 알림 1건',exact=True)).to_be_visible()
    advance();expect(page.get_by_test_id('inbox-event')).to_have_count(1)
    page.get_by_role('button',name='모두 읽음',exact=True).click()
    expect(page.get_by_role('link',name='알림함, 읽지 않은 알림 0건',exact=True)).to_be_visible()
    page.get_by_role('button',name='안 읽음',exact=True).click()
    expect(page.get_by_test_id('inbox-event')).to_have_count(0)
    page.reload();settled();advance(1001)
    expect(page.locator('.alert-rule')).to_have_count(1)
    page.get_by_role('button',name='안 읽음',exact=True).click()
    expect(page.get_by_test_id('inbox-event')).to_have_count(0)
    print('PASS: inclusive price alert, no duplicate polling, persisted rules and read state')
    page.get_by_label('알림 대상').select_option('premium');page.get_by_label('알림 기준값').fill('2');page.get_by_role('button',name='조건 추가',exact=True).click()
    page.get_by_role('button',name='가격 조건',exact=True).click()
    mode['premium']=2;mode['stale']=True;advance()
    expect(page.get_by_test_id('inbox-event')).to_have_count(1)
    mode['stale']=False;advance()
    expect(page.get_by_test_id('inbox-event')).to_have_count(2)
    advance();expect(page.get_by_test_id('inbox-event')).to_have_count(2)
    mode['price']=90000;mode['premium']=1;advance(601000)
    mode['price']=100000;mode['premium']=2;advance()
    expect(page.get_by_test_id('inbox-event')).to_have_count(4)
    page.get_by_role('button',name='국내외 가격 차이 2% 이상 중지',exact=True).click()
    expect(page.locator('.alert-rule').filter(has_text='국내외 가격 차이')).to_contain_text('일시 중지')
    page.get_by_role('button',name='국내외 가격 차이 2% 이상 삭제',exact=True).click()
    expect(page.locator('.alert-rule')).to_have_count(1)
    print('PASS: stale isolation, premium threshold, cooldown/re-entry, pause and delete')
    page.get_by_role('button',name='수집 상태',exact=True).click()
    mode['system']='error';advance()
    expect(page.get_by_test_id('inbox-event')).to_have_count(1)
    advance();expect(page.get_by_test_id('inbox-event')).to_have_count(1)
    mode['system']='recovered';advance()
    expect(page.get_by_test_id('inbox-event')).to_have_count(2)
    mode['system']='network';advance();advance(31001)
    expect(page.get_by_test_id('inbox-event')).to_have_count(3)
    mode['system']='recovered';advance()
    expect(page.get_by_test_id('inbox-event')).to_have_count(4)
    print('PASS: server failure/recovery deduplication, transport failure, retained inbox and recovery')
    for width in [1440,1024,768,390,320]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),f'Overflow at {width}'
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#history').screenshot(path='/tmp/fd-history-chart-desktop.png')
    page.locator('#alerts').screenshot(path='/tmp/fd-alerts-desktop.png')
    page.get_by_role('button',name='밝은 테마로 전환').click()
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#history').screenshot(path='/tmp/fd-history-chart-mobile.png')
    page.locator('#alerts').screenshot(path='/tmp/fd-alerts-mobile.png')
    assert not errors,errors
    print('PASS: five viewports, dark/light themes and no JavaScript errors')
    browser.close()
