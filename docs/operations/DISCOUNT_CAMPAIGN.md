# 할인 캠페인 자동화 운영 가이드 (Phase 142)

## 개요

재고 과잉 SKU를 자동 추출하고 마진 가드를 통과한 할인율을 추천합니다.
쿠팡 할인 쿠폰, 스마트스토어 즉시 할인을 지원합니다.

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DISCOUNT_CAMPAIGN_ENABLED` | `0` | 1=활성화 |
| `DISCOUNT_CAMPAIGN_MAX_PCT` | `20` | 최대 할인율 (%) |
| `DISCOUNT_CAMPAIGN_MARGIN_FLOOR_PCT` | `10` | 마진 하한선 (%) — 이 이하 할인 불가 |
| `DISCOUNT_CAMPAIGN_OVERSTOCK_DAYS` | `60` | 재고 과잉 기준 (일 이상이면 과잉) |

## 캠페인 추천 로직

1. 현재 재고 ÷ 일평균 판매량 = 재고 소진 예상일
2. 예상일 > OVERSTOCK_DAYS → 재고 과잉으로 판단
3. 할인율 = min(MAX_PCT, max(5%, (재고일-30) ÷ 10))
4. 할인 후 마진 ≥ MARGIN_FLOOR_PCT → 캠페인 생성
5. 마진 미달 시 마진 하한선 기준으로 최대 가능 할인율로 조정

## 승인 흐름

1. `/seller/marketing/campaigns`에서 추천 캠페인 확인
2. 운영자가 캠페인별 승인 → 마켓 어댑터에 가격 적용
3. 마진 가드 미통과 캠페인은 자동 거부

## 운영 페이지

- `/seller/marketing/campaigns` — 추천/활성 캠페인 목록
- `/admin/diagnostics` 섹션 10 — 캠페인 현황 요약

## 마진 가드 연동

Phase 140 마진 가드(`src/pricing/margin_guard.py`)를 통해
할인 후에도 최소 마진이 보장되는 캠페인만 생성합니다.

## 지원 마켓

- 쿠팡: 즉시 할인 쿠폰
- 스마트스토어: 즉시 할인
