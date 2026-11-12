"""
고급 분석 함수들 (COT 보고서, 한국 ETF 분석 등)
"""

import datetime
import importlib.util

# Presence detection must not import cot_reports/pandas on the HTTP analysis path.
COT_AVAILABLE = importlib.util.find_spec('cot_reports') is not None


def analyze_cot_positions():
    """COT 보고서 분석 - 금 선물 포지션"""
    if not COT_AVAILABLE:
        return {
            "error": "COT 라이브러리 없음",
            "message": "pip install cot-reports 필요"
        }
    
    try:
        return {"available": False, "message": "COT 데이터 소스가 연결되지 않았습니다"}

    except Exception as e:
        print(f"COT 분석 오류: {e}")
        return None


def get_cot_market_signal(commercial_net, large_spec_net):
    """COT 데이터 기반 시장 신호"""
    # 상업적 거래자와 대형 투기자의 포지션 분석
    if commercial_net > 10000 and large_spec_net < -10000:
        return {"signal": "강한 매수", "reason": "상업적 거래자 롱, 투기자 숏 증가"}
    elif commercial_net < -10000 and large_spec_net > 10000:
        return {"signal": "강한 매도", "reason": "상업적 거래자 숏, 투기자 롱 증가"}
    elif commercial_net > 0:
        return {"signal": "매수", "reason": "상업적 거래자 순 롱 포지션"}
    elif commercial_net < 0:
        return {"signal": "매도", "reason": "상업적 거래자 순 숏 포지션"}
    else:
        return {"signal": "중립", "reason": "명확한 방향성 없음"}


def analyze_korean_gold_etfs():
    """한국 금 관련 ETF 분석"""
    try:
        # 주요 금 ETF 티커들
        gold_etfs = [
            "132030",  # KODEX 골드선물(H)
            "114800",  # KODEX 인버스
            "261220",  # KODEX 골드선물인버스2X
        ]
        
        etf_analysis = []
        
        for etf_code in gold_etfs:
            # 여기서는 실제 ETF 데이터를 조회해야 하지만
            # 예시로 구조만 제공
            etf_data = {
                "code": etf_code,
                "name": get_etf_name(etf_code),
                "correlation_with_gold": "분석 필요",  # 실제로는 가격 데이터로 상관관계 계산
                "recommendation": "분석 필요"
            }
            etf_analysis.append(etf_data)
        
        return etf_analysis
        
    except Exception as e:
        print(f"한국 금 ETF 분석 오류: {e}")
        return []


def get_etf_name(code):
    """ETF 코드로 이름 반환"""
    etf_names = {
        "132030": "KODEX 골드선물(H)",
        "114800": "KODEX 인버스",
        "261220": "KODEX 골드선물인버스2X"
    }
    return etf_names.get(code, f"ETF {code}")


def calculate_volatility(prices, window=20):
    """변동성 계산"""
    try:
        if len(prices) < window:
            return None
        
        # Only this optional historical-volatility calculation needs NumPy.
        import numpy as np

        # 수익률 계산
        returns = np.diff(np.log(prices))
        
        # 롤링 변동성 (연간화)
        volatility = np.std(returns[-window:]) * np.sqrt(252)
        
        return round(volatility * 100, 2)  # 퍼센트로 변환
        
    except Exception as e:
        print(f"변동성 계산 오류: {e}")
        return None


def generate_comprehensive_analysis(premium_data):
    """현물 프리미엄 중심 종합 분석 (단순화)"""
    try:
        if not premium_data:
            return {"error": "프리미엄 데이터가 없습니다"}
        
        premium_pct = premium_data.get('premium_percentage')
        
        analysis = {
            "timestamp": premium_data.get('timestamp', datetime.datetime.now().isoformat()),
            "market_overview": {
                "london_gold_usd": premium_data.get('international_price_usd_oz'),
                "london_gold_krw": premium_data.get('converted_intl_price_krw_g', 0) * 31.1035,  # g당을 oz당으로 변환
                "domestic_gold_price": premium_data.get('domestic_price_krw_g'),
                "premium_percentage": premium_pct
            },
            "risk_assessment": {
                "premium_grade": get_premium_grade_detail(premium_pct),
                "market_volatility": "미측정",
                "liquidity_score": None  # No measured volume/liquidity data
            },
            "trading_signals": generate_simple_trading_signals(premium_pct),
            "recommendations": generate_premium_recommendations(premium_pct)
        }
        
        return analysis
        
    except Exception as e:
        print(f"종합 분석 생성 오류: {e}")
        return {"error": f"분석 생성 실패: {str(e)}"}


def get_volatility_assessment(premium):
    """프리미엄 기준 변동성 평가"""
    if premium is None:
        return "분석불가"
    
    abs_premium = abs(premium)
    if abs_premium < 1:
        return "낮음"
    elif abs_premium < 3:
        return "보통"
    elif abs_premium < 5:
        return "높음"
    else:
        return "매우높음"


def generate_simple_trading_signals(premium):
    """단순 프리미엄 기반 매매 신호"""
    signals = []
    
    try:
        if premium is None:
            return signals
        
        if premium < -2:
            signals.append({
                "type": "BUY", 
                "strength": "Strong", 
                "reason": f"국내가 국제가보다 {abs(premium):.1f}% 저렴"
            })
        elif premium < 1:
            signals.append({
                "type": "BUY", 
                "strength": "Medium", 
                "reason": "낮은 프리미엄 - 매수 고려"
            })
        elif premium > 6:
            signals.append({
                "type": "SELL", 
                "strength": "Strong", 
                "reason": f"높은 프리미엄 {premium:.1f}% - 매도 고려"
            })
        elif premium > 4:
            signals.append({
                "type": "SELL", 
                "strength": "Medium", 
                "reason": "프리미엄 상승 - 주의 필요"
            })
        else:
            signals.append({
                "type": "HOLD", 
                "strength": "Medium", 
                "reason": "보통 프리미엄 - 관망"
            })
        
        return signals
        
    except Exception as e:
        print(f"매매 신호 생성 오류: {e}")
        return []


def generate_premium_recommendations(premium):
    """프리미엄 기반 추천사항"""
    recommendations = []
    
    try:
        if premium is None:
            return ["데이터 부족으로 분석이 어렵습니다."]
        
        if premium < -1:
            recommendations.append("국내 금가가 국제가보다 저렴합니다. 좋은 매수 기회일 수 있습니다.")
        elif premium < 2:
            recommendations.append("적정 프리미엄 수준입니다. 매수를 고려해보세요.")
        elif premium < 5:
            recommendations.append("프리미엄이 다소 높습니다. 신중한 접근이 필요합니다.")
        else:
            recommendations.append("높은 프리미엄 상태입니다. 매수를 연기하거나 매도를 고려하세요.")
        
        # 공통 추천사항
        recommendations.append("환율 변동에 따른 리스크를 고려하세요.")
        recommendations.append("분산투자의 관점에서 접근하시기 바랍니다.")
        recommendations.append("투자 전 개인의 리스크 허용도를 확인하세요.")
        
        return recommendations
        
    except Exception as e:
        print(f"추천사항 생성 오류: {e}")
        return ["전문가와 상담 후 투자하시기 바랍니다."]


def get_premium_grade_detail(premium):
    """상세 프리미엄 등급"""
    if premium is None:
        return {"grade": "판정불가", "description": "데이터 부족"}
    
    if premium < 1:
        return {"grade": "매우좋음", "description": "매수 적극 고려"}
    elif premium < 2:
        return {"grade": "좋음", "description": "매수 고려"}
    elif premium < 4:
        return {"grade": "보통", "description": "관망"}
    elif premium < 6:
        return {"grade": "높음", "description": "매도 고려"}
    else:
        return {"grade": "매우높음", "description": "매도 적극 고려"}


def calculate_liquidity_score(domestic_data):
    """유동성 점수 계산"""
    if not domestic_data:
        return None
    
    volume = domestic_data.get('volume', 0)
    open_interest = domestic_data.get('open_interest', 0)
    
    # 간단한 유동성 점수 (0-100)
    volume_score = min(volume / 1000, 50)  # 거래량 기준
    oi_score = min(open_interest / 10000, 50)  # 미결제약정 기준
    
    total_score = volume_score + oi_score
    return round(total_score, 1)


def generate_trading_signals(london_data, domestic_data, premium_data, cot_data):
    """매매 신호 생성"""
    signals = []
    
    try:
        # 프리미엄 신호
        if premium_data:
            premium = premium_data.get('premium_percentage')
            if premium < 2:
                signals.append({"type": "BUY", "strength": "Strong", "reason": "낮은 프리미엄"})
            elif premium > 6:
                signals.append({"type": "SELL", "strength": "Strong", "reason": "높은 프리미엄"})
        
        # COT 신호
        if cot_data:
            cot_signal = cot_data.get('market_signal', {})
            if cot_signal.get('signal') in ['강한 매수', '매수']:
                signals.append({"type": "BUY", "strength": "Medium", "reason": "COT 매수 신호"})
            elif cot_signal.get('signal') in ['강한 매도', '매도']:
                signals.append({"type": "SELL", "strength": "Medium", "reason": "COT 매도 신호"})
        
        return signals
        
    except Exception as e:
        print(f"매매 신호 생성 오류: {e}")
        return []


def generate_recommendations(premium_data, cot_data):
    """투자 추천사항 생성"""
    recommendations = []
    
    try:
        # 프리미엄 기반 추천
        if premium_data:
            premium = premium_data.get('premium_percentage')
            if premium < 2:
                recommendations.append("국내 금 프리미엄이 낮아 매수 기회로 판단됩니다.")
            elif premium > 6:
                recommendations.append("국내 금 프리미엄이 높아 매도를 고려해보세요.")
        
        # COT 기반 추천
        if cot_data:
            commercial_sentiment = cot_data.get('commercial_sentiment', '')
            if commercial_sentiment == '강세':
                recommendations.append("상업적 거래자들이 강세 포지션을 취하고 있습니다.")
        
        # 기본 추천사항
        recommendations.append("투자 전 충분한 리스크 관리를 하시기 바랍니다.")
        recommendations.append("소액으로 시작하여 경험을 쌓으시길 권합니다.")
        
        return recommendations
        
    except Exception as e:
        print(f"추천사항 생성 오류: {e}")
        return ["투자 전 전문가와 상담하시기 바랍니다."]
