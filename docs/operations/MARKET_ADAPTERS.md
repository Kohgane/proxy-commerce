# MARKET_ADAPTERS (Phase 151)

- 기본 위치: `src/markets/adapters/`
- 기본 모드: `MARKET_ADAPTER_DEFAULT=mock`
- live 모드는 각 마켓 자격증명이 모두 있을 때만 사용

## 포함 어댑터

- `coupang_wing.py` — 쿠팡 윙 scaffold
- `naver_commerce.py` — 네이버 커머스 scaffold
- `eleven_st.py` — 11번가 scaffold
- `amazon.py` — Amazon SP-API scaffold (stub)
- `ebay.py` — eBay scaffold (stub)
- `shopify.py` — Shopify Admin API 실연동 (상품 생성/수정, 429 재시도, 멱등 업데이트)
- `shopee.py` — Shopee scaffold (stub)
- `mock.py` — 기본 mock

## 공통 인터페이스

- `create_listing(payload)`
- `update_inventory(sku, qty)`
- `get_order_status(external_order_id)`
- `is_configured()`
- `validate_listing(payload)`
- `upload_product(payload)`
- `marketplace_meta()`

## Shopify (Phase 184)

- Render 권장 env: `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SHOPIFY_AUTO_TOKEN`, `SHOPIFY_API_VERSION`, `SHOPIFY_SHOP`
- 인증 헤더: `X-Shopify-Access-Token: ${SHOPIFY_AUTO_TOKEN}` (하위호환: `SHOPIFY_ACCESS_TOKEN`/`SHOPIFY_ADMIN_TOKEN`)
- API 버전: `SHOPIFY_API_VERSION` (미설정 시 어댑터 기본값 `2026-04`)
- `SHOPIFY_CLIENT_SECRET`은 웹훅 검증 전용이며 상품 등록 토큰과 별개다.
- 자격증명 미설정 시 절대 성공 위조 없이 `not_configured` 상태를 반환한다.
- `/seller/markets`의 **Shopify 연결 확인** 버튼은 `GET /admin/api/{version}/shop.json` 진단 결과(스토어명/도메인/통화/플랜/실패 사유)를 표시한다.
