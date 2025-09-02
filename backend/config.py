"""
설정 파일 - 환경 변수 및 상수 정의
"""

import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# KIS API 설정
KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")

# 환율 API 설정
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")

# Supabase 설정
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# API 엔드포인트
KIS_TOKEN_URL = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
KIS_FUTURES_URL = "https://openapi.koreainvestment.com:9443/uapi/domestic-futureoption/v1/quotations/inquire-price"
NAVER_GOLD_URL = "https://polling.finance.naver.com/api/realtime/domestic/GOLD"
EXCHANGE_RATE_URL = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"

# 네이버 금시세 API URLs (실제 사용)
NAVER_GOLD_INTERNATIONAL_CHART_URL = "https://m.stock.naver.com/front-api/chart/pricesByPeriod?reutersCode=GCcv1&category=metals&chartInfoType=futures&scriptChartType=day"
NAVER_GOLD_INTERNATIONAL_MARKET_URL = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=GCcv1&page=1"
NAVER_GOLD_DOMESTIC_CHART_URL = "https://m.stock.naver.com/front-api/chart/pricesByPeriod?reutersCode=M04020000&category=metals&chartInfoType=gold&scriptChartType=day"
NAVER_GOLD_DOMESTIC_MARKET_URL = "https://m.stock.naver.com/front-api/marketIndex/prices?category=metals&reutersCode=M04020000&page=1"

# 캐시 설정
CACHE_DURATION_MINUTES = 10
ACTIVE_CONTRACT_UPDATE_HOURS = 24

# 데이터베이스 테이블명
GOLD_DATA_TABLE = "gold_prices"
ACTIVE_CONTRACT_TABLE = "active_contracts"
KIS_TOKENS_TABLE = "kis_token"
