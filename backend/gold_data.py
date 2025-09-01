"""
금 현물 프리미엄 분석 함수들
"""

import datetime
from api_utils import get_naver_gold_price, get_domestic_gold_price, get_exchange_rate


def get_gold_premium_data():
    """금 프리미엄 분석을 위한 모든 데이터 수집"""
    try:
        # 1. 국제 금시세 (USD/oz)
        international_price_usd = get_naver_gold_price()
        
        # 2. 환율 (USD/KRW)
        exchange_rate = get_exchange_rate()
        
        # 3. 국내 금시세 (KRW/g)
        domestic_price_krw = get_domestic_gold_price()
        
        if not all([international_price_usd, exchange_rate, domestic_price_krw]):
            return None
            
        # 국제 금시세를 KRW/g으로 변환 (1 oz = 31.1035 g)
        international_price_krw_per_gram = (international_price_usd * exchange_rate) / 31.1035
        
        # 프리미엄 계산
        premium_data = calculate_gold_premium(international_price_krw_per_gram, domestic_price_krw)
        
        return {
            "international_price_usd_oz": international_price_usd,
            "domestic_price_krw_g": domestic_price_krw, 
            "usd_krw_rate": exchange_rate,
            "converted_intl_price_krw_g": round(international_price_krw_per_gram, 2),
            "premium_percentage": premium_data.get('premium_percentage') if premium_data else 0,
            "premium_grade": get_premium_grade(premium_data.get('premium_percentage') if premium_data else 0),
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"금 프리미엄 데이터 수집 오류: {e}")
        return None


def calculate_gold_premium(international_price_krw, domestic_price_krw):
    """금 프리미엄 계산 (현물 vs 현물)"""
    if not international_price_krw or not domestic_price_krw:
        return None
    
    try:
        # 프리미엄 계산 (%)
        premium = ((domestic_price_krw - international_price_krw) / international_price_krw) * 100
        
        # 절대 차이 (원)
        absolute_diff = domestic_price_krw - international_price_krw
        
        return {
            "premium_percentage": round(premium, 2),
            "absolute_difference": round(absolute_diff, 2),
            "international_price_krw": round(international_price_krw, 2),
            "domestic_price_krw": round(domestic_price_krw, 2)
        }
    except Exception as e:
        print(f"프리미엄 계산 오류: {e}")
        return None


def get_premium_grade(premium):
    """프리미엄 등급 판정"""
    if premium is None:
        return "판정불가"
    
    if premium < 1:
        return "매우좋음"  # 1% 미만
    elif premium < 3:
        return "좋음"      # 1-3%
    elif premium < 5:
        return "보통"      # 3-5%  
    elif premium < 7:
        return "높음"      # 5-7%
    else:
        return "매우높음"  # 7% 이상


def analyze_premium_signals(premium_percentage):
    """프리미엄 기반 투자 신호 분석"""
    signals = []
    
    try:
        if premium_percentage is None:
            return []
            
        if premium_percentage < 1:
            signals.append({
                "type": "매수신호",
                "message": "국내 금 프리미엄이 매우 낮습니다 (1% 미만)",
                "strength": "강함",
                "recommendation": "적극 매수 고려"
            })
        elif premium_percentage < 3:
            signals.append({
                "type": "매수신호",
                "message": "국내 금 프리미엄이 낮은 수준입니다",
                "strength": "중간",
                "recommendation": "매수 고려"
            })
        elif premium_percentage > 7:
            signals.append({
                "type": "매도신호", 
                "message": "국내 금 프리미엄이 매우 높습니다 (7% 이상)",
                "strength": "강함",
                "recommendation": "매도 고려 또는 구매 연기"
            })
        elif premium_percentage > 5:
            signals.append({
                "type": "주의신호",
                "message": "국내 금 프리미엄이 높은 수준입니다",
                "strength": "중간", 
                "recommendation": "신중한 접근 필요"
            })
        else:
            signals.append({
                "type": "중립신호",
                "message": "국내 금 프리미엄이 보통 수준입니다",
                "strength": "약함",
                "recommendation": "시장 상황 관찰"
            })
        
        return signals
        
    except Exception as e:
        print(f"프리미엄 신호 분석 오류: {e}")
        return []
