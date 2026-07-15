# v72 STEP1 — 북마클릿 인증 뿌리 수술: 세션 폴백

## 증상 (오너)
- 북마클릿 401 3차 재발(토큰 수명 설계 결함). 토큰이 죽으면 수집 전면 실패.

## 수리
### 1) 세션 쿠키 폴백 (`src/api/extension_api.py`)
- `_auth_user()` = **Bearer 우선 → 무효(401)면 콘솔 로그인 세션 쿠키 폴백**. `collect_from_extension`이 사용.
- `_session_user()`: 유효한 콘솔 세션(`session["user_id"]`)이면 통과. **CSRF 방어**: 커스텀 헤더 `X-KGP: 1` 요구 — 단순 HTML 폼은 커스텀 헤더를 못 붙이고, 커스텀 헤더 크로스사이트 fetch는 CORS preflight를 거쳐야 하므로(우리 CORS는 `/api/v1/collect/*`만 자격 허용) 임의 사이트 폼 위조가 세션을 악용 못 함.
- 401 + 세션도 없음 → `{ok:false, login_required:true, login_url}` 응답.

### 2) 자격 동반 CORS + 쿠키 (`src/order_webhook.py`)
- `/api/v1/collect/*`: `supports_credentials:True`(flask_cors가 요청 Origin 반영 + `Allow-Credentials:true`), `allow_headers`에 `X-KGP` 추가.
- 세션 쿠키: **프로덕션(HTTPS)에서만 `SameSite=None; Secure`**(크로스사이트 전송 가능). 개발/테스트는 Lax 유지(HTTP 세션 정상).

### 3) 북마클릿 fetch (`_bookmarklet_js`)
- `credentials:'include'`(세션 쿠키 동반) + `'X-KGP':'1'` 헤더 + `'Bearer '+T`(토큰 우선 유지).
- `login_required` 응답 시 토스트 **"콘솔 로그인 후 다시 눌러 주세요 [열기]"**(링크, 새 창 안 띄움 — v38 규약). 코어 버전 `bm-v72`.

### 4) 토큰 정책 (명문화 — 이미 충족)
- `generate_token`은 **기존 토큰을 폐기하지 않음**(insert만) — 재발급해도 옛 북마클릿 토큰 유효. 만료 기본 **365일**(브리프 90일 이상). 발급/최근사용/만료는 기존 토큰 목록에 표시. (회귀 금지: revoke 호출 0.)

## 판정
- 가드 `tests/test_v72_bookmarklet_session.py` (7):
  - 소스계약(_session_user·_auth_user·X-KGP·login_required / CORS supports_credentials·X-KGP / SameSite=None Secure / 북마클릿 credentials+X-KGP+링크 / 토큰 no-revoke·만료≥90).
  - **behavioral(flask_client)**: 세션+X-KGP → 수집 200 ok / 세션인데 X-KGP 없음 → 401(CSRF 차단) / 무인증 → 401 login_required.
- 부수: `test_v38_global_audit`의 전역 `_require_token` 오염(직접 재할당) → monkeypatch로 격리(테스트 위생 수리).
- **실기기(오너 몫)**: ①만료 토큰 파일로 수집 → 세션 폴백 성공 토스트 ②로그아웃 상태 → 로그인 안내 토스트, 2캡처.

## 금지 준수
- 토큰 재발급 시 기존 폐기 0(회귀) · 자격증명 평문 0(세션 쿠키·HttpOnly) · 가짜 성공 0(세션 없으면 정직 401).
- CSRF: 세션 인증은 X-KGP 커스텀 헤더 요구(단순 폼 위조 차단). SameSite=None은 프로덕션 HTTPS 한정.

적용 스킬: (백엔드 인증·CORS·북마클릿 — UI 렌더 변경 최소(토스트 링크). impeccable/humanizer CLI 미설치.)
