# SHOP.md — 자체몰 (코가네멀티샵) 운영 가이드 (Phase 131)

## 아키텍처

```
kohganepercentiii.com/shop/   → 자체몰 (B2C, Phase 131)
kohganepercentiii.com/seller/ → 셀러 콘솔 (운영자/셀러)
kohganepercentiii.com/admin/  → 어드민 패널
kohganepercentiii.com/api/    → REST API
```

### 컴포넌트

```
src/shop/
  __init__.py           # Blueprint 등록
  views.py              # Flask 라우트 (/shop/*)
  catalog.py            # ShopCatalog — Sheets 카탈로그 → 진열 상품
  cart.py               # Cart — Flask 세션 기반 장바구니
  checkout.py           # CheckoutService — 주문/결제/취소
  templates/shop/       # Jinja2 템플릿
  static/shop/          # CSS/JS
```

---

## catalog 워크시트 컬럼 정의

Google Sheets `catalog` 워크시트 컬럼 (이 순서대로 입력):

| 컬럼 | 필수 | 설명 |
|---|---|---|
| `sku` | — | 상품 코드 (고유 식별자) |
| `title_ko` | ✅ | 한국어 상품명 |
| `title_en` | — | 영문 상품명 |
| `price_krw` | ✅ | 정가 (원, 정수) |
| `sale_price_krw` | — | 할인가 (정가보다 낮아야 함) |
| `marketplace` | ✅ | `kohganemultishop` 또는 `all` |
| `state` | ✅ | `active` 또는 `inactive` |
| `slug` | — | URL 슬러그 (예: `alo-yoga-legging-xs`) — 미입력 시 제목에서 자동 생성 |
| `featured` | — | `true` / `false` — 메인 추천 노출 여부 |
| `category` | — | 카테고리명 (예: `yoga`, `outerwear`, `accessories`) |
| `thumbnail_url` | — | 대표 이미지 URL |
| `gallery_urls_json` | — | 갤러리 이미지 JSON 배열 (예: `["url1","url2"]`) |
| `description_html_short` | — | 단문 상품 설명 (목록 페이지) |
| `description_html_long` | — | HTML 상세 설명 (상품 상세 페이지) |
| `stock_qty` | — | 재고 수량 (정수, 0=품절) |
| `shipping_fee_krw` | — | 배송비 (원, 0=무료) |
| `options_json` | — | 옵션 JSON (예: `[{"name":"size","values":["XS","S","M"]}]`) |

### 진열 조건
1. `marketplace` == `kohganemultishop` 또는 `all`
2. `state` == `active`
3. `price_krw` > 0

---

## 토스페이먼츠 설정

### 테스트(Sandbox) 모드
키 미설정 시 자동으로 sandbox 모드 동작. 실제 결제 없음.

```bash
# 미설정 = sandbox 자동 사용 (아무것도 안 해도 됨)
```

### 운영(Live) 모드 전환
토스페이먼츠 대시보드(https://developers.tosspayments.com)에서 키 발급 후:

```bash
# Render 환경변수 등록
TOSS_CLIENT_KEY=live_ck_xxxxxxxxxxxx
TOSS_SECRET_KEY=live_sk_xxxxxxxxxxxx
```

주의사항:
- `TOSS_SECRET_KEY`는 절대 프론트엔드에 노출하지 말 것
- 모든 결제 승인은 서버에서 금액 재검증 후 처리 (위변조 방지)
- `ADAPTER_DRY_RUN=1` 시 실제 결제 API 호출 차단

---

## 텔레그램 알림 설정

신규 결제 완료 시 자동 알림:

```bash
TELEGRAM_BOT_TOKEN=7xxxxxxxxxx:AAxxxxx...
TELEGRAM_CHAT_ID=-100xxxxxxxxxx
```

알림 형식:
```
💰 신규 주문 #ORD-20260504-001
상품:
  Alo Yoga Legging XS x 2
금액: ₩150,000
구매자: 홍*동 (010-****-5678)
배송지: 서울시 강남구 ***
```

---

## 이메일 알림 설정

SendGrid 사용:

```bash
SENDGRID_API_KEY=SG.xxxxxxxxxxxx
```

미설정 시 이메일 발송 건너뜀.

---

## 운송장 자동 추적 (SweetTracker)

```bash
SWEETTRACKER_API_KEY=xxxxx
```

- cron 엔드포인트: `GET /cron/track-shipments`
- Render에서 Cron Job으로 30분마다 호출 권장
- 배송완료(level 6) 감지 시 → orders 시트 상태 `delivered` 갱신 + 텔레그램 알림

---

## ROOT_REDIRECT 환경변수

루트(`/`) 접속 시 동작 제어:

| 값 | 동작 |
|---|---|
| `seller` (기본) | `/seller/` 로 리다이렉트 (셀러 콘솔) |
| `shop` | `/shop/` 로 리다이렉트 (자체몰) |
| `landing` | 통합 랜딩 페이지 표시 |

---

## 자체몰 URL 구조

| URL | 설명 |
|---|---|
| `/shop/` | 메인 랜딩 (히어로 + 추천 상품 + 카테고리) |
| `/shop/products` | 상품 목록 (카테고리/검색 필터 + 페이지네이션) |
| `/shop/products/<slug>` | 상품 상세 페이지 |
| `/shop/cart` | 장바구니 |
| `/shop/checkout` | 결제 (배송지 입력 + 토스 위젯) |
| `/shop/checkout/confirm` | 토스 결제 승인 콜백 |
| `/shop/orders/<id>?token=...` | 주문 조회 (비로그인 token 방식) |
| `/shop/health` | 자체몰 헬스체크 JSON |
| `/cron/track-shipments` | 운송장 자동 추적 cron |

---

## Shopify / WooCommerce 연동

### Shopify
```bash
SHOPIFY_ACCESS_TOKEN=shpat_xxxxx
SHOPIFY_SHOP=myshop.myshopify.com
```

### WooCommerce
```bash
WC_KEY=ck_xxxxx    # 또는 WOO_CK
WC_SECRET=cs_xxxxx # 또는 WOO_CS
WC_URL=https://myshop.example.com  # 또는 WOO_BASE_URL
```

미설정 시 stub 모드. `ADAPTER_DRY_RUN=1` 시 실제 API 호출 차단.

---

## /health/deep 자체몰 체크

```json
{
  "name": "shop_catalog",
  "status": "ok",
  "detail": "진열 상품 12개 (featured 4개)"
},
{
  "name": "shop_payments",
  "status": "ok",
  "detail": "토스페이먼츠 활성 (sandbox)",
  "provider": "toss",
  "mode": "sandbox"
}
```

---

## 다음 단계

- **Phase 132**: 카카오/구글/네이버 로그인 + 마이페이지 + 주문이력
- **Phase 133**: 셀러 SaaS 가입 + 토스 정기결제(구독료)
- **Phase 134**: 약관/개인정보처리방침 페이지
- **Phase 135**: 모바일 PWA + 푸시 알림
