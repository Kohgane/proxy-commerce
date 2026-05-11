# WHOLESALE.md — B2B 도매 모드 운영 가이드 (Phase 148)

## 개요

Phase 148부터 B2B 도매 기능이 활성화됩니다.

- 등급별 가격: 일반 / 도매 / VIP
- 최소 주문 수량 (MOQ): 도매 10개, VIP 1개
- 수량 구간별 할인: 10~49개 ×0.9 / 50+ ×0.8 / VIP ×0.75
- B2B 회원가입 → 사업자등록증 업로드 → 운영자 승인 → 도매가 노출

## 환경변수

```env
WHOLESALE_ENABLED=1                        # 1=활성화 (기본 ON)
WHOLESALE_REQUIRE_BUSINESS_CERT=1          # 1=사업자등록증 업로드 필수
WHOLESALE_APPLICATIONS_PATH=data/wholesale_applications.jsonl
```

## 라우트

| 경로 | 설명 |
|---|---|
| `GET /seller/wholesale/tiers` | 도매 등급/할인 룰 관리 |
| `GET /seller/wholesale/applications` | B2B 신청 승인 큐 |
| `POST /seller/wholesale/applications/<id>/approve` | 신청 승인 |
| `POST /seller/wholesale/applications/<id>/reject` | 신청 거절 |

## 코드 모듈

```
src/wholesale/
  __init__.py
  tier_manager.py          — WholesaleTierManager, WholesaleTier, PriceLevel
  application_manager.py   — WholesaleApplicationManager, WholesaleApplication
```

## 가격 계산 예시

```python
from src.wholesale.tier_manager import WholesaleTierManager

mgr = WholesaleTierManager()
# 기준가 10,000원 × 30개 도매
price = mgr.calculate_price(10000, "wholesale", 30)
# → 9000 (× 0.9)
```

## Admin Diagnostics

`/admin/diagnostics` → "🏢 B2B 도매 (Phase 148)" 카드에서 현황 확인.

## 테스트

```bash
python3 -m pytest tests/test_wholesale_tiers.py -v
```
