# FastAPI와 공유 시세 스냅샷 전환

## 배포 구조

사용자 결정에 따라 **새 유료 Worker 서비스를 생성하지 않는다.** 기존 Render Web Service 안에서 `run_service.py`가 단일 수집 프로세스와 Uvicorn/FastAPI 프로세스를 감독한다. 두 프로세스의 배포·재시작 수명은 같지만, 시세 수집은 HTTP 요청/ASGI lifespan에서 실행하지 않는다. 추후 별도 Worker 서비스로 옮길 때에는 API의 `DASHBOARD_COLLECTOR_MODE=external`을 사용하고 별도 서비스에서 `DASHBOARD_COLLECTOR_MODE=standalone python -u snapshot_collector.py`를 실행할 수 있다. 별도 서비스 생성은 이번 작업 범위에 포함하지 않았다.

기존 Flask 앱은 `app.py`에 그대로 남겨 호환성 비교와 운영 복구에 사용한다. API URL·기본 응답 필드는 유지하고 Pydantic 모델로 응답을 검사한다. 실제 비교 테스트는 금 프리미엄·전략·종합 분석·후보·활성 계약·호가·압력의 기존 Flask 결과와 비교한다.

## 저장소와 잠금

`ops/sql/create_dashboard_snapshot.sql`은 기존 네 테이블을 변경하지 않는 추가 마이그레이션이다.

- `dashboard_snapshot`: 한 행의 JSON bundle. 같은 세대의 금 시세·후보·활성 계약·계약별 호가를 원자적으로 교체한다.
- `dashboard_collector_lease`: 서버 시각을 기준으로 하는 단일 수집기 임대. 기본 60초이고 각 provider 호출 전 갱신한다.
- 임대를 소유한 수집기만 스냅샷을 쓸 수 있다. 재배포 시 두 프로세스가 잠시 겹쳐도 임대를 얻은 하나만 수집한다. 정상 종료 시 반납하며 비정상 종료 시 만료된다.
- KIS 새 토큰 발급 직전에도 소유권을 재확인한다. API 프로세스는 토큰을 발급하지 않으며 token-status는 id 존재 여부만 확인한다.
- 새 테이블은 RLS를 켜고 anon/authenticated 권한과 RPC 실행 권한을 차단한다. backend service_role만 사용한다. 관리 API 토큰은 Render 환경 변수에 복사하지 않는다.

운영 DB에서 실제 수집기 경쟁·소유권 없는 쓰기 거부·소유권 양도·anon 접근 거부를 확인했다. 이 검사에서는 가짜 가격이나 테스트 시장 데이터를 운영 저장소에 넣지 않았다.

## 데이터 유효성과 응답

수집 주기는 약 30초이며 실제 수집 시간에 따라 길어질 수 있다. 스냅샷과 각 section의 최대 나이는 90초다. 수집에 실패한 데이터는 unavailable로 기록해 이전 가격으로 새 매매 신호를 만들지 않는다. API는 다음을 구분한다:

| 상태 | API 결과 |
|---|---|
| 유효 데이터 | 200 |
| 정상 조회했지만 계약/호가 없음 | 404 |
| 공급자 실패, 저장소 실패, 만료 | 503 |
| 응답 계약 검증 실패 | 502 |
| 잘못된 symbol 요청 | 422 |

API의 로컬 읽기 캐시는 최대 15초다. 동시 요청을 합쳐 Supabase egress를 줄이되 매 요청 때 원래 만료 시각을 검사하며, 캐시가 만료를 연장하지 않는다. 그러므로 수집기의 새 결과/오류 반영은 읽기 캐시만큼 늦어질 수 있다. 프론트엔드는 기존 카드 구조를 유지하고 선물 카드는 30초마다 갱신한다.

`POST /api/update-active-contract`는 요청 중 KIS에 접속하지 않고 수집기에 갱신을 요청한다. 기존 contract 필드를 돌려주되 `refresh_requested=true`를 추가하고, UI는 실제 updated_at이 바뀔 때까지 갱신 대기 상태를 표시한다. 동기적으로 새 가격을 받았다고 주장하지 않는다.

금선물 후보는 수집기가 공식 KIS master를 TLS 검증을 유지한 채 자동 갱신해 생성한다. 일 단위로 새 master를 확인하고 실패 시 5분 간격으로 재시도한다. 마지막으로 검증한 master가 36시간을 넘으면 후보를 제공하지 않는다. 월물 코드나 만기 날짜를 추측하지 않으며 스프레드는 제외한다. 시장 휴장 시 제공된 마지막 시세와 수집 시각은 서로 다를 수 있고, 금 프리미엄은 국제 선물과 국내 현물의 참고 비교다.

## 시작과 관측

Render의 Root Directory는 기존 backend를 유지하고 시작 명령만 다음으로 전환한다:

```sh
python run_service.py
```

필요한 기존 앱 환경 변수: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, KIS_APP_KEY, KIS_APP_SECRET, EXCHANGE_RATE_API_KEY. `DASHBOARD_COLLECTOR_MODE=embedded`가 이번 배포 방식이다. 시세 저장소를 이용하지 않는 구 SQLite collector/QUOTE_SNAPSHOT_PATH 모드는 호환용으로 남아 있으며 새 시작 명령에서는 사용하지 않는다.

- `/health`: FastAPI 프로세스 liveness. framework=fastapi, background_update_running=false.
- `/ready`: 금 시세·후보 snapshot의 freshness. 데이터를 읽을 수 없으면 503. 시장 데이터 장애를 프로세스 장애와 혼동하지 않도록 Render health check는 `/health`를 유지한다.
- `/openapi.json`, `/docs`: 명시적 응답 모델과 같은 API 경로.
- 초기 시작은 fresh snapshot을 확인한 후 서버를 연다. 데이터가 준비되지 않으면 기존 배포를 정상이라고 바꾸지 않는다.
- 감독 프로세스는 수집기 또는 API가 죽으면 나머지도 정리하고 실패 종료해 Render가 재시작하게 한다. 수집기만 죽고 API가 무기한 옛 가격을 제공하지 않는다.

## 검증과 복구

```sh
# repo root
backend/venv/bin/python -m unittest discover -s backend/tests -v
# frontend
npm ci
npm run lint
npm run build
```

관리형 클라우드의 TLS 검사 프록시에서는 build 시 `NEXT_TURBOPACK_EXPERIMENTAL_USE_SYSTEM_TLS_CERTS=1` 옵션을 사용했다. 검증을 비활성화하지 않는다.

복구는 기존 시작 명령 `gunicorn app:app`으로 되돌리고 검증된 Flask 포함 커밋을 재배포한다. service_role 키와 기존 네 테이블의 RLS는 유지한다. 새 스냅샷 테이블을 즉시 삭제하거나 RLS를 끄지 않는다. 기존 프론트엔드의 Render URL은 바뀌지 않는다.

전체 테스트는 API parity·오류/CORS·토큰 비노출·수집 호출 분리·ASGI event loop 비차단·만료·잠금·원자적 bundle·감독 프로세스 종료 동작을 검증한다. 운영 배포 후에는 실제 후보·계약·압력과 기존 금 시세 API, 새 테이블의 익명 접근 차단 및 데이터 세대 갱신을 별도로 확인한다.


개발 환경의 안전한 기본값은 collector 비활성이다. 운영 Supabase 키를 사용하는 로컬/클라우드 개발 작업은 `uvicorn asgi:app --host 127.0.0.1 --port 5000`으로 조회 API만 시작한다. 운영 데이터 저장소를 대상으로 임의의 개발 수집기를 켜지 않는다. 수집기 CLI는 embedded/standalone의 명시적인 opt-in 없이는 종료한다.
