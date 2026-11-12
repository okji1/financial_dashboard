# 대시보드 오류 수정 및 운영 전환 검토

## 범위와 운영 확인의 한계

2026-11-12, 기준 HEAD와 원격 main은 `d18dbe33b31ea6f9681c48175bb62cf7bddfe455`로 일치했다. 코드 수정은 작업 디렉터리에만 있으며 push, 배포, 환경 게시, DB DDL은 수행하지 않았다.

사용자가 제공한 운영 백엔드는 `https://financial-dashboard-backend-sggl.onrender.com`이다. 이 도메인과 `financial-dashboard-six-chi.vercel.app`에 대한 요청은 클라우드 egress proxy에서 CONNECT 403으로 차단됐다. 이것은 운영 앱이 403을 반환했다는 증거가 아니다. Vercel 환경 설정을 읽을 연결 도구도 없어 실제 배포의 NEXT_PUBLIC_API_URL은 확인하지 못했다. 운영 장애의 원인을 CORS로 확정하지 않는다.

운영 검증을 재개하려면 위 두 호스트의 네트워크 접근이 필요하다. Supabase 읽기/정책 검증에는 `mccahwtqogammiggthoh.supabase.co`, 현재 KIS 마스터에는 `new.real.download.dws.co.kr` 접근이 필요하다. 환경 초안/게시 설정은 이번 작업에서 수정하지 않았다.

## 확인한 원인과 수정

- 환율 오류를 임의의 1380원으로 치환하던 코드를 제거했다. 실패 시 가격/투자 신호를 반환하지 않는다. 환율 성공은 600초, 실패는 30초 캐시한다. 빈 영업일 데이터만 최대 5일 되돌아가며, 전송 실패는 즉시 중단한다. API 키가 포함될 수 있는 URL/예외 문자열은 로그에 남기지 않는다.
- 세 시세 의존성을 병렬 조회한다. 완성된 프리미엄은 60초, 실패는 15초 캐시하여 동시 요청과 반복 장애 시 외부 호출을 줄인다. 만료 가격을 현재 가격으로 반환하지 않는다. 캐시는 프로세스별이며 Gunicorn worker 간 공유되지 않는다.
- 각 카드의 재조회 성공 시 기존 오류를 지우고 실패 시 이전 데이터를 지운다. 공통 fetch에 20초 타임아웃, 네트워크/HTTP 오류/형식 검사와 누락된 운영 API URL 안내를 넣었다. 잘못된 200 JSON을 TypeScript 타입 단언만으로 렌더링하지 않는다.
- 선물 404는 정상적인 데이터 없음으로 표시하고, 호가 오류 후 이전 압력값을 제거한다. 누락 압력을 0%로 보여주지 않는다. 후보 조회 오류도 화면에 표시한다.
- 호가 요청에 연결 3초/응답 8초 타임아웃을 추가했다. 누락/음수/양쪽 0인 잔량은 신호를 만들지 않는다. 활성 계약의 API 중복 시세 요청을 제거했다. 응답의 미확인 만기일은 null로 유지한다.
- 요청서의 Preview Origin은 기존 규칙에서 이미 허용됐다. 별도로 발견한 접미 도메인 허용 취약점은 정규식 시작/끝 앵커로 막았다. localhost 개발 Origin 두 개를 명시적으로 허용한다.
- 공개 token-status는 cache_hit만 반환한다. 토큰 일부도 노출하지 않는다. DB 예외 및 API 실패 응답에 외부 예외 문자열을 반영하지 않는다.
- 네이버 실제 GCcv1 응답은 `infoType=futures`, `stockExchangeType=COMEX`였다. 런던 현물로 표시하던 문구를 고쳤다. 국제 선물/국내 현물 비교라는 안내를 추가했다. 실측하지 않은 고정 유동성 8.5, 프리미엄만으로 추정한 시계열 변동성, COT 더미 포지션을 제거했다. 가격 시각 정렬/선물 베이시스가 검증되지 않았으므로 이 비교는 실행 가능한 현물 스프레드가 아니다.

## 수집 프로세스와 배포 영향

기존에는 Gunicorn worker마다 첫 요청에서 백그라운드 수집 스레드를 시작했다. 이제 기본값은 비활성이다. `ENABLE_BACKGROUND_UPDATES=1`은 단일 프로세스 환경의 임시 호환 옵션이며 멀티워커에서는 사용하지 않는다.

별도 수집 프로세스는 backend에서 `venv/bin/python collector.py`로 시작할 수 있다. 이 프로세스는 기존 5분 갱신 및 DB 정리 동작을 포함하므로 운영 자격 증명을 주입하면 DB 쓰기가 발생한다. 이번 작업에서 이 수집 프로세스를 운영 DB에 실행하지 않았다. DB 조회 함수와 Flask route의 동명 충돌도 alias로 수정했다.

**아직 완전한 수집/조회 분리는 아니다.** 현재 collector의 메모리 캐시는 Gunicorn에 전달되지 않는다. HTTP 요청도 캐시가 비면 직접 수집한다. 다음 단계는 quote timestamp, source, expiry, error 상태를 갖는 공유 저장소를 도입하고 collector만 기록하며 조회 API는 유효한 snapshot만 읽게 하는 것이다. KIS 토큰 발급 잠금 역시 프로세스별이므로 분산 잠금 또는 단일 token broker가 필요하다. 이 단계 전에는 다중 worker에서 토큰 발급 중복이 완전히 해결됐다고 볼 수 없다.

API 응답에는 Server-Timing을 추가했다. app logger는 경로/HTTP 상태/경과 ms, upstream logger는 호스트/경로/경과 ms만 기록하며 쿼리/헤더/본문은 기록하지 않는다. 모듈 upstream INFO 기록을 받으려면 런처에서 root logging INFO handler를 구성한다. example: `python -c 'import logging; logging.basicConfig(level=logging.INFO); from app import app; app.run()'` (개발용). 운영은 Gunicorn logconfig로 같은 수준을 설정한다.

## KIS 공식 자료 검토

공식 저장소 `koreainvestment/open-trading-api`, 검토 커밋 `3a9be59a3ed8745720dc3aa9d584bdf3b7830362`:

- `examples_llm/domestic_futureoption/inquire_price/inquire_price.py`: `/uapi/domestic-futureoption/v1/quotations/inquire-price`, TR_ID `FHMIF10000000`.
- `examples_llm/domestic_futureoption/inquire_asking_price/inquire_asking_price.py`: `/uapi/domestic-futureoption/v1/quotations/inquire-asking-price`, TR_ID `FHMIF10010000`.
- `stocks_info/종목마스터정보(상품선물옵션).h`: 상품 구분 3, 선물 구분 1, 기초자산 `GLD`(금)의 정의가 있다. 정의가 있다는 사실은 현재 상장 또는 해당 REST API의 CF 지원을 입증하지 않는다.
- `stocks_info/domestic_commodity_future_code.py`: 다운로드 대상은 `https://new.real.download.dws.co.kr/common/master/fo_com_code.mst.zip`. 현재 네트워크 정책에서 차단돼 최신 계약 목록은 검증하지 못했다. 공식 예제에 TLS 검증을 끄는 코드가 있어 그대로 실행하지 않았다.

현재의 CF는 기존 코드의 가정으로 남아 있으며 공식 예제는 주로 F/O/JF를 설명한다. 계약 마스터와 API 포털의 지원 시장 확인 및 실계약 조회가 완료될 때까지 검증된 금선물 코드가 있다고 주장하거나 코드를 추측해서 추가하지 않는다. 현재의 빈 목록/404는 구성 미완료 상태다. KIS가 금선물을 지원하지 않는다는 결론도 내리지 않았다.

대안: KRX 금 현물은 현물 가격만 제공하므로 선물 계약/호가 압력의 대체가 아니다. COMEX GC를 쓸 경우 해외선물 시세/호가 권한을 가진 별도 공급자, 계약 마스터, 통화/단위/지연 표시가 필요하다. 네이버 GCcv1 가격 차트만으로 선물 호가 압력을 만들 수 없다.

## Supabase RLS 전환 설계 (미적용)

현재 주입된 SUPABASE_KEY는 디코딩한 JWT claim상 anon이다. 서명 검증이나 실제 DB 권한 검증 결과가 아니며 운영 Render에도 같은 키가 쓰인다고 단정하지 않는다. 이 상태로 무작정 RLS를 켜면 백엔드도 차단될 수 있다.

1. 운영의 실제 table grants, policies, RLS 상태와 백엔드 key 역할을 안전하게 점검하고 복구 가능한 정책/권한 사본을 준비한다. 공개 브라우저가 직접 Supabase에 접근하는 경로가 있는지도 확인한다.
2. 백엔드 전용 `SUPABASE_SERVICE_ROLE_KEY`를 Render의 비밀 환경 변수에 주입한다. 코드에서는 이것을 우선 사용하며 기존 SUPABASE_KEY fallback은 점진 전환 호환용이다. service_role은 RLS를 우회하는 고권한 키이므로 브라우저 번들, NEXT_PUBLIC 변수, 응답/로그에 넣지 않는다. 가능하면 제한된 DB 역할과 전용 token broker로 권한을 더 줄인다.
3. 새 키로 읽기/쓰기 동작을 staging에서 검증하고 백엔드를 전환한다. 기존 anon 키가 여전히 필요한 클라이언트가 있다면 해당 기능부터 backend 경유로 전환한다.
4. DB 담당자 검토 후 트랜잭션으로 `kis_token`의 anon/authenticated 권한을 철회하고 RLS를 활성화한다. public 허용 정책을 만들지 않는다. 기존 허용 정책도 함께 검토해야 하며 ENABLE RLS만으로 접근 차단을 가정하지 않는다. service_role 경로의 접근을 검증한다.
5. gold_prices, active_contracts, investment_strategies는 공개 API를 통해 읽게 하고 브라우저의 직접 write/delete는 차단한다. 직접 공개 읽기를 유지해야 한다면 민감 필드를 제외한 view/명시적 SELECT 정책을 별도로 설계한다. 기존 grants/policies를 모르므로 이번에는 DDL을 생성·실행하지 않았다.
6. anonymous/authenticated 접근 거부, backend 정상 접근을 확인한 후 기존 키 폐기/회전 여부를 결정한다. RLS 전환 전 토큰 노출 가능성이 있었다면 기존 KIS 토큰도 안전하게 폐기/재발급하는 절차를 별도로 검토한다.

## PR #1 KRX와 FastAPI 순서

PR #1 HEAD `c707585e7bb93972b6318f2a33223c1c9ace9691`의 provider와 문서/테스트를 검토했다. 별도 임시 디렉터리에서 provider 단위 테스트 6개를 실행해 통과했다. main에 병합하지 않았다. 실서비스 KRX 호출은 수행하지 않았다.

좋은 점: 일별 종가임을 명시, 금 1kg 코드 구분, 인증/응답 실패 시 가짜 가격 금지, 거래일 조회, 소스/날짜 메타데이터. 남은 점: 반복 빈 응답 최대 8회×15초의 총 지연 예산, 국제 선물/일별 국내 종가/FX 간 시각 정합성, 과거 close인데 현재처럼 신호를 표시하는 문제, 재배포 시 새 KRX 키·네트워크 요구사항. 현재 변경과 api_utils/gold_data/app 부분이 겹치므로 병합 전 조정과 전체 회귀 검증이 필요하다.

FastAPI는 현재 Flask 오류를 덮는 전체 교체 대신 다음 순서로 진행한다:

1. 이번 Flask 응답 계약과 오류/브라우저 테스트를 기준선으로 확정하고 운영 환경에서 재검증한다.
2. provider/캐시/토큰/분석을 framework와 분리한다. collector와 공유 quote snapshot 저장소를 먼저 도입한다.
3. FastAPI에 동일 URL/필드와 Pydantic response model을 추가하고 Flask와 같은 snapshot을 읽도록 한다. 동기 requests를 async route 내부에서 직접 실행하지 않는다.
4. staging에서 CORS, 타임아웃, null/404/502 계약 및 응답 parity를 비교하고 트래픽 일부부터 전환한다. lifespan에 수집 스레드를 복제하지 않는다.
5. Vercel API URL 전환 후 관측하고 Flask로 되돌릴 수 있는 기간을 둔다.

이번에는 FastAPI 의존성 추가나 운영 전환을 하지 않았다. 운영 장애/공급자 지원/DB 권한 검증이 남아 있으므로 프레임워크 변경을 안정성 해결로 주장하지 않는다.

## 재현 명령

저장소 루트:

```sh
backend/venv/bin/python -m unittest discover -s backend/tests -v
```

frontend 디렉터리:

```sh
npm ci --cache /tmp/financial-npm-cache --no-audit --no-fund
npm run lint
npx --no-install tsc --noEmit
NEXT_TURBOPACK_EXPERIMENTAL_USE_SYSTEM_TLS_CERTS=1 npm run build
npm run start -- --hostname 127.0.0.1
```

시스템 CA 옵션은 이 환경의 TLS 검사 프록시를 신뢰하게 하며 TLS 검증을 끄지 않는다. 운영 Vercel에서 필요한지는 별도 확인한다.

backend 디렉터리에서 `venv/bin/flask --app app run --host 127.0.0.1 --port 5000` 실행 후 실제 로컬 API와 브라우저를 점검할 수 있다. 운영 프론트엔드는 빌드 시점에 NEXT_PUBLIC_API_URL을 위 Render origin으로 설정하고 Production/Preview scope에 각각 적용한 뒤 재빌드해야 한다. 없으면 이제 명시적 구성 오류를 표시한다.

브라우저 회귀 테스트는 저장소 루트에서 `python3 frontend/tests/dashboard_browser.py`. Python playwright와 `/usr/bin/chromium`이 필요하며 다른 경로는 CHROMIUM_PATH로 지정한다. 이 환경에는 이미 설치되어 있다. 테스트는 실제 Flask route에서 만든 고정 fixture를 브라우저 네트워크에 주입하므로 외부 공급자 가용성 검증과 구별한다.

## 이번 실행 결과

- 백엔드 단위/API 회귀 테스트: **23개 통과**. 외부 API/DB 쓰기는 mock으로 대체했다.
- frontend `npm ci`, lint, TypeScript 검사 및 최종 production build 통과. 빌드에는 위 시스템 CA 옵션이 필요했다.
- Chromium에서 실제 로컬 Flask를 호출해 gold-premium / investment-strategy / gold-analysis 200 응답과 화면 표시를 확인했다. active-contract / pressure-signal은 404, futures-candidates는 빈 목록 200이며 화면에 데이터 없음으로 표시됐다. 렌더링 예외는 없었다.
- 실제 로컬 gold-premium 콜드 요청 1회는 약 **2.845초**였다. 한 번의 측정이며 운영 지연 분포나 성능 개선율을 입증하지 않는다.
- 브라우저 회귀 테스트: Flask 응답 계약 렌더링, 빈 계약, 500→성공 polling 복구, malformed 200, 네트워크 실패, 20초 timeout 통과. 최종 빌드 후 frontend를 재시작해 다시 검증했다.
- PR #1 provider만 임시 디렉터리에 분리한 단위 테스트 **6개 통과**. 전체 PR 통합 빌드/실제 KRX 호출 검증을 의미하지 않는다.
- `git diff --check` 통과. 의존성 선언/lockfile은 변경하지 않았다.

다음 운영 작업은 네트워크 접근 확보 후 실제 배포 Origin/응답 JSON 및 Vercel 빌드 환경 변수를 확인하고, 검토된 코드만 배포하는 것이다. DB RLS/키 전환과 완전한 공유 collector 구조 및 FastAPI 구현은 미적용 상태로 남아 있다.

## 후속 작업: 공유 스냅샷 모드 구현

이 절은 앞의 '아직 완전한 수집/조회 분리는 아니다'와 collector 실행 방법을 보완한다. 기본 모드(QUOTE_SNAPSHOT_PATH 미설정)는 이전처럼 프로세스별 캐시를 사용한다. **QUOTE_SNAPSHOT_PATH를 설정한 모드에서는 조회 API가 외부 시세를 수집하지 않는다.**

`quote_store.py`에 로컬 SQLite 원자적 스냅샷 저장소를 추가했다. `collector.py`는 프레임워크를 import하지 않고 실제 시세 3종만 수집해 30초 간격으로 스냅샷을 기록한다. 토큰 발급/DB 정리/선물 탐색은 수행하지 않는다. 단일 writer가 필요하며, worker 두 개가 writer를 겸하게 실행하지 않는다. 실패 결과도 기록하여 이전 투자 신호가 계속 제공되지 않게 한다. API 프로세스는 읽기 전용 연결로 저장소를 읽고, 누락/손상/만료/미래 시각/잘못된 가격이면 503을 반환한다. 저장소를 읽을 수 없다고 HTTP 요청이 외부 공급자를 직접 호출하도록 우회하지 않는다.

같은 머신과 파일시스템의 프로세스들을 대상으로 검증한 선택형 구현이다. **서로 다른 Render Web Service/Background Worker는 보통 디스크를 공유하지 않는다.** 그 구조에서는 이 SQLite 설정을 그대로 사용하지 말고 Redis 등 네트워크 공유 저장소 또는 검토된 Supabase snapshot 테이블로 어댑터를 교체해야 한다. 현재 DB schema나 권한은 변경하지 않았다. SQLite를 네트워크 파일시스템 위의 분산 잠금/캐시로 사용한다고 보장하지 않는다.

예시 (각 프로세스에 동일한 경로를 지정):

```sh
mkdir -p /tmp/fd-shared-runtime
cd /workspace/financial_dashboard/backend
QUOTE_SNAPSHOT_PATH=/tmp/fd-shared-runtime/quotes.sqlite venv/bin/python collector.py
# 별도 터미널: 이 환경의 Gunicorn 27은 readonly home의 control socket을 비활성화한다.
QUOTE_SNAPSHOT_PATH=/tmp/fd-shared-runtime/quotes.sqlite venv/bin/gunicorn --no-control-socket --workers 2 --threads 2 --bind 127.0.0.1:5001 app:app
```

지속 보관이 필요한 환경에서는 /tmp 대신 해당 서비스가 소유한 경로를 사용한다. 프로세스가 살아 있다는 것만으로 quote readiness를 판단하지 말고 `/api/gold-premium` 200을 확인한다. `/health`는 liveness이며 시세 가용성을 의미하지 않는다. 이 모드에서는 ENABLE_BACKGROUND_UPDATES를 설정하지 않는다.

후속 검증: backend 테스트 **32개 통과**(기존 23개 + 저장소/프로세스 분리/API 통합 9개). 별도 수집 프로세스의 실제 공급자 요청으로 생성한 스냅샷을 Gunicorn worker 2개가 읽었으며 프리미엄·전략·분석 API 모두 200이었다. 실패 스냅샷을 기록한 후 세 endpoint 모두 503으로 전환하는 것도 확인했다. 테스트용 스냅샷만 로컬 /tmp에 기록했으며 Supabase 쓰기나 KIS 토큰 발급은 수행하지 않았다.

운영 접근을 계속하기 위해 이번 후속 작업에서 기존 6개 custom domain을 보존하고 다음 4개 host를 **설정 초안에만 추가**했다: `financial-dashboard-backend-sggl.onrender.com`, `financial-dashboard-six-chi.vercel.app`, `mccahwtqogammiggthoh.supabase.co`, `new.real.download.dws.co.kr`. 이전 절의 '환경 초안을 수정하지 않았다'는 설명은 최초 수정 작업에 대한 기록이다. 후속 저장 이후에도 실행 환경의 적용 revision은 1로 유지되어 아직 새 네트워크 규칙은 적용되지 않았다. 사용자 환경 설정에서 검토/저장이 필요하며, 이번에도 환경 게시나 운영 배포는 수행하지 않았다.

## 게시 후 운영 검증 (2026-11-12 17:02~17:08 KST)

새 실행 환경은 현재 unrestricted 네트워크 정책이 enforced 상태였다. 이 정책은 사용자가 게시한 환경의 설정이며 에이전트가 unrestricted로 변경한 것이 아니다. 기존 코드 수정은 스냅샷에 보존되어 있었고 다시 적용하지 않았다.

### 운영 API와 프론트엔드

운영 Render `/health` 200, background_update_running=true였다. 요청서의 Preview Origin을 보낸 실제 요청에서 다음을 확인했다:

| API | 상태 | 응답/시간 |
|---|---|---|
| gold-premium | 200 | 기존 UI 필드 포함, 약 3.09초 |
| investment-strategy | 200 | signals 배열 포함, 약 3.10초 |
| gold-analysis | 200 | market_overview/risk_assessment 포함, 약 3.09초 |
| futures-candidates | 200 | 빈 목록 |
| active-contract | 404 | error JSON |
| pressure-signal | 404 | error JSON |

6개 응답 모두 `Access-Control-Allow-Origin: https://financial-dashboard-8s2zdjlqt-kim-juins-projects.vercel.app`를 반환했다. 현재의 운영 재현에서는 CORS 장애가 확인되지 않았다. 단일 시점이며 간헐적 장애까지 배제하지 않는다.

Vercel의 HTML과 실제 dashboard JS chunk를 TLS 검증을 유지한 HTTP 클라이언트로 읽었다. 번들에는 `https://financial-dashboard-backend-sggl.onrender.com`이 포함되어 있고 localhost fallback은 없었다. 관리 콘솔의 변수 자체를 읽은 것은 아니지만 배포 번들의 실제 API 주소는 확인됐다.

운영 브라우저 직접 방문은 Chromium의 ERR_CERT_AUTHORITY_INVALID로 실패했다. 환경 제공 프록시 CA를 사용자 NSS 신뢰 저장소에 등록하려 했으나 자동 승인 검토가 '영구적 사용자 브라우저 신뢰 경계 확대에 대한 정확한 사용자 승인 부재'를 이유로 거부했다. 등록 명령은 실행되지 않았으며 우회/인증서 검증 비활성화도 하지 않았다. 운영 서버에서 실제로 받은 JSON을 로컬 최신 UI에 주입하는 별도 검증은 수행했다. 이는 운영 Origin에서의 브라우저 end-to-end 검증과 다르다.

### 최신 KIS 마스터: GLD가 아닌 KGD

최신 공식 ZIP은 122행, 해제된 master 14,274 bytes였다. ZIP SHA256:
`f3475666292ef03a512933ef682532bbfa9844f066f329228f4da0a6475bf86a`.

과거 C 헤더의 GLD만 검색해 금이 없다고 판단하는 것은 잘못이다. 실제 최신 파일은 **KGD**이며 일반 금 선물 7개와 금 스프레드 6개를 포함했다. 일반 선물 코드는 A88611, A88612, A88702, A88704, A88706, A88708, A88710으로 확인했다. 기록 구분 31만 허용해 스프레드는 제외했다.

`gold_master.py`와 `KIS_GOLD_FUTURES_MASTER_PATH` 선택형 연동을 추가했다. 공식 CP949/ZIP, 계약 월, 과거 월 제외, 상품 구분, 중복 충돌, 파일 크기/갱신 36시간 제한을 검증한다. 운영 환경 변수는 바꾸지 않았고 수동 종목 목록도 자동으로 넣지 않았다. 후보가 master에 존재한다는 사실과 KIS quote API 지원/가격 가용성은 별도다.

공유 DB에서 유효한 기존 토큰을 백엔드 코드로 재사용해 CF/A88612 시세 조회를 시도했다. 토큰/앱 키는 출력하지 않았고 신규 토큰을 발급하지 않았다. KIS 9443 연결은 JSON이 아닌 Envoy `upstream connect error ... connection timeout` 503이었다. 별도 비인증 루트 연결도 같은 유형이었다. 운영 Render의 pressure-signal에 실제 A88612를 지정한 읽기 요청은 404였다. 따라서 정확한 지원 시장/시세/호가 필드의 live 검증은 아직 미완료다. 국내 금선물 미지원이라는 결론을 내리지 않는다.

### Supabase 접근 노출과 필요한 외부 조치

현재 anon 키를 사용한 `HEAD /rest/v1/kis_token?select=id&limit=0` 및 exact count 요청은 206과 `Content-Range: */32`를 반환했다. 이 점검에서 토큰 행 본문은 가져오지 않았다. 이어서 기존 백엔드 캐시 함수를 통해 유효한 토큰을 내부적으로 재사용할 수 있었다. 즉 이 키로 토큰 테이블 행에 접근 가능하다. 토큰 값은 어느 출력/파일/보고서에도 기록하지 않았다.

행 접근 가능하다는 관찰은 확인되지만, 관리 권한으로 catalog를 읽은 것이 아니므로 RLS 비활성인지 허용 정책 때문인지는 확정하지 않는다. DB grants/policies는 변경하지 않았다. 현재 환경에 `SUPABASE_SERVICE_ROLE_KEY`는 없어 새 요구사항 이름만 설정 초안에 추가했다. 값은 환경 설정에 안전하게 입력해야 하며 채팅으로 전달하지 않는다. 앞서 설계한 백엔드 키 전환→접근 검증→RLS/권한 제한 순서를 지킨다. 공개 anon 키를 가진 클라이언트에서 토큰 테이블을 읽을 수 있는 상태는 우선 처리해야 할 보안 문제다.

최신 backend 회귀 테스트는 **38개 통과**. 새 마스터 파서는 실제 내려받은 파일에서도 7개의 정상 선물을 추출했다. 이번에도 DB 권한 변경, 코드 push/운영 배포, 환경 게시를 수행하지 않았다. FastAPI/네트워크 공유 저장소 기반 수집기 전환은 현재 운영 시세 지원과 DB 접근 보안 문제를 확인한 뒤 진행할 단계로 남아 있다.
