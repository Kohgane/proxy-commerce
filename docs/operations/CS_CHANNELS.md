# CS 다채널 인바운드 어댑터 (Phase 138)

각 채널 어댑터는 키 부재 시 `is_active()=False`를 반환하며 cron이 자동으로 skip합니다.

## 채널 목록

| 채널 | 어댑터 | 환경변수 | 모드 |
|------|--------|---------|------|
| Telegram | 기존 webhook | `TELEGRAM_BOT_TOKEN`, `CS_TELEGRAM_WEBHOOK_SECRET` | webhook |
| Email (IMAP) | `EmailImapAdapter` | `CS_EMAIL_IMAP_HOST`, `CS_EMAIL_IMAP_USER`, `CS_EMAIL_IMAP_PASS` | poll |
| 쿠팡 Q&A | `CoupangQAAdapter` | `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY`, `COUPANG_VENDOR_ID` | poll |
| 네이버 톡톡 | `NaverTalkAdapter` | `NAVER_TALKTALK_BOT_ID`, `NAVER_TALKTALK_ACCESS_TOKEN` | poll |
| 11번가 Q&A | `ElevenQAAdapter` | `ELEVEN_API_KEY` 또는 `ELEVEN_OPENAPIKEY` | poll |

## Email IMAP 설정

```env
CS_EMAIL_IMAP_HOST=imap.gmail.com
CS_EMAIL_IMAP_PORT=993
CS_EMAIL_IMAP_USER=cs@example.com
CS_EMAIL_IMAP_PASS=app_password_here
CS_EMAIL_IMAP_FOLDER=INBOX
CS_EMAIL_FROM=cs@example.com
```

Gmail 앱 비밀번호 발급: https://myaccount.google.com/apppasswords

## 임베딩 설정

```env
CS_EMBEDDING_PROVIDER=openai   # 또는 disabled
CS_EMBEDDING_MODEL=text-embedding-3-small
```

`/admin/cs/rebuild-embeddings`를 1회 클릭하면 모든 FAQ 임베딩이 계산됩니다.
