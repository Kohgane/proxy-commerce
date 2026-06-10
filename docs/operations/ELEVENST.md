# 11st 연동 운영 가이드

## 1. 필요한 환경변수 / 시크릿
- `ELEVENST_API_KEY`

## 2. 필수 권한 / API 설정
- 11번가 Seller Office API 키 발급
- 상품 조회/등록/수정 권한
- 주문 조회/배송 처리 권한

## 3. 연결 테스트 순서
1. `/seller/markets` 또는 `/admin/diagnostics`에서 **연결 확인**
2. read 검증: 상품 목록 1건 조회
3. write 검증: safe dry-run 상품 등록 검증 확인

## 4. 흔한 실패 원인과 해결 체크리스트
- `token_missing`: API Key 누락 여부 확인
- `token_expired`: 키 폐기/재발급 여부 확인
- `scope_insufficient`: Seller Office에서 연동 권한 범위 재확인
- `api_error`: XML/JSON 형식 오류, 429, 5xx 여부 확인

## 5. 확인 위치
- `/admin/diagnostics`
- `/seller/markets`
- 11번가 seller office

## 6. 보안 주의사항
- API Key는 Secret 저장소 외 평문 저장 금지
- 실패 로그에 원본 키/헤더를 남기지 않는다
- 외부 공유용 로그는 반드시 마스킹 후 전달한다
