# Shopify 연동 운영 가이드

## 1. 필요한 환경변수 / 시크릿
- `SHOPIFY_CLIENT_ID`
- `SHOPIFY_CLIENT_SECRET`
- `SHOPIFY_AUTO_TOKEN`
- `SHOPIFY_API_VERSION`
- `SHOPIFY_SHOP`

## 2. 필수 권한 / API 설정
- Shopify Admin 앱 설치
- `read_products`, `write_products`
- `read_inventory`, `write_inventory`
- `read_orders`, `write_orders`

## 3. 연결 테스트 순서
1. `/seller/markets` 또는 `/admin/diagnostics`에서 **연결 확인**
2. read 검증: `shop.json` 조회로 스토어 도메인/플랜 확인
3. write 검증: safe dry-run 상품 등록 검증 또는 payload validation 확인

## 4. 흔한 실패 원인과 해결 체크리스트
- `token_missing`: `SHOPIFY_SHOP` 또는 `SHOPIFY_AUTO_TOKEN` 누락
- `token_expired`: 401 응답, 토큰 재발급 필요
- `scope_insufficient`: 403 응답, 앱 scope 재설정 필요
- `api_error`: 404 도메인 오입력, 429 rate limit, 5xx 여부 확인

## 5. 확인 위치
- `/admin/diagnostics`
- `/seller/markets`
- Shopify Admin > Apps

## 6. 보안 주의사항
- Admin API 토큰과 client secret은 절대 커밋 금지
- `X-Shopify-Access-Token` 헤더와 웹훅 시크릿은 로그 마스킹
- 운영자 공유 시 store domain 외 민감값은 가려서 전달
