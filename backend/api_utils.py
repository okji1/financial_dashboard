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
    EXCHANGE_RATE_URL
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
    """네이버 금 시세 조회"""
    try:
        url = "https://m.stock.naver.com/front-api/v1/marketIndex/category/CMDT"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://m.stock.naver.com/'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        for item in data.get('result', []):
            if item.get('reutersCode') == 'XAU=':  # 금 코드
                return {
                    'current_price': float(item.get('closePrice', 0)),
                    'change': float(item.get('change', 0)),
                    'change_rate': float(item.get('changeRate', 0)),
                    'currency': 'USD'
                }
        return None
    except Exception as e:
        print(f"네이버 금 시세 조회 실패: {e}")
        return None


def get_exchange_rate():
    """환율 조회 (USD/KRW)"""
    try:
        params = {
            'authkey': EXCHANGE_RATE_API_KEY,
            'searchdate': '',
            'data': 'AP01'
        }
        
        response = requests.get(EXCHANGE_RATE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        for item in data:
            if item.get('cur_unit') == 'USD':
                return float(item.get('deal_bas_r', '0').replace(',', ''))
        
        # API 키 없을 때 기본값
        return 1380.0
        
    except Exception as e:
        print(f"환율 조회 실패: {e}")
        return 1380.0  # 기본값
