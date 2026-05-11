# SETTLEMENT (Phase 146)

## 환경변수

- `SETTLEMENT_TAX_RATE_PCT` (기본 `10`)
- `SETTLEMENT_REPORT_EMAIL` (기본 빈 값)

## 동작

- 월별 채널 정산 데이터 집계
- 수수료/광고비/배송비/환불 차감 후 실 입금 예정액 계산
- 세금계산서/카드 매출 필드 분리
- 셀러 화면: `/seller/settlement`
- 내보내기: `/seller/settlement/export.csv`, `/seller/settlement/export.xlsx`
