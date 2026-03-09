# Proxy Commerce — 프로젝트 진행상황

> 마지막 업데이트: 2026-03-09

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
| 4 | 4-1 | 모니터링 대시보드 (주문 상태 추적 + 매출/마진 리포트 + 일일 요약) | — | 🚀 진행 중 |

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
│   ├── deploy.yml              # 카탈로그 싱크 + 웹훅
│   ├── import_catalog.yml      # 크롤링 데이터 적재
│   └── export_channels.yml     # 채널별 CSV 내보내기
├── config.example.yml
├── data/
│   ├── catalog.sample.csv      # 18컬럼 카탈로그 스키마
│   ├── porter_raw_sample.csv   # 포터 Listly 샘플
│   ├── memo_raw_sample.csv     # 메모파리 Listly 샘플
│   └── exports/.gitkeep
├── requirements.txt
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
    └── test_dashboard.py       # 68 tests
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
| **합계** | | **364** |

---

## 🚀 다음 단계 (미정)

- [x] Phase 3: 주문 자동 라우팅 (Shopify 주문 → 벤더별 자동 발주)
- [x] Phase 4 Step 4-1: 모니터링 대시보드 (주문 상태 추적 + 매출/마진 리포트 + 일일 요약)
- [ ] 실시간 환율 API 연동 (`FX_SOURCE=api`)
- [ ] 재고 자동 동기화 (크롤링 스케줄링)
- [ ] 쿠팡/스마트스토어 API 직접 연동 (퍼센티 대체)

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
