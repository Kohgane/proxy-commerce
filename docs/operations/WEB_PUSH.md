# Web Push 알림 운영 가이드 (Phase 147)

## 개요

Phase 147에서 Web Push (VAPID 기반) 알림이 추가되었습니다.

## 환경변수 설정

```env
WEB_PUSH_VAPID_PUBLIC=<Base64url 인코딩된 공개키>
WEB_PUSH_VAPID_PRIVATE=<Base64url 인코딩된 비밀키>
WEB_PUSH_CONTACT_EMAIL=admin@kohganepercentiii.com
```

## VAPID 키 생성

### 방법 1: 온라인 도구 (권장)
https://web-push-codelab.glitch.me 에서 생성 후 Render 환경변수에 입력

### 방법 2: py-vapid 설치 후 생성
```bash
pip install py-vapid
python3 -c "
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
print('PUBLIC:', v.public_key.decode())
print('PRIVATE:', v.private_key.decode())
"
```

### 방법 3: /admin/diagnostics에서 가이드 확인
`/admin/diagnostics` → "🔔 푸시 알림" 섹션에서 VAPID 설정 상태 확인

## 구독 흐름

1. 사용자가 `/seller/me/notifications` 접속
2. "🔔 구독" 버튼 클릭 → 브라우저 알림 권한 허용
3. Service Worker가 Push Manager에 구독 등록
4. `/seller/me/notifications/subscribe` POST로 서버에 저장
5. 이후 해당 기기에 서버 이벤트 발생 시 푸시 전송

## 알림 카테고리

| 카테고리 | 트리거 | 링크 |
|---|---|---|
| order | 신규 주문 | /seller/orders |
| cs | 긴급 CS 문의 | /seller/cs/inbox |
| shipping | 배송 지연 감지 | /seller/shipping/tracking |
| ads | ROAS 급변 (±20%) | /seller/ads/campaigns |

## 트리거 함수 (코드 연동)

```python
from src.notifications.web_push import (
    notify_new_order,
    notify_cs_urgent,
    notify_shipping_delay,
    notify_roas_change,
)

# 신규 주문 알림
notify_new_order("ORD-12345", 85000)

# 긴급 CS 알림
notify_cs_urgent("MSG-001", "환불 요청 긴급 처리 바람")

# 배송 지연 알림
notify_shipping_delay("ORD-12345")

# ROAS 급변 알림
notify_roas_change("coupang", roas=1.5, prev_roas=3.2)
```

## 구독자 관리

```python
from src.notifications.web_push import PushSubscriptionStore

store = PushSubscriptionStore()
print(f"총 구독자: {store.count()}")
for sub in store.list_all():
    print(sub.user_id, sub.endpoint[:40])
```

## VAPID 미설정 시 동작

VAPID 키가 없으면 stub 모드로 동작합니다:
- 로그에 `[STUB] Web Push: user → title` 기록
- 실제 푸시 미전송

## 보안 고려사항

- VAPID 키는 절대 소스코드에 포함하지 마세요
- Render 환경변수에 저장
- 공개키만 프론트엔드에 노출 (비밀키는 서버 전용)
- Service Worker background fetch 비활성 (데이터 유출 방지)

## 데이터 저장

구독 정보: `data/push_subscriptions.jsonl` (기본)
변경: 환경변수 `PUSH_SUBSCRIPTIONS_PATH`

## 관련 파일

- `src/notifications/web_push.py` — VAPID / 구독 / 전송
- `src/seller_console/static/sw.js` — Service Worker push/notificationclick 이벤트
- `src/seller_console/templates/_base.html` — 구독 UI JS
- `src/seller_console/views.py` — `/seller/me/notifications` 라우트
