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
from futures_api import find_active_gold_contract, generate_gold_futures_candidates, get_domestic_futures_data
from gold_data import get_london_gold_data, calculate_gold_premium, get_premium_grade, analyze_gold_market_signals
from analysis import analyze_cot_positions, analyze_korean_gold_etfs, generate_comprehensive_analysis
from database import (
    get_cached_token, save_token, get_cached_gold_data, save_gold_data,
    get_active_contract, save_active_contract, cleanup_old_data
)

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)

# 전역 변수
background_update_running = False


def get_or_create_kis_token():
    """KIS 토큰 조회 또는 생성"""
    # 캐시된 토큰 확인
    cached_token = get_cached_token()
    if cached_token:
        return cached_token
    
    # 새 토큰 발급
    new_token = get_kis_token()
    if new_token:
        save_token(new_token)
        return new_token
    
    return None


def update_gold_data():
    """금 데이터 업데이트"""
    try:
        # 런던 금 데이터 조회
        london_data = get_london_gold_data()
        
        # 활성 계약 조회
        active_contract = get_active_contract()
        if not active_contract:
            # 새로운 활성 계약 찾기
            new_contract = find_active_gold_contract()
            if new_contract:
                save_active_contract(new_contract)
                active_contract = new_contract
        
        # 국내 선물 데이터 조회
        domestic_data = None
        if active_contract:
            domestic_data = get_domestic_futures_data(active_contract.get('symbol'))
        
        # 프리미엄 계산
        premium_data = None
        if london_data and domestic_data:
            premium_data = calculate_gold_premium(
                london_data.get('krw_price'),
                domestic_data.get('current_price')
            )
        
        # 데이터 저장
        if london_data or domestic_data:
            save_gold_data(london_data, domestic_data, premium_data)
        
        return london_data, domestic_data, premium_data
        
    except Exception as e:
        print(f"데이터 업데이트 오류: {e}")
        return None, None, None


def background_update_worker():
    """백그라운드 데이터 업데이트"""
    global background_update_running
    
    while background_update_running:
        try:
            print(f"[{datetime.datetime.now()}] 백그라운드 업데이트 시작")
            update_gold_data()
            cleanup_old_data()
            print("백그라운드 업데이트 완료")
        except Exception as e:
            print(f"백그라운드 업데이트 오류: {e}")
        
        # 10분 대기
        time.sleep(600)


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
    """금 프리미엄 조회"""
    try:
        # 캐시된 데이터 확인
        cached_data = get_cached_gold_data()
        if cached_data:
            return jsonify({
                "london_gold_usd": cached_data.get('london_gold_usd'),
                "london_gold_krw": cached_data.get('london_gold_krw'),
                "domestic_gold_price": cached_data.get('domestic_gold_price'),
                "premium_percentage": cached_data.get('premium_percentage'),
                "premium_grade": get_premium_grade(cached_data.get('premium_percentage')),
                "exchange_rate": cached_data.get('exchange_rate'),
                "active_contract": cached_data.get('active_contract'),
                "cached": True
            })
        
        # 실시간 데이터 조회
        london_data, domestic_data, premium_data = update_gold_data()
        
        if not london_data and not domestic_data:
            return jsonify({"error": "데이터 조회 실패"}), 500
        
        result = {
            "london_gold_usd": london_data.get('usd_price') if london_data else None,
            "london_gold_krw": london_data.get('krw_price') if london_data else None,
            "domestic_gold_price": domestic_data.get('current_price') if domestic_data else None,
            "premium_percentage": premium_data.get('premium_percentage') if premium_data else None,
            "premium_grade": get_premium_grade(premium_data.get('premium_percentage') if premium_data else None),
            "exchange_rate": london_data.get('exchange_rate') if london_data else None,
            "active_contract": domestic_data.get('symbol') if domestic_data else None,
            "cached": False
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500


@app.route('/api/investment-strategy', methods=['GET'])
def get_investment_strategy():
    """투자 전략 분석"""
    try:
        # 캐시된 데이터 사용
        cached_data = get_cached_gold_data()
        if cached_data:
            premium = cached_data.get('premium_percentage')
            grade = get_premium_grade(premium)
            
            # 간단한 신호 생성
            signals = []
            if premium and premium < 2:
                signals.append({"type": "매수신호", "message": "낮은 프리미엄", "strength": "강함"})
            elif premium and premium > 6:
                signals.append({"type": "매도신호", "message": "높은 프리미엄", "strength": "강함"})
            
            return jsonify({
                "premium_grade": grade,
                "signals": signals,
                "recommendation": "프리미엄 기준 투자 전략을 참고하세요"
            })
        
        return jsonify({"error": "분석할 데이터가 없습니다"}), 404
        
    except Exception as e:
        return jsonify({"error": f"분석 오류: {str(e)}"}), 500


@app.route('/api/gold-analysis', methods=['GET'])
def get_gold_analysis():
    """종합 금 분석"""
    try:
        # 기본 데이터 조회
        london_data, domestic_data, premium_data = update_gold_data()
        
        # COT 분석
        cot_data = analyze_cot_positions()
        
        # 종합 분석 생성
        comprehensive_analysis = generate_comprehensive_analysis(
            london_data, domestic_data, premium_data, cot_data
        )
        
        if comprehensive_analysis:
            return jsonify(comprehensive_analysis)
        else:
            return jsonify({"error": "분석 데이터 부족"}), 404
            
    except Exception as e:
        return jsonify({"error": f"분석 오류: {str(e)}"}), 500


@app.route('/api/active-contract', methods=['GET'])
def get_active_contract_info():
    """활성 계약 정보 조회"""
    try:
        active_contract = get_active_contract()
        if active_contract:
            return jsonify(active_contract)
        
        # 새로운 계약 찾기
        new_contract = find_active_gold_contract()
        if new_contract:
            save_active_contract(new_contract)
            return jsonify(new_contract)
        
        return jsonify({"error": "활성 계약을 찾을 수 없습니다"}), 404
        
    except Exception as e:
        return jsonify({"error": f"조회 오류: {str(e)}"}), 500


@app.route('/api/update-active-contract', methods=['POST'])
def update_active_contract():
    """활성 계약 수동 업데이트"""
    try:
        new_contract = find_active_gold_contract()
        if new_contract:
            save_active_contract(new_contract)
            return jsonify({"message": "활성 계약 업데이트 완료", "contract": new_contract})
        
        return jsonify({"error": "새로운 계약을 찾을 수 없습니다"}), 404
        
    except Exception as e:
        return jsonify({"error": f"업데이트 오류: {str(e)}"}), 500


@app.route('/api/futures-candidates', methods=['GET'])
def get_futures_candidates():
    """선물 후보 월물 목록"""
    try:
        candidates = generate_gold_futures_candidates()
        return jsonify({"candidates": candidates})
        
    except Exception as e:
        return jsonify({"error": f"조회 오류: {str(e)}"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "background_update_running": background_update_running
    })


if __name__ == '__main__':
    # 백그라운드 업데이트 시작
    start_background_updates()
    
    # Flask 앱 실행
    app.run(debug=True, host='0.0.0.0', port=5000)
