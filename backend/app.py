
import os
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime

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
            # 토큰 만료 시간 확인 (24시간 유효)
            created_at = datetime.datetime.fromisoformat(token_data['created_at'])
            if datetime.datetime.now() - created_at < datetime.timedelta(hours=23, minutes=55):
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
        price_str = soup.select_one('strong.DetailInfo_price__I_VJn').text.replace(',', '')
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
        for i in range(7): # 최대 7일 전까지 조회
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

        # 4. 금 프리미엄 계산
        # 1 온스 = 28.3495 그램
        oz_to_g = 28.3495
        # 국제 금 시세 (USD/oz -> KRW/g)
        intl_price_usd_g = results['international_price_usd_oz'] / oz_to_g
        intl_price_krw_g = intl_price_usd_g * usd_krw_rate
        results['converted_intl_price_krw_g'] = intl_price_krw_g

        # 프리미엄 계산 (%)
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
    # 이 부분은 KIS API의 실제 응답 형식을 보며 구현해야 합니다.
    # 현재는 기술서의 내용을 바탕으로 한 가상의 로직입니다.
    
    # 예시: 일자별 시세 조회 ([해외선물-018])
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "HHDFS76200200" # 일자별 시세
    }
    params = {
        "EXCD": "NAS", # 거래소코드
        "SYMB": "GCZ24", # 종목코드 (예: 24년 12월물 금) - 실제 코드는 확인 필요
        "GUBN": "0", # 일/주/월 구분
        "BYMD": "", # 조회종료일자
        "MODP": "0" # 수정주가반영여부
    }
    
    # 실제 API 엔드포인트 경로는 `api키.pdf`에 명시된 것을 사용해야 합니다.
    # "execution_trend": "/uapi/overseas-futureoption/v1/quotations/inquire-daily-price"
    # 이 부분은 현재 문서에 없어 가상의 tr_id를 사용했습니다. 실제 구현 시 확인이 필요합니다.
    
    # 가상 데이터로 응답 생성
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
