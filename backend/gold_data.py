"""
금 관련 데이터 처리 및 분석 함수들
"""

import datetime
from api_utils import get_naver_gold_price, get_exchange_rate


def get_london_gold_data():
    """런던 금 현물 가격 조회"""
    try:
        gold_price_usd = get_naver_gold_price()
        exchange_rate = get_exchange_rate()
        
        if gold_price_usd and exchange_rate:
            gold_price_krw = gold_price_usd * exchange_rate
            return {
                "usd_price": gold_price_usd,
                "krw_price": gold_price_krw,
                "exchange_rate": exchange_rate,
                "timestamp": datetime.datetime.now().isoformat()
            }
    except Exception as e:
        print(f"런던 금 데이터 조회 오류: {e}")
    
    return None


def calculate_gold_premium(london_gold_krw, domestic_gold_price):
    """금 프리미엄 계산"""
    if not london_gold_krw or not domestic_gold_price:
        return None
    
    try:
        # 프리미엄 계산 (%)
        premium = ((domestic_gold_price - london_gold_krw) / london_gold_krw) * 100
        
        # 절대 차이 (원)
        absolute_diff = domestic_gold_price - london_gold_krw
        
        return {
            "premium_percentage": round(premium, 2),
            "absolute_difference": round(absolute_diff, 2),
            "london_price_krw": round(london_gold_krw, 2),
            "domestic_price": round(domestic_gold_price, 2)
        }
    except Exception as e:
        print(f"프리미엄 계산 오류: {e}")
        return None


def get_premium_grade(premium):
    """프리미엄 등급 판정"""
    if premium is None:
        return "판정불가"
    
    if premium < 2:
        return "매우좋음"
    elif premium < 4:
        return "좋음"
    elif premium < 6:
        return "보통"
    elif premium < 8:
        return "높음"
    else:
        return "매우높음"


def analyze_gold_market_signals(london_data, domestic_data, premium_data):
    """금 시장 신호 분석"""
    signals = []
    
    try:
        # 프리미엄 기반 신호
        premium = premium_data.get('premium_percentage', 0)
        if premium < 2:
            signals.append({
                "type": "매수신호",
                "message": "국내 금 프리미엄이 매우 낮습니다",
                "strength": "강함"
            })
        elif premium > 8:
            signals.append({
                "type": "매도신호", 
                "message": "국내 금 프리미엄이 매우 높습니다",
                "strength": "강함"
            })
        
        # 변동성 분석 (선물 데이터가 있는 경우)
        if domestic_data and domestic_data.get('change_rate'):
            change_rate = domestic_data.get('change_rate', 0)
            if abs(change_rate) > 2:
                signal_type = "상승신호" if change_rate > 0 else "하락신호"
                signals.append({
                    "type": signal_type,
                    "message": f"선물 가격이 {abs(change_rate):.2f}% 크게 변동했습니다",
                    "strength": "중간"
                })
        
        return signals
        
    except Exception as e:
        print(f"시장 신호 분석 오류: {e}")
        return []
