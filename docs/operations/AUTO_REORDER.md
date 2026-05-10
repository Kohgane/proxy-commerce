# 자동 리오더 운영 가이드 (Phase 142)

## 개요

BI 분석(Phase 141)에서 추출한 재고 임박 SKU를 자동으로 감지하고
소싱처별 권장 발주량을 계산합니다.

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AUTO_REORDER_ENABLED` | `0` | 1=활성화 |
| `AUTO_REORDER_AUTO_PLACE` | `0` | 1=자동 발주 (기본: 운영자 승인 필요) |
| `AUTO_REORDER_DAILY_BUDGET_KRW` | `500000` | 일일 발주 예산 (원) |
| `AUTO_REORDER_SAFETY_DAYS` | `14` | 안전 재고 일수 |

## 권장 발주량 계산

```
권장발주량 = (리드타임일수 + 안전재고일수) × 일평균판매량 - 현재재고
```

예) 리드타임 7일, 안전재고 14일, 일평균 2개 판매, 현재재고 5개:
```
(7 + 14) × 2 - 5 = 37개
```

## 발주 승인 흐름

1. `AUTO_REORDER_AUTO_PLACE=0` (기본): 운영자가 `/seller/inventory/reorder`에서 승인
2. `AUTO_REORDER_AUTO_PLACE=1`: 예산 한도 내에서 자동 발주
3. 예산 초과 시 → 자동 거부 + 승인 필요 항목으로 전환

## 운영 페이지

- `/seller/inventory/reorder` — 권장 발주 목록, 일괄 승인
- `/admin/diagnostics` 섹션 9 — 발주 현황 요약

## 데이터 소스 우선순위

1. Phase 141 BI 분석 재고 임박 알림 (`src/analytics/reorder_alert.py`)
2. 재고 동기화 직접 조회 (`src/inventory/inventory_sync.py`)

## 발주 이력

Google Sheets `auto_reorder_log` 워크시트에 기록됩니다:
- 발주일시, SKU, 수량, 예상 비용, 상태
