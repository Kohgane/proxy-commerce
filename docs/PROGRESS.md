# Proxy Commerce — 프로젝트 진행상황

> 마지막 업데이트: 2026-03-11

---

## 📋 전체 로드맵

| Phase | Step | 설명 | PR | 상태 |
|-------|------|------|----|------|
| 1 | 1-1 | 다중통화 환율 변환 (JPY, EUR) + 구매대행 landed cost 계산 | [#1](https://github.com/Kohgane/proxy-commerce/pull/1) | ✅ 머지 완료 |
| 1 | 1-2 | DeepL 기반 다국어 번역 모듈 (JA↔KO, FR↔KO, KO↔EN) | [#2](https://github.com/Kohgane/proxy-commerce/pull/2) | ✅ 머지 완료 |
| 1 | 1-3 | 소싱 벤더 모듈 (Porter Exchange + Memo Paris) | [#3](https://github.com/Kohgane/proxy-commerce/pull/3) | ✅ 머지 완료 |
| 1 | 1-4 | 스크래퍼 모듈 (Listly CSV/JSON 로더 + Sheets 적재 + CLI) | [#4](https://github.com/Kohgane/proxy-commerce/pull/4) | ✅ 머지 완료 |
| 2 | 2-1 | 판매 채널 모듈 (Percenty CSV 내보내기 + Shopify/WooCommerce 래퍼) | [#5](https://github.com/Kohgane/proxy-commerce/pull/5) | ✅ 머지 완료 |
| 2 | 2-2 | Shopify 인증 강화 (HMAC 검증 + CLIENT_SECRET + retry/GraphQL) | [#6](https://github.com/Kohgane/proxy-commerce/pull/6) | ✅ 머지 완료 |
| 3 | 3-1 | 주문 자동 라우팅 엔진 (SKU→벤더→배대지→알림→Fulfillment) | [#7](https://github.com/Kohgane/proxy-commerce/pull/7) | ✅ 머지 완료 |
| 4 | 4-1 | 모니터링 대시보드 (주문 상태 추적 + 매출/마진 리포트 + 일일 요약) | [#9](https://github.com/Kohgane/proxy-commerce/pull/9) | ✅ 머지 완료 |
| 4 | 4-2 | 재고 자동 동기화 (벤더 재고 확인 → 카탈로그 → 스토어 반영) | [#10](https://github.com/Kohgane/proxy-commerce/pull/10) | ✅ 머지 완료 |
| 4 | 4-3 | 실시간 환율 자동 연동 (다중 프로바이더 + 캐시 + 이력 + 가격 재계산) | [#11](https://github.com/Kohgane/proxy-commerce/pull/11) | ✅ 머지 완료 |
| 5 | 5-1 | 프로덕션 배포 환경 (Docker + Gunicorn + Healthcheck) | <a href="https://github.com/Kohgane/proxy-commerce/pull/12">#12</a> | ✅ 머지 완료 |
| 5 | 5-2 | CI/CD 파이프라인 (GitHub Actions 테스트 자동화 + Docker 이미지 빌드/푸시) | <a href="https://github.com/Kohgane/proxy-commerce/pull/13">#13</a>, <a href="https://github.com/Kohgane/proxy-commerce/pull/14">#14</a>, <a href="https://github.com/Kohgane/proxy-commerce/pull/15">#15</a> | ✅ 머지 완료 |
| 6 | 6-1 | 다국가 배송/세금 엔진 (13개국 통관/세금/배송비 자동 계산) | #16 | ✅ 머지 완료 |
| 6 | 6-2 | Shopify Markets 다통화 연동 + 국제 주문 라우팅 | #18 | ✅ 머지 완료 |
| 17 | 17-1 | Amazon US/JP 상품 수집기 + 수집 파이프라인 기반 | #35 | ✅ 머지 완료 |
| 17 | 17-2 | 타오바오/1688 수집기 + 쿠팡/스마트스토어 업로더 | — | 🚧 진행 중 |

---

## ✅ Phase 1: 소싱 파이프라인 (완료)

### PR #1 — 다중통화 지원 + Landed Cost 계산
- `src/price.py` 리팩터링: USD/JPY/EUR ↔ KRW 양방향 변환
- `calc_landed_cost()` 신규: 배대지 수수료 + 국제배송비 + 관부가세(15만원 초과 시 20%) + 마진율
- `DEFAULT_FX_RATES` (KRW 피벗): USDKRW=1350, JPYKRW=9.0, EURKRW=1470
- `calc_price()` 하위호환 유지, `fx_rates=` 키워드 인자 추가
- 16개 테스트 (`tests/test_price.py`)

### PR #2 — DeepL 다국어 번역 모듈
- `src/translate.py` 전면 재작성: `translate()` 범용 함수 + 편의 래퍼 (`ja_to_ko`, `fr_to_ko`, `ko_to_en`, `ko_to_ja`)
- `TRANSLATE_PROVIDER` 환경변수 (`deepl` | `none`), API 키 미설정 시 graceful degradation
- 인메모리 캐시 (중복 API 호출 방지)
- `ko_to_en_if_needed()` 하위호환 유지
- `catalog_sync.py`: JP 소스 → `ja_to_ko()`, FR 소스 → `fr_to_ko()` 자동 번역
- 19개 테스트 (`tests/test_translate.py`)

### PR #3 — 소싱 벤더 모듈 (Porter + Memo Paris)
- `src/vendors/base_vendor.py`: `BaseVendor` ABC, `CATALOG_FIELDS` 18개 필드
- `src/vendors/porter.py`: `PorterVendor` (JPY, JP, zenmarket), 시리즈→코드 매핑, SKU `PTR-{CAT}-{NUM}`
- `src/vendors/memo_paris.py`: `MemoPariVendor` (EUR, FR), EDP/EDT 라인 감지, SKU `MMP-{LINE}-{NUM}`
- `src/vendors/__init__.py`: `VENDOR_REGISTRY` + `get_vendor()` 팩토리
- `data/catalog.sample.csv` 18컬럼 확장
- 53개 테스트 (`tests/test_vendors.py`)

### PR #4 — 스크래퍼 모듈 (Listly → Sheets)
- `src/scrapers/listly_client.py`: `ListlyLoader` (CSV/JSON, 인코딩 폴백 utf-8-sig→utf-8→euc-kr→shift_jis)
- `src/scrapers/sheet_importer.py`: `SheetImporter` (SKU 중복 검사, upsert, 벤더 정규화 통합)
- `src/scrapers/cli.py`: CLI 엔트리포인트 (`--vendor`, `--file`, `--dry-run`)
- 샘플 데이터: `data/porter_raw_sample.csv`, `data/memo_raw_sample.csv`
- `.github/workflows/import_catalog.yml`: workflow_dispatch
- 36개 테스트 (`tests/test_scrapers.py`)

---

## ✅ Phase 2: 판매 채널 + 인증 강화 (완료)

### PR #5 — 판매 채널 모듈 (Percenty CSV)
- `src/channels/` 패키지 신규:
  - `base_channel.py`: `BaseChannel` ABC (`prepare_product`, `export_batch`, `get_category_mapping`)
  - `percenty.py`: 퍼센티 CSV 내보내기 (쿠팡/스마트스토어/11번가), UTF-8 BOM
  - `shopify_global.py` / `woo_domestic.py`: 기존 클라이언트 래핑
  - `cli.py`: `--channel percenty --market coupang --output data/exports/`
  - `templates/`: 벤더별 상세 HTML (porter_detail.html, memo_detail.html)
- 카테고리 매핑: `COUPANG_CATEGORIES`, `NAVER_CATEGORIES`
- 마켓별 가격정책: `MARKET_PRICE_POLICY` (쿠팡 10.8%, 스마트스토어 5%, 11번가 12%)
- `.github/workflows/export_channels.yml`: workflow_dispatch
- 51개 테스트 (`tests/test_channels.py`)

### PR #6 — Shopify 인증 강화 + Secrets 통합
- `src/vendors/shopify_client.py` 리팩터링:
  - `verify_webhook()`: HMAC-SHA256 서명 검증
  - `_request_with_retry()`: 지수 백오프 + 429 Retry-After 처리
  - `graphql_query()`: Shopify Admin GraphQL API
  - `_find_by_sku()`: GraphQL 우선 → REST 폴백
  - `get_shop_info()`: 연결 상태 확인
- `src/order_webhook.py`: X-Shopify-Hmac-Sha256 검증 추가 (401 반환)
- `src/auth/shopify_oauth.py` 신규: OAuth HMAC 검증, 토큰 유효성, 스코프 조회
- `src/utils/secret_check.py` 신규: 환경변수 그룹별 진단 유틸리티
- 워크플로: `deploy.yml`, `export_channels.yml`에 `SHOPIFY_CLIENT_SECRET` 추가

---

## ✅ Phase 3: 주문 자동 라우팅 (완료)

### PR #7 — 주문 자동 라우팅 엔진 (SKU→벤더→배대지→알림→Fulfillment)
- `src/orders/` 패키지 신규:
  - `catalog_lookup.py`: `CatalogLookup` — Google Sheets에서 SKU 조회, 배치 조회, 벤더 정보 추출, 캐싱
  - `router.py`: `OrderRouter` — Shopify 주문 → 벤더별 구매 태스크 라우팅 (PTR-→포터/젠마켓, MMP-→메모파리/직배송)
  - `notifier.py`: `OrderNotifier` — 텔레그램/이메일/Notion 통합 알림
  - `tracker.py`: `OrderTracker` — 배대지 송장 수신 → Shopify fulfillment + WooCommerce 상태 업데이트, 택배사 코드 매핑
- `src/order_webhook.py` 리팩터링: OrderRouter/Notifier/Tracker 통합
- `.env.example` 업데이트: `ZENMARKET_ADDRESS`, `WAREHOUSE_ADDRESS`, `SHOPIFY_LOCATION_ID`, 택배사 기본값
- 70개 테스트 (`tests/test_orders.py`)

---

## 📁 현재 프로젝트 구조

```
proxy-commerce/
├── .env.example
├── .github/workflows/
│   ├── ci.yml                  # PR + main push 자동 lint/test/docker
│   ├── deploy.yml              # 카탈로그 싱크 + 웹훅
│   ├── docker-publish.yml      # main push + v* 태그 시 GHCR 자동 배포
│   ├── import_catalog.yml      # 크롤링 데이터 적재
│   └── export_channels.yml     # 채널별 CSV 내보내기
├── config.example.yml
├── data/
│   ├── catalog.sample.csv      # 18컬럼 카탈로그 스키마
│   ├── porter_raw_sample.csv   # 포터 Listly 샘플
│   ├── memo_raw_sample.csv     # 메모파리 Listly 샘플
│   └── exports/.gitkeep
├── requirements.txt
├── requirements-dev.txt        # pytest, pytest-cov, flake8
├── setup.cfg                   # flake8 + pytest 중앙 설정
├── src/
│   ├── __init__.py
│   ├── catalog_sync.py         # Sheets → Shopify/WooCommerce 동기화
│   ├── order_webhook.py        # 주문 웹훅 (라우팅+알림+트래킹 통합)
│   ├── image_uploader.py       # Cloudinary 이미지
│   ├── price.py                # 다중통화 + calc_landed_cost()
│   ├── translate.py            # DeepL 다국어 번역 + 캐시
│   ├── auth/
│   │   └── shopify_oauth.py    # OAuth HMAC, 토큰 검증
│   ├── channels/
│   │   ├── __init__.py         # CHANNEL_REGISTRY
│   │   ├── base_channel.py     # BaseChannel ABC
│   │   ├── percenty.py         # 퍼센티 CSV 내보내기
│   │   ├── shopify_global.py   # Shopify 채널 래퍼
│   │   ├── woo_domestic.py     # WooCommerce 채널 래퍼
│   │   ├── cli.py              # 채널 CLI
│   │   └── templates/          # 상세페이지 HTML
│   ├── orders/
│   │   ├── __init__.py         # orders 패키지
│   │   ├── catalog_lookup.py   # CatalogLookup (SKU→시트 조회, 캐싱)
│   │   ├── router.py           # OrderRouter (주문→벤더 태스크 라우팅)
│   │   ├── notifier.py         # OrderNotifier (텔레그램/이메일/Notion)
│   │   └── tracker.py          # OrderTracker (Shopify fulfillment + WooCommerce)
│   ├── dashboard/
│   │   ├── __init__.py         # dashboard 패키지
│   │   ├── order_status.py     # OrderStatusTracker (주문 상태 Sheets 기록)
│   │   ├── revenue_report.py   # RevenueReporter (매출/마진 분석)
│   │   ├── daily_summary.py    # DailySummaryGenerator (일일 요약 + 발송)
│   │   └── cli.py              # 대시보드 CLI
│   ├── fx/
│   │   ├── __init__.py         # fx 패키지 (FXProvider/FXCache/FXHistory/FXUpdater)
│   │   ├── provider.py         # FXProvider (frankfurter → exchangerate-api → env)
│   │   ├── cache.py            # FXCache (TTL 인메모리 + Sheets 영속화)
│   │   ├── history.py          # FXHistory (Sheets 이력 + 급변 감지)
│   │   ├── updater.py          # FXUpdater (업데이트 → 재계산 → 스토어 반영)
│   │   └── cli.py              # 환율 CLI
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── listly_client.py    # Listly CSV/JSON 로더
│   │   ├── sheet_importer.py   # Sheets upsert
│   │   └── cli.py              # 스크래퍼 CLI
│   ├── utils/
│   │   ├── sheets.py           # Google Sheets 연동
│   │   ├── secret_check.py     # 환경변수 진단
│   │   ├── emailer.py
│   │   ├── telegram.py
│   │   └── notion.py
│   ├── shipping/               # Phase 6-1: 다국가 배송/세금 엔진
│   │   ├── __init__.py         # 패키지 초기화
│   │   ├── country_config.py   # 13개국 통관/세금 설정 DB
│   │   ├── tax_calculator.py   # TaxCalculator (관세+VAT 자동 계산)
│   │   ├── shipping_estimator.py # ShippingEstimator (배송비/리드타임)
│   │   └── customs_document.py # CustomsDocumentHelper (인보이스/HS코드)
│   └── vendors/
│       ├── __init__.py         # VENDOR_REGISTRY + get_vendor()
│       ├── base_vendor.py      # BaseVendor ABC
│       ├── porter.py           # PorterVendor (JPY, zenmarket)
│       ├── memo_paris.py       # MemoPariVendor (EUR)
│       ├── shopify_client.py   # Shopify (HMAC, retry, GraphQL)
│       └── woocommerce_client.py
└── tests/
    ├── test_price.py           # 16 tests
    ├── test_translate.py       # 19 tests
    ├── test_vendors.py         # 53 tests
    ├── test_scrapers.py        # 36 tests
    ├── test_channels.py        # 51 tests
    ├── test_shopify_auth.py    # 17 tests
    ├── test_woocommerce.py     # 34 tests
    ├── test_orders.py          # 70 tests
    ├── test_dashboard.py       # 68 tests
    └── test_shipping.py        # 105 tests
```

---

## 🔑 등록된 GitHub Secrets

| Secret | 용도 |
|--------|------|
| `GOOGLE_SERVICE_JSON_B64` | Google 서비스계정 JSON (base64) |
| `GOOGLE_SHEET_ID` | 카탈로그 시트 ID |
| `SHOPIFY_ACCESS_TOKEN` | Shopify Admin API Token |
| `SHOPIFY_CLIENT_SECRET` | Shopify HMAC 웹훅 검증 |
| `SHOPIFY_SHOP` | `your-shop.myshopify.com` |
| `WOO_BASE_URL` | WooCommerce 사이트 URL |
| `WOO_CK` | WooCommerce Consumer Key |
| `WOO_CS` | WooCommerce Consumer Secret |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 (일일 요약 발송) |
| `TELEGRAM_CHAT_ID` | 텔레그램 채널/그룹 ID |

---

## 🔧 주요 CLI 명령

```bash
# 카탈로그 동기화
python -m src.catalog_sync

# 크롤링 데이터 적재
python -m src.scrapers.cli --vendor porter --file data/porter_raw.csv
python -m src.scrapers.cli --vendor memo_paris --file data/memo_raw.csv --dry-run

# 채널 CSV 내보내기
python -m src.channels.cli --channel percenty --output data/exports/
python -m src.channels.cli --channel percenty --market coupang --output data/exports/
python -m src.channels.cli --channel percenty --output data/exports/ --dry-run

# 대시보드
python -m src.dashboard.cli --action daily-summary
python -m src.dashboard.cli --action revenue --period daily --date 2026-03-09
python -m src.dashboard.cli --action status --filter pending
python -m src.dashboard.cli --action margin-analysis

# 테스트
python -m pytest tests/ -v
```

---

## 📊 테스트 현황

| 모듈 | 테스트 파일 | 테스트 수 |
|------|------------|----------|
| price.py | test_price.py | 16 |
| translate.py | test_translate.py | 19 |
| vendors/ | test_vendors.py | 53 |
| scrapers/ | test_scrapers.py | 36 |
| channels/ | test_channels.py | 51 |
| auth/ + utils/ | test_shopify_auth.py | 17 |
| vendors/woocommerce | test_woocommerce.py | 34 |
| orders/ | test_orders.py | 70 |
| dashboard/ | test_dashboard.py | 68 |
| inventory/ | test_inventory.py | 52 |
| fx/ | test_fx.py | 38 |
| healthcheck | test_health.py | 10 |
| shipping/ | test_shipping.py | 105 |
| **합계** | | **569** |

---

## 🚀 다음 단계 (미정)

- [x] Phase 3: 주문 자동 라우팅 (Shopify 주문 → 벤더별 자동 발주)
- [x] Phase 4 Step 4-1: 모니터링 대시보드 (주문 상태 추적 + 매출/마진 리포트 + 일일 요약)
- [x] Phase 4 Step 4-2: 재고 자동 동기화 (벤더 재고 변동 감지 → 카탈로그/스토어 반영)
- [x] Phase 4 Step 4-3: 실시간 환율 자동 연동 (다중 프로바이더 + 캐시 + 이력 + 가격 재계산)
- [x] Phase 5 Step 5-1: 프로덕션 배포 환경 (Docker + Gunicorn + Healthcheck)
- [x] Phase 5 Step 5-2: CI/CD 파이프라인 (GitHub Actions + Docker GHCR + Lint)
- [x] Phase 6 Step 6-1: 다국가 배송/세금 엔진 (13개국 통관/세금/배송비 자동 계산)
- [ ] Phase 6 Step 6-2: 글로벌 확장 (해외 직판 D2C 채널 연동)
- [ ] 쿠팡/스마트스토어 API 직접 연동 (퍼센티 대체)

---

## ✅ Phase 5: 프로덕션 배포 + CI/CD (완료)

### Step 5-1 — Docker + Gunicorn + Healthcheck

- `Dockerfile` 신규:
  - `python:3.11-slim` 베이스 이미지
  - non-root 유저 `appuser` 실행
  - `HEALTHCHECK` 지시자 (curl 기반, 30초 간격)
  - 환경변수 `PORT`, `GUNICORN_WORKERS`, `GUNICORN_TIMEOUT` 커스터마이즈 지원
- `docker-compose.yml` 신규:
  - `web` 서비스: Flask/Gunicorn 웹훅 서버 (포트 8000)
  - `worker` 서비스: 카탈로그 동기화/재고/환율 스케줄러 (`python -m src.main`)
  - `healthcheck` + `restart: unless-stopped` 설정
- `gunicorn.conf.py` 신규: bind/workers/timeout/log 환경변수 기반 설정
- `.dockerignore` 신규: 불필요 파일 제외
- `src/order_webhook.py` 업데이트:
  - `GET /health`: 서비스 상태 확인 (200 OK)
  - `GET /health/ready`: 외부 의존성(Secrets) 연결 확인 (200/503)
- `requirements.txt` 업데이트: `gunicorn` 추가
- `.env.example` 업데이트: Docker/Gunicorn 환경변수 추가
- `README.md` 업데이트: Docker 배포 섹션 추가
- 10개 테스트 (`tests/test_health.py`)

### Step 5-2 — CI/CD 파이프라인

- `.github/workflows/ci.yml` 신규: PR + main push 시 자동 실행
  - `lint` → `test` (Python 3.11 / 3.12 matrix) → `docker` 순차 실행
  - 테스트 환경 격리: `TRANSLATE_PROVIDER=none`, `FX_USE_LIVE=0` 등 외부 API 호출 없음
  - JUnit XML 아티팩트 업로드, GHA Docker 레이어 캐시 적용
  - 모든 job에 `permissions: contents: read` 명시 (최소 권한)
- `.github/workflows/docker-publish.yml` 신규: main push + `v*` 태그 시 GHCR 자동 배포
  - `GITHUB_TOKEN` 기본 토큰으로 push (별도 시크릿 불필요)
  - `docker/metadata-action@v5`로 branch / semver / sha 태그 자동 생성
- `requirements-dev.txt` 신규: `pytest`, `pytest-cov`, `flake8`
- `setup.cfg` 신규: flake8(`max-line-length=120`, E501/W503/W504/E402 무시) + pytest `testpaths`/`addopts`/`env` 중앙 관리
- PR #14, #15: 전체 flake8 lint 에러 수정 (14개 파일, 30건+ 에러 — F401/F841/F541/E401/E131/E302/E305/E231)

---

## ✅ Phase 4: 모니터링 대시보드 (진행 중)

### Step 4-1 — 주문 상태 추적 + 매출/마진 리포트 + 일일 요약

- `src/dashboard/` 패키지 신규:
  - `order_status.py`: `OrderStatusTracker` — Google Sheets `orders` 시트에 주문 상태 기록/업데이트, 상태별 조회, 통계
  - `revenue_report.py`: `RevenueReporter` — 일별/주별/월별 매출 요약, 벤더별 마진 분석, 환율 영향 분석
  - `daily_summary.py`: `DailySummaryGenerator` — 일일 요약 생성, 텔레그램/이메일 포맷팅, 발송, 장기 미배송/환율 급변 알림
  - `cli.py`: 대시보드 CLI (`daily-summary`, `revenue`, `status`, `margin-analysis`)
- `src/order_webhook.py` 업데이트: `OrderStatusTracker` 통합 — 주문 수신 시 자동 상태 기록, 배송 추적 수신 시 자동 상태 업데이트 (graceful degradation)
- `.github/workflows/daily_summary.yml`: 매일 KST 22:00 자동 실행 + `workflow_dispatch`
- `.env.example` 업데이트: `DAILY_SUMMARY_ENABLED`, `ORDERS_WORKSHEET`, `ALERT_*` 환경변수
- `config.example.yml` 업데이트: `dashboard` 섹션 추가
- 68개 테스트 (`tests/test_dashboard.py`)
### Step 4-2 — 재고 자동 동기화

- `src/inventory/` 패키지 신규:
  - `stock_checker.py`: `StockChecker` — 벤더 사이트 HTML 스크래핑으로 재고/가격 확인 (포터: カートに入れる/売り切れ, 메모파리: add to bag/out of stock)
  - `inventory_sync.py`: `InventorySync` — 핵심 동기화 엔진 (Sheets ↔ Shopify/WooCommerce), full_sync/sync_single/dry_run 지원
  - `stock_alerts.py`: `StockAlertManager` — 품절/재입고/가격변동 텔레그램/이메일 알림
  - `cli.py`: 재고 CLI (`full-sync`, `check`, `check-all`, `report`)
- `.github/workflows/inventory_sync.yml`: 4시간마다 자동 실행 + `workflow_dispatch` (액션/드라이런/벤더 필터)
- `.env.example` 업데이트: `INVENTORY_SYNC_ENABLED`, `STOCK_CHECK_DELAY`, `LOW_STOCK_THRESHOLD`, `PRICE_CHANGE_THRESHOLD_PCT`, `INVENTORY_CHECK_TIMEOUT`
- `config.example.yml` 업데이트: `inventory` 섹션 추가 (벤더별 HTML 패턴 포함)
- 52개 테스트 (`tests/test_inventory.py`)

### Step 4-3 — 실시간 환율 자동 연동

- `src/fx/` 패키지 신규:
  - `provider.py`: `FXProvider` — 다중 API 프로바이더 (frankfurter.app → exchangerate-api.com → 환경변수 폴백), 자동 폴백
  - `cache.py`: `FXCache` — TTL 기반 인메모리 캐시 + Google Sheets `fx_rates` 시트 영속화
  - `history.py`: `FXHistory` — Google Sheets `fx_history` 시트 이력 기록, 변동률 계산, 급변 감지 (기본 3%)
  - `updater.py`: `FXUpdater` — 환율 업데이트 → 이력 기록 → 급변 알림 → 카탈로그 가격 재계산 → Shopify/WooCommerce 업데이트 통합
  - `cli.py`: 환율 CLI (`update`, `current`, `history`, `recalculate`, `check-changes`)
- `src/price.py` 수정: `_build_fx_rates(use_live=None)` 파라미터 추가 — FXCache 우선, 하위호환 유지
- `src/catalog_sync.py` 수정: `use_live=True`로 실시간 환율 사용 (`FX_USE_LIVE` 환경변수 제어)
- `.github/workflows/fx_update.yml`: 하루 4회 (UTC 00:30, 06:30, 12:30, 18:30) 자동 실행 + `workflow_dispatch`
- `.env.example` 업데이트: `FX_PROVIDER`, `FX_USE_LIVE`, `FX_CACHE_TTL`, `FX_CHANGE_ALERT_PCT`, `EXCHANGERATE_API_KEY`, `FX_HISTORY_WORKSHEET`, `FX_RATES_WORKSHEET`
- `config.example.yml` 업데이트: `fx` 섹션 추가
- 38개 테스트 (`tests/test_fx.py`)

---

## 🌍 Phase 6 준비: 글로벌 확장 시장조사

### 2-1. 한국 제품 수요가 높은 국가

| 순위 | 국가/지역 | 핵심 근거 |
|------|----------|----------|
| 1 | 🇺🇸 미국 | K-뷰티 수출 상위권, 한류 콘텐츠 확산 |
| 2 | 🇯🇵 일본 | 한국 화장품 수입 상위, "한국 감성" 소비재 수용도 높음 |
| 3 | 🇻🇳🇮🇩🇹🇭🇵🇭 동남아 | 한류 호감도 최상위권(필리핀/인도네시아/태국/베트남), K-뷰티 수출 성장 |
| 4 | 🇦🇪 UAE/중동 | K-뷰티 수출 급성장 신흥 시장, 한류 선호도 높음 |
| 5 | 🇵🇱🇬🇧🇫🇷 유럽 | 폴란드: K-뷰티 신흥 급성장, 영국/프랑스도 성장세 |

### 2-2. 온라인 쇼핑 비중이 높은 국가

| 국가 | 온라인 비중 | 출처/기준 |
|------|-----------|----------|
| 🇰🇷 한국 | ~50.6% (2024) | 주요 유통업체 기준 |
| 🇬🇧 영국 | ~27.4% (2025) | ONS(영국 통계청) |
| 🇨🇳 중국 | ~26.8% (2024) | NBS(국가통계) |
| 🇺🇸 미국 | ~16.1% (2024) | Census Bureau |

### 2-3. 우선 공략 국가 Tier 분류 (D2C Shopify 수출 MVP 기준)

**Tier 1 — 즉시 공략:**
- 🇺🇸 미국: 한국 수요 + 이커머스 비중 + 결제/물류 생태계 완성
- 🇬🇧 영국: 온라인 비중 매우 높고, K-콘텐츠/뷰티 수요 성장

**Tier 2 — 성장 시장:**
- 🇯🇵 일본: 한국 제품 수요 확실 + 구매력/반복구매 강점
- 🇵🇭🇮🇩🇹🇭🇻🇳 동남아: 한류 호감도 기반 "K-라이프스타일" 수용 강함
- 🇦🇪 UAE: 신흥 고성장 + 한류 선호

**Tier 3 — 확장 카드:**
- 🇵🇱 폴란드: 유럽 내 신흥 수요 급성장
- 🇨🇳 중국: 온라인 비중 높지만 크로스보더/정책 변수 큼

### 2-4. 국가별 통관 요건 & 세금 정리

#### 🇺🇸 미국 (US)
- **면세**: 기존 $800 de minimis 사실상 종료 방향 (소포에도 관세 적용)
- **관세**: HS코드(HTS)별 상이 + 추가관세(무역조치) 가능
- **부가세(VAT)**: 없음 (주(State) 판매세는 별도)
- **통관 필수**: 인보이스 + HS코드 + 원산지 + 수입자 연락처
- **전략**: 초반 DAP(수취인 부담) + 라벨/트래킹 자동화로 리스크 최소화

#### 🇬🇧 영국 (UK)
- **£135 이하**: 판매자가 결제 시점에 UK VAT 부과/신고
- **£135 초과**: 수입 시점에 수입 VAT + 관세
- **VAT**: 표준 20%
- **통관 필수**: 인보이스 + HS코드 + 원산지 + 정확한 가격/배송비
- **전략**: 세금 선납(DDP) 권장 (반품/CS 감소)

#### 🇯🇵 일본 (JP)
- **면세**: 총 과세가격 10,000엔 이하 → 관세+소비세 면세 (일부 예외 품목)
- **소비세**: 표준 10%
- **통관 필수**: 인보이스(구체 품명) + HS코드 + 원산지 + 가격
- **주의**: 화장품/식품류는 별도 규정

#### 🇨🇳 중국 (CN)
- **개인우편물 루트**: 세액 50위안 이하 면세, 신고가액 한도 2,000위안
- **CBEC(크로스보더)**: 1회 5,000위안 / 연 26,000위안 한도
- **수입 VAT**: 품목별 13%/9% 등
- **주의**: 통관 루트 선택이 성패 좌우, 자동화 난이도 높음

#### 🇪🇺 EU / 🇵🇱 폴란드
- **면세**: €22 이하 VAT 면세 이미 폐지 → 모든 수입품에 VAT
- **IOSS**: €150 이하 B2C VAT 신고/납부 단순화 제도
- **변화 예정**: EU가 €150 관세 면제도 2026년 제거 진행 중
- **폴란드 VAT**: 표준 23%
- **전략**: IOSS 활용 + DDP 선호(DAP 시 반품/클레임 증가)

#### 🇸🇬 싱가포르 (SG)
- **GST**: 9%
- **S$400 이하**: 항공/우편 GST 면제 규정 있으나, 저가물품(LVG) 해외판매자 GST 징수(OVR) 구조도 도입

#### 🇲🇾 말레이시아 (MY)
- **LVG(RM500 이하)**: 판매세 10% (2024-01-01부터 실제 부과)
- **주의**: "저가라도 세금 0" 아님

#### 🇹🇭 태국 (TH)
- **2026-01-01부터**: 1바트부터 온라인 해외구매에 수입관세 + VAT 7% (저가면세 종료)

#### 🇻🇳 베트남 (VN)
- **2025-02-18부터**: 100만동 이하 저가수입 VAT 면제 폐지
- **VAT**: 품목/정책에 따라 변동 가능

#### 🇮🇩 인도네시아 (ID)
- **FOB ≤ $3**: 관세 면제 + VAT 11%
- **$3~$1,500**: 관세 7.5% + VAT 11%

#### 🇵🇭 필리핀 (PH)
- **10,000페소 이하**: de minimis → 관세/세금 면제
- **수입 VAT**: 12%

#### 🇦🇪 UAE
- **관세**: 대부분 5% (CIF 기준)
- **VAT**: 표준 5%

#### 🇸🇦 사우디 (KSA)
- **관세**: GCC 체계 5%+ (품목별 상향 가능)
- **VAT**: 표준 15%
- **주의**: 통관 전자화/사전 제출 요구 강화 추세

### 2-5. 운영 전략 요약

| 국가 | 추천 Incoterms | 핵심 이유 |
|------|---------------|----------|
| 미국 | DAP | 정책변동 커서 수취인 부담으로 리스크 최소화 |
| 영국 | DDP | 세금 선납 → 반품/CS 감소 |
| EU/폴란드 | DDP (IOSS) | IOSS로 VAT 단순화, DAP 시 클레임 증가 |
| 일본 | DAP/DDP | 저가(1만엔 이하) 면세 활용, 고가는 DDP 검토 |
| 동남아 | DAP | 저가면세 종료 추세이므로 면세 기대 금지 |
| UAE/사우디 | DAP | 관세/VAT 낮아서 수취인 부담도 저항 적음 |
| 중국 | CBEC 전용 | 크로스보더 전자상거래 전용 루트 필수 |

---

## ✅ Phase 6: 글로벌 확장 (진행 중)

### Step 6-1 — 다국가 배송/세금 엔진 (13개국 통관/세금/배송비 자동 계산)

#### 신규 파일

- `src/shipping/__init__.py`: 패키지 초기화 (`CountryConfig`, `TaxCalculator`, `ShippingEstimator` 노출)
- `src/shipping/country_config.py`: 13개국 통관/세금 설정 DB (`COUNTRY_DB`, `get_country()`, `SUPPORTED_COUNTRIES`)
- `src/shipping/tax_calculator.py`: `TaxCalculator` — `calc_import_tax()`, `calc_landed_price()`
- `src/shipping/shipping_estimator.py`: `ShippingEstimator` — `estimate()`, `cheapest()`, `fastest()`
- `src/shipping/customs_document.py`: `CustomsDocumentHelper` — `generate_invoice_data()`, `get_hs_code()`
- `tests/test_shipping.py`: 105개 테스트

#### 지원 국가 (13개국)

| 국가 | 코드 | 통화 | VAT | 관세 | de minimis | Incoterms | Tier |
|------|------|------|-----|------|-----------|-----------|------|
| 미국 | US | USD | 0% | 5% | $800 | DAP | 1 |
| 영국 | GB | GBP | 20% | 4% | £135 | DDP | 1 |
| 일본 | JP | JPY | 10% | 5% | ¥10,000 | DAP | 2 |
| 태국 | TH | THB | 7% | 10% | 없음 | DAP | 2 |
| 베트남 | VN | VND | 10% | 10% | 없음 | DAP | 2 |
| 인도네시아 | ID | IDR | 11% | 7.5% | $3 | DAP | 2 |
| 필리핀 | PH | PHP | 12% | 5% | ₱10,000 | DAP | 2 |
| UAE | AE | AED | 5% | 5% | 없음 | DAP | 2 |
| 사우디 | SA | SAR | 15% | 5% | 없음 | DAP | 2 |
| 싱가포르 | SG | SGD | 9% | 0% | S$400 | DAP | 2 |
| 말레이시아 | MY | MYR | 10% | 5% | RM500 | DAP | 2 |
| 폴란드 | PL | PLN | 23% | 4% | 없음 (IOSS €150) | DDP | 3 |
| 중국 | CN | CNY | 13% | 10% | ¥50 | DAP | 3 |

#### 주요 구현 사항

- **KRW 피벗 환율 변환**: `_convert_currency()` — 모든 통화 쌍을 KRW 경유로 환산
- **de minimis 면세 로직**: 완전 면세(JP/PH) vs. 관세만 면제+VAT 부과(GB/ID/SG/MY) 분리 처리
- **배송비 포함 CIF 관세**: 관세 = (상품가 + 배송비) × 관세율
- **배송비 KRW 테이블 (0.5kg 기준)**: EMS/K-Packet/등기 3종 × 5개 zone
- **중량 비례 배송비**: 0.5kg 단위 올림 처리
- **EU IOSS 메타데이터**: `ioss_eligible`, `ioss_threshold` 플래그 제공
- **기존 `src/price.py` 수정 없음**: 완전 독립 패키지로 동작

---

## ✅ Phase 17: 수입 구매대행 — 상품 수집 파이프라인

### Step 17-1 — Amazon 상품 수집기 (US/JP) + 수집 파이프라인 기반

#### 배경

Phase 1~16 + lint fix(PR #34)까지 전체 머지 완료. 이제 **수입(해외→한국)** 구매대행 기능을 추가하여 퍼센티 스타일의 상품 수집 → 번역 → 가격계산 → 국내 마켓 업로드 파이프라인을 구축한다.

#### 신규 파일

- `src/collectors/__init__.py`: 패키지 초기화 (`BaseCollector`, `AmazonCollector`, `CollectionManager` 노출)
- `src/collectors/base_collector.py`: `BaseCollector` ABC — 수집 표준 필드 정의, 번역/가격계산/SKU 공통 로직
- `src/collectors/amazon_collector.py`: `AmazonCollector` — Amazon US/JP 상품 수집 (ASIN 추출, BeautifulSoup 파싱, User-Agent 로테이션)
- `src/collectors/collection_manager.py`: `CollectionManager` — Google Sheets 저장/중복 검사/리포트
- `src/collectors/cli.py`: 수집 CLI (`search`, `collect`, `batch`, `report` 액션)
- `tests/test_collectors.py`: 40+ 테스트

#### 업데이트 파일

- `requirements.txt`: `beautifulsoup4>=4.12`, `lxml>=5.0`, `fake-useragent>=1.4` 추가
- `.env.example`: Phase 17 수집기 환경변수 추가 (`COLLECTOR_TIMEOUT`, `IMPORT_MARGIN_PCT` 등)
- `config.example.yml`: `collectors:` 섹션 추가

#### 주요 구현 사항

- **BaseCollector ABC**: `COLLECTED_FIELDS` 27개 표준 필드, `translate_product()` / `calculate_prices()` / `generate_sku()` 공통 메서드
- **AmazonCollector**: US/JP 멀티리전 지원, ASIN 정규식 추출, BeautifulSoup HTML 파싱 (제목/가격/이미지/카테고리/브랜드/평점/리뷰/재고/중량/옵션), User-Agent 로테이션 (fake-useragent + fallback 내장 UA 5종)
- **가격 계산**: `src/price.py` `calc_landed_cost()` 재활용, 마진/배송비/관세 자동 계산
- **번역 통합**: `src/translate.py` `translate()` 재활용, EN→KO / JA→KO 자동 번역, 실패 시 원문 유지
- **SKU 생성**: `AMZ-US-ELC-001` / `AMZ-JP-BTY-001` 형식
- **CollectionManager**: 중복 검사(collector_id 기준), 신규 추가/가격변동 업데이트, dry_run 모드, 필터 조회
- **에러 핸들링**: 모든 HTTP 요청 try/except, 절대 크래시하지 않음, COLLECTOR_TIMEOUT/DELAY 적용

---

## 🚧 Phase 17: 수입 구매대행 — 상품 수집 파이프라인 (진행 중)

### Step 17-2 — 타오바오/1688 수집기 + 국내 마켓 업로더 (쿠팡/스마트스토어)

#### 신규 파일

- `src/collectors/taobao_collector.py`: `TaobaoCollector` — 타오바오/1688 상품 수집 (URL ID 추출, BeautifulSoup 파싱, 중국어→한국어 번역, CNY→KRW 가격계산)
- `src/uploaders/__init__.py`: 패키지 초기화 (`BaseUploader`, `CoupangUploader`, `NaverSmartStoreUploader`, `UploadManager` 노출)
- `src/uploaders/base_uploader.py`: `BaseUploader` ABC — `UPLOAD_FIELDS` 15개 표준 필드, `upload_batch()` / `prepare_product()` 공통 메서드
- `src/uploaders/coupang_uploader.py`: `CoupangUploader` — 쿠팡 Wing API HMAC 인증, 상품 등록/업데이트/삭제/카테고리 조회
- `src/uploaders/naver_uploader.py`: `NaverSmartStoreUploader` — 네이버 커머스 API OAuth2 토큰, 상품 등록/업데이트/삭제
- `src/uploaders/upload_manager.py`: `UploadManager` — 수집 상품 → 마켓 업로드 전체 흐름, 이력 관리, 가격 동기화, 리포트
- `src/uploaders/cli.py`: 업로드 CLI (`upload`, `upload-pending`, `sync-prices`, `report` 액션, `--dry-run` 지원)
- `tests/test_taobao_collector.py`: 54개 테스트
- `tests/test_uploaders.py`: 65개 테스트

#### 업데이트 파일

- `src/translate.py`: `zh_to_ko()`, `zh_to_en()` 편의 함수 추가 (중국어 번역 지원)
- `src/price.py`: `DEFAULT_FX_RATES`에 `'CNYKRW': Decimal('185')` 추가, `_build_fx_rates()` CNY 파라미터 지원
- `src/collectors/__init__.py`: `TaobaoCollector` 내보내기 추가
- `src/collectors/cli.py`: `--marketplace taobao` / `--marketplace 1688` 지원 추가
- `.env.example`: 타오바오/1688 수집 + 쿠팡/네이버 API + 업로더 공통 환경변수 추가

#### 주요 구현 사항

- **TaobaoCollector**: 타오바오/1688 양 플랫폼 지원, `_extract_item_id()` URL 파싱, `_parse_taobao_page()` / `_parse_1688_page()` HTML 파싱, CNY 가격 범위(¥19.9-39.9) 처리
- **CNY→KRW 가격 계산**: `_calculate_import_price()` — 원가 KRW 환산 + 배대지 수수료(기본 3,000원 + kg당 2,000원) + 관세(15만원 초과 시) + 마진
- **SKU 생성**: 타오바오 `TAO-{카테고리}-{번호}`, 1688 `ALB-{카테고리}-{번호}`
- **19개 카테고리 매핑**: 女装→WCL, 数码→DIG 등
- **CoupangUploader**: HMAC-SHA256 서명 생성, 상품명 50자 제한 + `[해외직구]` 접두사, 가격 100원 단위 올림, 429/401/500 에러 처리
- **NaverSmartStoreUploader**: OAuth2 client_credentials 토큰 자동 갱신, 가격 10원 단위 올림, 401 시 토큰 무효화 + 재시도
- **UploadManager**: CollectionManager 연동, dry_run 모드, Google Sheets upload_history 이력 기록, 미업로드 SKU 필터링
- **에러 핸들링**: 모든 API 호출 try/except, API 키 미설정 시 경고 로그 + graceful degradation

---

## Phase 91: 주문 분쟁/중재 시스템 + SEO/CTA 보강 (2026-04-04)

### 최종 업데이트: 2026-04-04

### 전체 진행률
- 완료된 Phase: 1~91
- 총 PR: #1~#55 (예상)
- 현재 상태: Phase 91 구현 완료

### 최근 완료
| Phase | 내용 | PR |
|---|---|---|
| Phase 85~90 | 재고 트랜잭션, 고객 세그멘테이션, 상품 비교, 이메일 마케팅, 창고 관리, 세금 엔진 | #54 |
| Phase 91 | 주문 분쟁/중재 시스템 + SEO/CTA 보강 | #55 |

### Phase 91 구현 상세
- `DisputeManager`: 분쟁 CRUD + 상태 전환 (opened→under_review→mediation→resolved/rejected)
- `EvidenceCollector`: 증거 자료 첨부 (스크린샷, 사진, 대화 기록, 운송장) — 분쟁당 최대 10개
- `MediationService`: 자동 판정 규칙 (소액 < 50,000원, 배송 +7일 초과, 사진 증거) + 수동 대기열
- `RefundDecision`: 전액/부분/거절 환불 + 판매자 패널티 (분쟁률 5%→경고, 10%→판매 제한)
- `DisputeAnalytics`: 분쟁률, 평균 해결 시간, 유형별/상태별/판매자별 통계
- `SitemapGenerator`: XML sitemap 자동 생성 (상품/카테고리/정적 페이지), sitemap index 지원
- `RobotsGenerator`: robots.txt 동적 생성 (/admin/, /api/ Disallow, /products/, /categories/ Allow)
- `MetaGenerator` 보강: canonical URL 필드, Twitter Card 태그, 중국어 CTA "立即购买" 추가
- 대시보드 웹 UI: `<meta name="description">`, `<meta name="robots">`, Open Graph 태그 적용
- API Blueprint: `/api/v1/disputes` (POST /, GET /, GET /<id>, PUT /<id>/status, POST /<id>/evidence, GET /<id>/evidence, POST /<id>/mediate, GET /analytics)
- 봇 커맨드: `/disputes`, `/dispute_create <order_id> <type> <reason>`, `/dispute_resolve <id> <decision>`
