# SUBSCRIPTIONS.md — 정기구독 상품 운영 가이드 (Phase 148)

## 개요

Phase 148부터 정기구독 상품 기능이 추가됩니다.

- 상품에 "정기구독 가능" 플래그
- 주기 옵션: 1주(7일) / 2주(14일) / 4주(28일) / 8주(56일)
- 자동 결제 (PG 연동 — 기본 mock)
- 다음 결제 7일 전 알림
- 일시정지 / 스킵 / 해지

## 환경변수

```env
SUBSCRIPTION_ENABLED=1                     # 1=활성화 (기본 ON)
SUBSCRIPTION_PG_PROVIDER=mock              # mock | tosspayments | iamport
SUBSCRIPTION_RETRY_DAYS=3                  # 결제 실패 재시도 간격 (일)
PRODUCT_SUBSCRIPTIONS_PATH=data/product_subscriptions.jsonl
```

## 라우트

| 경로 | 설명 |
|---|---|
| `GET /seller/subscriptions` | 판매자 정기구독 관리 (활성 구독 리스트, 통계) |
| `GET /seller/me/subscriptions` | 사용자 자신의 구독 관리 |
| `POST /seller/me/subscriptions/<id>/pause` | 일시정지 |
| `POST /seller/me/subscriptions/<id>/resume` | 재개 |
| `POST /seller/me/subscriptions/<id>/cancel` | 해지 |
| `POST /seller/me/subscriptions/<id>/skip` | 다음 주기 스킵 |

## 코드 모듈

```
src/product_subscriptions/
  __init__.py
  subscription_products.py  — ProductSubscriptionManager, ProductSubscription
                              SubscriptionCycle, SubscriptionStatus
```

## PG 제공사 전환

1. `SUBSCRIPTION_PG_PROVIDER=tosspayments` 설정
2. Toss Payments 빌링키 발급 플로우 구현 (별도 PR)
3. `process_billing_mock()` → 실제 PG API 호출로 교체

## Admin Diagnostics

`/admin/diagnostics` → "🔁 정기구독 (Phase 148)" 카드에서 현황 확인.

## 테스트

```bash
python3 -m pytest tests/test_product_subscriptions.py -v
```
