# EMAIL.md — Resend 이메일 설정 가이드 (Phase 133)

## 개요

SendGrid에서 **Resend**로 교체. 회원가입 인증 / 주문 확인 / 비밀번호 재설정 메일 발송.

---

## 환경변수

| 변수명 | 설명 | 예시 |
|---|---|---|
| `RESEND_API_KEY` | Resend API 키 | `re_...` |
| `RESEND_FROM_EMAIL` | 발신자 이메일 (선택) | `noreply@kohganepercentiii.com` |

---

## Resend 설정

1. [resend.com](https://resend.com) → 가입
2. API Keys → Create API Key → 키 복사 → `RESEND_API_KEY`
3. Domains → Add Domain:
   - `kohganepercentiii.com` 추가
   - DNS TXT 레코드 설정 (SPF, DKIM)
4. Domain 인증 완료 후:
   - `RESEND_FROM_EMAIL=noreply@kohganepercentiii.com`

---

## DNS 설정 (도메인 인증)

Resend 대시보드에서 제공하는 레코드를 DNS 공급업체(Cloudflare 등)에 등록:

```
Type: TXT
Name: resend._domainkey.kohganepercentiii.com
Value: v=DKIM1; k=rsa; p=...
```

---

## 사용처

| 이벤트 | 수신자 |
|---|---|
| 회원가입 이메일 인증 | 신규 가입자 |
| 비밀번호 재설정 | 요청 사용자 |
| 주문 확인 (자체몰) | 구매자 |
| 운영자 알림 (텔레그램 보조) | ADMIN_EMAILS |

---

## 폐기된 서비스

- `SendGrid` → Resend로 교체
- `SENDGRID_API_KEY` → Render에서 **삭제 권장** (혼란 방지)
- `src/notifications/email_sendgrid.py` → deprecated stub (백워드 호환)

---

## 헬스 체크

```
GET /health/deep
→ {"name": "resend", "category": "notification", "status": "ok"|"missing", ...}
```
