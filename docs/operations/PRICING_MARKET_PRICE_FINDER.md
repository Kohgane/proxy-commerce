# Pricing Market Price Finder (Phase 153)

가격 결정 우선순위:
1. 실측 동일 상품 가격 중앙값(`actual_market_median`)
2. 경쟁사 분포(`competitor_distribution`)
3. 계산값(`calculated`)

환경변수:
- `NAVER_SHOPPING_SEARCH_CLIENT_ID`
- `NAVER_SHOPPING_SEARCH_CLIENT_SECRET`
- `COUPANG_SEARCH_API_KEY`
- `GOOGLE_SHOPPING_API_KEY`
- `PRICING_DECISION_PRIORITY`
- `PRICING_ACTUAL_DISCOUNT`
- `PRICING_LOSS_WARNING_ENABLED`

API 키가 없으면 안전한 mock 데이터로 폴백한다.
