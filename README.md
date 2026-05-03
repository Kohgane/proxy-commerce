# Proxy Commerce — 해외 구매대행 자동화 플랫폼

> 🌐 **Live**: https://kohganepercentiii.com  
> [![Render](https://img.shields.io/badge/Render-Deployed-46E3B7?logo=render)](https://dashboard.render.com)
> [![Phase](https://img.shields.io/badge/Phase-123-blue)](ROADMAP.md)
> [![Tests](https://img.shields.io/badge/Tests-7000%2B-brightgreen)](tests/)

Python 3.11 + Flask 3 + Google Sheets 기반의 **완전 자동화된 해외 구매대행 운영 플랫폼**입니다.
크롤링부터 주문 라우팅, 재고 동기화, BI 분석, Staging/Production 배포까지 모든 단계를 자동화합니다.

---

## 🌐 둘러볼 화면

| URL | 화면 |
|---|---|
| [`/`](https://kohganepercentiii.com/) | 랜딩 |
| [`/seller/`](https://kohganepercentiii.com/seller/) | 셀러 콘솔 (Phase 122) |
| [`/admin/`](https://kohganepercentiii.com/admin/) | 관리자 패널 |
| [`/api/docs`](https://kohganepercentiii.com/api/docs) | API 문서 |
| [`/health/deep`](https://kohganepercentiii.com/health/deep) | 시스템 상태 |

---

## 🚀 Quick Deploy (Render)

1. **Fork** 또는 이 레포를 Render에 연결
2. `render.yaml` Blueprint 자동 적용 → `proxy-commerce` 서비스 생성
3. Render 대시보드 → **Environment** 에 시크릿 등록 ([환경변수 가이드](docs/deployment/ENV_VARS.md))
4. `main` 브랜치 push 시 자동 배포

```bash
# 배포 후 헬스체크
curl https://kohganepercentiii.com/health
python scripts/render_smoke.py https://kohganepercentiii.com
```

> 📖 **전체 배포 가이드**: [docs/deployment/DOMAIN_CLOUDFLARE.md](docs/deployment/DOMAIN_CLOUDFLARE.md)

---

## 📚 운영 문서

| 문서 | 내용 |
|------|------|
| [📋 RUNBOOK](docs/operations/RUNBOOK.md) | 일일/주간/월간 체크리스트, 장애 대응 플레이북 |
| [🗺️ SYSTEM_OVERVIEW](docs/operations/SYSTEM_OVERVIEW.md) | Phase 1~120 전체 요약, 데이터 플로우 다이어그램 |
| [✅ STABILIZATION_CHECKLIST](docs/operations/STABILIZATION_CHECKLIST.md) | Known limitation + 실서비스 전환 체크리스트 |
| [🖥️ SITE_PREVIEW_GUIDE](docs/operations/SITE_PREVIEW_GUIDE.md) | 화면별 미리보기 + 수정 파일 매핑 |
| [🔑 ENV_VARS](docs/deployment/ENV_VARS.md) | 환경변수 전체 목록 + Render 등록 방법 |
| [🌐 DOMAIN_CLOUDFLARE](docs/deployment/DOMAIN_CLOUDFLARE.md) | 도메인 구매 + Cloudflare DNS 연결 상세 가이드 |

---

## 📊 Phase 누적 통계 (Phase 1 → 120)

| 항목 | 수치 |
|------|------|
| 완료 Phase | 120 |
| 총 테스트 수 | 7,000+ |
| 주요 모듈 수 | 80+ |
| API 엔드포인트 | 200+ |
| 봇 커맨드 | 50+ |
| 지원 판매 채널 | 쿠팡, 네이버, WooCommerce, Shopify |
| 지원 소싱처 | Amazon US/JP, 타오바오, 1688 |
| 지원 알림 채널 | 텔레그램, 이메일, 카카오 |

---

## 목차

1. [아키텍처](#아키텍처)
2. [주요 기능](#주요-기능)
3. [빠른 시작](#빠른-시작)
4. [환경변수 매뉴얼](#환경변수-매뉴얼)
5. [API 엔드포인트](#api-엔드포인트)
6. [CLI 명령어](#cli-명령어)
7. [배포 가이드](#배포-가이드)
8. [기여 가이드](#기여-가이드)

---

## 아키텍처

```
┌────────────────────────────────────────────────────────┐
│                   외부 판매 채널                         │
│    Shopify (글로벌/다통화)  ·  WooCommerce (국내)         │
└────────────────┬───────────────────┬───────────────────┘
                 │ 주문 웹훅            │ 상품 동기화
                 ▼                   ▼
┌────────────────────────────────────────────────────────┐
│              order_webhook.py  (Flask 3)               │
│   POST /webhook/shopify/order  (HMAC + Rate Limit)     │
│   POST /webhook/forwarder/tracking                     │
│   GET  /health  /health/ready  /health/deep            │
└────────────────┬───────────────────────────────────────┘
                 │
        ┌────────▼────────────────────────┐
        │       src/orders/               │
        │   OrderRouter → CatalogLookup   │
        │   InternationalRouter           │
        │   OrderNotifier (Telegram)      │
        │   OrderTracker  (Sheets)        │
        └────────┬────────────────────────┘
                 │
    ┌────────────▼──────────────┐  ┌──────────────────────┐
    │   src/vendors/            │  │  src/inventory/      │
    │   ShopifyClient (REST/GQL)│  │  InventorySync       │
    │   WooCommerceClient       │  │  StockChecker        │
    │   PorterVendor            │  │  StockAlerts         │
    │   MemoPariVendor          │  └──────────────────────┘
    └───────────────────────────┘
                 │
    ┌────────────▼──────────────┐  ┌──────────────────────┐
    │   src/fx/                 │  │  src/dashboard/      │
    │   FXProvider (다중공급사)  │  │  DailySummary        │
    │   FXCache (Sheets 영속)   │  │  RevenueReporter     │
    │   FXUpdater               │  │  OrderStatusTracker  │
    └───────────────────────────┘  └──────────────────────┘
                 │
    ┌────────────▼──────────────────────────────────────┐
    │               src/analytics/ (Phase 7 BI)         │
    │   BusinessAnalytics · AutoPricingEngine           │
    │   ReorderAlertManager · PeriodicReportGenerator   │
    │   NewProductDetector                              │
    └───────────────────────────────────────────────────┘
                 │
    ┌────────────▼──────────────┐
    │   Google Sheets (데이터 허브) │
    │   catalog / orders / fx_rates / fx_history       │
    │   weekly_reports / monthly_reports / ...         │
    └───────────────────────────────────────────────────┘
```

**데이터 흐름:**
```
벤더 사이트 → src/scrapers → Google Sheets(catalog)
                                      ↓
                              src/price.py (랜딩 코스트)
                              src/translate.py (DeepL)
                                      ↓
                     Shopify / WooCommerce (상품 등록)
                                      ↓
                       고객 주문 → order_webhook
                                      ↓
                     OrderRouter → 벤더 구매 지시 (Telegram)
                                      ↓
                     배대지 배송 → tracking webhook
                                      ↓
                       Shopify fulfillment 업데이트
```

---

## 🛒 셀러 콘솔 (Phase 122)

셀러(=운영자) 관점의 SaaS UI. `/seller/` URL로 접근.

| 화면 | URL | 설명 |
|------|-----|------|
| 대시보드 | `/seller/dashboard` | 오늘 KPI·수집큐·마켓현황·알림·환율 통합 |
| 수동 수집기 | `/seller/collect` | 상품 URL → 추출 → 편집 → 마켓 업로드 |
| 마진 계산기 | `/seller/pricing` | 원가+관세+수수료+환율 기반 실시간 마진 계산 |
| 마켓 현황 | `/seller/market-status` | 쿠팡/스마트스토어/11번가 상품 상태 모니터링 |

**비전 마스터 문서**: [docs/vision/MASTER_VISION.md](docs/vision/MASTER_VISION.md)

### 수동 수집기 사용법 (3단계)

1. **URL 입력**: `/seller/collect` 접속 → 상품 URL 붙여넣기
   (Amazon, 타오바오, 1688, Porter, Memo, Alo Yoga, lululemon 등)

2. **메타데이터 추출**: "🔍 메타데이터 추출" 버튼 클릭
   → 이미지/제목(한국어)/가격/옵션/마진 슬라이더 미리보기

3. **마켓 업로드**: 업로드 대상 마켓 선택(쿠팡/스스/11번가/WC) → "📤 업로드" 버튼

> **참고**: 현재 모든 어댑터는 mock 데이터 기반. 실 스크래핑은 Phase 123 PR에서 처리.

---

## 주요 기능

### Phase 1 — 기반
| 기능 | 설명 |
|------|------|
| 🌏 다중통화 지원 | JPY·EUR·USD → KRW 랜딩 코스트 자동 계산 (관·부가세 포함) |
| 🌐 DeepL 다국어 번역 | 일본어·프랑스어 → 한국어·영어 자동 번역 + 인메모리 캐시 |
| 🏷️ 소싱 벤더 모듈 | Porter(일), Memo Paris(프) 상품 정규화 |
| 🕷️ 크롤러/스크래퍼 | Listly CSV → Google Sheets 카탈로그 자동 적재 |

### Phase 2 — 판매 채널
| 기능 | 설명 |
|------|------|
| 📦 퍼센티 CSV | 국내 판매채널 상품 내보내기 |
| 🛒 Shopify | HMAC 검증, Retry, GraphQL/REST, Markets 다통화 |
| 🛍️ WooCommerce | REST API 기반 국내 스토어 연동 |

### Phase 3 — 주문
| 기능 | 설명 |
|------|------|
| 🔀 자동 주문 라우팅 | SKU→벤더 매핑, 배대지 자동 배정 |
| 🌍 국제 라우팅 | 국가별 배송 전략 + Shopify Markets |

### Phase 4 — 모니터링
| 기능 | 설명 |
|------|------|
| 📊 모니터링 대시보드 | 주문 상태 추적, 매출/마진 분석 |
| 📦 재고 자동 동기화 | 벤더 재고 확인 → 카탈로그/스토어 자동 반영 |
| 💱 실시간 환율 | frankfurter.app API → Google Sheets 캐시 → 자동 갱신 |

### Phase 5-3 — 인프라
| 기능 | 설명 |
|------|------|
| 🐳 Docker + Gunicorn | 프로덕션급 컨테이너 배포 |
| 🚀 Staging/Production 분리 | 환경별 docker-compose, CD 워크플로 |

### Phase 6 — 글로벌
| 기능 | 설명 |
|------|------|
| ✈️ 다국가 배송/세금 엔진 | 13개국 배송비·관세 자동 계산 |
| 💰 Shopify Markets 다통화 | USD·EUR·JPY 자동 가격 노출 |

### Phase 7 — BI
| 기능 | 설명 |
|------|------|
| 📈 비즈니스 분석 | 국가별·브랜드별·채널별 매출/마진/트렌드 |
| 💸 자동 가격 조정 | 환율 변동 시 마진 보호 자동 가격 재계산 |
| 📦 재주문 알림 | 판매 속도 기반 재주문 시점 예측 |
| 📋 주간/월간 리포트 | Telegram + Google Sheets 자동 발송 |
| 🆕 신상품 감지 | 벤더 신상품 자동 감지 + 카탈로그 등록 제안 |

### Phase 8 — 프로덕션 안정화
| 기능 | 설명 |
|------|------|
| 🧪 통합 테스트 | 전 모듈 단위/통합 테스트 (944+ 테스트) |
| 🔒 Rate Limiting | Flask-Limiter 기반 웹훅/헬스체크 요청 제한 |
| 🌐 CORS | Flask-Cors 기반 헬스체크 엔드포인트 CORS 설정 |
| ⚡ TTL 캐시 유틸 | `src/utils/cache.py` — 환율·번역·재고 캐싱 통합 |
| 📊 Deep Healthcheck | `/health/deep` — Sheets·시크릿·업타임 통합 검증 |

---

## 빠른 시작

### 1. 사전 준비

```bash
# Python 3.11 이상 필요
python --version

# 저장소 클론
git clone https://github.com/Kohgane/proxy-commerce.git
cd proxy-commerce

# 가상환경 생성 및 패키지 설치
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-cov  # 개발/테스트용
```

### 2. 환경변수 설정

```bash
# 예시 파일 복사 후 값 입력
cp .env.example .env
# 편집기로 .env 열고 필수 값 입력
```

최소 필요 환경변수:
```bash
GOOGLE_SERVICE_JSON_B64=<base64 인코딩된 서비스계정 JSON>
GOOGLE_SHEET_ID=<Google Sheets 파일 ID>
SHOPIFY_SHOP=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxx
SHOPIFY_CLIENT_SECRET=shpss_xxxxx
```

### 3. Google Sheets 설정 (자격증명 등록)

#### 방법 1 — Render Secret File (권장 ⭐)

Render 배포 시 가장 안정적인 방법입니다. base64 인코딩이 필요 없습니다.

1. Render Dashboard → 서비스 → **Environment** 탭
2. **Secret Files** 섹션 → **Add Secret File**
3. Filename: `service-account.json`
4. Contents: `service-account.json` 파일 내용 그대로 붙여넣기 (base64 X)
5. Save → 자동 재배포

`/health/deep` 에서 `google_credentials.source = "secret_file:/etc/secrets/service-account.json"` 으로 확인.

#### 방법 2 — 환경변수 (base64)

```bash
# Linux / Mac / Git Bash (LF 보장, 줄바꿈 없이)
base64 -w 0 service-account.json > sa_b64.txt

# 검증 (올바른 JSON이 나와야 함)
cat sa_b64.txt | base64 -d | python3 -m json.tool | head -3

# 길이 확인 (보통 3000~4500자)
wc -c sa_b64.txt
```

Render → Environment Variables → `GOOGLE_SERVICE_JSON_B64` 에 `sa_b64.txt` 내용 붙여넣기.

> ⚠️ Windows base64 도구 사용 시 **LF (Unix)** 옵션 선택, 줄바꿈 없이 한 줄로 출력할 것.

#### 방법 3 — 환경변수 (raw JSON)

`GOOGLE_SERVICE_JSON` 환경변수에 JSON 전체를 그대로 붙여넣기.
특수문자(`"`, `\n` 등) 이스케이프에 주의.

#### 등록 후 검증

```bash
curl https://your-service.onrender.com/health/deep | python3 -m json.tool
# google_credentials.source 필드로 어느 소스가 사용 중인지 확인
# google_sheets.status 가 ok 이면 완료
```

1. Google Cloud Console에서 서비스 계정 생성
2. Google Sheets API 활성화
3. 서비스 계정에 대상 시트 편집 권한 부여 (시트 공유 → 서비스계정 이메일 → 편집자)
4. 위 방법 중 하나로 자격증명 등록
5. Google Sheet에 다음 워크시트 생성:
   - `catalog` — 상품 카탈로그
   - `orders` — 주문 이력
   - `fx_rates` — 환율 캐시
   - `fx_history` — 환율 이력

### 4. 로컬 실행

```bash
# 환경변수 로드
export $(grep -v '^#' .env | xargs)

# 웹훅 서버 실행
python -m src.order_webhook

# 테스트 실행
python -m pytest tests/ --no-cov -q

# 커버리지 포함 테스트
python -m pytest tests/
```

### 5. Docker 실행

```bash
# 빌드 및 실행
docker build -t proxy-commerce .
docker run -p 8000:8000 --env-file .env proxy-commerce

# Docker Compose
docker-compose up -d

# Staging 환경
docker-compose -f docker-compose.staging.yml up -d

# Production 환경
docker-compose -f docker-compose.production.yml up -d
```

---

## 환경변수 매뉴얼

### 핵심 (필수)

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `GOOGLE_SERVICE_JSON_B64` | Google 서비스계정 JSON (base64) | — | ✅ |
| `GOOGLE_SHEET_ID` | Google Sheets 파일 ID | — | ✅ |
| `SHOPIFY_SHOP` | Shopify 도메인 (`xxx.myshopify.com`) | — | ✅ |
| `SHOPIFY_ACCESS_TOKEN` | Shopify Admin API Token | — | ✅ |
| `SHOPIFY_CLIENT_SECRET` | Shopify App Secret (웹훅 HMAC 검증) | — | ✅ |

### 판매 채널

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `WOO_BASE_URL` | WooCommerce 사이트 URL | — | WooCommerce 사용 시 |
| `WOO_CK` | WooCommerce Consumer Key | — | WooCommerce 사용 시 |
| `WOO_CS` | WooCommerce Consumer Secret | — | WooCommerce 사용 시 |
| `WOO_API_VERSION` | WooCommerce API 버전 | `wc/v3` | ❌ |
| `SHOPIFY_API_VERSION` | Shopify API 버전 | `2024-07` | ❌ |
| `SHOPIFY_LOCATION_ID` | Shopify 재고 위치 ID | — | ❌ |
| `SHOPIFY_MARKETS_ENABLED` | Shopify Markets 활성화 | `1` | ❌ |

### 번역

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `TRANSLATE_PROVIDER` | 번역 공급자 (`deepl` \| `none`) | `deepl` | ❌ |
| `DEEPL_API_KEY` | DeepL API 키 | — | 번역 사용 시 |
| `DEEPL_API_URL` | DeepL API 엔드포인트 | Free API URL | ❌ |

### 환율

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `FX_USE_LIVE` | 실시간 환율 사용 | `1` | ❌ |
| `FX_PROVIDER` | 환율 공급자 (`frankfurter` \| `exchangerate-api`) | `frankfurter` | ❌ |
| `FX_CACHE_TTL` | 환율 캐시 유효 시간 (초) | `3600` | ❌ |
| `FX_USDKRW` | 수동 USD/KRW 환율 | `1350` | ❌ |
| `FX_JPYKRW` | 수동 JPY/KRW 환율 | `9.0` | ❌ |
| `FX_EURKRW` | 수동 EUR/KRW 환율 | `1470` | ❌ |
| `FX_CHANGE_ALERT_PCT` | 환율 급변 알림 임계값 % | `3.0` | ❌ |
| `EXCHANGERATE_API_KEY` | exchangerate-api.com 키 | — | exchangerate-api 사용 시 |

### 알림

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | — | 알림 사용 시 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | — | 알림 사용 시 |
| `TELEGRAM_ENABLED` | Telegram 알림 활성화 | `1` | ❌ |
| `EMAIL_ENABLED` | 이메일 알림 활성화 | `0` | ❌ |
| `NOTION_TOKEN` | Notion API 토큰 | — | ❌ |
| `NOTION_DB` | Notion 데이터베이스 ID | — | ❌ |

### 재고 동기화

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `INVENTORY_SYNC_ENABLED` | 재고 동기화 활성화 | `1` | ❌ |
| `LOW_STOCK_THRESHOLD` | 재고 부족 임계값 | `3` | ❌ |
| `PRICE_CHANGE_THRESHOLD_PCT` | 가격 변동 알림 임계값 % | `5.0` | ❌ |
| `STOCK_CHECK_DELAY` | 벤더 요청 간격 (초) | `2` | ❌ |
| `INVENTORY_CHECK_TIMEOUT` | HTTP 타임아웃 (초) | `15` | ❌ |

### 가격/마진

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `TARGET_MARGIN_PCT` | 목표 마진율 % | `22` | ❌ |
| `MIN_MARGIN_PCT` | 최소 마진율 % (자동가격조정) | `10` | ❌ |
| `MAX_PRICE_CHANGE_PCT` | 최대 가격 변동폭 % | `8` | ❌ |
| `AUTO_PRICING_ENABLED` | 자동 가격 조정 활성화 | `1` | ❌ |
| `AUTO_PRICING_MODE` | 자동 가격 조정 모드 (`DRY_RUN` \| `APPLY`) | `DRY_RUN` | ❌ |
| `CUSTOMS_THRESHOLD_KRW` | 관세 면세 한도 (KRW) | `150000` | ❌ |
| `CUSTOMS_RATE_DEFAULT` | 기본 관세율 | `0.20` | ❌ |
| `SHIPPING_FEE_DEFAULT` | 기본 배송비 (KRW) | `12000` | ❌ |
| `FORWARDER_FEE_JPY` | 배대지 수수료 (JPY) | `300` | ❌ |

### 보안 / Rate Limiting

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `RATE_LIMIT_ENABLED` | Rate Limiting 활성화 | `1` | ❌ |
| `RATE_LIMIT_WEBHOOK` | 웹훅 요청 제한 | `60 per minute` | ❌ |
| `RATE_LIMIT_HEALTH` | 헬스체크 요청 제한 | `120 per minute` | ❌ |
| `CORS_ORIGINS` | CORS 허용 오리진 | `*` | ❌ |

### 서버

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `PORT` | 서버 포트 | `8000` | ❌ |
| `APP_VERSION` | 앱 버전 (헬스체크 응답) | `dev` | ❌ |
| `APP_ENV` | 환경 (`development` \| `staging` \| `production`) | `development` | ❌ |
| `GUNICORN_WORKERS` | Gunicorn 워커 수 | `2` | ❌ |
| `GUNICORN_TIMEOUT` | Gunicorn 타임아웃 (초) | `120` | ❌ |

### 워크시트

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `WORKSHEET` | 카탈로그 워크시트명 | `catalog` | ❌ |
| `ORDERS_WORKSHEET` | 주문 워크시트명 | `orders` | ❌ |
| `FX_RATES_WORKSHEET` | 환율 캐시 워크시트명 | `fx_rates` | ❌ |
| `FX_HISTORY_WORKSHEET` | 환율 이력 워크시트명 | `fx_history` | ❌ |

---

## API 엔드포인트

### 웹훅

| 메서드 | URL | 설명 | 인증 |
|--------|-----|------|------|
| `POST` | `/webhook/shopify/order` | Shopify 주문 수신 | HMAC 서명 |
| `POST` | `/webhook/forwarder/tracking` | 배대지 배송 추적 업데이트 | — |

**Shopify 주문 웹훅 등록:**
```bash
# Shopify Admin에서 웹훅 URL 등록
# URL: https://your-server.com/webhook/shopify/order
# 이벤트: orders/create
```

**배송 추적 업데이트 예시:**
```bash
curl -X POST https://your-server.com/webhook/forwarder/tracking \
  -H 'Content-Type: application/json' \
  -d '{
    "order_id": "12345",
    "sku": "PTR-TNK-001",
    "tracking_number": "JD123456789KR",
    "carrier": "CJ대한통운",
    "status": "in_transit"
  }'
```

### 헬스체크

| 메서드 | URL | 설명 | 응답 |
|--------|-----|------|------|
| `GET` | `/health` | 기본 헬스체크 | `{"status":"ok","service":"proxy-commerce","version":"..."}` |
| `GET` | `/health/ready` | Readiness check (시크릿 검증) | `{"status":"ready","checks":{...}}` |
| `GET` | `/health/deep` | Deep healthcheck (Sheets + 시크릿 + 업타임) | `{"status":"ok","checks":{...},"uptime_seconds":...}` |

**헬스체크 예시:**
```bash
curl http://localhost:8000/health
# {"status":"ok","service":"proxy-commerce","version":"8.0.0"}

curl http://localhost:8000/health/ready
# {"status":"ready","checks":{"secrets_core":true}}

curl http://localhost:8000/health/deep
# {"status":"ok","timestamp":"2026-03-23T17:00:00+00:00","uptime_seconds":3600.0,
#  "version":"8.0.0","checks":{"secrets_core":true,"google_sheets":true}}
```

---

## CLI 명령어

### 크롤러/스크래퍼

```bash
# Porter 상품 적재
python -m src.scrapers.cli --vendor porter --file data/porter_raw.csv

# Memo Paris 상품 적재
python -m src.scrapers.cli --vendor memo_paris --file data/memo_raw.csv

# DRY_RUN (시트에 쓰지 않고 확인만)
python -m src.scrapers.cli --vendor porter --file data/porter_raw_sample.csv --dry-run
```

### 대시보드

```bash
# 일일 요약 발송 (Telegram/이메일)
python -m src.dashboard.cli --action daily-summary

# 특정 날짜 일일 요약
python -m src.dashboard.cli --action daily-summary --date 2026-03-23

# 매출 리포트 (일별/주별/월별)
python -m src.dashboard.cli --action revenue --period daily --date 2026-03-23
python -m src.dashboard.cli --action revenue --period weekly --week-start 2026-03-17
python -m src.dashboard.cli --action revenue --period monthly --month 2026-03

# 주문 상태 조회
python -m src.dashboard.cli --action status --filter pending
python -m src.dashboard.cli --action status --order-id 12345

# 마진 분석
python -m src.dashboard.cli --action margin-analysis
```

### 재고 동기화

```bash
# 전체 재고 동기화
python -m src.inventory.cli --action full-sync

# DRY_RUN (변경사항 확인만)
python -m src.inventory.cli --action full-sync --dry-run

# 단일 SKU 확인
python -m src.inventory.cli --action check --sku PTR-TNK-001

# 특정 벤더만 확인
python -m src.inventory.cli --action check-all --vendor porter

# 동기화 리포트
python -m src.inventory.cli --action report
```

### 환율

```bash
# 환율 업데이트
python -m src.fx.cli --action update

# 강제 갱신 (캐시 무시)
python -m src.fx.cli --action update --force

# DRY_RUN
python -m src.fx.cli --action update --dry-run

# 현재 환율 확인
python -m src.fx.cli --action current

# 최근 30일 이력
python -m src.fx.cli --action history --days 30

# 환율 변동 기반 가격 재계산
python -m src.fx.cli --action recalculate --dry-run
```

### 판매 채널

```bash
# Shopify 상품 내보내기
python -m src.channels.cli --channel shopify --action export

# WooCommerce 상품 동기화
python -m src.channels.cli --channel woocommerce --action sync

# 퍼센티 CSV 내보내기
python -m src.channels.cli --channel percenty --action export
```

### BI / 분석 (Phase 7)

```bash
# 자동 가격 조정 (DRY_RUN)
python -m src.analytics.cli --action auto-pricing --dry-run

# 주간 리포트 발송
python -m src.analytics.cli --action weekly-report

# 월간 리포트 발송
python -m src.analytics.cli --action monthly-report

# 신상품 감지
python -m src.analytics.cli --action detect-new-products

# 재주문 알림
python -m src.analytics.cli --action reorder-check
```

### 보안 / 환경변수 검증

```bash
# 필수 환경변수 검증
python scripts/validate_env.py

# .env 파일 생성 템플릿
python scripts/generate_env.py --env staging > .env.staging

# 배포 후 헬스체크
python scripts/post_deploy_check.py --url https://your-server.com
```

---

## 배포 가이드

### 로컬 → Staging

```bash
# 1. Staging 환경변수 설정
cp .env.example .env.staging
# .env.staging 수정 (APP_ENV=staging, DRY_RUN 등)

# 2. Staging Docker Compose 실행
docker-compose -f docker-compose.staging.yml up -d

# 3. 헬스체크
curl http://localhost:8001/health/deep
```

### Staging → Production

```bash
# 1. git tag 생성 (Production CD 트리거)
git tag v8.0.0
git push origin v8.0.0

# 2. GitHub Actions > cd_production.yml 에서 수동 승인

# 3. 배포 후 검증
python scripts/post_deploy_check.py --url https://your-production-server.com
```

### Render 배포

`render.yaml` Blueprint를 사용하면 Staging/Production 서비스를 자동 생성합니다:
```bash
# Render CLI로 배포
render blueprint apply
```

### GitHub Actions 워크플로

| 워크플로 | 트리거 | 설명 |
|---------|--------|------|
| `daily_summary.yml` | 매일 22:00 KST | 일일 운영 요약 |
| `inventory_sync.yml` | 4시간마다 | 재고 자동 동기화 |
| `fx_update.yml` | 하루 4회 | 환율 자동 갱신 |
| `auto_pricing_check.yml` | 매일 07:00 KST | 자동 가격 조정 |
| `weekly_report.yml` | 매주 월요일 09:00 KST | 주간 리포트 |
| `monthly_report.yml` | 매월 1일 09:00 KST | 월간 리포트 |
| `new_product_check.yml` | 매일 10:00 KST | 신상품 감지 |
| `cd_staging.yml` | main push | Staging 자동 배포 |
| `cd_production.yml` | v* 태그 | Production 수동 승인 배포 |

---

## 기여 가이드

### 코드 스타일

```bash
# flake8 린트 (max-line-length=120)
flake8 src/ tests/ scripts/

# 테스트 실행
python -m pytest tests/ -q

# 커버리지 확인
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### PR 규칙

1. **브랜치 이름**: `feature/`, `fix/`, `refactor/`, `docs/` 접두사 사용
2. **커밋 메시지**: Conventional Commits 형식 (`feat:`, `fix:`, `docs:`, `test:`)
3. **테스트**: 모든 변경에 대한 테스트 추가 (커버리지 유지)
4. **flake8**: 린트 오류 없어야 함
5. **한글 주석**: 비즈니스 로직 주석은 한국어로 작성
6. **mock**: 모든 테스트는 외부 서비스 호출 없이 mock으로 처리

### 디렉토리 구조

```
src/
├── analytics/      Phase 7 — BI + 운영 자동화
├── auth/           Shopify OAuth
├── channels/       Phase 2 — 판매 채널
├── dashboard/      Phase 4 — 모니터링
├── fx/             Phase 4-3 — 환율
├── inventory/      Phase 4-2 — 재고
├── orders/         Phase 3 — 주문 라우팅
├── scrapers/       Phase 1-4 — 크롤러
├── shipping/       Phase 6-1 — 배송/세금
├── vendors/        Phase 1-3 — 소싱 벤더
├── utils/
│   ├── cache.py        TTL 인메모리 캐시
│   ├── rate_limiter.py Flask-Limiter 미들웨어
│   ├── secret_check.py 환경변수 검증
│   ├── sheets.py       Google Sheets 연결
│   ├── telegram.py     Telegram 알림
│   └── emailer.py      이메일 알림
├── catalog_sync.py
├── order_webhook.py
├── price.py
└── translate.py
tests/
├── conftest.py     공통 fixtures
├── test_*.py       모듈별 테스트
docs/
├── DEPLOYMENT.md   배포 가이드
├── operations.md   운영 매뉴얼
└── PROGRESS.md     개발 진행 현황
```

---

> 주의: 실제 판매 전 **이미지 사용권/상표권/약관**을 반드시 확인하세요.
