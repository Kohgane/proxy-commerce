# Shopify 자동화 토큰 설정 가이드 (Phase 184)

Render 환경변수는 아래 5개를 기준으로 설정합니다.

- `SHOPIFY_CLIENT_ID` = `68aa23f31fbb4f50e50357c68d5e8008` (앱 식별)
- `SHOPIFY_CLIENT_SECRET` = `shpss_***` (웹훅 HMAC 검증용)
- `SHOPIFY_AUTO_TOKEN` = `atk_***` (Admin API 호출용, `X-Shopify-Access-Token` 헤더 사용)
- `SHOPIFY_API_VERSION` = 예: `2026-04`
- `SHOPIFY_SHOP` = `catdyy-p0.myshopify.com`

하위호환으로 `SHOPIFY_ACCESS_TOKEN`/`SHOPIFY_ADMIN_TOKEN`도 읽지만, 운영 표준은 `SHOPIFY_AUTO_TOKEN`입니다.

## dev.shopify.com 앱 확인 항목

- Admin API 권한: `write_products`, `read_products`, `write_inventory`, `read_inventory`, `write_orders`, `read_orders`
- 앱 자동화 토큰 발급 후 `SHOPIFY_AUTO_TOKEN`에 저장

## 연결 확인 절차

1. `/seller/markets` 접속
2. **Shopify 연결 확인** 버튼 클릭
3. 성공 시 `shop.json` 기준 스토어 이름/도메인/통화/플랜 표시
4. 실패 시 HTTP 상태(401/403/404/429/5xx)와 사유를 정직하게 표시
