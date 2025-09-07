"""
간소화된 Flask 애플리케이션
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import time
import datetime
from datetime import timezone, timedelta

# 모듈화된 함수들 import  
from api_utils import get_kis_token
from database import get_cached_token, save_token, cleanup_old_data, get_active_contract, save_active_contract

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)

# 전역 변수
background_update_running = False


def get_or_create_kis_token():
    """KIS 토큰 조회 또는 생성 - 캐시 우선 사용"""
    # 1단계: 캐시된 토큰 확인 (23시간 미만)
    cached_token = get_cached_token()
    if cached_token:
        print("🔄 캐시된 KIS 토큰 사용")
        return cached_token
    
    # 2단계: 새 토큰 발급 (캐시에 없을 때만)
    print("🔑 새 KIS 토큰 발급 중...")
    new_token = get_kis_token()
    if new_token:
        save_token(new_token)
        print("✅ 새 KIS 토큰 발급 완료")
        return new_token
    
    print("❌ KIS 토큰 발급 실패")
    return None



def background_update_worker():
    """백그라운드 데이터 업데이트"""
    global background_update_running
    while background_update_running:
        # Push application context for each iteration to avoid cross-thread context issues
        with app.app_context():
            try:
                print(f"[{datetime.datetime.now()}] 백그라운드 업데이트 시작")

                # 단순한 금 프리미엄 데이터 업데이트
                from gold_data import get_gold_premium_data
                premium_data = get_gold_premium_data()

                if premium_data:
                    print(f"✅ 금 프리미엄 업데이트 완료: {premium_data.get('premium_percentage', 'N/A')}%")
                else:
                    print("⚠️ 금 프리미엄 업데이트 실패")

                # 활성 계약 자동 업데이트 (1시간마다)
                current_active = get_active_contract()
                if not current_active or (datetime.datetime.now(timezone.utc) - datetime.fromisoformat(current_active['updated_at'].replace('Z', '+00:00'))) > timedelta(hours=1):
                    try:
                        from futures_api import find_active_gold_contract
                        print("🔍 활성 계약 업데이트 확인 중...")
                        try:
                            new_active = find_active_gold_contract()
                            print(f"🔎 find_active_gold_contract 반환값: {type(new_active)}")
                        except Exception as fae:
                            print(f"⚠️ find_active_gold_contract 예외: {fae!r}")
                            new_active = None

                        if new_active:
                            try:
                                saved = save_active_contract(new_active)
                                if saved:
                                    print(f"✅ 활성 계약 저장 성공: {new_active.get('symbol')} (거래량: {new_active.get('volume', 0):,})")
                                else:
                                    print(f"❌ 활성 계약 저장 실패(함수 반환값 False): {new_active.get('symbol')} - 데이터가 Supabase에 저장되지 않았습니다")
                            except Exception as se:
                                print(f"❌ save_active_contract 예외 발생: {se!r}")
                        else:
                            print("⚠️ 활성 계약 데이터 없음 (find_active_gold_contract이 None 반환)")
                    except Exception as e:
                        print(f"⚠️ 활성 계약 업데이트 실패: {e!r}")
                else:
                    print(f"ℹ️ 활성 계약 업데이트 건너뜀 (마지막 업데이트: {current_active.get('updated_at', 'N/A')})")

                # 오래된 데이터 정리
                cleanup_old_data()

            except Exception as e:
                print(f"백그라운드 업데이트 오류: {e}")

        # 5분마다 업데이트
        time.sleep(300)


def start_background_updates():
    """백그라운드 업데이트 시작"""
    global background_update_running
    
    if not background_update_running:
        background_update_running = True
        thread = threading.Thread(target=background_update_worker, daemon=True)
        thread.start()
        print("백그라운드 업데이트 시작됨")


# API 엔드포인트들
@app.route('/api/gold-premium', methods=['GET'])
def get_gold_premium():
    """금 프리미엄 분석 (현물 vs 현물)"""
    try:
        # 금 프리미엄 데이터 수집
        from gold_data import get_gold_premium_data
        
        premium_data = get_gold_premium_data()
        
        if not premium_data:
            return jsonify({"error": "금 프리미엄 데이터 조회 실패"}), 500
        
        # 프론트엔드 기대 구조로 변환
        response_data = {
            "london_gold_usd": premium_data.get('international_price_usd_oz'),
            "london_gold_krw": premium_data.get('converted_intl_price_krw_g') * 31.1035,  # g당 가격을 oz당으로 변환
            "domestic_gold_price": premium_data.get('domestic_price_krw_g'),
            "premium_percentage": premium_data.get('premium_percentage'),
            "premium_grade": premium_data.get('premium_grade'),
            "exchange_rate": premium_data.get('usd_krw_rate'),
            "active_contract": "현물금",  # 현물 거래이므로
            "cached": False,  # 실시간 데이터
            "timestamp": premium_data.get('timestamp')
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500


@app.route('/api/investment-strategy', methods=['GET'])
def get_investment_strategy():
    """프리미엄 기반 투자 전략"""
    try:
        from gold_data import get_gold_premium_data, analyze_premium_signals
        
        # 프리미엄 데이터 조회
        premium_data = get_gold_premium_data()
        if not premium_data:
            return jsonify({"error": "분석할 데이터가 없습니다"}), 404
        
        # 투자 신호 분석
        signals = analyze_premium_signals(premium_data.get('premium_percentage'))
        
        return jsonify({
            "premium_grade": premium_data.get('premium_grade'),
            "premium_percentage": premium_data.get('premium_percentage'),
            "signals": signals,
            "recommendation": "프리미엄 기준 현물 금 투자 전략을 참고하세요"
        })
        
    except Exception as e:
        return jsonify({"error": f"분석 오류: {str(e)}"}), 500


@app.route('/api/futures-candidates', methods=['GET'])
def get_futures_candidates():
    """선물 월물 후보 목록"""
    try:
        from futures_api import generate_gold_futures_candidates
        candidates = generate_gold_futures_candidates()
        
        return jsonify({
            "candidates": candidates,
            "count": len(candidates)
        })
        
    except Exception as e:
        return jsonify({"error": f"후보 조회 오류: {str(e)}"}), 500


@app.route('/api/active-contract', methods=['GET'])
def get_active_contract():
    """현재 활성 계약 정보"""
    try:
        from database import get_active_contract
        from futures_api import get_domestic_futures_data
        
        # 저장된 활성 계약 조회
        active_contract = get_active_contract()
        
        if not active_contract:
            return jsonify({"error": "활성 계약이 설정되지 않았습니다"}), 404
        
        # 실시간 가격 정보 추가
        current_data = get_domestic_futures_data(active_contract.get('symbol'))
        if current_data:
            active_contract.update(current_data)
        
        return jsonify(active_contract)
        
    except Exception as e:
        return jsonify({"error": f"계약 조회 오류: {str(e)}"}), 500


@app.route('/api/update-active-contract', methods=['POST'])
def update_active_contract():
    """활성 계약 업데이트 (거래량 기준)"""
    try:
        from futures_api import find_active_gold_contract
        from database import save_active_contract
        
        # 거래량 기준으로 최적 계약 찾기
        best_contract = find_active_gold_contract()
        
        if not best_contract:
            print("update_active_contract: find_active_gold_contract 반환값 없음")
            return jsonify({"error": "적절한 활성 계약을 찾을 수 없습니다"}), 404
        
        # 데이터베이스에 저장
        try:
            saved = save_active_contract(best_contract)
            if not saved:
                print(f"update_active_contract: save_active_contract returned False for {best_contract.get('symbol')}")
                return jsonify({"error": "활성 계약 저장 실패"}), 500
        except Exception as e:
            print(f"update_active_contract: save_active_contract 예외: {e!r}")
            return jsonify({"error": f"저장 중 예외 발생: {str(e)}"}), 500

        return jsonify({
            "message": "활성 계약이 업데이트되었습니다",
            "contract": best_contract
        })
        
    except Exception as e:
        return jsonify({"error": f"업데이트 오류: {str(e)}"}), 500


@app.route('/api/gold-analysis', methods=['GET'])
def get_gold_analysis():
    """종합 금 시장 분석"""
    try:
        from gold_data import get_gold_premium_data
        from analysis import generate_comprehensive_analysis
        
        # 기본 프리미엄 데이터
        premium_data = get_gold_premium_data()
        if not premium_data:
            return jsonify({"error": "분석할 데이터가 없습니다"}), 404
        
        # 종합 분석 생성
        analysis = generate_comprehensive_analysis(premium_data)
        
        return jsonify(analysis)
        
    except Exception as e:
        return jsonify({"error": f"종합 분석 오류: {str(e)}"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "background_update_running": background_update_running
    })


@app.route('/api/token-status', methods=['GET'])
def get_token_status():
    """토큰 상태 확인"""
    try:
        cached_token = get_cached_token()
        if cached_token:
            # 토큰의 앞 10자리와 뒷 5자리만 표시 (보안)
            masked_token = f"{cached_token[:10]}...{cached_token[-5:]}"
            return jsonify({
                "status": "토큰 있음",
                "token_preview": masked_token,
                "cache_hit": True,
                "message": "캐시된 토큰 사용 중"
            })
        else:
            return jsonify({
                "status": "토큰 없음", 
                "cache_hit": False,
                "message": "새 토큰 발급이 필요합니다"
            })
    except Exception as e:
        return jsonify({"error": f"토큰 상태 확인 오류: {str(e)}"}), 500


@app.route('/api/orderbook-analysis', methods=['GET'])
def get_orderbook_analysis():
    """호가 데이터 기반 매수/매도 압력 분석"""
    try:
        from futures_api import find_active_gold_contract, get_domestic_futures_orderbook
        
        # 파라미터로 종목코드 받기 (기본값: 주계약)
        symbol = request.args.get('symbol')
        
        if not symbol:
            # 주계약 자동 선택
            active_contract = find_active_gold_contract()
            if not active_contract:
                return jsonify({"error": "활성 계약을 찾을 수 없습니다"}), 404
            symbol = active_contract['symbol']
        
        # 호가 분석 수행
        orderbook_data = get_domestic_futures_orderbook(symbol)
        
        if not orderbook_data:
            return jsonify({"error": f"{symbol} 종목의 호가 데이터를 찾을 수 없습니다"}), 404
        
        # 압력 분석 결과 정리
        analysis_result = {
            "symbol": symbol,
            "contract_name": orderbook_data.get("contract_name", ""),
            "current_price": orderbook_data.get("current_price", "0"),
            "volume": orderbook_data.get("volume", "0"),
            "pressure_analysis": {
                "buy_pressure_pct": orderbook_data.get("buy_pressure_pct", 50.0),
                "sell_pressure_pct": orderbook_data.get("sell_pressure_pct", 50.0),
                "pressure_ratio": orderbook_data.get("pressure_ratio", 1.0),
                "pressure_signal": orderbook_data.get("pressure_signal", "균형"),
                "total_bid_quantity": orderbook_data.get("total_bid_quantity", 0),
                "total_ask_quantity": orderbook_data.get("total_ask_quantity", 0)
            },
            "orderbook": orderbook_data.get("orderbook", {}),
            "price_info": {
                "prev_day_price": orderbook_data.get("prev_day_price", "0"),
                "price_change": orderbook_data.get("price_change", "0"),
                "change_rate": orderbook_data.get("change_rate", "0")
            },
            "last_update_time": orderbook_data.get("last_update_time", ""),
            "analysis_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return jsonify(analysis_result)
        
    except Exception as e:
        return jsonify({"error": f"호가 분석 오류: {str(e)}"}), 500


@app.route('/api/pressure-signal', methods=['GET'])
def get_pressure_signal():
    """간단한 매수/매도 압력 신호만 반환"""
    try:
        from futures_api import find_active_gold_contract, get_domestic_futures_orderbook
        
        symbol = request.args.get('symbol')
        
        if not symbol:
            active_contract = find_active_gold_contract()
            if not active_contract:
                return jsonify({"error": "활성 계약을 찾을 수 없습니다"}), 404
            symbol = active_contract['symbol']
        
        orderbook_data = get_domestic_futures_orderbook(symbol)
        
        if not orderbook_data:
            return jsonify({"error": "호가 데이터 없음"}), 404
        
        # 간단한 신호만 반환
        signal_result = {
            "symbol": symbol,
            "pressure_signal": orderbook_data.get("pressure_signal", "균형"),
            "buy_pressure": orderbook_data.get("buy_pressure_pct", 50.0),
            "sell_pressure": orderbook_data.get("sell_pressure_pct", 50.0),
            "recommendation": get_trading_recommendation(orderbook_data.get("pressure_signal", "균형")),
            "timestamp": datetime.datetime.now().strftime('%H:%M:%S')
        }
        
        return jsonify(signal_result)
        
    except Exception as e:
        return jsonify({"error": f"압력 신호 조회 오류: {str(e)}"}), 500


def get_trading_recommendation(pressure_signal):
    """압력 신호 기반 매매 추천"""
    recommendations = {
        "강한 매수": "🟢 매수 고려 - 매수 압력이 강합니다",
        "약한 매수": "🟡 관망 - 매수 압력이 약간 우세합니다", 
        "균형": "⚪ 중립 - 매수/매도 압력이 균형입니다",
        "약한 매도": "🟡 관망 - 매도 압력이 약간 우세합니다",
        "강한 매도": "🔴 매도 고려 - 매도 압력이 강합니다"
    }
    return recommendations.get(pressure_signal, "⚪ 데이터 부족")


if __name__ == '__main__':
    # 백그라운드 업데이트 시작
    start_background_updates()
    
    # Flask 앱 실행
    app.run(debug=True, host='0.0.0.0', port=5000)


# In production (WSGI servers like gunicorn on Render), __name__ == '__main__' is False
# so the background updater would not start. Ensure it starts on the first incoming request.
# Some Flask builds/environments may not provide before_first_request.
# Use a thread-safe before_request hook that runs start_background_updates() only once.
_background_started = False
_background_start_lock = threading.Lock()


@app.before_request
def ensure_background_updates_started():
    global _background_started
    if not _background_started:
        # Acquire lock to ensure only one thread starts the background worker
        with _background_start_lock:
            if not _background_started:
                try:
                    start_background_updates()
                    _background_started = True
                    print("백그라운드 업데이트가 before_request로 시작되었습니다")
                except Exception as e:
                    print(f"백그라운드 업데이트 시작 오류: {e}")
