# 인증/관리자 운영 가이드 (Phase 136.1)

## ADMIN_EMAILS 설정
- 환경변수: `ADMIN_EMAILS`
- 형식: 콤마(,) 구분 이메일 목록
- 예시:
  ```env
  ADMIN_EMAILS=admin1@example.com,admin2@example.com
  ```
- 비교는 대소문자 무시(`lower()`)로 수행됩니다.

## OAuth 로그인 시 role 결정
1. Google/Kakao/Naver OAuth 콜백에서 사용자 이메일을 확인
2. `ADMIN_EMAILS`에 이메일이 포함되면 `admin`
3. 그 외는 `seller`
4. 세션(`user_role`)과 사용자 저장소 role을 즉시 동기화

> Kakao에서 이메일 동의를 하지 않은 경우(`email` 없음):
> - `seller` 권한으로 로그인 처리
> - 경고 플래시 표시

## `/auth/whoami` 사용법
현재 브라우저 세션 상태를 JSON으로 즉시 확인합니다.

- URL: `/auth/whoami`
- 응답 필드:
  - `logged_in`
  - `user_id`
  - `user_email`
  - `user_role`
  - `user_name`
  - `admin_emails_configured` (`ADMIN_EMAILS` 값 자체는 노출하지 않음)
  - `is_admin`

## 트러블슈팅

### `/admin/diagnostics` 접근이 403/리다이렉트되는 경우
1. `/auth/login`으로 먼저 로그인
2. `/auth/whoami`에서 `logged_in=true` 확인
3. `user_role=admin` 확인
4. 아니라면 `ADMIN_EMAILS`에 현재 OAuth 이메일이 정확히 등록됐는지 확인

### Kakao 로그인 후 admin이 안 되는 경우
- Kakao 동의 항목에서 이메일이 미동의일 수 있습니다.
- 이메일 동의 후 재로그인하면 `ADMIN_EMAILS` 매칭이 적용됩니다.
