"""FastAPI query process. No collector threads or provider calls on requests."""
import logging
import time
from functools import lru_cache
from typing import Annotated
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from api_models import Premium, Strategy, Candidates, ActiveContract, Pressure, Analysis, Orderbook, Update, TokenStatus, KRXGoldDaily
from dashboard_service import DashboardService, ServiceError
from shared_store import SharedStore, StoreUnavailable, utc_now

logger = logging.getLogger(__name__)
api = FastAPI(title='Financial Dashboard API', version='2.0.0')


@lru_cache(maxsize=1)
def get_store():
    return SharedStore(read_cache_seconds=15)


def get_service(store=Depends(get_store)):
    return DashboardService(store)


@api.middleware('http')
async def timing(request: Request, call_next):
    started = time.monotonic()
    response = await call_next(request)
    milliseconds = (time.monotonic() - started) * 1000
    response.headers['Server-Timing'] = f'app;dur={milliseconds:.1f}'
    logger.info('request_timing method=%s path=%s status=%s duration_ms=%.1f',
                request.method, request.url.path, response.status_code, milliseconds)
    return response


@api.exception_handler(ServiceError)
async def service_error(request, error):
    return JSONResponse({'error': error.message}, status_code=error.status)


@api.exception_handler(StoreUnavailable)
async def store_error(request, error):
    return JSONResponse({'error': '시세 저장소를 일시적으로 사용할 수 없습니다'}, status_code=503)


@api.exception_handler(RequestValidationError)
async def request_error(request, error):
    return JSONResponse({'error': '잘못된 요청입니다'}, status_code=422)


@api.exception_handler(ResponseValidationError)
async def response_error(request, error):
    logger.error('response_contract_validation_failed path=%s', request.url.path)
    return JSONResponse({'error': '시세 응답 형식이 올바르지 않습니다'}, status_code=502)


@api.exception_handler(Exception)
async def unexpected_error(request, error):
    logger.error('request_failed error=%s', type(error).__name__)
    return JSONResponse({'error': '요청 처리 중 오류가 발생했습니다'}, status_code=500)


@api.get('/health')
async def health():
    return {'status': 'healthy', 'timestamp': utc_now().isoformat(),
            'background_update_running': False, 'framework': 'fastapi', 'storage': 'supabase'}


@api.get('/ready')
def ready(service=Depends(get_service)):
    service.quote()
    service.candidates()
    return {'status': 'ready', 'generation': service._row['generation']}


@api.get('/api/gold-premium', response_model=Premium)
def premium(service=Depends(get_service)):
    return service.premium()


@api.get('/api/investment-strategy', response_model=Strategy)
def strategy(service=Depends(get_service)):
    return service.strategy()


@api.get('/api/gold-analysis', response_model=Analysis)
def analysis(service=Depends(get_service)):
    return service.analysis()


@api.get('/api/futures-candidates', response_model=Candidates)
def candidates(service=Depends(get_service)):
    return service.candidates()


@api.get('/api/krx-gold-daily', response_model=KRXGoldDaily)
def krx_daily(service=Depends(get_service)):
    return service.krx_daily()


@api.get('/api/active-contract', response_model=ActiveContract)
def active(service=Depends(get_service)):
    return service.active()


Symbol = Annotated[str | None, Query(pattern=r'^[A-Z0-9]{4,16}$')]


@api.get('/api/pressure-signal', response_model=Pressure)
def pressure(symbol: Symbol = None, service=Depends(get_service)):
    return service.pressure(symbol)


@api.get('/api/orderbook-analysis', response_model=Orderbook)
def orderbook(symbol: Symbol = None, service=Depends(get_service)):
    return service.orderbook(symbol)


@api.post('/api/update-active-contract', response_model=Update)
def update(service=Depends(get_service)):
    return service.update()


@api.get('/api/token-status', response_model=TokenStatus)
def token_status(store=Depends(get_store)):
    return store.token_status()


# Wrap the whole app so even exception responses carry the permitted CORS origin.
app = CORSMiddleware(api, allow_origins=['https://financial-dashboard-six-chi.vercel.app',
    'http://127.0.0.1:3000', 'http://localhost:3000'],
    allow_origin_regex=r'^https://financial-dashboard-[a-z0-9-]+-kim-juins-projects\.vercel\.app$',
    allow_methods=['GET', 'POST', 'OPTIONS'], allow_headers=['Content-Type'])
