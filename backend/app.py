import os
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime
from datetime import timezone

# .env 파일에서 환경 변수 로드
load_dotenv()

# Flask 앱 초기화
app = Flask(__name__)
CORS(app) # 모든 출처에서의 요청을 허용합니다.

# 환경 변수에서 설정 값 가져오기
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# KIS API 설정
KIS_API_MODE = "prod"
KIS_DOMAIN_CONFIG = {
    "prod": "https://openapi.koreainvestment.com:9443",
    "vps": "https://openapivts.koreainvestment.com:29443"
}
KIS_BASE_URL = KIS_DOMAIN_CONFIG[KIS_API_MODE]

# Supabase 클라이언트 초기화
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase 클라이언트 초기화 실패: {e}")
    supabase = None

# --- Helper Functions ---

def get_kis_token():
    """Supabase에서 토큰을 가져오거나 새로 발급받습니다."""
    if not supabase:
        return None, "Supabase client not initialized"

    # 1. Supabase에서 기존 토큰 확인
    try:
        response = supabase.table('kis_token').select('*').order('created_at', desc=True).limit(1).execute()
        if response.data:
            token_data = response.data[0]
            created_at = datetime.datetime.fromisoformat(token_data['created_at'])
            # Timezone-aware datetime으로 비교
            if datetime.datetime.now(timezone.utc) - created_at < datetime.timedelta(hours=23, minutes=55):
                return token_data['access_token'], "Token from Supabase"
    except Exception as e:
        print(f"Supabase에서 토큰 조회 실패: {e}")

    # 2. 토큰이 없거나 만료되었으면 새로 발급
    path = "/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    try:
        res = requests.post(f"{KIS_BASE_URL}{path}", headers=headers, json=body)
        res.raise_for_status()
        token_data = res.json()
        access_token = token_data.get("access_token")

        # 3. 새 토큰을 Supabase에 저장
        if access_token:
            try:
                supabase.table('kis_token').insert({
                    'access_token': access_token,
                    'expires_in': token_data.get('expires_in'),
                }).execute()
                return access_token, "New token issued and saved"
            except Exception as e:
                print(f"Supabase에 토큰 저장 실패: {e}")
                return access_token, "New token issued but failed to save"
        return None, "Failed to issue new token"
    except requests.exceptions.RequestException as e:
        print(f"KIS 토큰 발급 API 요청 실패: {e}")
        return None, str(e)


# --- API Routes ---

@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "API is running."})

@app.route('/api/gold-premium')
def get_gold_premium():
    """국제/국내 금 시세 및 환율을 가져와 프리미엄을 계산합니다."""
    results = {}
    try:
        # 1. 국제 금 시세 (네이버 금융 크롤링)
        intl_url = "https://m.stock.naver.com/marketindex/metals/GCcv1"
        response = requests.get(intl_url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # New resilient scraping logic
        unit_element = soup.find(string=lambda text: "USD/OZS" in text if text else False)
        if not unit_element:
            return jsonify({"error": "국제 금 시세 크롤링 실패: 가격 단위를 포함한 HTML 요소를 찾을 수 없습니다."}), 500

        price_text = unit_element.strip().split(' ')[0]
        price_str = price_text.replace(',', '')
        results['international_price_usd_oz'] = float(price_str)

        # 2. 국내 금 시세 (네이버 증권 API)
        domestic_url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000&page=1"
        response = requests.get(domestic_url)
        response.raise_for_status()
        domestic_data = response.json()['result'][0]
        results['domestic_price_krw_g'] = float(domestic_data['closePrice'].replace(',', ''))

        # 3. 환율 정보 (한국수출입은행 API)
        today = datetime.date.today()
        usd_krw_rate = None
        for i in range(7):
            search_date = today - datetime.timedelta(days=i)
            exchange_url = f"https://www.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={EXCHANGE_RATE_API_KEY}&searchdate={search_date.strftime('%Y%m%d')}&data=AP01"
            response = requests.get(exchange_url)
            response.raise_for_status()
            exchange_data = response.json()
            if exchange_data and isinstance(exchange_data, list):
                for item in exchange_data:
                    if item['cur_unit'] == 'USD':
                        usd_krw_rate = float(item['deal_bas_r'].replace(',', ''))
                        break
            if usd_krw_rate:
                results['usd_krw_rate'] = usd_krw_rate
                break
        
        if not usd_krw_rate:
            return jsonify({"error": "환율 정보를 가져올 수 없습니다."}), 500

        # 4. 금 프리미엄 계산 (Using Troy Ounce)
        oz_to_g = 31.1035 # Correct conversion for Troy Ounce
        intl_price_usd_g = results['international_price_usd_oz'] / oz_to_g
        intl_price_krw_g = intl_price_usd_g * usd_krw_rate
        results['converted_intl_price_krw_g'] = intl_price_krw_g

        premium = ((results['domestic_price_krw_g'] - intl_price_krw_g) / intl_price_krw_g) * 100
        results['premium_percentage'] = premium

        return jsonify(results)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"API 요청 실패: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"데이터 처리 중 오류 발생: {e}"}), 500


@app.route('/api/investment-strategy')
def get_investment_strategy():
    """KIS API를 사용하여 금 선물 투자 전략을 분석합니다."""
    access_token, message = get_kis_token()
    if not access_token:
        return jsonify({"error": "Failed to get KIS token", "details": message}), 500

    # --- 분석 로직 (기술서 기반) ---
    # 현재는 가상 데이터 반환
    strategy_data = {
        "market_condition": "강력한 상승 전망",
        "recommended_strategy": "콜(Call) 옵션 매수",
        "supporting_data": {
            "price_trend": "상승 (거래량 동반)",
            "speculative_position": "순매수 증가",
            "open_interest": "증가"
        },
        "raw_data_summary": {
            "last_price": 1850.5,
            "volume": 150000,
            "speculative_net_long": 50000,
            "total_open_interest": 300000
        },
        "message": "이것은 가상 데이터입니다. KIS API 연동이 필요합니다."
    }

    return jsonify(strategy_data)


if __name__ == '__main__':
    app.run(debug=True, port=os.getenv("PORT", 5000))