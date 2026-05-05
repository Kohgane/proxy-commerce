# API_KEYS.md — 외부 API 키 발급 가이드 (Phase 130)

형이 발급할 모든 API 키 목록과 등록 방법. 총 24개 항목.

---

## ⚠️ 중요: Render Environment vs GitHub Secrets

**GitHub Secrets**는 GitHub Actions(CI/CD)에서만 사용됩니다. 앱은 읽지 못합니다.

**Render Dashboard → proxy-commerce → Environment** 탭에 등록해야 앱이 읽을 수 있습니다.

확인: [https://kohganepercentiii.com/seller/api-status](https://kohganepercentiii.com/seller/api-status)

---

## 카테고리별 요약

| 카테고리 | API | 환경변수 | 목적 |
|---|---|---|---|
| **마켓** | 쿠팡 윙 | COUPANG_VENDOR_ID, COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY | 쿠팡 상품/주문 |
| **마켓** | 스마트스토어 | NAVER_COMMERCE_CLIENT_ID, NAVER_COMMERCE_CLIENT_SECRET | 네이버 상품/주문 |
| **마켓** | 11번가 | ELEVENST_API_KEY | 11번가 상품/주문 |
| **소싱** | Amazon PA-API | AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG | Amazon 소싱 |
| **소싱** | 라쿠텐 | RAKUTEN_APP_ID | 일본 소싱 |
| **AI** | OpenAI | OPENAI_API_KEY | 번역 + 광고 카피 |
| **AI** | DeepL | DEEPL_API_KEY | 번역 (OpenAI 대체) |
| **결제** | 토스페이먼츠 | TOSS_CLIENT_KEY, TOSS_SECRET_KEY | 한국 결제 |
| **결제** | PayPal | PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET | 해외 결제 |
| **인증** | 카카오 | KAKAO_REST_API_KEY, KAKAO_CLIENT_SECRET | 카카오 로그인 |
| **인증** | Google OAuth | GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET | 구글 로그인 |
| **인증** | 네이버 로그인 | NAVER_CLIENT_ID, NAVER_CLIENT_SECRET | 네이버 로그인 |
| **알림** | 텔레그램 | TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID | 실시간 알림 |
| **알림** | SendGrid | SENDGRID_API_KEY | 이메일 발송 |
| **물류** | 스윗트래커 | SWEETTRACKER_API_KEY | 운송장 자동 추적 |
| **자체몰** | Shopify | SHOPIFY_ACCESS_TOKEN, SHOPIFY_SHOP | Shopify 자체몰 |
| **자체몰** | WooCommerce | WC_KEY, WC_SECRET, WC_URL | kohganemultishop.org 실연동 (Phase 132) |
| **유틸** | ExchangeRate-API | EXCHANGE_RATE_API_KEY | 실시간 환율 |
| **유틸** | Pexels | PEXELS_API_KEY | 무료 보조 이미지 |
| **유틸** | Unsplash | UNSPLASH_ACCESS_KEY | 무료 보조 이미지 |
| **인프라** | Google Sheets | GOOGLE_SHEET_ID, GOOGLE_SERVICE_JSON_B64 | 데이터 저장 |

---

## 별칭 매핑

환경변수 이름 다양성 대응 — 어떤 이름으로 등록해도 인식:

| 표준 이름 | 별칭 |
|---|---|
| NAVER_COMMERCE_CLIENT_ID | NAVER_API_CLIENT_ID |
| WC_URL | WOO_BASE_URL |
| WC_KEY | WOO_CK |
| WC_SECRET | WOO_CS |

---

## 상세 발급 가이드

### 1. 쿠팡 윙 OpenAPI

**발급 방법**
1. https://wing.coupang.com 로그인
2. 마이페이지 → 판매자 정보 → API 신청
3. 벤더 ID, 액세스 키, 시크릿 키 발급

**Render 환경변수**
```
COUPANG_VENDOR_ID=A001234567
COUPANG_ACCESS_KEY=xxxx
COUPANG_SECRET_KEY=yyyy
```

**활성화 후 사용처**: `/seller/markets`, `/seller/orders`, 상품 업로드

---

### 2. 네이버 커머스 API

**발급 방법**
1. https://commerce.naver.com/openapi/guide 접속
2. 애플리케이션 등록 → 클라이언트 ID / 시크릿 발급

**Render 환경변수**
```
NAVER_COMMERCE_CLIENT_ID=xxxx
NAVER_COMMERCE_CLIENT_SECRET=yyyy
```

**참고**: `NAVER_CLIENT_ID/SECRET`은 네이버 **로그인** API 용도입니다 (별개).

---

### 3. 11번가 OpenAPI

**발급 방법**
1. https://soffice.11st.co.kr 로그인
2. 판매자 서비스 → OpenAPI 신청

```
ELEVENST_API_KEY=xxxx
```

---

### 4. ExchangeRate-API

**발급 방법**: https://app.exchangerate-api.com 가입 (무료 1,500회/월)

```
EXCHANGE_RATE_API_KEY=xxxx
```

---

### 5. OpenAI API

**발급**: https://platform.openai.com/api-keys → Create new secret key

```
OPENAI_API_KEY=sk-xxxx
```

**활성화 후**: `/seller/collect` 미리보기에서 "번역/카피 생성" 버튼 활성화

---

### 6. DeepL API

**발급**: https://www.deepl.com/pro-api 가입

```
DEEPL_API_KEY=xxxx:fx
```

---

### 7. 토스페이먼츠

**발급**: https://app.tosspayments.com → 개발 → API 키

```
TOSS_CLIENT_KEY=test_ck_xxxx   # 테스트는 test_ prefix
TOSS_SECRET_KEY=test_sk_xxxx
```

---

### 8. 텔레그램 알림

**발급 방법**
1. @BotFather에게 `/newbot` 명령
2. Bot Token 발급
3. @userinfobot으로 Chat ID 확인

```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxyz
TELEGRAM_CHAT_ID=987654321
```

**활성화 후**: `/seller/notifications/test` 에서 테스트 메시지 전송 가능

---

### 9. 스윗트래커

**발급**: https://www.sweettracker.co.kr → API 서비스

```
SWEETTRACKER_API_KEY=xxxx
```

---

### 10. Shopify

**발급**: https://partners.shopify.com → Custom App → Admin API 접근 허용

```
SHOPIFY_ACCESS_TOKEN=shpat_xxxx
SHOPIFY_SHOP=myshop.myshopify.com
```

---

### 11. WooCommerce

**발급**: WordPress 관리자 → WooCommerce → 설정 → 고급 → REST API

```
WC_KEY=ck_xxxx
WC_SECRET=cs_xxxx
WC_URL=https://myshop.com
```

또는 별칭: `WOO_CK`, `WOO_CS`, `WOO_BASE_URL`

---

### 12. Pexels / Unsplash

```
PEXELS_API_KEY=xxxx        # https://www.pexels.com/api/
UNSPLASH_ACCESS_KEY=xxxx   # https://unsplash.com/developers
```

---

## Render Environment 등록 방법

1. [Render Dashboard](https://dashboard.render.com) → proxy-commerce → **Environment** 탭
2. **Add Environment Variable** → 이름과 값 입력
3. **Manual Deploy** → `/seller/api-status` 에서 활성화 확인

## 운영 안전장치

| 환경변수 | 효과 |
|---|---|
| `ADAPTER_DRY_RUN=1` | 모든 외부 API 호출 차단 (텔레그램/이메일 포함) |
| `FX_DISABLE_NETWORK=1` | 환율 네트워크 호출 비활성화 |

> **중요**: API 키 없어도 모든 화면이 stub/mock 데이터로 동작합니다.

