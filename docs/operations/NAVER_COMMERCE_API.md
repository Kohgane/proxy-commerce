# NAVER_COMMERCE_API (Phase 151)

토큰 발급 헬퍼 위치: `src/markets/adapters/naver_commerce_auth.py`

## 환경변수

- `NAVER_COMMERCE_CLIENT_ID`
- `NAVER_COMMERCE_CLIENT_SECRET`
- `NAVER_COMMERCE_API_BASE` (기본 `https://api.commerce.naver.com/external`)

## 토큰 발급

- 엔드포인트: `/v1/oauth2/token`
- grant type: `client_credentials`
- type: `SELF`
- 요청 필드:
  - `client_id`
  - `timestamp` (ms)
  - `client_secret_sign`
  - `grant_type`
  - `type`

토큰은 메모리 캐시에 저장되며 만료 직전 자동 갱신됩니다.
