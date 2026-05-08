# Telegram CS Webhook 설정

## 등록
```bash
curl -F "url=https://kohganepercentiii.com/webhooks/telegram/cs" \
     -F "secret_token=$CS_TELEGRAM_WEBHOOK_SECRET" \
     https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook
```

## 검증
- 서버는 `X-Telegram-Bot-Api-Secret-Token` 헤더를 검증
- 불일치 시 403 반환
