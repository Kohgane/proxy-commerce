# RETURNS_AUTOMATION (Phase 146)

## 환경변수

- `RETURNS_AUTO_APPROVE_ENABLED` (기본 `1`)
- `RETURNS_AUTO_APPROVE_MAX_KRW` (기본 `50000`)
- `RETURNS_AUTO_APPROVE_REASONS` (기본 `defective,wrong_item`)

## 동작

- 마켓 반품 요청 수집 → 사유 분류(`defective`, `wrong_item`, `change_of_mind`, `other`)
- 환불 정책 계산(단순변심 시 왕복배송비 6,000원 차감)
- 금액/사유 화이트리스트에 맞으면 자동 승인, 아니면 수동 승인 큐
- 셀러 화면: `/seller/returns/inbox`
