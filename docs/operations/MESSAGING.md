# 다채널 고객 메시징 가이드

## 개요

Phase 134에서 구현된 다채널 메시징 허브는 고객의 locale에 따라 최적 채널을 자동 선택하여 주문/배송/환불 알림을 발송합니다.

## 지원 채널

| 채널 | 클래스 | 환경변수 | 대상 고객 |
|---|---|---|---|
| 이메일 | `ResendChannel` | `RESEND_API_KEY` | 전 고객 |
| 텔레그램 | `TelegramNotifyChannel` | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | 운영자 알림 |
| 카카오 알림톡 | `KakaoAlimtalkChannel` | `KAKAO_ALIMTALK_API_KEY` + `KAKAO_ALIMTALK_SENDER_KEY` | 한국 고객 |
| LINE Notify | `LineNotifyChannel` | `LINE_NOTIFY_TOKEN` | 일본 고객 (채널 공지) |
| LINE Messaging | `LineMessagingChannel` | `LINE_CHANNEL_ACCESS_TOKEN` + `LINE_CHANNEL_SECRET` | 일본 고객 (1:1) |
| WhatsApp | `WhatsAppChannel` | `META_WHATSAPP_TOKEN` + `META_WHATSAPP_PHONE_ID` | 글로벌 고객 |
| WeChat | `WeChatChannel` | `WECHAT_APP_ID` + `WECHAT_APP_SECRET` | 중국 고객 |
| SMS (Twilio) | `SMSChannel` | `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` + `TWILIO_FROM` | 글로벌 |
| SMS (Aligo) | `SMSChannel` | `ALIGO_API_KEY` + `ALIGO_USER_ID` + `ALIGO_SENDER` | 한국 |
| Discord | `DiscordChannel` | `DISCORD_WEBHOOK_URL` | 운영자 보조 |

## locale → 채널 라우팅 정책

| locale | 우선순위 |
|---|---|
| `ko` (한국) | 카카오 알림톡 → SMS → 텔레그램 → 이메일 |
| `ja` (일본) | LINE Messaging → LINE Notify → SMS → 이메일 |
| `en` (영어권) | WhatsApp → 이메일 → SMS |
| `zh-CN` (중국 간체) | WeChat → 이메일 → SMS |
| `zh-TW` (중국 번체) | LINE → 이메일 → SMS |
| `vi` (베트남) | WhatsApp → 이메일 |
| 기타 | 이메일 → SMS → 텔레그램 |

환경변수 미설정 채널은 자동 skip됩니다.
모든 채널 실패 시 운영자에게 텔레그램 fallback 알림이 전송됩니다.

## 이벤트 타입

| 이벤트 | 설명 |
|---|---|
| `order_received` | 주문 접수 |
| `payment_confirmed` | 결제 완료 |
| `order_shipped` | 배송 시작 + 운송장 |
| `order_delivered` | 배송 완료 |
| `refund_requested` | 환불 요청 접수 |
| `refund_completed` | 환불 완료 |
| `out_of_stock` | 품절 안내 |
| `cs_auto_reply` | CS 자동응답 |

## 템플릿

위치: `src/messaging/templates/{event}/{locale}.{channel}.txt`

폴백 순서:
1. `{locale}.{channel}.txt` (예: `ko.kakao_alimtalk.txt`)
2. `{locale}.txt` (예: `ko.txt`)
3. `ko.txt` (한국어 폴백)
4. `default.txt`
5. 인라인 기본값

### 템플릿 변수

| 변수 | 설명 |
|---|---|
| `{name}` | 고객 이름 |
| `{order_id}` | 주문 번호 |
| `{tracking_no}` | 운송장 번호 |
| `{courier_name}` | 택배사 이름 |
| `{eta_date}` | 예상 배송일 |
| `{tracking_url}` | 배송 추적 URL |
| `{shop_url}` | 쇼핑몰 URL |
| `{total_krw}` | 주문 금액 |
| `{placed_at}` | 주문 일시 |
| `{refund_amount}` | 환불 금액 |
| `{refund_method}` | 환불 수단 |
| `{refund_date}` | 환불 처리일 |
| `{product_name}` | 상품명 |

## 채널 발급 가이드

### 카카오 알림톡 (한국)
1. [카카오 비즈니스](https://business.kakao.com) 가입
2. 카카오 알림톡 채널 개설
3. Aligo([https://smartsms.aligo.in](https://smartsms.aligo.in)) 가입 → 알림톡 서비스 신청
4. 환경변수 설정: `KAKAO_ALIMTALK_API_KEY`, `KAKAO_ALIMTALK_SENDER_KEY`, `KAKAO_ALIMTALK_USER_ID`, `KAKAO_ALIMTALK_SENDER`

### LINE (일본)
- LINE Notify: [https://notify-bot.line.me](https://notify-bot.line.me) → 토큰 발급 → `LINE_NOTIFY_TOKEN`
- LINE Messaging API: [LINE Developers](https://developers.line.biz) → 채널 생성 → `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`

### WhatsApp Business
1. [Meta for Developers](https://developers.facebook.com) → WhatsApp Business → Cloud API
2. 비즈니스 인증 후 전화번호 등록
3. 환경변수: `META_WHATSAPP_TOKEN`, `META_WHATSAPP_PHONE_ID`

### WeChat 공식계정 (중국)
1. [WeChat 공식계정 플랫폼](https://mp.weixin.qq.com) → 서비스 계정 등록
2. 환경변수: `WECHAT_APP_ID`, `WECHAT_APP_SECRET`

### SMS (한국 — Aligo)
1. [Aligo](https://www.aligo.in) 가입 → SMS 서비스 신청
2. 환경변수: `ALIGO_API_KEY`, `ALIGO_USER_ID`, `ALIGO_SENDER`

### SMS (글로벌 — Twilio)
1. [Twilio](https://www.twilio.com) 가입 → 전화번호 구매
2. 환경변수: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`

## 메시지 로그

Sheets `message_log` 워크시트에 자동 기록됩니다.

| 컬럼 | 설명 |
|---|---|
| `sent_at` | 발송 시각 (ISO 8601 UTC) |
| `recipient_user_id` | 수신자 ID |
| `locale` | 수신자 언어 |
| `channel` | 사용된 채널 |
| `event` | 이벤트 타입 |
| `template_key` | 사용된 템플릿 키 |
| `status` | `ok` / `fail` |
| `provider_msg_id` | 공급자 메시지 ID |
| `error` | 오류 메시지 |

## 테스트

`/seller/messaging` 페이지에서:
1. 이벤트 / locale / 채널 선택
2. "운영자에게 테스트 발송" 클릭
3. 운영자 본인 이메일/텔레그램으로 테스트 메시지 전송
