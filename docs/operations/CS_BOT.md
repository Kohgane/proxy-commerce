# CS Bot 운영 가이드 (Phase 137)

## 운영 흐름
1. 고객 메시지 수신(텔레그램 webhook)
2. 언어 감지 + 카테고리 분류
3. FAQ 매칭 + 답변 초안 생성
4. 운영자 승인/수정 후 발송
5. SLA 추적(임박/초과 알림)

## FAQ 작성 가이드
- `{{customer_name}}`, `{{order_no}}`, `{{tracking_no}}`, `{{eta}}` 변수 사용 가능
- 카테고리: refund/shipping/size/stock/general
- 언어: ko/en/ja/zh

## SLA 정책
- refund: 2h
- shipping: 12h
- size/stock: 24h
- general: 48h

## 보안 권고
- `CS_AUTO_SEND=0` 기본 유지 권장
- 자동 발송을 켜더라도 webhook secret(`CS_TELEGRAM_WEBHOOK_SECRET`) 필수
