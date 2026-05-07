# Resend 도메인 인증 가이드

Magic Link/운영 알림 메일 발송 안정화를 위해 Resend 도메인 인증을 완료합니다.

## 1) 도메인 추가

1. Resend Dashboard → Domains → Add Domain
2. 발송 도메인 입력 (예: `kohganepercentiii.com`)
3. Resend가 제공하는 DNS 레코드 확인

## 2) DNS 레코드 설정

아래 레코드를 DNS 관리 콘솔(Cloudflare 등)에 추가합니다.

- SPF (TXT)
- DKIM (CNAME, 보통 2~3개)
- DMARC (TXT, 권장)

Resend 화면의 Host/Value를 그대로 복사해 등록하세요.

## 3) 검증 확인

1. DNS 반영 후 Resend Domains 페이지에서 Verify 실행
2. 상태가 `Verified` 로 바뀌는지 확인
3. `/auth/magic-link` 발송 테스트

## 4) 미인증 상태 임시 운영

- 도메인 미인증 시 sandbox 발신이 제한될 수 있습니다.
- 이 경우 운영자 계정은 Magic Link 화면표시 폴백 또는 Diagnostic Token을 사용하세요.

## 5) 권장 보안 설정

- DMARC 정책을 점진적으로 강화 (`p=none` → `quarantine` → `reject`)
- 발신 전용 서브도메인 분리 고려 (`mail.kohganepercentiii.com`)
