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
    """Step 2: 국내 선물 데이터 수집 (KIS API) - GitHub 공식 저장소 기준"""
    access_token = get_kis_token()
    if not access_token:
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
    
    data = api_call(url, headers=headers)
    
    if data and data.get('rt_cd') == '0' and data.get('output1'):
        output1 = data.get('output1', {})
        # 선물 데이터가 실제로 있는지 확인 (거래량 체크)
        volume = int(output1.get('acml_vol', 0))
        if volume > 0:  # 거래량이 있는 경우만 유효한 데이터로 간주
            return {
                "symbol": symbol,
                "current_price": float(output1.get('futs_prpr', 0)),         # 선물현재가
                "volume": volume,                                            # 총거래량
                "open_interest": int(output1.get('hts_otst_stpl_qty', 0)),   # 미결제약정
                "change_rate": float(output1.get('futs_prdy_ctrt', 0)),      # 전일대비율
                "high": float(output1.get('futs_hgpr', 0)),                  # 고가
                "low": float(output1.get('futs_lwpr', 0))                    # 저가
            }
    return None


def find_active_gold_contract():
    """Step 3: 주 계약(Active Contract) 자동 선택"""
    
    # 1. 후보 월물 생성
    candidates = generate_gold_futures_candidates()
    
    # 2. 각 후보의 데이터 수집
    candidate_data = []
    for candidate in candidates:
        symbol = candidate['symbol']
        data = get_domestic_futures_data(symbol)
        
        if data:
            candidate_data.append({
                **candidate,
                **data
            })
    
    # 3. 주 계약 선택 (거래량 기준)
    if not candidate_data:
        return None
    
    # 거래량이 가장 높은 월물 선택
    active_contract = max(candidate_data, key=lambda x: x['volume'])
    
    return active_contract
