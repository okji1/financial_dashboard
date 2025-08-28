import os
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime
from datetime import timezone, timedelta

# .env 파일에서 환경 변수 로드
load_dotenv()

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)

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

    try:
        response = supabase.table('kis_token').select('*').order('created_at', desc=True).limit(1).execute()
        if response.data:
            token_data = response.data[0]
            created_at = datetime.datetime.fromisoformat(token_data['created_at'])
            if datetime.datetime.now(timezone.utc) - created_at < datetime.timedelta(hours=23, minutes=55):
                return token_data['access_token'], "Token from Supabase"
    except Exception as e:
        print(f"Supabase에서 토큰 조회 실패: {e}")

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

def update_data_if_needed():
    """필요시 데이터를 업데이트합니다 (Vercel용 - 요청 시마다 실행)"""
    if not supabase:
        return False
    
    try:
        # 최신 금 시세 데이터 확인
        gold_response = supabase.table('gold_prices').select('created_at').order('created_at', desc=True).limit(1).execute()
        
        # 10분 이상 된 데이터면 업데이트
        if not gold_response.data:
            should_update = True
        else:
            last_update = datetime.datetime.fromisoformat(gold_response.data[0]['created_at'])
            should_update = (datetime.datetime.now(timezone.utc) - last_update).total_seconds() > 600  # 10분
        
        if should_update:
            print("데이터 업데이트 필요 - 업데이트 시작")
            
            # 금 시세 업데이트
            try:
                intl_url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=GCcv1&page=1"
                response = requests.get(intl_url, timeout=5)
                response.raise_for_status()
                intl_data = response.json()['result'][0]
                international_price = float(intl_data['closePrice'].replace(',', ''))

                domestic_url = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000&page=1"
                response = requests.get(domestic_url, timeout=5)
                response.raise_for_status()
                domestic_data = response.json()['result'][0]
                domestic_price = float(domestic_data['closePrice'].replace(',', ''))

                # 환율 정보
                today = datetime.date.today()
                usd_krw_rate = None
                for i in range(3):  # 최대 3일만 확인 (Vercel 시간 제한)
                    search_date = today - timedelta(days=i)
                    exchange_url = f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={EXCHANGE_RATE_API_KEY}&searchdate={search_date.strftime('%Y%m%d')}&data=AP01"
                    response = requests.get(exchange_url, timeout=5)
                    response.raise_for_status()
                    exchange_data = response.json()
                    if exchange_data and isinstance(exchange_data, list):
                        for item in exchange_data:
                            if item['cur_unit'] == 'USD':
                                usd_krw_rate = float(item['deal_bas_r'].replace(',', ''))
                                break
                    if usd_krw_rate:
                        break
                
                if usd_krw_rate:
                    # 프리미엄 계산 및 저장
                    oz_to_g = 31.1035
                    intl_price_usd_g = international_price / oz_to_g
                    intl_price_krw_g = intl_price_usd_g * usd_krw_rate
                    premium = ((domestic_price - intl_price_krw_g) / intl_price_krw_g) * 100

                    supabase.table('gold_prices').insert({
                        'international_price_usd_oz': international_price,
                        'domestic_price_krw_g': domestic_price,
                        'usd_krw_rate': usd_krw_rate,
                        'premium_percentage': premium
                    }).execute()
                    
                    print("금 시세 데이터 업데이트 완료")
                    return True
                else:
                    print("환율 정보 조회 실패")
                    
            except Exception as e:
                print(f"금 시세 업데이트 오류: {e}")
                
        return False
    except Exception as e:
        print(f"데이터 업데이트 확인 오류: {e}")
        return False

def update_investment_strategy_if_needed():
    """필요시 투자 전략을 업데이트합니다"""
    if not supabase:
        return False
    
    try:
        # 최신 투자 전략 확인
        strategy_response = supabase.table('investment_strategies').select('created_at').order('created_at', desc=True).limit(1).execute()
        
        # 10분 이상 된 데이터면 업데이트
        if not strategy_response.data:
            should_update = True
        else:
            last_update = datetime.datetime.fromisoformat(strategy_response.data[0]['created_at'])
            should_update = (datetime.datetime.now(timezone.utc) - last_update).total_seconds() > 600  # 10분
        
        if should_update:
            print("투자 전략 업데이트 필요 - 업데이트 시작")
            
            access_token, message = get_kis_token()
            if not access_token:
                print(f"토큰 발급 실패: {message}")
                return False

            gold_symbols = ["132030", "411060", "069500"]
            strategy_results = []
            
            for symbol in gold_symbols:
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
                    response = requests.get(price_url, headers=headers, params=params, timeout=5)
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
                                "name": f"종목-{symbol}",
                                "current_price": current_price,
                                "volume": volume,
                                "change_rate": change_rate,
                                "price_trend": "상승" if change_rate > 0 else "하락" if change_rate < 0 else "보합"
                            })
                            
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

                supabase.table('investment_strategies').insert({
                    'market_condition': market_condition,
                    'recommended_strategy': recommended_strategy,
                    'average_change_rate': avg_change_rate,
                    'total_volume': total_volume,
                    'analyzed_symbols': len(strategy_results),
                    'detailed_analysis': strategy_results
                }).execute()
                
                print("투자 전략 업데이트 완료")
                return True
            else:
                print("투자 전략 데이터 수집 실패")
                
        return False
    except Exception as e:
        print(f"투자 전략 업데이트 오류: {e}")
        return False

# --- API Routes ---

@app.route('/')
@app.route('/api')
def health_check():
    return jsonify({"status": "ok", "message": "API is running on Vercel."})

@app.route('/api/gold-premium')
def get_gold_premium():
    """DB에서 최신 금 시세 데이터를 조회합니다."""
    try:
        # 필요시 데이터 업데이트
        update_data_if_needed()
        
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
        # 필요시 투자 전략 업데이트
        update_investment_strategy_if_needed()
        
        if not supabase:
            return jsonify({"error": "Database connection not available"}), 500
        
        response = supabase.table('investment_strategies').select('*').order('created_at', desc=True).limit(1).execute()
        
        if not response.data:
            return jsonify({"error": "투자 전략 데이터가 없습니다. 잠시 후 다시 시도해주세요."}), 404
        
        data = response.data[0]
        detailed_analysis = data.get('detailed_analysis', [])
        
        raw_data_summary = {
            "price_trend": f"{len(detailed_analysis)}개 종목 실시간 분석" if detailed_analysis else "데이터 수집 중",
            "speculation_position": f"평균 변동률: {data.get('average_change_rate', 0):.2f}%",
            "open_interest": f"총 거래량: {data.get('total_volume', 0):,}주"
        }
        
        return jsonify({
            "market_condition": data.get('market_condition', '데이터 없음'),
            "recommended_strategy": data.get('recommended_strategy', '데이터 없음'),
            "supporting_data": {
                "average_change_rate": data.get('average_change_rate', 0),
                "total_volume": data.get('total_volume', 0),
                "analyzed_symbols": data.get('analyzed_symbols', 0)
            },
            "detailed_analysis": detailed_analysis,
            "raw_data_summary": raw_data_summary,
            "analysis_time": data.get('created_at', '시간 정보 없음'),
            "message": "Vercel 서버리스 환경에서 실행 중 (10분마다 업데이트)"
        })
        
    except Exception as e:
        return jsonify({"error": f"데이터 조회 중 오류 발생: {e}"}), 500



if __name__ == '__main__':
    app.run()