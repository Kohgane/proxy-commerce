# 코고가네 마켓 릴레이 (v8) — 쿠팡/네이버 고정 IP 경유

Render는 아웃바운드 IP가 고정이 아니라 쿠팡·네이버 OpenAPI의 **호출 IP 화이트리스트**가 안 맞습니다.
이 릴레이를 **고정 IP 호스트(Bluehost 등)** 에 올려, 서명까지 끝난 요청을 그 고정 IP에서 대신 호출합니다.

## 1) Bluehost(고정 IP)에 릴레이 배포
```bash
pip install flask requests gunicorn
export MARKET_RELAY_TOKEN="아주-긴-랜덤-토큰"     # Render 앱과 동일 값
gunicorn -w 2 -b 0.0.0.0:8800 market_relay_server_v8:app
# 또는 Bluehost Passenger/WSGI에 market_relay_server_v8:app 등록 + HTTPS 도메인 연결
```
- 공개 도메인 예: `https://relay.yourdomain.com` (HTTPS 필수)
- 이 서버의 공인 IP 확인: `curl https://api.ipify.org`

## 2) 쿠팡/네이버에 그 IP 등록
- 위 IP를 **쿠팡 Wing(OPEN API 허용 IP, 최대 10개)** · **네이버 커머스API(호출 IP, 최대 3개)** 에 등록.

## 3) Render 앱 환경변수
| 변수 | 값 |
|---|---|
| `MARKET_RELAY_URL` | `https://relay.yourdomain.com` |
| `MARKET_RELAY_TOKEN` | 릴레이와 동일한 긴 랜덤 토큰 |
| `MARKET_RELAY_MARKETS` | (선택) 기본 `coupang,smartstore,naver` |
| `SERVER_OUTBOUND_IP` | (선택) 위 Bluehost 공인 IP — 연동 화면 '복사' 버튼에 노출 |

설정되면 쿠팡/네이버 호출(업로드·연결 테스트 동일)이 릴레이를 경유합니다.
**미설정이면 기존처럼 직접 호출**(폴백 — 회귀 없음). Shopify/WooCommerce/Shopee는 IP 화이트리스트가
없어 항상 직접 호출합니다.

## 보안/정직
- Bearer 토큰 + HMAC(timestamp+body) 검증, 5분 시계오차 허용(재전송 차단).
- 허용 호스트(쿠팡/네이버)만 포워딩. 자격증명/페이로드 **미저장**, 키·바디 **로깅 금지**.
- 실제 마켓 응답의 status/body만 패스스루 — **가짜 성공 없음**(IP 미등록이면 그 실패가 그대로 표시).
