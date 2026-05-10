# Admin Role 부여 규칙 (Phase 142)

## 개요

이메일/OAuth 로그인 사용자에게 admin 권한을 부여하는 통일된 메커니즘입니다.
`src/auth/admin_resolver.py`에 구현됩니다.

## 판정 규칙 (우선순위 순)

| # | 규칙 | 환경변수/DB |
|---|------|-------------|
| 1 | `user.role == "admin"` | DB (Google Sheets) |
| 2 | `user.email in ADMIN_EMAILS` | `ADMIN_EMAILS` (콤마 구분) |
| 3 | 카카오 `provider_user_id in ADMIN_KAKAO_IDS` | `ADMIN_KAKAO_IDS` |
| 4 | Google `provider_user_id in ADMIN_GOOGLE_SUBS` | `ADMIN_GOOGLE_SUBS` |
| 5 | 네이버 `provider_user_id in ADMIN_NAVER_IDS` | `ADMIN_NAVER_IDS` |
| 6 | `user.email == ADMIN_BOOTSTRAP_EMAIL` | `ADMIN_BOOTSTRAP_EMAIL` (Phase 136 잔존) |

## 환경변수 설정

```env
ADMIN_EMAILS=shanks8@hanmail.net,admin2@example.com
ADMIN_KAKAO_IDS=<카카오 사용자 ID>
ADMIN_GOOGLE_SUBS=<Google sub>
ADMIN_NAVER_IDS=<네이버 사용자 ID>
```

## 카카오 사용자 ID 확인 방법

1. 카카오로 로그인 후 `/auth/whoami` 방문
2. `"user_id"` 값을 확인 (이 값이 provider_user_id)
3. 또는 `/admin/diagnostics` 접근 후 인증 상태 카드에서 확인

## 적용 시점

1. 로그인 시: `_resolve_user_role()` → `resolve_role_for_login()`
2. `/admin/diagnostics` 접근 시: `is_admin_session(session)` 확인
3. 헤더 배지: 동일 함수로 통일

## 부트스트랩 가이드

관리자가 없는 초기 상태라면:

1. `ADMIN_EMAILS=<본인 이메일>` 환경변수 추가
2. 이메일 또는 magic link로 로그인
3. `/admin/diagnostics` 접근 → admin 판정 통과 확인
4. 이후 카카오 등 소셜 계정도 ADMIN_KAKAO_IDS 등 추가

## 보안 고려사항

- ADMIN_EMAILS 등 환경변수는 Render/Railway 환경변수 패널에만 저장
- 절대 코드에 하드코딩하지 않음
- 세션 role과 env var 양쪽 모두 확인 (outdated 세션 대비)
