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
        # 1. 국제 금 시세 (네이버 증권 API)
        intl_url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=GCcv1&page=1"
        response = requests.get(intl_url)
        response.raise_for_status()
        intl_data = response.json()['result'][0]
        results['international_price_usd_oz'] = float(intl_data['closePrice'].replace(',', ''))

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
            exchange_url = f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={EXCHANGE_RATE_API_KEY}&searchdate={search_date.strftime('%Y%m%d')}&data=AP01"
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

    try:
        # KIS API 헤더 설정
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {access_token}",
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SECRET,
            "tr_id": "FHKST01010100"  # 주식현재가 시세
        }

        # 금 선물 종목 코드 (예시: 금 ETF 또는 금 관련 종목)
        # 실제로는 금 선물 코드를 사용해야 함 (예: KRX 금선물)
        gold_symbols = [
            "132030",  # KODEX 골드선물(H) ETF
            "411060",  # ACE KRX금현물
            "069500"   # KODEX 200
        ]

        strategy_results = []
        
        for symbol in gold_symbols:
            # 현재가 조회
            price_url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol
            }
            
            try:
                response = requests.get(price_url, headers=headers, params=params)
                response.raise_for_status()
                price_data = response.json()
                
                if price_data.get('rt_cd') == '0':  # 성공
                    output = price_data.get('output', {})
                    current_price = float(output.get('stck_prpr', 0))  # 현재가
                    volume = int(output.get('acml_vol', 0))  # 누적거래량
                    change_rate = float(output.get('prdy_ctrt', 0))  # 전일대비율
                    
                    strategy_results.append({
                        "symbol": symbol,
                        "current_price": current_price,
                        "volume": volume,
                        "change_rate": change_rate,
                        "price_trend": "상승" if change_rate > 0 else "하락" if change_rate < 0 else "보합"
                    })
                    
            except Exception as e:
                print(f"종목 {symbol} 데이터 조회 실패: {e}")
                continue

        # 투자 전략 분석 로직
        if strategy_results:
            avg_change_rate = sum(item['change_rate'] for item in strategy_results) / len(strategy_results)
            total_volume = sum(item['volume'] for item in strategy_results)
            
            # 전략 결정 로직
            if avg_change_rate > 1:
                market_condition = "강력한 상승 전망"
                recommended_strategy = "콜(Call) 옵션 매수"
            elif avg_change_rate > 0:
                market_condition = "약한 상승 전망"
                recommended_strategy = "콜(Call) 옵션 매수 (소량)"
            elif avg_change_rate < -1:
                market_condition = "강력한 하락 전망"
                recommended_strategy = "풋(Put) 옵션 매수"
            elif avg_change_rate < 0:
                market_condition = "약한 하락 전망"
                recommended_strategy = "풋(Put) 옵션 매수 (소량)"
            else:
                market_condition = "횡보 전망"
                recommended_strategy = "관망"

            strategy_data = {
                "market_condition": market_condition,
                "recommended_strategy": recommended_strategy,
                "supporting_data": {
                    "average_change_rate": round(avg_change_rate, 2),
                    "total_volume": total_volume,
                    "analyzed_symbols": len(strategy_results)
                },
                "detailed_analysis": strategy_results,
                "analysis_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": "실제 KIS API 데이터를 기반으로 한 분석입니다."
            }
        else:
            # API 데이터를 가져오지 못한 경우 기본 전략 반환
            strategy_data = {
                "market_condition": "데이터 부족",
                "recommended_strategy": "추가 분석 필요",
                "supporting_data": {
                    "error": "금 관련 종목 데이터를 가져올 수 없습니다."
                },
                "raw_data_summary": {},
                "message": "KIS API 연동 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            }

        return jsonify(strategy_data)

    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "KIS API 요청 실패", 
            "details": str(e),
            "fallback_strategy": {
                "market_condition": "분석 불가",
                "recommended_strategy": "수동 분석 권장",
                "message": "API 연결 문제로 인해 실시간 분석이 불가능합니다."
            }
        }), 500
    except Exception as e:
        return jsonify({
            "error": f"투자 전략 분석 중 오류 발생: {e}",
            "fallback_strategy": {
                "market_condition": "분석 불가",
                "recommended_strategy": "전문가 상담 권장",
                "message": "시스템 오류로 인해 분석이 불가능합니다."
            }
        }), 500


if __name__ == '__main__':
    app.run(debug=True, port=os.getenv("PORT", 5000))