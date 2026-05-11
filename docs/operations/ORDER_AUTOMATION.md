# ORDER 자동화 (Phase 145)

- 모듈: `src/orders/auto_processor.py`
- 화면: `/seller/orders/auto`
- 환경변수:
  - `ORDER_AUTO_PROCESS_ENABLED` (기본 ON)
  - `ORDER_AUTO_PLACE_PO` (기본 OFF 권장)

주요 동작:
- 신규 주문 자동 검수(재고/주소/결제)
- 발주 생성(자동 발주 OFF면 수동 승인)
- 송장 동기화 상태 관리
- 단계별 알림(입금/발주/입고/출고/도착)
