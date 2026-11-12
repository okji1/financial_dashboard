# 금선물·Supabase 운영 전환

2026-11-12에 운영 Render의 백엔드 service_role 키 전환과 네 테이블의 RLS 전환을 완료했다. 키는 환경 설정/Render에만 보관하며 저장소에는 기록하지 않는다. 읽기 전용 사전 점검 도구는 상태 확인용으로 재사용할 수 있다. SQL 파일은 같은 전환에 사용한 검토 가능한 마이그레이션이며 재실행 전에도 키·대상·catalog 확인이 필요하다.

## 필요한 관리 연결

클라우드 환경 설정에 다음 비밀값을 안전하게 등록하고 저장한다. 채팅/저장소/명령 인자/로그에 값을 넣지 않는다.

- RENDER_API_KEY: 운영 Render 서비스의 설정·배포를 관리할 API 키
- SUPABASE_ACCESS_TOKEN: 해당 Supabase 프로젝트의 메타데이터·키·SQL을 관리할 토큰

가능한 한 해당 서비스/프로젝트로 범위를 제한한다. Supabase anon 키는 관리 토큰이 아니고 service_role 키만 있어도 SQL DDL 권한은 제공되지 않는다. 관리 토큰으로 backend-only 키를 조회할 수 있으면 별도의 키 재입력을 요구하지 않는다. 현재 초안의 SUPABASE_SERVICE_ROLE_KEY 항목은 기존 코드가 사용할 backend key binding으로 유지되지만 관리 토큰의 대체가 아니다.

다음은 읽기 전용 사전 점검이다:

```sh
cd /workspace/financial_dashboard
backend/venv/bin/python ops/preflight_production.py \
  --backend-url https://financial-dashboard-backend-sggl.onrender.com
```

이 도구는 Render 서비스를 URL로 정확히 하나만 선택하고 실제 SUPABASE_URL이 의도한 프로젝트와 일치하는지 검사한다. 네 테이블의 RLS/grants/정책 메타데이터와 환경 변수 이름만 출력한다. 키 값이나 token row를 출력하지 않는다. 다른 프로젝트/중복 서비스/누락 테이블이면 중단한다. 실제 쓰기·배포·DDL은 하지 않는다.

## 금선물 설정 순서

1. 공식 TLS 경로에서 최신 상품 master를 내려받아 기존 gold_master.py로 검사한다. `KGD`의 `31` 일반 선물만 사용하며 spread는 제외한다. 현재 마스터의 계약 월은 확정해도 만기 날짜는 추정하지 않는다.
2. Render에서 기존 환경 변수를 보존하면서 KIS_GOLD_FUTURES_SYMBOLS만 master에서 추출한 실제 코드 목록으로 설정하거나, 갱신 관리되는 KIS_GOLD_FUTURES_MASTER_PATH를 사용한다. ephemeral 로컬 파일을 배포 영구 경로처럼 설정하지 않는다. 마스터 경로 방식은 36시간마다 갱신이 필요하다.
3. 한 계약으로 실계약 quote/호가를 읽어 CF, TR_ID, output schema와 권한을 확인한다. 관리자 키가 준비되면 Render의 실제 설정·배포 로그를 읽어 404 원인을 분리한다. 여기서 시세/호가 지원이 확인되지 않으면 임의 market 코드나 가짜 0 거래량으로 성공 처리하지 않는다.
4. 정상일 때 후보·활성 계약·압력 API와 브라우저를 확인한다. 거래소 비거래/잔량 없음과 인증/전송 실패를 구분한다.

Render API의 단일 환경 변수 PUT `/v1/services/{serviceId}/env-vars/{envVarKey}`를 사용해 무관한 변수 목록을 대체하지 않는다. 환경 변수 갱신 후 새 deploy를 만들고 live 완료까지 기다린다. 현재 접근에서 KIS port 9443은 upstream connection timeout 503이었으며 이 오류는 상품 미지원의 증거가 아니다.

## Supabase 전환 순서

1. 관리 API의 read-only SQL endpoint로 대상 테이블의 RLS 상태, grants, permissive/restrictive policies, service_role BYPASSRLS 및 역할 상속을 점검한다. 기존 catalog metadata를 비밀값 없는 사본으로 보관한다. 토큰 테이블 데이터는 백업 파일/로그에 넣지 않는다.
2. 프로젝트 API key inventory에서 backend용 service_role 또는 지원되는 secret key를 내부적으로 선택한다. Render의 SUPABASE_SERVICE_ROLE_KEY에만 설정하고 다른 환경 변수는 보존한다. NEXT_PUBLIC 변수에는 넣지 않는다. 이후 Render를 재배포한다.
3. 키가 단지 설정됐다는 사실과 실제 동작을 구분한다. Render 적용 변수의 일치 확인, backend readiness/API, 서비스 키의 실제 테이블 접근을 검증한다. 같은 프로젝트/현재 deploy인지 확인한다.
4. 그 뒤에만 SQL 초안 `sql/restrict_dashboard_tables.sql`을 실제 catalog에 맞춰 검토하고 적용한다. 이 초안은 네 테이블에 RLS와 browser role을 차단하는 RESTRICTIVE 정책을 추가하고 anon/authenticated 권한을 철회한다. 기존 policies를 지우지 않아 다른 허용 정책이 남아도 browser role의 접근을 막는다. 키 전환 확인 flag 없이는 실패하도록 되어 있다. 운영 프로젝트에서 이 마이그레이션을 실행하고 anon 차단·service_role 접근 및 backend API 정상 상태를 검증했다.
5. 별도 anon/authenticated 요청은 거부되고 backend service_role 접근은 유지되는지 확인한다. 예상치 못한 역할/직접 DB 클라이언트가 발견되면 먼저 조정하며 일괄 정책 삭제/권한 부여로 우회하지 않는다. 비상 복구는 이전 catalog snapshot에 따라 복원한다.
6. 과거 공개 접근 가능했던 KIS 토큰은 노출 여부를 단정할 수 없다. DB 읽기 차단 후 기존 토큰 무효화·회전은 KIS 절차에 맞춰 별도로 처리하며 반복 발급을 유도하지 않는다.

공식 schema를 확인한 경로: Render update-env-var reference, Supabase Management API `/api/v1-json`의 api-keys 및 database/query/read-only 경로. 실제 관리 접근은 자격 증명 주입 후 검증해야 한다.


## 실제 전환 결과

- 대상 서비스: financial_dashboard_backend / main, 대상 Supabase 프로젝트: mccahwtqogammiggthoh. Render 환경의 기존 SUPABASE_URL과 프로젝트 API key inventory의 일치까지 확인했다.
- Backend service_role 키를 단일 환경 변수 PUT으로 설정하고 Render deploy `dep-dbqnk35ckfvc73cvviig`의 live 완료를 확인했다. 기존 변수 전체를 덮어쓰지 않았다.
- 변경 전 네 테이블 모두 RLS=false, anon/authenticated 전체 권한, 정책 없음이었다. role bypass/상속과 service_role의 읽기·쓰기 권한을 점검하고 schema/grants/policies 메타데이터만 별도로 백업했다. 토큰 행/키값은 파일에 보관하지 않았다.
- 키 적용을 확인한 뒤 트랜잭션 하나로 네 테이블에 RLS와 restrictive deny 정책을 적용하고 anon/authenticated 테이블 권한을 철회했다. 다른 테이블과 역할 구성은 변경하지 않았다.
- 네 테이블의 실제 REST HEAD: anon은 모두 401, service_role은 모두 200/206. authenticated는 catalog에서 SELECT 권한 없음으로 확인했다(실제 사용자 JWT를 새로 만들지는 않았다).
- 전환 뒤 token-status, gold-premium, investment-strategy, gold-analysis 모두 200이었다. 가격·토큰 데이터는 삭제하거나 임의로 생성하지 않았다.
- 금선물은 공식 master의 일반 계약 7개를 확인해 KIS_GOLD_FUTURES_SYMBOLS에 등록했다. 처음 A88612 한 계약으로 배포·시세/호가를 점검한 뒤 전체 후보 설정을 저장했다. 단일 계약의 호가 API는 성공했지만 잔량 0을 반환해 신호를 생성하지 않았다. 전체 후보의 최종 데이터 가용성은 최신 배포 후 별도 확인한다.
- 공급자 전송/인증/요청 실패는 FuturesUnavailable과 HTTP 503으로 구분하고, 성공 응답인데 실제 유효 거래/호가가 없는 404와 섞지 않도록 회귀 테스트를 추가했다. 진단 로그에는 제한된 응답 코드·숫자 시세/거래량만 기록하고 provider 메시지/자격 증명은 기록하지 않는다.

과거 노출 가능성이 있던 KIS 토큰/anon 프로젝트 키의 전역 폐기·회전은 수행하지 않았다. 다른 연동의 영향을 확인한 뒤 별도 계획으로 처리한다. 현재 보호 대상 네 테이블은 이전 anon 키로도 접근할 수 없다.
