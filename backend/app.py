import os
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime
from datetime import timezone, timedelta
import time
import threading

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

# 백그라운드 작업 상태 추적
background_started = False

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

def update_gold_data():
    """10분마다 금 시세 데이터를 업데이트하는 백그라운드 함수"""
    while True:
        try:
            print(f"[{datetime.datetime.now()}] 금 시세 데이터 업데이트 시작...")
            
            # 1. 국제 금 시세
            intl_url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=GCcv1&page=1"
            response = requests.get(intl_url)
            response.raise_for_status()
            intl_data = response.json()['result'][0]
            international_price = float(intl_data['closePrice'].replace(',', ''))

            # 2. 국내 금 시세
            domestic_url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000&page=1"
            response = requests.get(domestic_url)
            response.raise_for_status()
            domestic_data = response.json()['result'][0]
            domestic_price = float(domestic_data['closePrice'].replace(',', ''))

            # 3. 환율 정보
            today = datetime.date.today()
            usd_krw_rate = None
            for i in range(7):
                search_date = today - timedelta(days=i)
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
                    break

            if not usd_krw_rate:
                print(f"[{datetime.datetime.now()}] 환율 정보를 가져올 수 없습니다.")
                time.sleep(600)
                continue

            # 4. 프리미엄 계산
            oz_to_g = 31.1035
            intl_price_usd_g = international_price / oz_to_g
            intl_price_krw_g = intl_price_usd_g * usd_krw_rate
            premium = ((domestic_price - intl_price_krw_g) / intl_price_krw_g) * 100

            # 5. DB에 저장
            if supabase:
                supabase.table('gold_prices').insert({
                    'international_price_usd_oz': international_price,
                    'domestic_price_krw_g': domestic_price,
                    'usd_krw_rate': usd_krw_rate,
                    'premium_percentage': premium
                }).execute()
                print(f"[{datetime.datetime.now()}] 금 시세 데이터 업데이트 완료 - Premium: {premium:.2f}%")

        except Exception as e:
            print(f"[{datetime.datetime.now()}] 금 시세 업데이트 오류: {e}")

        # 10분 대기
        print(f"[{datetime.datetime.now()}] 10분 후 다음 업데이트 예정...")
        time.sleep(600)

def update_investment_strategy():
    """10분마다 투자 전략을 업데이트하는 백그라운드 함수"""
    while True:
        try:
            print(f"[{datetime.datetime.now()}] 투자 전략 업데이트 시작...")
            
            access_token, message = get_kis_token()
            if not access_token:
                print(f"토큰 발급 실패: {message}")
                time.sleep(600)
                continue

            gold_symbols = ["132030", "411060", "069500"]
            strategy_results = []
            
            for i, symbol in enumerate(gold_symbols):
                if i > 0:
                    time.sleep(1)
                
                headers = {
                    "Content-Type": "application/json",
                    "authorization": f"Bearer {access_token}",
                    "appkey": KIS_APP_KEY,
                    "appsecret": KIS_APP_SECRET,
                    "tr_id": "FHKST01010100",
                    "custtype": "P"
                }
                
                price_url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
                params = {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol
                }
                
                try:
                    response = requests.get(price_url, headers=headers, params=params, timeout=10)
                    response.raise_for_status()
                    price_data = response.json()
                    
                    if price_data.get('rt_cd') == '0':
                        output = price_data.get('output', {})
                        if output:
                            current_price = float(output.get('stck_prpr', 0))
                            volume = int(output.get('acml_vol', 0))
                            change_rate = float(output.get('prdy_ctrt', 0))
                            
                            strategy_results.append({
                                "symbol": symbol,
                                "current_price": current_price,
                                "volume": volume,
                                "change_rate": change_rate,
                                "price_trend": "상승" if change_rate > 0 else "하락" if change_rate < 0 else "보합"
                            })
                            print(f"종목 {symbol} 수집 완료: 가격 {current_price}, 변동률 {change_rate}%")
                            
                except Exception as e:
                    print(f"종목 {symbol} 업데이트 오류: {e}")
                    continue

            # 전략 분석 및 DB 저장
            if strategy_results:
                avg_change_rate = sum(item['change_rate'] for item in strategy_results) / len(strategy_results)
                total_volume = sum(item['volume'] for item in strategy_results)
                
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

                if supabase:
                    supabase.table('investment_strategies').insert({
                        'market_condition': market_condition,
                        'recommended_strategy': recommended_strategy,
                        'average_change_rate': avg_change_rate,
                        'total_volume': total_volume,
                        'analyzed_symbols': len(strategy_results),
                        'detailed_analysis': strategy_results
                    }).execute()
                    print(f"[{datetime.datetime.now()}] 투자 전략 업데이트 완료 - {market_condition}: {recommended_strategy}")
            else:
                print(f"[{datetime.datetime.now()}] 투자 전략 데이터 수집 실패")

        except Exception as e:
            print(f"[{datetime.datetime.now()}] 투자 전략 업데이트 오류: {e}")

        print(f"[{datetime.datetime.now()}] 투자 전략 10분 후 다음 업데이트 예정...")
        time.sleep(600)

def start_background_tasks():
    """백그라운드 업데이트 스레드들을 시작합니다."""
    global background_started
    
    if background_started:
        print("백그라운드 작업이 이미 시작되었습니다.")
        return
    
    print("백그라운드 업데이트 스레드들을 시작합니다...")
    
    gold_thread = threading.Thread(target=update_gold_data, daemon=True)
    strategy_thread = threading.Thread(target=update_investment_strategy, daemon=True)
    
    gold_thread.start()
    strategy_thread.start()
    
    background_started = True
    print("✅ 백그라운드 업데이트 스레드들이 성공적으로 시작되었습니다.")

# --- API Routes ---

@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "API is running."})

@app.route('/api/gold-premium')
def get_gold_premium():
    """DB에서 최신 금 시세 데이터를 조회합니다."""
    try:
        if not supabase:
            return jsonify({"error": "Database connection not available"}), 500
        
        response = supabase.table('gold_prices').select('*').order('created_at', desc=True).limit(1).execute()
        
        if not response.data:
            return jsonify({"error": "금 시세 데이터가 없습니다. 잠시 후 다시 시도해주세요."}), 404
        
        data = response.data[0]
        
        return jsonify({
            "international_price_usd_oz": data['international_price_usd_oz'],
            "domestic_price_krw_g": data['domestic_price_krw_g'],
            "usd_krw_rate": data['usd_krw_rate'],
            "converted_intl_price_krw_g": (data['international_price_usd_oz'] / 31.1035) * data['usd_krw_rate'],
            "premium_percentage": data['premium_percentage'],
            "last_updated": data['created_at']
        })
        
    except Exception as e:
        return jsonify({"error": f"데이터 조회 중 오류 발생: {e}"}), 500

@app.route('/api/investment-strategy')
def get_investment_strategy():
    """DB에서 최신 투자 전략 데이터를 조회합니다."""
    try:
        if not supabase:
            return jsonify({"error": "Database connection not available"}), 500
        
        response = supabase.table('investment_strategies').select('*').order('created_at', desc=True).limit(1).execute()
        
        if not response.data:
            return jsonify({"error": "투자 전략 데이터가 없습니다. 잠시 후 다시 시도해주세요."}), 404
        
        data = response.data[0]
        
        return jsonify({
            "market_condition": data['market_condition'],
            "recommended_strategy": data['recommended_strategy'],
            "supporting_data": {
                "average_change_rate": data['average_change_rate'],
                "total_volume": data['total_volume'],
                "analyzed_symbols": data['analyzed_symbols']
            },
            "detailed_analysis": data['detailed_analysis'],
            "analysis_time": data['created_at'],
            "message": "실제 KIS API 데이터를 기반으로 한 분석입니다 (10분마다 업데이트)"
        })
        
    except Exception as e:
        return jsonify({"error": f"데이터 조회 중 오류 발생: {e}"}), 500

# Flask 앱 시작 시 백그라운드 작업 시작
@app.before_request
def initialize_background():
    global background_started
    if not background_started:
        start_background_tasks()

if __name__ == '__main__':
    start_background_tasks()
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))