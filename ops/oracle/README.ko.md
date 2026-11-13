# Oracle Linux 9 이전 절차

대상: `opc@151.145.41.202`, ARM64, vCPU 1개, 메모리 5.5GiB.
API·수집기는 네이티브 Python 3.12/systemd, HTTPS는 Oracle 기본 Podman의
공식 Caddy 컨테이너를 사용한다. Docker 전용 저장소나 Compose 설치는 필요 없다.
초기 설치·확인은 사용자가 SSH 터미널에서 실행한다. 개인키를 채팅에 넣지 않는다.

## 1. 설치 — 아직 서비스나 수집기는 시작하지 않음

```bash
sudo dnf install -y git
git clone https://github.com/okji1/financial_dashboard.git
cd financial_dashboard
sudo bash ops/oracle/install.sh
```

`install.sh`는 Oracle Linux 9 여부를 확인하고 현재 Git 커밋의 backend와 배포
파일을 `/opt/financial-dashboard/releases/<commit>`에 복사한다. 실패 시 자동으로
서비스를 시작하지 않는다. 기존 설치가 있으면 덮어쓰지 않고 종료한다. venv 의존성은
서버 아키텍처에 맞춰 설치한다. 최초 설치 후 `pip freeze`를 별도 보관하면 이후
릴리스에서 의존성 변경도 비교할 수 있다. Caddy `:2`는 최초 pull한 이미지를
재시작 때 재사용한다. 운영 갱신 시 이미지 digest와 인증서 갱신 동작도 확인한다.

## 2. 키 등록 — 서버 파일에서만 입력

```bash
sudoedit /etc/financial-dashboard/backend.env
```

빈 여섯 변수에 Render Environment의 기존 값을 그대로 넣는다. 파일은 root 전용
0600이다. Supabase anon 키 대신 `SUPABASE_SERVICE_ROLE_KEY`를 사용한다.
`RENDER_API_KEY`, `SUPABASE_ACCESS_TOKEN`, GitHub 토큰은 서버에 복사하지 않는다.
키 값이나 이 파일의 내용을 채팅/로그/Git에 붙이지 않는다. `web.env`에는 비밀값이
없는 호스트명만 있으며 Caddy 컨테이너에 백엔드 키를 전달하지 않는다.

## 3. HTTPS 경로 개방

OCI 콘솔의 해당 인스턴스 VNIC에 연결된 NSG 또는 서브넷 Security List에서
**TCP 80, TCP 443**을 공개 웹 트래픽에 허용한다. SSH 22는 현재 접속 규칙을
유지한다. 5000, 2019, DB 포트는 외부에 열지 않는다.

서버의 firewalld가 실행 중이면 실제 사용 zone을 확인하고 해당 zone에만
http/https 서비스를 추가한다. SSH 규칙이나 SELinux를 끄지 않는다.

```bash
sudo firewall-cmd --get-active-zones
```

예를 들어 주 네트워크 인터페이스가 `public` zone에 있을 때만:

```bash
sudo firewall-cmd --permanent --zone=public --add-service=http
sudo firewall-cmd --permanent --zone=public --add-service=https
sudo firewall-cmd --reload
```

`151-145-41-202.sslip.io`는 현재 서버 IP를 가리키는 제삼자 무료 DNS다. IP 주소
변경·DNS 서비스 장애·공용 호스트명의 인증서 발급 제한에 영향을 받는다. 장기적으로는
본인 도메인을 권장한다. Caddy가 공인 인증서를 발급·갱신하며, 80/443 외부 접근과
서버의 DNS/HTTPS 아웃바운드가 필요하다. 인증서 상태는 실제 서버에서 검증해야 한다.
발급 실패 시 HTTPS 검증을 끄거나 프론트를 HTTP API로 연결하지 않는다.

## 4. 읽기 전용 API 먼저 확인

```bash
sudo systemctl enable --now financial-dashboard-api financial-dashboard-web
bash ops/oracle/check.sh
```

이 단계에서는 Oracle 수집기를 시작하지 않는다. API는 기존 Render 수집기의
Supabase 스냅샷을 읽는다. `/health`, `/ready`, 실제 API, 허용된 Vercel Origin의
CORS 헤더와 공인 HTTPS를 확인한다. 운영 프론트의 API 주소는 아직 바꾸지 않는다.
서비스 실패 시 키 값 대신 아래 상태/로그를 확인한다.

```bash
sudo systemctl status financial-dashboard-api financial-dashboard-web --no-pager
sudo journalctl -u financial-dashboard-api -u financial-dashboard-web -n 60 --no-pager
```

## 5. 수집기 인계와 프론트 전환

새 HTTPS/API 확인 후 Oracle 수집기를 먼저 실행한다:

```bash
sudo systemctl enable --now financial-dashboard-collector
```

기존 Render 수집기가 리스를 소유하는 동안 `collector_waiting_for_lease`로 대기하는
것이 정상이다. Oracle 서비스와 환경 변수 검사가 정상인지 확인한 다음 Render의
`DASHBOARD_COLLECTOR_MODE=external`을 저장하고 재배포한다. 기존 수집기의 종료와
새 소유자로의 리스 변경을 확인한다. 임의로 소유권을 강제 변경하지 않는다.

기존 리스가 만료될 때까지 최대 약 60초 기다릴 수 있다. 임의로 DB의 리스나
KIS 토큰을 삭제하지 않는다. 금 시세, 선물, KRX, 이력 API가 정상이고
`dashboard_system_state`의 네 source가 ok이며 새 스냅샷이 30초 주기로 갱신되는지
확인한다. 이 시점에 Oracle에서의 공급자 접근이 검증된다. API만 켠 4단계는
Oracle의 KIS/네이버/환율 공급자 접근을 검증한 것이 아니다.

이후 Vercel Production의 `NEXT_PUBLIC_API_URL`을
`https://151-145-41-202.sslip.io`로 바꾸고 재배포한다. 실제 화면에서 자동 갱신,
차트·알림·선물 갱신 요청을 확인한다. Render API는 검증/롤백 기간 동안 유지한다.

## 롤백

두 호스트는 같은 Supabase를 사용하므로 API URL만 바꾸는 것은 수집기 롤백이
아니다. Oracle 수집기를 `sudo systemctl disable --now financial-dashboard-collector`로
중지하고 Render의 수집 모드를 `embedded`로 복원해 재배포한다. 리스 인계 및
신선한 데이터가 확인되면 Vercel API URL을 기존 Render URL로 복원해 재배포한다.
기존 테이블·토큰·RLS는 변경하지 않는다.

## 이후 코드 업데이트

현재 설치기는 최초 설치용이다. 새 커밋은 별도 release/venv에 준비·검증하고,
실행 중인 API/수집기를 중지한 뒤 current 링크를 새 release로 전환해 재시작한다.
이전 release를 보관한다. 단순히 서비스 실행 중 current를 바꾸거나 서버에서
무조건 `git pull`하지 않는다. 이 단계의 자동 배포는 별도 구성한다.

## 2026-11-13 인계 검증 기록

Oracle의 공인 HTTPS, API 및 Vercel Origin의 CORS를 확인했다. Render는 기존
백엔드 커밋의 수집 모드만 external로 바꿔 재배포했다. 리스 소유자 변경과
Oracle의 연속 정상 스냅샷을 확인했으며 금 시세·선물·KRX·수집기 상태는 정상이다.
기존 토큰이나 DB 리스/정책은 수동 변경하지 않았다. 운영 Vercel의
NEXT_PUBLIC_API_URL 변경·재배포도 완료했다. 배포 번들에서 Oracle URL을 확인하고
기존 Render URL이 없는 것을 확인했다. 운영 브라우저의 9개 API 요청 모두 Oracle로
향했으며 시세·이력 차트·수동 새로 고침·모바일 및 JavaScript 오류 없음까지 검증했다.
Render는 external 모드의 롤백용 API로 유지한다.
