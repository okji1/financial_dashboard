"""
공통 API 유틸리티 함수들
"""

import requests
import logging
import threading
import time
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
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
    started = time.monotonic()
    try:
        if json_data:
            response = requests.post(url, headers=headers, json=json_data, timeout=(3, 8))
        else:
            response = requests.get(url, headers=headers, timeout=(3, 8))
        response.raise_for_status()
        return response.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        # Never log the exception URL: exchange queries contain an API key.
        logger.warning("upstream_failed host=%s error=%s", urlsplit(url).hostname, type(e).__name__)
        return None
    finally:
        logger.info("upstream_timing host=%s path=%s duration_ms=%.1f", urlsplit(url).hostname,
                    urlsplit(url).path, (time.monotonic() - started) * 1000)


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


_exchange_lock = threading.Lock()
_exchange_value = None
_exchange_until = 0.0


def get_exchange_rate():
    """Cache valid USD/KRW for 10 minutes; suppress failed retries for 30s.

    Empty business-day results permit date fallback. Transport/auth failures
    stop immediately rather than paying five successive network timeouts.
    Never replace an unavailable quote with an invented exchange rate.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    global _exchange_value, _exchange_until
    with _exchange_lock:
        if time.monotonic() < _exchange_until:
            return _exchange_value
        value = None
        if EXCHANGE_RATE_API_KEY:
            today = datetime.now(ZoneInfo("Asia/Seoul")).date()
            for i in range(5):
                date = (today - timedelta(days=i)).strftime('%Y%m%d')
                data = api_call(f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={EXCHANGE_RATE_API_KEY}&searchdate={date}&data=AP01")
                if data is None or not isinstance(data, list):
                    break
                for item in data:
                    if item.get('result') not in (None, 1):
                        break
                    if item.get('cur_unit') == 'USD':
                        try:
                            import math
                            candidate = float(str(item['deal_bas_r']).replace(',', ''))
                            if math.isfinite(candidate) and candidate > 0:
                                value = candidate
                        except (KeyError, ValueError, TypeError):
                            pass
                        break
                if value is not None or (data and any(item.get('result') not in (None, 1) for item in data)):
                    break
        _exchange_value = value
        _exchange_until = time.monotonic() + (600 if value is not None else 30)
        return value
