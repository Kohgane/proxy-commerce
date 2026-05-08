# COMPETITOR_MONITORING (Phase 140)

## 지원 사이트

- 한국: 쿠팡, 스마트스토어, 11번가, G마켓, 옥션
- 일본: Amazon JP, 라쿠텐, Yahoo Shopping

## 기능

- 경쟁사 상품 URL CRUD (`/seller/pricing/competitors`)
- 본사 SKU와 1:N 매핑
- 가격/재고/배송비 스냅샷 수집
- 변동 이력 저장 (Sheets `competitor_prices` + JSONL 폴백)
- 임계값 초과 시 텔레그램 경고 (`PRICING_NOTIFY_THRESHOLD_PCT`)

## 주의사항

- `ADAPTER_DRY_RUN=1`이면 외부 스크랩 호출을 하지 않습니다.
- BudgetGuard를 확인한 뒤 스크랩을 수행합니다.
- 멀티워커 환경에서 JSONL 쓰기는 `tmp → replace` 원자 교체를 사용합니다.
