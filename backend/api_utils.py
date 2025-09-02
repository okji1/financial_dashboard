"""
공통 API 유틸리티 함수들
"""

import requests
from config import (
    EXCHANGE_RATE_API_KEY, 
    KIS_APP_KEY, 
    KIS_APP_SECRET,
    KIS_TOKEN_URL,
    NAVER_GOLD_URL,
    EXCHANGE_RATE_URL,
    NAVER_GOLD_INTERNATIONAL_CHART_URL,
    NAVER_GOLD_INTERNATIONAL_MARKET_URL,
    NAVER_GOLD_DOMESTIC_CHART_URL,
    NAVER_GOLD_DOMESTIC_MARKET_URL
)


def api_call(url, headers=None, json_data=None):
    """API 호출 공통 함수"""
    try:
        if json_data:
            response = requests.post(url, headers=headers, json=json_data)
        else:
            response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API 호출 실패: {e}")
        return None


def get_kis_token():
    """KIS API 토큰 발급"""
    headers = {"content-type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    
    response = api_call(KIS_TOKEN_URL, headers, data)
    if response and response.get('access_token'):
        return response['access_token']
    return None


def get_naver_gold_price():
    """네이버 국제 금 시세 조회 (런던 현물)"""
    try:
        # 네이버 모바일 API - 국제 금시세 (GCcv1)
        data = api_call(NAVER_GOLD_INTERNATIONAL_CHART_URL)
        
        if data and data.get('result') and data['result'].get('priceInfos'):
            price_infos = data['result']['priceInfos']
            if price_infos:
                latest = price_infos[-1]
                current_price = latest.get('currentPrice')
                if current_price:
                    return float(str(current_price).replace(',', ''))
        
        # 백업: marketIndex API 시도
        backup_data = api_call(NAVER_GOLD_INTERNATIONAL_MARKET_URL)
        if backup_data and backup_data.get('result'):
            close_price = backup_data['result'].get('closePrice')
            if close_price:
                return float(str(close_price).replace(',', ''))
        
        return None
        
    except Exception as e:
        print(f"네이버 국제 금 시세 조회 실패: {e}")
        return None


def get_domestic_gold_price():
    """국내 금 현물 시세 조회 (KRW/g)"""
    try:
        # 국내 금시세 (chart API)
        domestic_data = api_call(NAVER_GOLD_DOMESTIC_CHART_URL)
        domestic_price = None
        
        if domestic_data and domestic_data.get('result') and domestic_data['result'].get('priceInfos'):
            # result 안의 priceInfos에서 최신 데이터 가져오기
            price_infos = domestic_data['result']['priceInfos']
            if price_infos:
                latest = price_infos[-1]
                current_price = latest.get('currentPrice')
                if current_price:
                    # 쉼표 제거 후 float 변환
                    domestic_price = float(str(current_price).replace(',', ''))
        
        # 백업: marketIndex API 사용
        if not domestic_price:
            domestic_backup = api_call(NAVER_GOLD_DOMESTIC_MARKET_URL)
            if domestic_backup and domestic_backup.get('result'):
                close_price = domestic_backup['result'].get('closePrice')
                if close_price:
                    domestic_price = float(str(close_price).replace(',', ''))
        
        return domestic_price
        
    except Exception as e:
        print(f"국내 금 시세 조회 실패: {e}")
        return None


def get_exchange_rate():
    """환율 조회 (USD/KRW) - 여러 날짜 시도"""
    from datetime import datetime, timedelta
    
    try:
        # 환율 조회 (여러 날짜 시도)
        usd_krw_rate = None
        for i in range(5):
            date = (datetime.now().date() - timedelta(days=i)).strftime('%Y%m%d')
            exchange_data = api_call(f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={EXCHANGE_RATE_API_KEY}&searchdate={date}&data=AP01")
            
            if exchange_data and isinstance(exchange_data, list):
                for item in exchange_data:
                    if item.get('cur_unit') == 'USD':
                        usd_krw_rate = float(item['deal_bas_r'].replace(',', ''))
                        break
                if usd_krw_rate:
                    break
        
        return usd_krw_rate if usd_krw_rate else 1380.0  # 기본값
        
    except Exception as e:
        print(f"환율 조회 실패: {e}")
        return 1380.0  # 기본값
