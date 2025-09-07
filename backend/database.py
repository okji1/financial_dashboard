"""
데이터베이스 관련 함수들
"""

import datetime
from config import SUPABASE_URL, SUPABASE_KEY, GOLD_DATA_TABLE, ACTIVE_CONTRACT_TABLE, KIS_TOKENS_TABLE
from supabase import create_client, Client

# Supabase 클라이언트 초기화
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase 초기화 실패: {e!r}")
    supabase = None


def get_cached_token():
    """캐시된 KIS 토큰 조회"""
    if not supabase:
        return None
    
    try:
        result = supabase.table(KIS_TOKENS_TABLE).select("*").order("created_at", desc=True).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            token_data = result.data[0]
            created_at = datetime.datetime.fromisoformat(token_data['created_at'].replace('Z', '+00:00'))
            
            # 토큰이 23시간 미만이면 재사용
            if datetime.datetime.now(datetime.timezone.utc) - created_at < datetime.timedelta(hours=23):
                return token_data['access_token']
    except Exception as e:
        print(f"토큰 조회 오류: {e}")
    
    return None


def save_token(access_token):
    """새 토큰 저장"""
    if not supabase or not access_token:
        return False
    
    try:
        supabase.table(KIS_TOKENS_TABLE).insert({
            "access_token": access_token,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }).execute()
        return True
    except Exception as e:
        print(f"토큰 저장 오류: {e}")
        return False


def get_cached_gold_data():
    """캐시된 금 데이터 조회"""
    if not supabase:
        return None
    
    try:
        cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
        
        result = supabase.table(GOLD_DATA_TABLE).select("*").gte("created_at", cutoff_time.isoformat()).order("created_at", desc=True).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
    except Exception as e:
        print(f"캐시된 데이터 조회 오류: {e}")
    
    return None


def save_gold_data(london_data, domestic_data, premium_data):
    """금 데이터 저장"""
    if not supabase:
        return False
    
    try:
        data_to_save = {
            "london_gold_usd": london_data.get('usd_price') if london_data else None,
            "london_gold_krw": london_data.get('krw_price') if london_data else None,
            "exchange_rate": london_data.get('exchange_rate') if london_data else None,
            "domestic_gold_price": domestic_data.get('current_price') if domestic_data else None,
            "domestic_volume": domestic_data.get('volume') if domestic_data else None,
            "domestic_open_interest": domestic_data.get('open_interest') if domestic_data else None,
            "premium_percentage": premium_data.get('premium_percentage') if premium_data else None,
            "absolute_difference": premium_data.get('absolute_difference') if premium_data else None,
            "active_contract": domestic_data.get('symbol') if domestic_data else None,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        supabase.table(GOLD_DATA_TABLE).insert(data_to_save).execute()
        return True
    except Exception as e:
        print(f"데이터 저장 오류: {e}")
        return False


def get_active_contract():
    """활성 계약 조회"""
    if not supabase:
        return None
    
    try:
        cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
        
        result = supabase.table(ACTIVE_CONTRACT_TABLE).select("*").gte("updated_at", cutoff_time.isoformat()).order("updated_at", desc=True).limit(1).execute()

        if result and getattr(result, 'data', None) and len(result.data) > 0:
            return result.data[0]

        # 폴백: 24시간 이내 레코드가 없으면 최신 레코드를 반환
        try:
            fallback = supabase.table(ACTIVE_CONTRACT_TABLE).select("*").order("updated_at", desc=True).limit(1).execute()
            if fallback and getattr(fallback, 'data', None) and len(fallback.data) > 0:
                return fallback.data[0]
        except Exception as e:
            print(f"활성 계약 폴백 조회 오류: {e}")
    except Exception as e:
        print(f"활성 계약 조회 오류: {e}")
    
    return None


def save_active_contract(contract_data):
    """활성 계약 저장"""
    if not supabase or not contract_data:
        return False
    
    try:
        data_to_save = {
            "symbol": contract_data.get('symbol'),
            "description": contract_data.get('description'),
            "current_price": contract_data.get('current_price'),
            "volume": contract_data.get('volume'),
            "open_interest": contract_data.get('open_interest'),
            "expiry_year": contract_data.get('year'),
            "expiry_month": contract_data.get('month'),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        # 가능한 경우 upsert(중복 시 갱신)를 시도합니다. 테이블에 unique constraint(symbol)가 있어야 합니다.
        try:
            res = supabase.table(ACTIVE_CONTRACT_TABLE).upsert(data_to_save, on_conflict='symbol').execute()
            # 일부 supabase 클라이언트는 status_code를 제공하지 않으므로 응답 내용을 확인
            if getattr(res, 'status_code', None) and res.status_code >= 400:
                print(f"활성 계약 upsert 실패: status_code={res.status_code}, response={getattr(res, 'data', None)}")
                # 폴백으로 insert 시도
                ins = supabase.table(ACTIVE_CONTRACT_TABLE).insert(data_to_save).execute()
                if getattr(ins, 'status_code', None) and ins.status_code >= 400:
                    print(f"활성 계약 insert 실패: status_code={ins.status_code}, response={getattr(ins, 'data', None)}")
                    return False
                return True
            return True
        except Exception as upsert_e:
            print(f"활성 계약 upsert 예외: {upsert_e!r} - insert로 재시도합니다.")
            try:
                ins2 = supabase.table(ACTIVE_CONTRACT_TABLE).insert(data_to_save).execute()
                if getattr(ins2, 'status_code', None) and ins2.status_code >= 400:
                    print(f"활성 계약 insert(재시도) 실패: status_code={ins2.status_code}, response={getattr(ins2, 'data', None)}")
                    return False
                return True
            except Exception as ins_e:
                print(f"활성 계약 insert(재시도) 예외: {ins_e!r}")
                return False
    except Exception as e:
        print(f"활성 계약 저장 오류: {e}")
        return False


def cleanup_old_data():
    """오래된 데이터 정리"""
    if not supabase:
        return
    
    try:
        # 7일 이전 데이터 삭제
        cutoff_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
        
        # 금 데이터 정리
        supabase.table(GOLD_DATA_TABLE).delete().lt("created_at", cutoff_time.isoformat()).execute()
        
        # 토큰 데이터 정리 (1일 이전)
        token_cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        supabase.table(KIS_TOKENS_TABLE).delete().lt("created_at", token_cutoff.isoformat()).execute()
        
        print("오래된 데이터 정리 완료")
    except Exception as e:
        print(f"데이터 정리 오류: {e}")
