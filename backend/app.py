import os
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime
from datetime import timezone, timedelta
import threading
import time

# 환경 변수 로드
load_dotenv()

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)

# 환경 변수
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Supabase 클라이언트
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase 초기화 실패: {e}")
    supabase = None

# API 호출 헬퍼
def api_call(url, headers=None, json_data=None):
    try:
        if json_data:
            response = requests.post(url, headers=headers, json=json_data, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"API 호출 실패: {e}")
        return None

# KIS 토큰 관리
def get_kis_token():
    if not supabase:
        return None

    # 기존 토큰 확인
    try:
        response = supabase.table('kis_token').select('*').order('created_at', desc=True).limit(1).execute()
        if response.data:
            token_data = response.data[0]
            created_at = datetime.datetime.fromisoformat(token_data['created_at'])
            if datetime.datetime.now(timezone.utc) - created_at < datetime.timedelta(hours=23):
                return token_data['access_token']
    except Exception:
        pass

    # 새 토큰 발급
    token_data = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    
    result = api_call(
        "https://openapi.koreainvestment.com:9443/oauth2/tokenP",
        headers={"content-type": "application/json"},
        json_data=token_data
    )
    
    if result and result.get("access_token"):
        access_token = result["access_token"]
        if supabase:
            try:
                supabase.table('kis_token').insert({
                    'access_token': access_token,
                    'expires_in': result.get('expires_in'),
                }).execute()
            except Exception:
                pass
        return access_token
    return None

# 금시세 조회
def get_gold_prices():
    # 국제 금시세
    intl_data = api_call("https://m.stock.naver.com/front-api/chart/pricesByPeriod?reutersCode=GCcv1&category=metals&chartInfoType=futures&scriptChartType=day")
    international_price = None
    if intl_data and intl_data.get('priceInfos'):
        international_price = float(intl_data['priceInfos'][-1].get('currentPrice', 0))

    # 국내 금시세
    domestic_data = api_call("https://m.stock.naver.com/front-api/chart/pricesByPeriod?reutersCode=M04020000&category=metals&chartInfoType=gold&scriptChartType=day")
    domestic_price = None
    if domestic_data and domestic_data.get('priceInfos'):
        domestic_price = float(domestic_data['priceInfos'][-1].get('currentPrice', 0))

    # 환율
    today = datetime.date.today().strftime('%Y%m%d')
    exchange_data = api_call(f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={EXCHANGE_RATE_API_KEY}&searchdate={today}&data=AP01")
    usd_krw_rate = None
    if exchange_data and isinstance(exchange_data, list):
        for item in exchange_data:
            if item.get('cur_unit') == 'USD':
                usd_krw_rate = float(item['deal_bas_r'].replace(',', ''))
                break

    # 계산
    if not all([international_price, domestic_price, usd_krw_rate]):
        return {"error": "데이터 조회 실패"}

    intl_price_krw_g = (international_price / 31.1035) * usd_krw_rate
    premium = ((domestic_price - intl_price_krw_g) / intl_price_krw_g) * 100

    return {
        "international_price_usd_oz": international_price,
        "domestic_price_krw_g": domestic_price,
        "usd_krw_rate": usd_krw_rate,
        "converted_intl_price_krw_g": intl_price_krw_g,
        "premium_percentage": premium,
        "last_updated": datetime.datetime.now(timezone.utc).isoformat()
    }

# 투자전략 업데이트
def update_strategy():
    if not supabase:
        return False

    # 10분 이내 업데이트 체크
    try:
        response = supabase.table('investment_strategies').select('created_at').order('created_at', desc=True).limit(1).execute()
        if response.data:
            last_update = datetime.datetime.fromisoformat(response.data[0]['created_at'])
            if (datetime.datetime.now(timezone.utc) - last_update).total_seconds() <= 600:
                return False
    except Exception:
        pass

    # KIS 토큰 발급
    access_token = get_kis_token()
    if not access_token:
        return False

    # 종목 데이터 수집
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST01010100",
        "custtype": "P"
    }

    results = []
    for symbol in ["132030", "411060", "069500"]:
        url = f"https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD={symbol}"
        data = api_call(url, headers=headers)

        if data and data.get('rt_cd') == '0' and data.get('output'):
            output = data['output']
            change_rate = float(output.get('prdy_ctrt', 0))
            results.append({
                "symbol": symbol,
                "current_price": float(output.get('stck_prpr', 0)),
                "volume": int(output.get('acml_vol', 0)),
                "change_rate": change_rate
            })

    if not results:
        return False

    # 전략 분석
    avg_change_rate = sum(item['change_rate'] for item in results) / len(results)

    if avg_change_rate > 1:
        condition, strategy = "강세", "콜옵션 매수"
    elif avg_change_rate > 0:
        condition, strategy = "약세상승", "콜옵션 소량매수"
    elif avg_change_rate < -1:
        condition, strategy = "약세", "풋옵션 매수"
    elif avg_change_rate < 0:
        condition, strategy = "약세하락", "풋옵션 소량매수"
    else:
        condition, strategy = "횡보", "관망"

    # DB 저장
    try:
        supabase.table('investment_strategies').insert({
            'market_condition': condition,
            'recommended_strategy': strategy,
            'average_change_rate': avg_change_rate,
            'total_volume': sum(item['volume'] for item in results),
            'analyzed_symbols': len(results),
            'detailed_analysis': results
        }).execute()

        # 오래된 데이터 정리
        all_data = supabase.table('investment_strategies').select('id').order('created_at', desc=False).execute()
        if len(all_data.data) > 10:
            for old_item in all_data.data[:-10]:
                supabase.table('investment_strategies').delete().eq('id', old_item['id']).execute()

        return True
    except Exception:
        return False

# API Routes
@app.route('/')
@app.route('/api')
def health():
    return jsonify({"status": "ok", "message": "Financial Dashboard API"})

@app.route('/api/gold-premium')
def gold_premium():
    result = get_gold_prices()
    if "error" in result:
        return jsonify(result), 500
    return jsonify({**result, "message": "금시세 조회 완료"})

@app.route('/api/investment-strategy')
def investment_strategy():
    if not supabase:
        return jsonify({"error": "Database unavailable"}), 500

    # 업데이트 시도
    update_strategy()

    # 최신 데이터 조회
    try:
        response = supabase.table('investment_strategies').select('*').order('created_at', desc=True).limit(1).execute()
        if not response.data:
            return jsonify({"error": "전략 데이터 없음"}), 404

        data = response.data[0]
        return jsonify({
            "market_condition": data.get('market_condition'),
            "recommended_strategy": data.get('recommended_strategy'),
            "supporting_data": {
                "average_change_rate": data.get('average_change_rate', 0),
                "total_volume": data.get('total_volume', 0),
                "analyzed_symbols": data.get('analyzed_symbols', 0)
            },
            "detailed_analysis": data.get('detailed_analysis', []),
            "analysis_time": data.get('created_at'),
            "message": "투자전략 분석 완료"
        })
    except Exception as e:
        return jsonify({"error": f"조회 오류: {e}"}), 500

# 백그라운드 업데이터
def background_updater():
    while True:
        try:
            update_strategy()
        except Exception:
            pass
        time.sleep(600)

if __name__ == '__main__':
    # 백그라운드 스레드 시작
    threading.Thread(target=background_updater, daemon=True).start()
    app.run()
