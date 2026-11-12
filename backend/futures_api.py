"""
선물 관련 API 함수들
"""

import datetime
from api_utils import get_kis_token, api_call
from config import KIS_APP_KEY, KIS_APP_SECRET, KIS_FUTURES_URL


def generate_gold_futures_candidates():
    """Step 1: 금 선물 후보 월물 목록 생성 (GitHub 공식 저장소 기준)"""
    current_date = datetime.date.today()
    current_year = current_date.year
    current_month = current_date.month
    
    # 주요 월물: 짝수 달 + 12월 (2, 4, 6, 8, 10, 12)
    major_months = [2, 4, 6, 8, 10, 12]
    
    candidates = []
    
    # 현재 월 이후의 가장 가까운 주요 월물부터 4개 생성
    year = current_year
    for i in range(8):  # 넉넉하게 8개월까지 체크
        for month in major_months:
            candidate_date = datetime.date(year, month, 1)
            
            # 현재 날짜 이후의 월물만 선택
            if candidate_date > current_date:
                # GitHub 예시 형식: 101W09 (금선물 + 연도코드 + 월코드)
                # 101 = 금선물, W = 2025년, 09 = 9월
                year_code = chr(ord('W') + (year - 2025))  # W(2025), X(2026), Y(2027)...
                month_code = f"{month:02d}"                # 02, 04, 06, 08, 10, 12
                symbol = f"101{year_code}{month_code}"     # 101W10
                
                candidates.append({
                    "symbol": symbol,
                    "year": year,
                    "month": month,
                    "expiry_date": candidate_date,
                    "description": f"{year}년 {month}월물"
                })
                
                if len(candidates) >= 4:  # 4개까지만
                    return candidates
        
        year += 1
        if year > current_year + 2:  # 최대 2년 후까지만
            break
    
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
    
    # 파라미터 설정 (GitHub 공식 저장소 기준)
    params = {
        "FID_COND_MRKT_DIV_CODE": "F",  # F: 지수선물, O: 지수옵션
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
            'fid_cond_mrkt_div_code': 'F',  # F: 지수선물 (CF가 아님!)
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
                    buy_pressure = sell_pressure = 50.0
                
                # 압력 강도 분석
                pressure_ratio = total_bid_quantity / total_ask_quantity if total_ask_quantity > 0 else 1.0
                
                if pressure_ratio > 1.2:
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
                    "buy_pressure_pct": round(buy_pressure, 2),
                    "sell_pressure_pct": round(sell_pressure, 2),
                    "pressure_ratio": round(pressure_ratio, 3),
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
    
    # 1. 후보 월물 생성
    candidates = generate_gold_futures_candidates()
    
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
