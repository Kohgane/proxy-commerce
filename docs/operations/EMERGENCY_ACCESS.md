# 비상 접근 가이드

OAuth 정상화 전에도 운영자가 admin 패널과 가격 룰 페이지에 진입할 수 있도록 Magic Link, Bootstrap, Diagnostic Token을 제공합니다.

## 1. Magic Link 사용법

![Magic Link 로그인 화면](assets/emergency_access_magic_link.png)

1. `/auth/magic-link` 접속
2. 관리자 이메일 입력
3. 받은 메일의 1회용 링크 클릭
4. `/auth/whoami` 에서 `user_role=admin` 확인

### 보안 메모
- 링크는 15분 동안만 유효합니다.
- 한 번 사용하면 재사용할 수 없습니다.
- 본인이 요청하지 않았다면 메일을 무시하세요.

## 2. Bootstrap 토큰 사용법

가장 빠른 우회 경로:

```text
/auth/bootstrap?token=<ADMIN_BOOTSTRAP_TOKEN>&email=<ADMIN_EMAIL>
```

조건:
- `ADMIN_BOOTSTRAP_TOKEN` 환경변수 설정
- `ADMIN_EMAILS` 에 관리자 이메일 등록
- HTTPS 환경에서만 사용 권장

## 3. Diagnostic Token 사용법 (최후 진입로)

1. 브라우저에서 `/auth/diagnostic-token/issue` 접속
2. JSON 응답 확인 후 Render Dashboard → Logs 탭 이동
3. `DIAGNOSTIC TOKEN` 검색
4. 로그에 출력된 `.../auth/diagnostic-token/redeem?token=...` URL 복사
5. 해당 URL 접속 → `/admin/diagnostics` 진입

예시 로그:

```text
DIAGNOSTIC TOKEN 발급됨 (10분 유효, 1회용)
URL: https://kohganepercentiii.com/auth/diagnostic-token/redeem?token=...
```

## 4. 진입 방식 비교

| 방식 | 의존성 | 장점 | 주의사항 |
|---|---|---|---|
| Magic Link | Resend 발송 | 사용자 친화적 | 이메일 발송 장애 시 실패 가능 |
| Bootstrap | `ADMIN_BOOTSTRAP_TOKEN` | 즉시 진입 가능 | 토큰 노출 주의, URL 입력 실수 주의 |
| Diagnostic Token | Render 로그 | 이메일/OAuth 장애에도 동작 | `ADMIN_EMAILS` 필수, 로그 접근 권한 필요 |

## 5. 운영 보안 권고

- OAuth 정상화 후 `ADMIN_BOOTSTRAP_TOKEN` 삭제
- `/admin/diagnostics` 에서 Bootstrap 설정 상태 확인
- 실패 로그가 반복되면 토큰 재발급 및 세션 만료 처리
- Diagnostic Token URL은 1회용이며 절대 공유 금지
