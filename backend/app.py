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

def cleanup_old_data():
    """오래된 데이터를 삭제하는 함수"""
    if not supabase:
        print("Supabase 클라이언트가 초기화되지 않았습니다.")
        return
    
    try:
        # 현재 시간에서 7일 전 계산
        week_ago = (datetime.datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        
        # 7일 이상 된 금 시세 데이터 삭제
        gold_delete_result = supabase.table('gold_prices').delete().lt('created_at', week_ago).execute()
        gold_deleted_count = len(gold_delete_result.data) if gold_delete_result.data else 0
        
        # 7일 이상 된 투자 전략 데이터 삭제
        strategy_delete_result = supabase.table('investment_strategies').delete().lt('created_at', week_ago).execute()
        strategy_deleted_count = len(strategy_delete_result.data) if strategy_delete_result.data else 0
        
        # 만료된 토큰 삭제 (25시간 이상 된 토큰)
        token_expire_time = (datetime.datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        token_delete_result = supabase.table('kis_token').delete().lt('created_at', token_expire_time).execute()
        token_deleted_count = len(token_delete_result.data) if token_delete_result.data else 0
        
        print(f"[{datetime.datetime.now()}] 데이터 정리 완료:")
        print(f"  - 금 시세 데이터 삭제: {gold_deleted_count}개")
        print(f"  - 투자 전략 데이터 삭제: {strategy_deleted_count}개") 
        print(f"  - 만료된 토큰 삭제: {token_deleted_count}개")
        
    except Exception as e:
        print(f"[{datetime.datetime.now()}] 데이터 정리 중 오류: {e}")

def daily_cleanup():
    """매일 자정에 오래된 데이터를 정리하는 백그라운드 함수"""
    while True:
        try:
            # 현재 시간 가져오기
            now = datetime.datetime.now()
            
            # 다음 자정까지의 시간 계산
            tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            seconds_until_midnight = (tomorrow - now).total_seconds()
            
            print(f"[{now}] 다음 데이터 정리까지 {seconds_until_midnight/3600:.1f}시간 대기...")
            
            # 자정까지 대기
            time.sleep(seconds_until_midnight)
            
            # 데이터 정리 실행
            cleanup_old_data()
            
            # 24시간 대기 (다음 자정까지)
            time.sleep(24 * 60 * 60)
            
        except Exception as e:
            print(f"[{datetime.datetime.now()}] 일일 정리 작업 오류: {e}")
            # 오류 발생 시 1시간 후 재시도
            time.sleep(3600)

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
                    
                    print(f"[DEBUG] 종목 {symbol} API 응답: rt_cd={price_data.get('rt_cd')}, msg1={price_data.get('msg1', 'N/A')}")
                    
                    if price_data.get('rt_cd') == '0':
                        output = price_data.get('output', {})
                        if output:
                            current_price = float(output.get('stck_prpr', 0))
                            volume = int(output.get('acml_vol', 0))
                            change_rate = float(output.get('prdy_ctrt', 0))
                            
                            strategy_results.append({
                                "symbol": symbol,
                                "name": f"종목-{symbol}",  # 종목명 추가
                                "current_price": current_price,
                                "volume": volume,
                                "change_rate": change_rate,
                                "price_trend": "상승" if change_rate > 0 else "하락" if change_rate < 0 else "보합"
                            })
                            print(f"종목 {symbol} 수집 완료: 가격 {current_price}, 변동률 {change_rate}%")
                        else:
                            print(f"[WARNING] 종목 {symbol} output 데이터가 비어있음")
                    else:
                        print(f"[ERROR] 종목 {symbol} API 오류 - rt_cd: {price_data.get('rt_cd')}, msg1: {price_data.get('msg1')}")
                            
                except Exception as e:
                    print(f"종목 {symbol} 업데이트 오류: {e}")
                    continue

            print(f"[DEBUG] 수집된 전략 결과: {len(strategy_results)}개")
            for result in strategy_results:
                print(f"  - {result}")

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
                    insert_data = {
                        'market_condition': market_condition,
                        'recommended_strategy': recommended_strategy,
                        'average_change_rate': avg_change_rate,
                        'total_volume': total_volume,
                        'analyzed_symbols': len(strategy_results),
                        'detailed_analysis': strategy_results
                    }
                    print(f"[DEBUG] DB에 저장할 데이터: {insert_data}")
                    
                    result = supabase.table('investment_strategies').insert(insert_data).execute()
                    print(f"[DEBUG] DB 저장 결과: {result}")
                    print(f"[{datetime.datetime.now()}] 투자 전략 업데이트 완료 - {market_condition}: {recommended_strategy}")
            else:
                print(f"[{datetime.datetime.now()}] 투자 전략 데이터 수집 실패 - 수집된 데이터가 없습니다")

        except Exception as e:
            print(f"[{datetime.datetime.now()}] 투자 전략 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()

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
    cleanup_thread = threading.Thread(target=daily_cleanup, daemon=True)
    
    gold_thread.start()
    strategy_thread.start()
    cleanup_thread.start()
    
    background_started = True
    print("✅ 백그라운드 업데이트 스레드들이 성공적으로 시작되었습니다.")
    print("   - 금 시세 업데이트: 10분마다")
    print("   - 투자 전략 업데이트: 10분마다") 
    print("   - 데이터 정리: 매일 자정")

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
        
        # detailed_analysis가 제대로 있는지 확인하고 로그 출력
        detailed_analysis = data.get('detailed_analysis', [])
        print(f"[DEBUG] detailed_analysis: {detailed_analysis}")
        print(f"[DEBUG] detailed_analysis 타입: {type(detailed_analysis)}")
        print(f"[DEBUG] detailed_analysis 길이: {len(detailed_analysis) if detailed_analysis else 0}")
        
        # raw_data_summary를 더 구체적으로 만들기
        raw_data_summary = {}
        if detailed_analysis and len(detailed_analysis) > 0:
            raw_data_summary = {
                "price_trend": f"{len(detailed_analysis)}개 종목 실시간 분석",
                "speculation_position": f"평균 변동률: {data.get('average_change_rate', 0):.2f}%",
                "open_interest": f"총 거래량: {data.get('total_volume', 0):,}주"
            }
        else:
            raw_data_summary = {
                "price_trend": "데이터 수집 중",
                "speculation_position": "분석 대기 중",
                "open_interest": "업데이트 예정"
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
            "message": "실제 KIS API 데이터를 기반으로 한 분석입니다 (10분마다 업데이트)"
        })
        
    except Exception as e:
        print(f"[ERROR] 투자 전략 API 오류: {e}")
        return jsonify({"error": f"데이터 조회 중 오류 발생: {e}"}), 500

# 디버깅을 위한 API 엔드포인트들 추가
@app.route('/api/debug/investment-strategy')
def debug_investment_strategy():
    """투자 전략 데이터 디버깅용 엔드포인트"""
    try:
        if not supabase:
            return jsonify({"error": "Database connection not available"}), 500
        
        # 최근 5개 데이터 조회
        response = supabase.table('investment_strategies').select('*').order('created_at', desc=True).limit(5).execute()
        
        debug_info = {
            "total_records": len(response.data) if response.data else 0,
            "latest_data": response.data[0] if response.data else None,
            "all_data": response.data,
            "message": "투자 전략 디버깅 데이터"
        }
        
        if response.data:
            latest = response.data[0]
            debug_info["detailed_analysis_info"] = {
                "exists": 'detailed_analysis' in latest,
                "type": str(type(latest.get('detailed_analysis'))),
                "length": len(latest.get('detailed_analysis', [])) if latest.get('detailed_analysis') else 0,
                "content": latest.get('detailed_analysis', [])
            }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({"error": f"디버깅 중 오류 발생: {e}"}), 500

@app.route('/api/debug/db-status')
def debug_db_status():
    """DB 연결 상태 및 테이블 상태 확인"""
    try:
        if not supabase:
            return jsonify({"error": "Supabase client not initialized"}), 500
        
        # 각 테이블의 최신 데이터 개수 확인
        gold_response = supabase.table('gold_prices').select('*', count='exact').execute()
        strategy_response = supabase.table('investment_strategies').select('*', count='exact').execute()
        token_response = supabase.table('kis_token').select('*', count='exact').execute()
        
        # 최신 데이터 확인
        latest_gold = supabase.table('gold_prices').select('created_at').order('created_at', desc=True).limit(1).execute()
        latest_strategy = supabase.table('investment_strategies').select('created_at').order('created_at', desc=True).limit(1).execute()
        
        return jsonify({
            "db_connection": "OK",
            "table_counts": {
                "gold_prices": gold_response.count if hasattr(gold_response, 'count') else len(gold_response.data),
                "investment_strategies": strategy_response.count if hasattr(strategy_response, 'count') else len(strategy_response.data),
                "kis_token": token_response.count if hasattr(token_response, 'count') else len(token_response.data)
            },
            "latest_updates": {
                "gold_prices": latest_gold.data[0]['created_at'] if latest_gold.data else None,
                "investment_strategies": latest_strategy.data[0]['created_at'] if latest_strategy.data else None
            },
            "background_started": background_started,
            "sample_strategy_data": strategy_response.data[:2] if strategy_response.data else []
        })
        
    except Exception as e:
        return jsonify({"error": f"DB 상태 확인 중 오류: {e}"}), 500

@app.route('/api/test/investment-strategy')
def test_investment_strategy():
    """프론트엔드 테스트용 고정 데이터"""
    return jsonify({
        "market_condition": "테스트 상승 전망",
        "recommended_strategy": "테스트 콜(Call) 옵션 매수",
        "supporting_data": {
            "average_change_rate": 1.5,
            "total_volume": 1000000,
            "analyzed_symbols": 3
        },
        "detailed_analysis": [
            {
                "symbol": "132030",
                "name": "KODEX 골드선물(H)",
                "current_price": 10500,
                "volume": 500000,
                "change_rate": 2.1,
                "price_trend": "상승"
            },
            {
                "symbol": "411060", 
                "name": "ACE KRX금현물",
                "current_price": 8900,
                "volume": 300000,
                "change_rate": 1.2,
                "price_trend": "상승"
            },
            {
                "symbol": "069500",
                "name": "KODEX 200",
                "current_price": 29800,
                "volume": 200000,
                "change_rate": 0.8,
                "price_trend": "상승"
            }
        ],
        "raw_data_summary": {
            "price_trend": "3개 종목 실시간 분석",
            "speculation_position": "평균 변동률: 1.37%",
            "open_interest": "총 거래량: 1,000,000주"
        },
        "analysis_time": "2025-01-28T12:00:00Z",
        "message": "테스트 데이터입니다"
    })

# 수동 데이터 정리를 위한 API 엔드포인트
@app.route('/api/cleanup')
def manual_cleanup():
    """수동으로 오래된 데이터를 정리합니다."""
    try:
        cleanup_old_data()
        return jsonify({"message": "데이터 정리가 완료되었습니다."})
    except Exception as e:
        return jsonify({"error": f"데이터 정리 중 오류 발생: {e}"}), 500

# Flask 앱 시작 시 백그라운드 작업 시작
@app.before_request
def initialize_background():
    global background_started
    if not background_started:
        start_background_tasks()

if __name__ == '__main__':
    start_background_tasks()
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))