# NOTIFICATIONS.md — 알림 설정 가이드 (Phase 130)

텔레그램/이메일 알림 설정 방법과 훅 포인트 설명.

---

## 텔레그램 알림

### 설정 방법

1. **BotFather에서 봇 생성**
   - Telegram → @BotFather → `/newbot`
   - 봇 이름/username 설정
   - **Bot Token** 복사: `1234567890:ABCdefGHIjklMNOpqrSTUvwxyz`

2. **Chat ID 확인**
   - @userinfobot 에 `/start` → ID 확인
   - 또는 그룹/채널 추가 후 `https://api.telegram.org/bot<TOKEN>/getUpdates`

3. **Render Environment 등록**
   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxyz
   TELEGRAM_CHAT_ID=987654321
   ```

4. **테스트**
   - 셀러 콘솔 → [알림 설정](/seller/notifications) → "테스트 메시지 전송" 버튼
   - 또는 `POST /seller/notifications/test`

### 알림 발송 코드

```python
from src.notifications.telegram import send_telegram

send_telegram("신규 주문 3건 도착", urgency="info")
send_telegram("재고 소진: 상품 A XS", urgency="warning")
send_telegram("결제 오류 발생", urgency="critical")
```

### 자동 알림 훅 포인트

| 이벤트 | urgency | 메시지 예시 |
|---|---|---|
| 주문 sync 완료 | info | ℹ️ 신규 주문 3건 (쿠팡 2, 스스 1) |
| `/health/deep` 실패 | warning | ⚠️ google_sheets 체크 실패 |
| 재고 0 도달 | warning | ⚠️ [Alo Yoga Legging XS] 재고 없음 |
| 마진 손실 예상 | critical | 🚨 쿠팡 [상품X] 마진 -3% 손실 예상 |

---

## ADAPTER_DRY_RUN 모드

`ADAPTER_DRY_RUN=1` 설정 시 텔레그램/이메일 등 모든 외부 API 호출이 차단됩니다.
로컬 개발 및 테스트 환경에서 사용하세요.

---

## SendGrid 이메일 알림 (Phase 130 등록, 활성화는 Phase 135 예정)

**발급**: https://app.sendgrid.com → Settings → API Keys

```
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxx
```

**사용처**: 주문 확인 이메일, 배송 시작 알림, 가입 환영 메일

---

## 알림 설정 페이지

셀러 콘솔 → 사이드바 → 알림 설정: [https://kohganepercentiii.com/seller/notifications](https://kohganepercentiii.com/seller/notifications)
