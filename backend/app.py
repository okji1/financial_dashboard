"""
간소화된 Flask 애플리케이션
"""

from flask import Flask, jsonify
from flask_cors import CORS
import threading
import time
import datetime

# 모듈화된 함수들 import  
from api_utils import get_kis_token
from database import get_cached_token, save_token, cleanup_old_data

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
        try:
            print(f"[{datetime.datetime.now()}] 백그라운드 업데이트 시작")
            
            # 단순한 금 프리미엄 데이터 업데이트
            from gold_data import get_gold_premium_data
            premium_data = get_gold_premium_data()
            
            if premium_data:
                print(f"✅ 금 프리미엄 업데이트 완료: {premium_data.get('premium_percentage', 'N/A')}%")
            else:
                print("⚠️ 금 프리미엄 업데이트 실패")
            
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


if __name__ == '__main__':
    # 백그라운드 업데이트 시작
    start_background_updates()
    
    # Flask 앱 실행
    app.run(debug=True, host='0.0.0.0', port=5000)
