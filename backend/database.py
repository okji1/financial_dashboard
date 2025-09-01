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
    print(f"Supabase 초기화 실패: {e}")
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
        
        if result.data and len(result.data) > 0:
            return result.data[0]
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
        
        supabase.table(ACTIVE_CONTRACT_TABLE).insert(data_to_save).execute()
        return True
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
