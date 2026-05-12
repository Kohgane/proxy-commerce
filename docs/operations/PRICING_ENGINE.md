# PRICING_ENGINE (Phase 152)

- 입력: 원가(외화), 통화, 무게, 마켓, 카테고리, 목표 마진, 광고 비율, 경쟁사 가격
- 계산: 원가 KRW 환산 → 국제배송비 → 관세 → 부가세(랜디드 코스트) → 마켓/결제/광고 차감 → 목표 마진 반영
- 출력: 자동 계산가, 경쟁사 비교, 권장가(100원 단위), 실제 마진율

환경변수(override 가능):
- `PRICING_INTL_SHIPPING_PER_KG_KRW`
- `PRICING_DEFAULT_TARGET_MARGIN_PCT`
- `PRICING_DEFAULT_AD_BUDGET_PCT`
- `PRICING_MIN_MARGIN_GUARD_PCT`
- `PRICING_DEFAULT_WEIGHT_KG`
- `PRICING_CUSTOMS_*`, `PRICING_FEE_*`, `PRICING_PAYMENT_FEE`, `PRICING_VAT`, `PRICING_COMPETITOR_DISCOUNT`
