# API_KEYS.md — 외부 API 키 발급 가이드 (Phase 128)

형이 발급할 모든 API 키 목록과 등록 방법.

---

## 우선순위 요약

| 우선순위 | API | 환경변수 | 목적 |
|---|---|---|---|
| **P0** (지금) | 쿠팡 윙 | COUPANG_VENDOR_ID, COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY | 쿠팡 상품 등록/주문 조회 |
| **P0** (지금) | 스마트스토어 | NAVER_COMMERCE_CLIENT_ID, NAVER_COMMERCE_CLIENT_SECRET | 네이버 상품 등록/주문 |
| **P0** (지금) | 11번가 | ELEVENST_API_KEY | 11번가 상품 등록 |
| **P0** (지금) | ExchangeRate-API | EXCHANGE_RATE_API_KEY | 실시간 환율 |
| **P1** (나중) | Amazon PA-API | AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG | Amazon 소싱 |
| **P1** (나중) | 라쿠텐 | RAKUTEN_APP_ID | 일본 소싱 |
| **P2** (선택) | OpenAI | OPENAI_API_KEY | 번역 + 광고 카피 |
| **P2** (선택) | DeepL | DEEPL_API_KEY | 번역 (OpenAI 대체) |

---

## 1. 쿠팡 윙 OpenAPI

### 발급 방법
1. https://wing.coupang.com 로그인
2. 마이페이지 → 판매자 정보 → **API 신청**
3. 벤더 ID (COUPANG_VENDOR_ID), 액세스 키 (COUPANG_ACCESS_KEY), 시크릿 키 (COUPANG_SECRET_KEY) 발급

### 환경변수 등록 (Render)
```
COUPANG_VENDOR_ID=A001234567
COUPANG_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
COUPANG_SECRET_KEY=yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
```

---

## 2. 네이버 커머스 API (스마트스토어)

### 발급 방법
1. https://commerce.naver.com/openapi/guide 접속
2. 스마트스토어 셀러 계정으로 로그인
3. 애플리케이션 등록 → **클라이언트 ID / 시크릿** 발급

### 환경변수 등록
```
NAVER_COMMERCE_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxx
NAVER_COMMERCE_CLIENT_SECRET=yyyyyyyyyyyyyyyy
```

---

## 3. 11번가 OpenAPI

### 발급 방법
1. https://soffice.11st.co.kr 로그인
2. 판매자 서비스 → OpenAPI 신청
3. **API 키** 발급

### 환경변수 등록
```
ELEVENST_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 4. ExchangeRate-API (실시간 환율)

### 발급 방법
1. https://app.exchangerate-api.com 가입 (무료 플랜 1,500회/월)
2. Dashboard → Your API Key 복사

### 환경변수 등록
```
EXCHANGE_RATE_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 폴백 환율 (선택)
API 키 없을 때 사용할 환율 수동 설정:
```
FX_USDKRW=1350
FX_JPYKRW=9.0
FX_EURKRW=1480
FX_CNYKRW=186
```

---

## 5. Amazon Product Advertising API (PA-API 5.0)

### 발급 방법
1. Amazon Associates 프로그램 가입: https://affiliate-program.amazon.com
2. Amazon Associates Central → Tools → **Product Advertising API** 신청
3. 액세스 키, 시크릿 키, 파트너 태그 발급

### 환경변수 등록
```
AMAZON_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
AMAZON_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AMAZON_PARTNER_TAG=mystore-20
```

---

## 6. 라쿠텐 Web Service

### 발급 방법
1. https://webservice.rakuten.co.jp 로그인
2. アプリID (App ID) 발급

### 환경변수 등록
```
RAKUTEN_APP_ID=xxxxxxxxxxxxxxxxxxxx
```

---

## 7. OpenAI API

### 발급 방법
1. https://platform.openai.com/api-keys
2. **Create new secret key** → 복사

### 환경변수 등록
```
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 8. DeepL API

### 발급 방법
1. https://www.deepl.com/pro-api 가입
2. Authentication Key 발급

### 환경변수 등록
```
DEEPL_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx
```

---

## Render Environment 등록 방법

1. [Render Dashboard](https://dashboard.render.com) → proxy-commerce → **Environment** 탭
2. **Add Environment Variable** → 이름과 값 입력
3. 또는 **Secret Files** → `/etc/secrets/` 경로에 파일 저장
4. **Manual Deploy** → `/seller/api-status` 에서 활성화 확인

## 검증

등록 완료 후 다음 URL에서 상태 확인:
- **UI**: `https://kohganepercentiii.com/seller/api-status`
- **JSON**: `https://kohganepercentiii.com/seller/api-status/json`
- **헬스**: `https://kohganepercentiii.com/health/deep` → `external_apis` 필드

## 운영 안전장치

| 환경변수 | 효과 |
|---|---|
| `ADAPTER_DRY_RUN=1` | 마켓 API 실제 호출 차단 (테스트용) |
| `FX_DISABLE_NETWORK=1` | 환율 네트워크 호출 비활성화 |

> **중요**: API 키 없어도 모든 화면이 stub/mock 데이터로 동작합니다.
