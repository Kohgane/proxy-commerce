# Coupang 연동 운영 가이드

## 1. 필요한 환경변수 / 시크릿
- `COUPANG_VENDOR_ID`
- `COUPANG_ACCESS_KEY`
- `COUPANG_SECRET_KEY`

## 2. 필수 권한 / API 설정
- 쿠팡 Wing OpenAPI 사용 승인
- 상품 조회/등록/수정 권한
- 주문 조회/배송 처리 권한

## 3. 연결 테스트 순서
1. `/seller/markets` 또는 `/admin/diagnostics`에서 **연결 확인**
2. read 검증: vendor 정보/상품 1건 조회가 성공하는지 확인
3. write 검증: safe dry-run 상품 등록 검증 결과가 `write_dry_run: ok`인지 확인

## 4. 흔한 실패 원인과 해결 체크리스트
- `token_missing`: 환경변수 3종이 모두 등록되었는지 확인
- `token_expired`: Access Key / Secret Key 재발급 후 반영
- `scope_insufficient`: Wing에서 API 권한이 주문/상품 모두 열려 있는지 확인
- `api_error`: 쿠팡 API 장애, rate limit, 잘못된 vendor id 여부 확인

## 5. 확인 위치
- `/admin/diagnostics`
- `/seller/markets`
- Coupang Wing 판매자센터

## 6. 보안 주의사항
- Access Key / Secret Key는 커밋하거나 로그에 남기지 않는다
- 운영 로그에는 마스킹된 키 힌트만 남긴다
- 실패 캡처를 공유할 때도 시크릿/서명 헤더는 반드시 가린다
