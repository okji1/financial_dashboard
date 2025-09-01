import os
import requests
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime
from datetime import timezone, timedelta
import threading
import time

# 환경 변수 로드
load_dotenv()

# Flask 앱 초기화
app = Flask(__name__)
CORS(app)

# 환경 변수
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Supabase 클라이언트
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase 초기화 실패: {e}")
    supabase = None

# API 호출 헬퍼
def api_call(url, headers=None, json_data=None):
    try:
        if json_data:
            response = requests.post(url, headers=headers, json=json_data, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"API 호출 실패: {e}")
        return None

# KIS 토큰 관리
def get_kis_token():
    if not supabase:
        return None

    # 기존 토큰 확인
    try:
        response = supabase.table('kis_token').select('*').order('created_at', desc=True).limit(1).execute()
        if response.data:
            token_data = response.data[0]
            created_at = datetime.datetime.fromisoformat(token_data['created_at'])
            if datetime.datetime.now(timezone.utc) - created_at < datetime.timedelta(hours=23):
                return token_data['access_token']
    except Exception:
        pass

    # 새 토큰 발급
    token_data = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }
    
    result = api_call(
        "https://openapi.koreainvestment.com:9443/oauth2/tokenP",
        headers={"content-type": "application/json"},
        json_data=token_data
    )
    
    if result and result.get("access_token"):
        access_token = result["access_token"]
        if supabase:
            try:
                supabase.table('kis_token').insert({
                    'access_token': access_token,
                    'expires_in': result.get('expires_in'),
                }).execute()
            except Exception:
                pass
        return access_token
    return None

# 금 선물 주 계약 자동 선택 시스템
def generate_gold_futures_candidates():
    """Step 1: 금 선물 후보 월물 목록 생성 (GitHub 공식 저장소 기준)"""
    import calendar
    
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
                
                if len(candidates) >= 4:  # 4개 후보면 충분
                    return candidates
        
        year += 1  # 다음 해로
    
    return candidates

def get_domestic_futures_data(symbol):
    """Step 2: 국내 선물 데이터 수집 (KIS API) - GitHub 공식 저장소 기준"""
    access_token = get_kis_token()
    if not access_token:
        print(f"❌ {symbol}: access_token 획득 실패")
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
    url = f"https://openapi.koreainvestment.com:9443/uapi/domestic-futureoption/v1/quotations/inquire-price?{query_string}"
    
    data = api_call(url, headers=headers)
    
    # 디버깅: API 응답 확인
    if data:
        print(f"🔍 {symbol} API 응답:")
        print(f"   rt_cd: {data.get('rt_cd')}")
        print(f"   msg_cd: {data.get('msg_cd')}")
        print(f"   msg1: {data.get('msg1')}")
        
        # 전체 응답 구조 확인
        print(f"   응답 키들: {list(data.keys())}")
        
        if data.get('output1'):
            output1 = data.get('output1', {})
            print(f"   output1 키들: {list(output1.keys()) if isinstance(output1, dict) else 'output1이 dict가 아님'}")
            print(f"   output1 데이터: 현재가={output1.get('futs_prpr')}, 거래량={output1.get('acml_vol')}, 미결제약정={output1.get('hts_otst_stpl_qty')}")
        else:
            print(f"   output1 없음 또는 비어있음")
            
        if data.get('output2'):
            print(f"   output2 존재")
        if data.get('output3'):
            print(f"   output3 존재")
    else:
        print(f"❌ {symbol}: API 응답 없음")
    
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
    print(f"🔍 금 선물 후보 월물: {[c['symbol'] for c in candidates]}")
    
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
            print(f"📊 {symbol}: 거래량 {data['volume']:,}, 미결제약정 {data['open_interest']:,}")
        else:
            print(f"❌ {symbol}: 데이터 조회 실패")
    
    # 3. 주 계약 선택 (거래량 기준)
    if not candidate_data:
        return None
    
    # 거래량이 가장 높은 월물 선택
    active_contract = max(candidate_data, key=lambda x: x['volume'])
    
    print(f"🎯 주 계약 선택: {active_contract['symbol']} (거래량: {active_contract['volume']:,})")
    
    return active_contract

def save_active_contract(contract_data):
    """Step 4: 주 계약 정보 DB 저장"""
    if not supabase or not contract_data:
        return False
    
    try:
        # 기존 주 계약 정보 삭제
        supabase.table('active_gold_contract').delete().execute()
        
        # 새로운 주 계약 정보 저장
        supabase.table('active_gold_contract').insert({
            'symbol': contract_data['symbol'],
            'description': contract_data['description'],
            'current_price': contract_data['current_price'],
            'volume': contract_data['volume'],
            'open_interest': contract_data['open_interest'],
            'change_rate': contract_data['change_rate'],
            'expiry_date': contract_data['expiry_date'].isoformat(),
            'selected_at': datetime.datetime.now(timezone.utc).isoformat()
        }).execute()
        
        print(f"✅ 주 계약 정보 DB 저장 완료: {contract_data['symbol']}")
        return True
        
    except Exception as e:
        print(f"❌ DB 저장 오류: {e}")
        return False

def get_current_active_contract():
    """현재 설정된 주 계약 조회"""
    if not supabase:
        return None
    
    try:
        response = supabase.table('active_gold_contract').select('*').order('selected_at', desc=True).limit(1).execute()
        if response.data:
            return response.data[0]
    except Exception:
        pass
    
    return None

def update_active_contract_daily():
    """일일 주 계약 업데이트 (스케줄러용)"""
    print("🔄 일일 주 계약 업데이트 시작")
    
    # 주 계약 자동 선택
    active_contract = find_active_gold_contract()
    
    if active_contract:
        # DB에 저장
        save_active_contract(active_contract)
        
        # 기존 분석에도 업데이트
        analyze_gold_futures_with_active_contract(active_contract)
        
        return active_contract
    else:
        print("❌ 주 계약 선택 실패")
        return None

def analyze_gold_futures_with_active_contract(active_contract=None):
    """주 계약 기반 금 선물 분석"""
    if not active_contract:
        active_contract = get_current_active_contract()
    
    if not active_contract:
        print("⚠️ 활성 계약이 없습니다. 주 계약 선택을 먼저 실행하세요.")
        return None
    
    symbol = active_contract['symbol']
    current_data = get_domestic_futures_data(symbol)
    
    if not current_data:
        return None
    
    # 시장 분석
    volume = current_data['volume']
    open_interest = current_data['open_interest']
    change_rate = current_data['change_rate']
    
    # 시장 활성도 분석
    if volume > 10000:  # 높은 거래량
        market_activity = "활발"
        activity_score = 80
    elif volume > 5000:  # 보통 거래량
        market_activity = "보통"
        activity_score = 60
    else:  # 낮은 거래량
        market_activity = "저조"
        activity_score = 40
    
    # 가격 동향 분석
    if change_rate > 2:
        price_trend = "강한 상승"
        trend_score = 80
    elif change_rate > 0:
        price_trend = "상승"
        trend_score = 60
    elif change_rate < -2:
        price_trend = "강한 하락"
        trend_score = 20
    elif change_rate < 0:
        price_trend = "하락"
        trend_score = 40
    else:
        price_trend = "보합"
        trend_score = 50
    
    return {
        "active_contract": active_contract,
        "current_data": current_data,
        "analysis": {
            "market_activity": market_activity,
            "activity_score": activity_score,
            "price_trend": price_trend,
            "trend_score": trend_score,
            "combined_score": (activity_score + trend_score) / 2
        }
    }

# 금 선물 데이터 조회 (국내 주 계약 기반)
def get_gold_futures_data():
    """현재 주 계약 기반 금 선물 데이터 조회"""
    
    # 현재 설정된 주 계약 조회
    active_contract = get_current_active_contract()
    
    if not active_contract:
        # 주 계약이 없으면 자동 선택 실행
        print("⚠️ 주 계약이 설정되지 않음. 자동 선택을 실행합니다.")
        active_contract = update_active_contract_daily()
        
        if not active_contract:
            return None
    
    # 주 계약의 실시간 데이터 조회
    symbol = active_contract['symbol']
    current_data = get_domestic_futures_data(symbol)
    
    if current_data:
        return {
            **current_data,
            "contract_info": {
                "description": active_contract['description'],
                "expiry_date": active_contract['expiry_date'],
                "selected_at": active_contract['selected_at']
            }
        }
    
    return None

def get_gold_options_data():
    """금 옵션 데이터로 풋/콜 비율 분석 (국내 옵션 기반)"""
    access_token = get_kis_token()
    if not access_token:
        return None
    
    # 현재 주 계약 기반 옵션 심볼 생성
    active_contract = get_current_active_contract()
    if not active_contract:
        return None
    
    base_symbol = active_contract['symbol']  # 예: GCZ25
    
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST01030300",  # 국내옵션 시세 조회
        "custtype": "P"
    }
    
    # 금 옵션 전광판 조회 (콜/풋 옵션 종합)
    call_volume = 0
    put_volume = 0
    
    # 옵션 전광판 API 호출
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",  # 옵션시장
        "FID_INPUT_ISCD": base_symbol[:2],  # GC (금 선물 기초자산)
        "FID_PRC_CLS_CODE": "0"  # 전체
    }
    
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"https://openapi.koreainvestment.com:9443/uapi/domestic-futureoption/v1/quotations/inquire-option-price?{query_string}"
    
    data = api_call(url, headers=headers)
    
    if data and data.get('rt_cd') == '0' and data.get('output'):
        output_list = data.get('output', [])
        
        for item in output_list:
            volume = int(item.get('acml_vol', 0))
            option_type = item.get('optn_type', '')  # 'C' = Call, 'P' = Put
            
            if option_type == 'C':  # Call 옵션
                call_volume += volume
            elif option_type == 'P':  # Put 옵션
                put_volume += volume
    
    # 풋/콜 비율 계산
    if call_volume > 0:
        put_call_ratio = put_volume / call_volume
    else:
        put_call_ratio = 0
    
    # 시장 심리 분석
    if put_call_ratio > 1.5:
        market_sentiment = "극도의 공포"
    elif put_call_ratio > 1.2:
        market_sentiment = "공포"
    elif put_call_ratio < 0.5:
        market_sentiment = "극도의 탐욕"
    elif put_call_ratio < 0.8:
        market_sentiment = "탐욕"
    else:
        market_sentiment = "중립"
    
    return {
        "call_volume": call_volume,
        "put_volume": put_volume,
        "put_call_ratio": put_call_ratio,
        "market_sentiment": market_sentiment,
        "base_contract": base_symbol
    }

def analyze_fear_greed_index():
    """시장 공포-탐욕 지수 분석"""
    futures_data = get_gold_futures_data()
    options_data = get_gold_options_data()
    
    if not futures_data or not options_data:
        return None
    
    # 공포-탐욕 지수 계산 로직
    fear_greed_score = 50  # 기본값 (중립)
    
    # 1. 풋/콜 비율 기반 점수 (40% 가중치)
    put_call_ratio = options_data['put_call_ratio']
    if put_call_ratio > 1.5:  # 극도의 공포
        fear_greed_score += -30
    elif put_call_ratio > 1.2:  # 공포
        fear_greed_score += -15
    elif put_call_ratio < 0.5:  # 극도의 탐욕
        fear_greed_score += 30
    elif put_call_ratio < 0.8:  # 탐욕
        fear_greed_score += 15
    
    # 2. 가격 변동률 기반 점수 (30% 가중치)
    change_rate = futures_data['change_rate']
    if change_rate > 3:  # 급등
        fear_greed_score += 20
    elif change_rate > 1:  # 상승
        fear_greed_score += 10
    elif change_rate < -3:  # 급락
        fear_greed_score += -20
    elif change_rate < -1:  # 하락
        fear_greed_score += -10
    
    # 3. 거래량 기반 점수 (30% 가중치)
    volume = futures_data['volume']
    # 거래량이 평균보다 높으면 관심도 증가
    if volume > 100000:  # 예시 임계값
        fear_greed_score += 10
    elif volume < 50000:
        fear_greed_score += -5
    
    # 점수를 0-100 범위로 조정
    fear_greed_score = max(0, min(100, fear_greed_score))
    
    # 등급 분류
    if fear_greed_score >= 80:
        grade = "극도의 탐욕"
    elif fear_greed_score >= 60:
        grade = "탐욕"
    elif fear_greed_score >= 40:
        grade = "중립"
    elif fear_greed_score >= 20:
        grade = "공포"
    else:
        grade = "극도의 공포"
    
    return {
        "fear_greed_score": fear_greed_score,
        "grade": grade,
        "put_call_ratio": put_call_ratio,
        "price_change": change_rate,
        "volume": volume,
        "open_interest": futures_data['open_interest']
    }

# 금시세 조회
def get_gold_prices():
    """수정된 금 시세 조회 함수 - API 응답 구조 변경 대응"""
    
    # 국제 금시세 (chart API)
    intl_data = api_call("https://m.stock.naver.com/front-api/chart/pricesByPeriod?reutersCode=GCcv1&category=metals&chartInfoType=futures&scriptChartType=day")
    international_price = None
    
    if intl_data and intl_data.get('result') and intl_data['result'].get('priceInfos'):
        # result 안의 priceInfos에서 최신 데이터 가져오기
        price_infos = intl_data['result']['priceInfos']
        if price_infos:
            latest = price_infos[-1]
            current_price = latest.get('currentPrice')
            if current_price:
                # 쉼표 제거 후 float 변환
                international_price = float(str(current_price).replace(',', ''))
    
    # 백업: marketIndex API 사용
    if not international_price:
        intl_backup = api_call("https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=GCcv1&page=1")
        if intl_backup and intl_backup.get('result'):
            close_price = intl_backup['result'].get('closePrice')
            if close_price:
                international_price = float(str(close_price).replace(',', ''))
    
    # 국내 금시세 (chart API)
    domestic_data = api_call("https://m.stock.naver.com/front-api/chart/pricesByPeriod?reutersCode=M04020000&category=metals&chartInfoType=gold&scriptChartType=day")
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
        domestic_backup = api_call("https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000&page=1")
        if domestic_backup and domestic_backup.get('result'):
            close_price = domestic_backup['result'].get('closePrice')
            if close_price:
                domestic_price = float(str(close_price).replace(',', ''))
    
    # 환율 조회 (여러 날짜 시도)
    usd_krw_rate = None
    for i in range(5):
        date = (datetime.date.today() - timedelta(days=i)).strftime('%Y%m%d')
        exchange_data = api_call(f"https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON?authkey={EXCHANGE_RATE_API_KEY}&searchdate={date}&data=AP01")
        
        if exchange_data and isinstance(exchange_data, list):
            for item in exchange_data:
                if item.get('cur_unit') == 'USD':
                    usd_krw_rate = float(item['deal_bas_r'].replace(',', ''))
                    break
            if usd_krw_rate:
                break
    
    # 결과 검증
    if not all([international_price, domestic_price, usd_krw_rate]):
        missing = []
        if not international_price: missing.append("국제 금시세")
        if not domestic_price: missing.append("국내 금시세")
        if not usd_krw_rate: missing.append("환율")
        return {"error": f"데이터 조회 실패: {', '.join(missing)}"}
    
    # 프리미엄 계산
    intl_price_krw_g = (international_price / 31.1035) * usd_krw_rate
    premium = ((domestic_price - intl_price_krw_g) / intl_price_krw_g) * 100
    
    return {
        "international_price_usd_oz": international_price,
        "domestic_price_krw_g": domestic_price,
        "usd_krw_rate": usd_krw_rate,
        "converted_intl_price_krw_g": intl_price_krw_g,
        "premium_percentage": premium,
        "last_updated": datetime.datetime.now(timezone.utc).isoformat()
    }

# 투자전략 업데이트
def update_strategy():
    if not supabase:
        return False

    # 10분 이내 업데이트 체크
    try:
        response = supabase.table('investment_strategies').select('created_at').order('created_at', desc=True).limit(1).execute()
        if response.data:
            last_update = datetime.datetime.fromisoformat(response.data[0]['created_at'])
            if (datetime.datetime.now(timezone.utc) - last_update).total_seconds() <= 600:
                return False
    except Exception:
        pass

    # KIS 토큰 발급
    access_token = get_kis_token()
    if not access_token:
        return False

    # 확장된 종목 데이터 수집
    headers = {
        "authorization": f"Bearer {access_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST01010100",
        "custtype": "P"
    }

    # 한국 ETF 분석 대상
    etf_symbols = {
        "132030": "KODEX 골드선물(H)",        # 금
        "229200": "KODEX 미국달러선물(H)",     # 달러
        "411060": "KODEX 미국채울트라30년선물(H)",  # 30년 국채
        "371160": "KODEX 미국물가연동국채10년(H)",  # 물가연동채
        "252670": "KODEX 200선물인버스2X"      # 리스크 자산
    }

    results = []
    for symbol, name in etf_symbols.items():
        url = f"https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD={symbol}"
        data = api_call(url, headers=headers)

        if data and data.get('rt_cd') == '0' and data.get('output'):
            output = data['output']
            change_rate = float(output.get('prdy_ctrt', 0))
            current_price = float(output.get('stck_prpr', 0))
            volume = int(output.get('acml_vol', 0))
            
            results.append({
                "symbol": symbol,
                "name": name,
                "current_price": current_price,
                "volume": volume,
                "change_rate": change_rate,
                "category": get_etf_category(symbol)
            })

    if not results:
        return False

    # 글로벌 금 선물 데이터 추가
    gold_futures = get_gold_futures_data()
    fear_greed = analyze_fear_greed_index()

    # 상관관계 분석
    correlation_analysis = analyze_correlations(results)
    
    # 종합 투자 신호 생성
    investment_signal = generate_investment_signal(results, gold_futures, fear_greed, correlation_analysis)

    # DB 저장
    try:
        supabase.table('investment_strategies').insert({
            'market_condition': investment_signal['condition'],
            'recommended_strategy': investment_signal['strategy'],
            'signal_strength': investment_signal['strength'],
            'fear_greed_index': fear_greed['fear_greed_score'] if fear_greed else 50,
            'correlation_analysis': correlation_analysis,
            'domestic_etf_analysis': results,
            'global_futures_data': gold_futures,
            'detailed_analysis': {
                'domestic_sentiment': correlation_analysis,
                'global_sentiment': fear_greed,
                'put_call_ratio': fear_greed['put_call_ratio'] if fear_greed else 0
            }
        }).execute()

        # 오래된 데이터 정리
        all_data = supabase.table('investment_strategies').select('id').order('created_at', desc=False).execute()
        if len(all_data.data) > 10:
            for old_item in all_data.data[:-10]:
                supabase.table('investment_strategies').delete().eq('id', old_item['id']).execute()

        return True
    except Exception as e:
        print(f"DB 저장 오류: {e}")
        return False

def get_etf_category(symbol):
    """ETF 카테고리 분류"""
    categories = {
        "132030": "gold",
        "229200": "usd", 
        "411060": "bond_30y",
        "371160": "tips",
        "252670": "risk"
    }
    return categories.get(symbol, "unknown")

def analyze_correlations(etf_data):
    """상관관계 분석"""
    if len(etf_data) < 2:
        return {}
    
    # 각 ETF의 변동률 추출
    changes = {item['category']: item['change_rate'] for item in etf_data}
    
    gold_change = changes.get('gold', 0)
    usd_change = changes.get('usd', 0)
    bond_change = changes.get('bond_30y', 0)
    tips_change = changes.get('tips', 0)
    risk_change = changes.get('risk', 0)
    
    # 상관관계 점수 계산 (단순화된 버전)
    correlations = {
        "gold_vs_usd": -1 if (gold_change > 0 and usd_change < 0) or (gold_change < 0 and usd_change > 0) else 1,
        "gold_vs_real_rate": -1 if (gold_change > 0 and (bond_change - tips_change) < 0) else 1,
        "gold_vs_risk": 1 if (gold_change > 0 and risk_change < 0) or (gold_change < 0 and risk_change > 0) else -1
    }
    
    # 국내 투자심리 점수
    domestic_sentiment = (
        abs(gold_change) * 0.4 +  # 금에 대한 관심도
        abs(usd_change) * 0.2 +   # 달러에 대한 관심도
        abs(risk_change) * 0.4    # 리스크 자산에 대한 관심도
    )
    
    return {
        "correlations": correlations,
        "domestic_sentiment_score": domestic_sentiment,
        "dominant_trend": "risk_on" if risk_change > 0 else "risk_off" if risk_change < -1 else "neutral"
    }

def generate_investment_signal(etf_data, gold_futures, fear_greed, correlation_analysis):
    """종합 투자 신호 생성"""
    
    # 점수 계산 (100점 만점)
    total_score = 50  # 기본 중립
    
    # 1. 공포-탐욕 지수 (30% 가중치)
    if fear_greed:
        fg_score = fear_greed['fear_greed_score']
        if fg_score >= 80:
            total_score += 15  # 극도의 탐욕 -> 매수 신호
        elif fg_score >= 60:
            total_score += 10
        elif fg_score <= 20:
            total_score -= 15  # 극도의 공포 -> 더 큰 매수 신호
        elif fg_score <= 40:
            total_score -= 10
    
    # 2. 국내 ETF 트렌드 (40% 가중치)
    gold_etf = next((item for item in etf_data if item['category'] == 'gold'), None)
    if gold_etf:
        gold_change = gold_etf['change_rate']
        if gold_change > 2:
            total_score += 20
        elif gold_change > 0:
            total_score += 10
        elif gold_change < -2:
            total_score -= 20
        elif gold_change < 0:
            total_score -= 10
    
    # 3. 상관관계 분석 (30% 가중치)
    if correlation_analysis:
        dominant_trend = correlation_analysis.get('dominant_trend', 'neutral')
        if dominant_trend == 'risk_off':  # 리스크 오프 -> 금 선호
            total_score += 15
        elif dominant_trend == 'risk_on':  # 리스크 온 -> 금 회피
            total_score -= 10
    
    # 점수를 0-100 범위로 조정
    total_score = max(0, min(100, total_score))
    
    # 신호 분류
    if total_score >= 80:
        condition, strategy, strength = "강력 매수", "적극적 매수 포지션", "매우 강함"
    elif total_score >= 65:
        condition, strategy, strength = "매수 고려", "점진적 매수 포지션", "강함"
    elif total_score >= 35:
        condition, strategy, strength = "중립", "관망 및 리밸런싱", "보통"
    elif total_score >= 20:
        condition, strategy, strength = "주의", "포지션 축소 고려", "약함"
    else:
        condition, strategy, strength = "강력 매도", "포지션 정리", "매우 약함"
    
    return {
        "condition": condition,
        "strategy": strategy,
        "strength": strength,
        "score": total_score
    }

# COT 리포트 분석
def get_cot_data():
    """COT(Commitment of Traders) 리포트 데이터 분석"""
    try:
        # 실제 COT 라이브러리 사용
        from cot_reports import cot_year
        import pandas as pd
        
        # 최신 COT 데이터 가져오기 (2025년)
        current_year = datetime.datetime.now().year
        cot_data = cot_year(year=current_year, cot_report_type='legacy_fut')
        
        # 금 관련 데이터 필터링
        gold_data = cot_data[cot_data['Market_and_Exchange_Names'].str.contains('GOLD', case=False, na=False)]
        
        if gold_data.empty:
            # 데이터가 없으면 더미 데이터 사용
            return get_dummy_cot_data()
        
        # 최신 데이터 가져오기
        latest_data = gold_data.iloc[-1]
        
        cot_info = {
            "commercial_long": int(latest_data.get('Commercial_Long', 0)),
            "commercial_short": int(latest_data.get('Commercial_Short', 0)),
            "large_spec_long": int(latest_data.get('Large_Spec_Long', 0)),
            "large_spec_short": int(latest_data.get('Large_Spec_Short', 0)),
            "small_spec_long": int(latest_data.get('Small_Spec_Long', 0)),
            "small_spec_short": int(latest_data.get('Small_Spec_Short', 0)),
            "report_date": str(latest_data.get('Report_Date_as_MM_DD_YYYY', ''))
        }
        
        return analyze_cot_positions(cot_info)
        
    except Exception as e:
        print(f"COT 데이터 조회 오류: {e}")
        # 오류 시 더미 데이터 반환
        return get_dummy_cot_data()

def get_dummy_cot_data():
    """COT 더미 데이터 (라이브러리 오류 시 사용)"""
    cot_data = {
        "commercial_long": 250000,
        "commercial_short": 180000,
        "large_spec_long": 120000,
        "large_spec_short": 95000,
        "small_spec_long": 45000,
        "small_spec_short": 65000,
        "report_date": datetime.datetime.now().strftime('%m/%d/%Y')
    }
    return analyze_cot_positions(cot_data)

def analyze_cot_positions(cot_data):
    """COT 포지션 분석"""
    if not cot_data:
        return None
    
    # 상업 참여자 (스마트 머니) 분석
    commercial_net = cot_data['commercial_long'] - cot_data['commercial_short']
    commercial_ratio = commercial_net / (cot_data['commercial_long'] + cot_data['commercial_short'])
    
    # 소형 투기자 (개미) 분석  
    small_spec_net = cot_data['small_spec_long'] - cot_data['small_spec_short']
    small_spec_ratio = small_spec_net / (cot_data['small_spec_long'] + cot_data['small_spec_short'])
    
    # 대형 투기자 분석
    large_spec_net = cot_data['large_spec_long'] - cot_data['large_spec_short']
    large_spec_ratio = large_spec_net / (cot_data['large_spec_long'] + cot_data['large_spec_short'])
    
    # 스마트 머니 신호 (상업 참여자 기준)
    if commercial_ratio > 0.15:  # 상업 참여자가 강한 롱 포지션
        smart_money_signal = "강력 매수"
        smart_money_score = 80
    elif commercial_ratio > 0.05:
        smart_money_signal = "매수"
        smart_money_score = 65
    elif commercial_ratio < -0.15:  # 상업 참여자가 강한 숏 포지션
        smart_money_signal = "강력 매도"
        smart_money_score = 20
    elif commercial_ratio < -0.05:
        smart_money_signal = "매도"
        smart_money_score = 35
    else:
        smart_money_signal = "중립"
        smart_money_score = 50
    
    # 개미 역발상 신호 (소형 투기자 역방향)
    if small_spec_ratio > 0.2:  # 개미가 과도하게 낙관적
        contrarian_signal = "매도 고려"  # 역발상
        contrarian_score = 30
    elif small_spec_ratio < -0.2:  # 개미가 과도하게 비관적
        contrarian_signal = "매수 고려"  # 역발상
        contrarian_score = 70
    else:
        contrarian_signal = "중립"
        contrarian_score = 50
    
    return {
        "commercial_analysis": {
            "net_position": commercial_net,
            "position_ratio": commercial_ratio,
            "signal": smart_money_signal,
            "score": smart_money_score
        },
        "retail_analysis": {
            "net_position": small_spec_net,
            "position_ratio": small_spec_ratio,
            "contrarian_signal": contrarian_signal,
            "contrarian_score": contrarian_score
        },
        "institutional_analysis": {
            "net_position": large_spec_net,
            "position_ratio": large_spec_ratio
        },
        "overall_sentiment": {
            "smart_money_score": smart_money_score,
            "contrarian_score": contrarian_score,
            "combined_score": (smart_money_score + contrarian_score) / 2
        },
        "report_date": cot_data['report_date']
    }

# API Routes
@app.route('/')
@app.route('/api')
def health():
    return jsonify({"status": "ok", "message": "Financial Dashboard API"})

@app.route('/api/gold-premium')
def gold_premium():
    result = get_gold_prices()
    if "error" in result:
        return jsonify(result), 500
    return jsonify({**result, "message": "금시세 조회 완료"})

@app.route('/api/investment-strategy')
def investment_strategy():
    if not supabase:
        return jsonify({"error": "Database unavailable"}), 500

    # 업데이트 시도
    update_strategy()

    # 최신 데이터 조회
    try:
        response = supabase.table('investment_strategies').select('*').order('created_at', desc=True).limit(1).execute()
        if not response.data:
            return jsonify({"error": "전략 데이터 없음"}), 404

        data = response.data[0]
        return jsonify({
            "market_condition": data.get('market_condition'),
            "recommended_strategy": data.get('recommended_strategy'),
            "supporting_data": {
                "average_change_rate": data.get('average_change_rate', 0),
                "total_volume": data.get('total_volume', 0),
                "analyzed_symbols": data.get('analyzed_symbols', 0)
            },
            "detailed_analysis": data.get('detailed_analysis', []),
            "analysis_time": data.get('created_at'),
            "message": "투자전략 분석 완료"
        })
    except Exception as e:
        return jsonify({"error": f"조회 오류: {e}"}), 500

@app.route('/api/gold-analysis')
def gold_analysis():
    """종합 금 투자 분석 API"""
    try:
        # 1. 글로벌 금 선물 데이터
        gold_futures = get_gold_futures_data()
        
        # 2. 공포-탐욕 지수
        fear_greed = analyze_fear_greed_index()
        
        # 3. COT 리포트 분석
        cot_analysis = get_cot_data()
        
        # 4. 한국 ETF 데이터 (최신)
        if supabase:
            response = supabase.table('investment_strategies').select('*').order('created_at', desc=True).limit(1).execute()
            domestic_data = response.data[0] if response.data else None
        else:
            domestic_data = None
        
        # 종합 분석 결과
        return jsonify({
            "global_analysis": {
                "gold_futures": gold_futures,
                "fear_greed_index": fear_greed,
                "cot_report": cot_analysis
            },
            "domestic_analysis": {
                "etf_data": domestic_data.get('domestic_etf_analysis', []) if domestic_data else [],
                "correlation_analysis": domestic_data.get('correlation_analysis', {}) if domestic_data else {},
                "domestic_sentiment": domestic_data.get('detailed_analysis', {}).get('domestic_sentiment', {}) if domestic_data else {}
            },
            "investment_recommendation": {
                "overall_signal": domestic_data.get('market_condition', '데이터 없음') if domestic_data else '데이터 없음',
                "strategy": domestic_data.get('recommended_strategy', '분석 중') if domestic_data else '분석 중',
                "confidence": domestic_data.get('signal_strength', '보통') if domestic_data else '보통',
                "fear_greed_score": fear_greed.get('fear_greed_score', 50) if fear_greed else 50,
                "smart_money_score": cot_analysis.get('overall_sentiment', {}).get('smart_money_score', 50) if cot_analysis else 50,
                "contrarian_score": cot_analysis.get('overall_sentiment', {}).get('contrarian_score', 50) if cot_analysis else 50
            },
            "last_updated": datetime.datetime.now(timezone.utc).isoformat(),
            "message": "종합 금 투자 분석 완료"
        })
        
    except Exception as e:
        return jsonify({"error": f"분석 오류: {e}"}), 500

@app.route('/api/fear-greed')
def fear_greed_api():
    """공포-탐욕 지수 API"""
    try:
        fear_greed = analyze_fear_greed_index()
        if fear_greed:
            return jsonify({**fear_greed, "message": "공포-탐욕 지수 분석 완료"})
        else:
            return jsonify({"error": "공포-탐욕 지수 계산 실패"}), 500
    except Exception as e:
        return jsonify({"error": f"오류: {e}"}), 500

@app.route('/api/cot-report')
def cot_report_api():
    """COT 리포트 API"""
    try:
        cot_data = get_cot_data()
        if cot_data:
            return jsonify({**cot_data, "message": "COT 리포트 분석 완료"})
        else:
            return jsonify({"error": "COT 데이터 조회 실패"}), 500
    except Exception as e:
        return jsonify({"error": f"오류: {e}"}), 500

@app.route('/api/domestic-etf')
def domestic_etf_api():
    """국내 ETF 분석 API"""
    try:
        if not supabase:
            return jsonify({"error": "Database unavailable"}), 500
        
        # 최신 국내 ETF 분석 데이터 조회
        response = supabase.table('investment_strategies').select('*').order('created_at', desc=True).limit(1).execute()
        
        if not response.data:
            return jsonify({"error": "ETF 분석 데이터 없음"}), 404
        
        data = response.data[0]
        
        return jsonify({
            "etf_analysis": data.get('domestic_etf_analysis', []),
            "correlation_analysis": data.get('correlation_analysis', {}),
            "market_sentiment": data.get('detailed_analysis', {}).get('domestic_sentiment', {}),
            "analysis_time": data.get('created_at'),
            "message": "국내 ETF 분석 완료"
        })
        
    except Exception as e:
        return jsonify({"error": f"조회 오류: {e}"}), 500

# 백그라운드 업데이터
def background_updater():
    while True:
        try:
            update_strategy()
            # 매일 새벽 3시에 주 계약 업데이트 (임시로 10분마다)
            update_active_contract_daily()
        except Exception:
            pass
        time.sleep(600)

@app.route('/api/active-contract')
def active_contract_api():
    """주 계약 정보 API"""
    try:
        active_contract = get_current_active_contract()
        
        if not active_contract:
            # 주 계약이 없으면 자동 선택 실행
            active_contract = update_active_contract_daily()
            
            if not active_contract:
                return jsonify({"error": "주 계약 선택 실패"}), 500
        
        # 실시간 데이터 추가
        current_data = get_domestic_futures_data(active_contract['symbol'])
        
        return jsonify({
            "active_contract": active_contract,
            "real_time_data": current_data,
            "message": "주 계약 정보 조회 완료"
        })
        
    except Exception as e:
        return jsonify({"error": f"오류: {e}"}), 500

@app.route('/api/update-active-contract')
def update_active_contract_api():
    """주 계약 업데이트 API (수동 실행)"""
    try:
        new_active_contract = update_active_contract_daily()
        
        if new_active_contract:
            return jsonify({
                "success": True,
                "new_active_contract": new_active_contract,
                "message": "주 계약 업데이트 완료"
            })
        else:
            return jsonify({"error": "주 계약 업데이트 실패"}), 500
            
    except Exception as e:
        return jsonify({"error": f"오류: {e}"}), 500

@app.route('/api/futures-candidates')
def futures_candidates_api():
    """금 선물 후보 월물 조회 API"""
    try:
        candidates = generate_gold_futures_candidates()
        
        # 각 후보의 데이터도 함께 조회
        candidates_with_data = []
        for candidate in candidates:
            data = get_domestic_futures_data(candidate['symbol'])
            candidates_with_data.append({
                **candidate,
                "market_data": data
            })
        
        return jsonify({
            "candidates": candidates_with_data,
            "total_count": len(candidates_with_data),
            "message": "금 선물 후보 월물 조회 완료"
        })
        
    except Exception as e:
        return jsonify({"error": f"오류: {e}"}), 500

if __name__ == '__main__':
    # 백그라운드 스레드 시작
    threading.Thread(target=background_updater, daemon=True).start()
    app.run()
