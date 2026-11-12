"""
선물 관련 API 함수들
"""

import datetime
from api_utils import get_kis_token, api_call
from config import KIS_APP_KEY, KIS_APP_SECRET, KIS_FUTURES_URL


def generate_gold_futures_candidates():
    """Use only explicitly verified commodity-futures codes.

    The former 101X12-style symbols belong to index futures examples and
    must never be fabricated as gold futures. An empty configuration means
    the feature is unavailable (not a successful zero-volume result).
    """
    import os
    import re

    raw = os.getenv("KIS_GOLD_FUTURES_SYMBOLS", "")
    symbols = [value.strip().upper() for value in raw.split(",") if value.strip()]
    candidates = []
    for symbol in dict.fromkeys(symbols):
        if not re.fullmatch(r"[A-Z0-9]{4,16}", symbol):
            raise ValueError("Invalid KIS commodity futures symbol in configuration")
        candidates.append({
            "symbol": symbol,
            "description": f"검증된 상품선물 {symbol}",
            "year": None,
            "month": None,
            "expiry_date": None,
        })
    return candidates


def get_domestic_futures_data(symbol):
    """Step 2: 국내 선물 데이터 수집 (KIS API) - 토큰 필수 확인"""
    from kis_auth import get_access_token
    access_token = get_access_token()

    # 토큰이 없으면 절대 API 호출하지 않음
    if not access_token:
        print("🚫 토큰 없음 - KIS API 호출 차단 (SMS 방지)")
        return None
    
    # 국내선물옵션 기본시세 조회 API (GitHub 공식 저장소 기준)
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHMIF10000000",  # 선물옵션 시세 조회
        "custtype": "P"
    }
    
    # Gold is a commodity future; F is for index futures, not gold.
    import os
    market_code = os.getenv("KIS_GOLD_FUTURES_MARKET_CODE", "CF")
    if market_code != "CF":
        print("⚠️ 상품선물 시장구분 코드는 CF여야 합니다")
        return None
    params = {
        "FID_COND_MRKT_DIV_CODE": market_code,
        "FID_INPUT_ISCD": symbol        # 종목코드 (예: 101W09)
    }
    
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{KIS_FUTURES_URL}?{query_string}"
    
    print(f"🔗 KIS API 호출: {symbol} (토큰 포함)")
    data = api_call(url, headers=headers)
    
    if data and data.get('rt_cd') == '0' and data.get('output1'):
        output1 = data.get('output1', {})
        # 선물 데이터가 실제로 있는지 확인 (거래량 체크)
        volume = int(output1.get('acml_vol', 0))
        if volume > 0:  # 거래량이 있는 경우만 유효한 데이터로 간주
            print(f"📊 {symbol} 선물 데이터 조회 성공 (거래량: {volume:,})")
            return {
                "symbol": symbol,
                "current_price": float(output1.get('futs_prpr', 0)),         # 선물현재가
                "volume": volume,                                            # 총거래량
                "open_interest": int(output1.get('hts_otst_stpl_qty', 0)),   # 미결제약정
                "change_rate": float(output1.get('futs_prdy_ctrt', 0)),      # 전일대비율
                "high": float(output1.get('futs_hgpr', 0)),                  # 고가
                "low": float(output1.get('futs_lwpr', 0))                    # 저가
            }
    
    print(f"⚠️ {symbol} 선물 데이터 없음 또는 거래량 0")
    return None


def get_domestic_futures_orderbook(symbol):
    """선물 호가 정보 조회 - 매수/매도 압력 분석용 (REST API 기반)"""
    from kis_auth import get_access_token
    import requests

    access_token = get_access_token()

    if not access_token:
        print("🚫 토큰 없음 - KIS 호가 API 호출 차단")
        return None
    
    try:
        # Excel에서 확인한 정확한 REST API 사용
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-futureoption/v1/quotations/inquire-asking-price"
        
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'authorization': f'Bearer {access_token}',
            'appkey': KIS_APP_KEY,
            'appsecret': KIS_APP_SECRET,
            'tr_id': 'FHMIF10010000'  # Excel에서 확인한 TR_ID
        }
        
        params = {
            'fid_cond_mrkt_div_code': 'CF',  # 상품선물
            'fid_input_iscd': symbol
        }
        
        print(f"🔗 KIS 호가 API 호출: {symbol} (TR_ID: FHMIF10010000)")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('rt_cd') == '0':
                output1 = data.get('output1', {})
                output2 = data.get('output2', {})
                
                # Excel에서 확인한 핵심 필드들 사용
                total_ask_quantity = int(output2.get('total_askp_rsqn', 0) or 0)  # 총 매도호가 잔량
                total_bid_quantity = int(output2.get('total_bidp_rsqn', 0) or 0)  # 총 매수호가 잔량
                
                # 매수/매도 압력 분석
                total_quantity = total_ask_quantity + total_bid_quantity
                if total_quantity > 0:
                    buy_pressure = (total_bid_quantity / total_quantity) * 100
                    sell_pressure = (total_ask_quantity / total_quantity) * 100
                else:
                    buy_pressure = sell_pressure = None
                
                # 압력 강도 분석
                pressure_ratio = total_bid_quantity / total_ask_quantity if total_ask_quantity > 0 else None
                
                if total_quantity == 0:
                    pressure_signal = "데이터 없음"
                elif pressure_ratio is None:
                    pressure_signal = "강한 매수"
                elif pressure_ratio > 1.2:
                    pressure_signal = "강한 매수"
                elif pressure_ratio > 1.05:
                    pressure_signal = "약한 매수"
                elif pressure_ratio < 0.8:
                    pressure_signal = "강한 매도"
                elif pressure_ratio < 0.95:
                    pressure_signal = "약한 매도"
                else:
                    pressure_signal = "균형"
                
                print(f"📊 {symbol} 호가 분석 성공: 매수 {total_bid_quantity:,} vs 매도 {total_ask_quantity:,} → {pressure_signal}")
                
                if total_quantity == 0:
                    print(f"⚠️ {symbol} 호가 잔량 없음 - 신호 계산 생략")
                    return None

                return {
                    "symbol": symbol,
                    "contract_name": output1.get('hts_kor_isnm', ''),
                    "current_price": output1.get('futs_prpr', '0'),
                    "prev_day_price": output1.get('futs_prdy_clpr', '0'),
                    "price_change": output1.get('futs_prdy_vrss', '0'),
                    "change_rate": output1.get('futs_prdy_ctrt', '0'),
                    "volume": output1.get('acml_vol', '0'),
                    "total_ask_quantity": total_ask_quantity,
                    "total_bid_quantity": total_bid_quantity,
                    "buy_pressure_pct": round(buy_pressure, 2) if buy_pressure is not None else None,
                    "sell_pressure_pct": round(sell_pressure, 2) if sell_pressure is not None else None,
                    "pressure_ratio": round(pressure_ratio, 3) if pressure_ratio is not None else None,
                    "pressure_signal": pressure_signal,
                    "orderbook": {
                        "ask_prices": [output2.get(f'futs_askp{i}', '') for i in range(1, 6)],
                        "ask_quantities": [output2.get(f'askp_rsqn{i}', '') for i in range(1, 6)],
                        "bid_prices": [output2.get(f'futs_bidp{i}', '') for i in range(1, 6)],
                        "bid_quantities": [output2.get(f'bidp_rsqn{i}', '') for i in range(1, 6)],
                        "ask_counts": [output2.get(f'askp_csnu{i}', '') for i in range(1, 6)],
                        "bid_counts": [output2.get(f'bidp_csnu{i}', '') for i in range(1, 6)]
                    },
                    "last_update_time": output2.get('aspr_acpt_hour', '')
                }
            else:
                print(f"⚠️ {symbol} API 오류: {data.get('msg1', 'Unknown error')}")
                return None
        else:
            print(f"⚠️ {symbol} HTTP 오류: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"⚠️ {symbol} 호가 조회 실패: {str(e)}")
        return None


def find_active_gold_contract():
    """Step 3: 주 계약(Active Contract) 자동 선택 + 매수/매도 압력 분석"""
    
    # 1. Verified commodity futures only
    candidates = generate_gold_futures_candidates()
    if not candidates:
        print("⚠️ 검증된 금 상품선물 종목코드가 설정되지 않았습니다")
        return None
    
    # 2. 각 후보의 데이터 수집
    candidate_data = []
    for candidate in candidates:
        symbol = candidate['symbol']
        
        # 기본 시세 데이터
        price_data = get_domestic_futures_data(symbol)
        
        # 호가 데이터 (매수/매도 압력 분석)
        orderbook_data = get_domestic_futures_orderbook(symbol)
        
        if price_data:
            combined_data = {
                **candidate,
                **price_data
            }
            
            # 호가 정보가 있으면 추가
            if orderbook_data:
                combined_data.update({
                    "buy_pressure": orderbook_data.get("buy_pressure_pct", 0),
                    "sell_pressure": orderbook_data.get("sell_pressure_pct", 0),
                    "pressure_signal": orderbook_data.get("pressure_signal", "데이터 없음"),
                    "best_bid": orderbook_data.get("orderbook", {}).get("bid_prices", [0])[0] if orderbook_data.get("orderbook", {}).get("bid_prices") else 0,
                    "best_ask": orderbook_data.get("orderbook", {}).get("ask_prices", [0])[0] if orderbook_data.get("orderbook", {}).get("ask_prices") else 0,
                    "total_bid_quantity": orderbook_data.get("total_bid_quantity", 0),
                    "total_ask_quantity": orderbook_data.get("total_ask_quantity", 0)
                })
            
            candidate_data.append(combined_data)
    
    # 3. 주 계약 선택 (거래량 기준)
    if not candidate_data:
        return None
    
    # 거래량이 가장 높은 월물 선택
    active_contract = max(candidate_data, key=lambda x: x['volume'])
    
    print(f"🎯 주계약 선택: {active_contract['symbol']} (거래량: {active_contract['volume']:,}, 매수압력: {active_contract.get('buy_pressure', 0)}%)")
    
    return active_contract
