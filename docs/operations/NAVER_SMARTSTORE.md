# Naver Smartstore 연동 운영 가이드

## 1. 필요한 환경변수 / 시크릿
- `NAVER_COMMERCE_CLIENT_ID`
- `NAVER_COMMERCE_CLIENT_SECRET`
- `NAVER_COMMERCE_API_BASE` (기본 `https://api.commerce.naver.com/external`)
- 필요 시 `NAVER_HTTPS_PROXY`

## 2. 필수 권한 / API 설정
- 네이버 커머스API센터 앱 활성화
- 상품 조회/등록/수정 권한
- 주문 조회/발송 처리 권한
- 허용 IP 또는 프록시 설정

## 3. 연결 테스트 순서
1. `/seller/markets` 또는 `/admin/diagnostics`에서 **연결 확인**
2. read 검증: OAuth 토큰 발급 + 상품 1건 조회
3. write 검증: safe dry-run 상품 등록 검증 확인

## 4. 흔한 실패 원인과 해결 체크리스트
- `token_missing`: client id/secret/base URL 누락 여부 확인
- `token_expired`: client secret 서명 값 또는 토큰 재발급 필요
- `scope_insufficient`: 앱 권한 또는 스토어 승인 상태 확인
- `api_error`: `GW.IP_NOT_ALLOWED`, 429, 네트워크/프록시 오류 확인

## 5. 확인 위치
- `/admin/diagnostics`
- `/seller/markets`
- 네이버 커머스API센터
- 스마트스토어 판매자센터

## 6. 보안 주의사항
- client secret과 프록시 인증정보는 반드시 Secret 저장소로만 관리
- 프록시 URL, Authorization 헤더를 로그에 남기지 않는다
- 진단 스크린샷 공유 시 토큰/시크릿 일부도 노출되지 않게 확인한다
