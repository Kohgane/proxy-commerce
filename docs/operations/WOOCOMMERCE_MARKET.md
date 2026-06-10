# WooCommerce 연동 운영 가이드

## 1. 필요한 환경변수 / 시크릿
- `WC_URL`
- `WC_KEY`
- `WC_SECRET`
- 별칭 사용 시 `WOO_BASE_URL`, `WOO_CK`, `WOO_CS`

## 2. 필수 권한 / API 설정
- WooCommerce REST API Key 생성
- 권한은 반드시 `Read/Write`

## 3. 연결 테스트 순서
1. `/seller/markets` 또는 `/admin/diagnostics`에서 **연결 확인**
2. read 검증: 상품 1건 조회
3. write 검증: safe dry-run 상품 등록 검증 확인

## 4. 흔한 실패 원인과 해결 체크리스트
- `token_missing`: URL / key / secret 등록 여부 확인
- `token_expired`: consumer key/secret 재발급 필요
- `scope_insufficient`: REST API Key 권한이 Read/Write인지 확인
- `api_error`: Basic Auth 전달, permalink, WordPress/WooCommerce 상태 확인

## 5. 확인 위치
- `/admin/diagnostics`
- `/seller/markets`
- WordPress 관리자 > WooCommerce > 설정 > 고급 > REST API

## 6. 보안 주의사항
- consumer key/secret은 Secret 저장소로만 관리
- Basic Auth 값이 로그/스크린샷에 노출되지 않게 한다
- 주문 노트/운송장 검증 시도도 시크릿과 분리해서 기록한다
