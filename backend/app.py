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

def get_real_time_gold_prices():
    """실시간으로 금 시세 데이터를 조회합니다."""
    try:
        # 국제 금시세 (차트 API 사용)
        print("국제 금시세 API 호출 중...")
        intl_url = "https://m.stock.naver.com/front-api/chart/pricesByPeriod?reutersCode=GCcv1&category=metals&chartInfoType=futures&scriptChartType=day"
        response = requests.get(intl_url, timeout=10)
        response.raise_for_status()
        intl_data = response.json()
        
        international_price = None
        if intl_data.get('priceInfos') and len(intl_data['priceInfos']) > 0:
            latest_intl = intl_data['priceInfos'][-1]  # 마지막(최신) 데이터
            international_price = float(latest_intl['currentPrice'])
            print(f"국제 금시세: ${international_price}/oz")

        # 국내 금시세 (차트 API 사용)
        print("국내 금시세 API 호출 중...")
        domestic_url = "https://m.stock.naver.com/front-api/chart/pricesByPeriod?reutersCode=M04020000&category=metals&chartInfoType=gold&scriptChartType=day"
        response = requests.get(domestic_url, timeout=10)
        response.raise_for_status()
        domestic_data = response.json()
        
        domestic_price = None
        if domestic_data.get('priceInfos') and len(domestic_data['priceInfos']) > 0:
            latest_domestic = domestic_data['priceInfos'][-1]  # 마지막(최신) 데이터
            domestic_price = float(latest_domestic['currentPrice'])
            print(f"국내 금시세: ₩{domestic_price}/g")

        # 환율 정보
        print("환율 정보 조회 중...")
        today = datetime.date.today()
        usd_krw_rate = None
        
        for i in range(3):  # 최대 3일간 시도
            search_date = today - timedelta(days=i)
            exchange_url = f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={EXCHANGE_RATE_API_KEY}&searchdate={search_date.strftime('%Y%m%d')}&data=AP01"
            
            try:
                response = requests.get(exchange_url, timeout=10)
                response.raise_for_status()
                exchange_data = response.json()
                
                if exchange_data and isinstance(exchange_data, list):
                    for item in exchange_data:
                        if item['cur_unit'] == 'USD':
                            usd_krw_rate = float(item['deal_bas_r'].replace(',', ''))
                            print(f"환율: {usd_krw_rate} KRW/USD ({search_date})")
                            break
                if usd_krw_rate:
                    break
            except Exception as ex:
                print(f"환율 API 호출 실패 ({search_date}): {ex}")
                continue
        
        # 모든 데이터가 있으면 프리미엄 계산
        if international_price and domestic_price and usd_krw_rate:
            oz_to_g = 31.1035
            intl_price_usd_g = international_price / oz_to_g
            intl_price_krw_g = intl_price_usd_g * usd_krw_rate
            premium = ((domestic_price - intl_price_krw_g) / intl_price_krw_g) * 100
            
            print(f"프리미엄 계산: {premium:.2f}%")
            
            return {
                "international_price_usd_oz": international_price,
                "domestic_price_krw_g": domestic_price,
                "usd_krw_rate": usd_krw_rate,
                "converted_intl_price_krw_g": intl_price_krw_g,
                "premium_percentage": premium,
                "last_updated": datetime.datetime.now(timezone.utc).isoformat(),
                "success": True
            }
        else:
            missing = []
            if not international_price: missing.append("국제 금시세")
            if not domestic_price: missing.append("국내 금시세")
            if not usd_krw_rate: missing.append("환율")
            
            return {
                "success": False,
                "error": f"데이터 조회 실패: {', '.join(missing)}"
            }
            
    except Exception as e:
        print(f"실시간 금시세 조회 오류: {e}")
        return {
            "success": False,
            "error": f"API 호출 중 오류 발생: {e}"
        }

def clean_old_data(table_name, max_records=10):
    """DB에서 오래된 데이터를 삭제하여 최대 개수 유지 (투자전략용)"""
    if not supabase:
        return False
    
    try:
        # 현재 데이터 개수 확인
        response = supabase.table(table_name).select('id').execute()
        current_count = len(response.data) if response.data else 0
        
        if current_count > max_records:
            # 삭제할 개수 계산
            delete_count = current_count - max_records
            
            # 가장 오래된 데이터 조회 (created_at 오름차순으로 정렬)
            old_data = supabase.table(table_name).select('id').order('created_at', desc=False).limit(delete_count).execute()
            
            if old_data.data:
                # 오래된 데이터들의 ID 수집
                old_ids = [item['id'] for item in old_data.data]
                
                # 일괄 삭제
                for old_id in old_ids:
                    supabase.table(table_name).delete().eq('id', old_id).execute()
                
                print(f"{table_name} 테이블에서 {len(old_ids)}개 오래된 데이터 삭제 완료")
                return True
        
        print(f"{table_name} 테이블 데이터 개수: {current_count}/{max_records} - 삭제 불필요")
        return True
        
    except Exception as e:
        print(f"{table_name} 테이블 데이터 정리 오류: {e}")
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
            print("DB에 투자 전략 데이터가 없음 - 업데이트 필요")
        else:
            last_update = datetime.datetime.fromisoformat(strategy_response.data[0]['created_at'])
            time_diff = (datetime.datetime.now(timezone.utc) - last_update).total_seconds()
            should_update = time_diff > 600  # 10분
            print(f"마지막 투자전략 업데이트: {time_diff:.0f}초 전, 업데이트 필요: {should_update}")
        
        if should_update:
            print("투자 전략 업데이트 시작...")
            
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
                            print(f"종목 {symbol} 업데이트: {current_price}원, {change_rate:+.2f}%")
                            
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

                print(f"투자 전략 분석: {market_condition} (평균 변동률: {avg_change_rate:+.2f}%)")

                # 새 데이터 저장
                supabase.table('investment_strategies').insert({
                    'market_condition': market_condition,
                    'recommended_strategy': recommended_strategy,
                    'average_change_rate': avg_change_rate,
                    'total_volume': total_volume,
                    'analyzed_symbols': len(strategy_results),
                    'detailed_analysis': strategy_results
                }).execute()
                
                print("투자 전략 데이터 저장 완료")
                
                # 오래된 데이터 정리 (최대 10개 유지)
                clean_old_data('investment_strategies', 10)
                
                return True
            else:
                print("투자 전략 데이터 수집 실패")
                
        else:
            print("투자전략 업데이트 불필요 - 최신 데이터 사용")
                
        return False
    except Exception as e:
        print(f"투자 전략 업데이트 오류: {e}")
        return False

# --- API Routes ---

@app.route('/')
@app.route('/api')
def health_check():
    return jsonify({"status": "ok", "message": "Financial Dashboard API is running."})

@app.route('/api/gold-premium')
def get_gold_premium():
    """실시간으로 금 시세 데이터를 조회합니다."""
    try:
        print("실시간 금시세 조회 시작...")
        gold_data = get_real_time_gold_prices()
        
        if gold_data["success"]:
            return jsonify({
                "international_price_usd_oz": gold_data["international_price_usd_oz"],
                "domestic_price_krw_g": gold_data["domestic_price_krw_g"],
                "usd_krw_rate": gold_data["usd_krw_rate"],
                "converted_intl_price_krw_g": gold_data["converted_intl_price_krw_g"],
                "premium_percentage": gold_data["premium_percentage"],
                "last_updated": gold_data["last_updated"],
                "message": "실시간 데이터 조회 완료"
            })
        else:
            return jsonify({"error": gold_data["error"]}), 500
        
    except Exception as e:
        return jsonify({"error": f"실시간 금시세 조회 중 오류 발생: {e}"}), 500

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