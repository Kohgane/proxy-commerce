# OAuth Flow (Google / Kakao / Naver)

공통:
- `/auth/<provider>/start`에서 `state`와 `oauth_next_*`를 세션에 저장
- `/auth/<provider>/callback`에서 state 검증 → 코드 교환 → 로그인 세션 발급 → 내부 경로로 redirect

Kakao:
- `KAKAO_OAUTH_NEXT_DEFAULT` 기본 이동 경로 지원
- `KAKAO_OAUTH_POPUP_MODE=1` 또는 `popup=1`이면 popup close + opener redirect 동작

보안:
- 외부 도메인 redirect 차단 (`_safe_next_url`)
