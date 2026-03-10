# Proxy Commerce – 2단계 구매대행 자동화 (Runnable)

이 레포는 **즉시 실행** 가능한 2단계(반자동 주문 라우팅) 템플릿입니다.

## 🐳 Docker 배포

### 빌드 & 실행
```bash
docker build -t proxy-commerce .
docker run -p 8000:8000 --env-file .env proxy-commerce
```

### Docker Compose
```bash
docker-compose up -d
```

### Healthcheck
```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

---

## 빠른 시작

1) **Google Sheet** 만들기 → 시트명 `catalog`, 헤더/데이터는 이 레포의 `data/catalog.sample.csv`를 그대로 Import (즉시 배포용)
2) **Cloudinary** 키 준비 (Dashboard에서 cloud_name/api_key/api_secret)
3) **Shopify** 앱 생성 → Admin API Token / Shop 도메인 준비
4) **WooCommerce** → REST API 키(consumer key/secret) 생성
5) 이 레포를 깃허브에 올린 뒤, 레포 **Settings → Secrets and variables → Actions**에 아래 시크릿 입력
6) **Actions** 탭에서 워크플로 수동 실행 → Shopify/Woo에 제품이 생성됨
7) `order_webhook`를 Render/Cloud Run 등에 배포 후, Shopify에 주문 Webhook 등록

### 필수 Secrets
- `GOOGLE_SERVICE_JSON_B64`: Google 서비스계정 JSON base64
- `GOOGLE_SHEET_ID`: 카탈로그 시트 파일 ID
- `SHOPIFY_ACCESS_TOKEN`: Shopify Admin API Token
- `SHOPIFY_SHOP`: `your-shop.myshopify.com`
- `SHOPIFY_LOCATION_ID`: (선택) 재고 관리 위치 ID (없으면 기본값 사용)
- `WOO_BASE_URL`: WooCommerce 사이트 URL (예: https://example.kr)
- `WOO_CK`: WooCommerce Consumer Key
- `WOO_CS`: WooCommerce Consumer Secret
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- (선택) `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- (선택) `NOTION_TOKEN`, `NOTION_DB`

> 주의: 실제 판매 전 **이미지 사용권/상표권/약관**을 반드시 확인하세요.

---

## 주문 자동 라우팅

Shopify에서 주문이 들어오면 자동으로 벤더별 구매 태스크를 생성합니다.

### 흐름
1. Shopify 주문 웹훅 수신 → HMAC 검증
2. SKU 기반 카탈로그 조회 → 벤더/배대지 식별
3. 벤더별 구매 태스크 생성 (포터→젠마켓, 메모파리→직배송)
4. 텔레그램/이메일/Notion으로 구매 지시 알림
5. 배대지에서 송장 수신 → Shopify fulfillment 업데이트

### 트래킹 업데이트
배대지에서 발송 후 아래 엔드포인트로 POST:
```bash
curl -X POST http://your-server/webhook/forwarder/tracking \
  -H 'Content-Type: application/json' \
  -d '{"order_id": 12345, "sku": "PTR-TNK-001", "tracking_number": "...", "carrier": "cj"}'
```

---

로컬 테스트:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export $(cat .env.example | xargs)  # 필요 시 값 수정 후 사용
python -m src.catalog_sync  # 카탈로그 동기화 1회 실행
python -m src.order_webhook  # 웹훅 서버 로컬 실행 (기본 8000)
```

## 크롤링 데이터 적재

Listly에서 내보낸 CSV/JSON 파일을 Google Sheets 카탈로그에 적재:

```bash
# 포터 상품 적재
python -m src.scrapers.cli --vendor porter --file data/porter_raw.csv

# 메모파리 상품 적재
python -m src.scrapers.cli --vendor memo_paris --file data/memo_raw.csv

# DRY_RUN (시트에 쓰지 않고 결과만 확인)
python -m src.scrapers.cli --vendor porter --file data/porter_raw.csv --dry-run
```

샘플 데이터로 테스트:
```bash
# 포터 샘플 DRY_RUN
python -m src.scrapers.cli --vendor porter --file data/porter_raw_sample.csv --dry-run

# 메모파리 샘플 DRY_RUN
python -m src.scrapers.cli --vendor memo_paris --file data/memo_raw_sample.csv --dry-run
```

---

## 대시보드 / 모니터링

주문 상태 추적, 매출/마진 분석, 일일 운영 요약을 제공합니다.
주문 상태는 Google Sheets(`orders` 시트)에 자동으로 기록됩니다.

```bash
# 일일 요약 발송 (텔레그램/이메일)
python -m src.dashboard.cli --action daily-summary

# 특정 날짜 일일 요약
python -m src.dashboard.cli --action daily-summary --date 2026-03-09

# 매출 리포트 (일별)
python -m src.dashboard.cli --action revenue --period daily --date 2026-03-09

# 매출 리포트 (주별)
python -m src.dashboard.cli --action revenue --period weekly --week-start 2026-03-03

# 매출 리포트 (월별)
python -m src.dashboard.cli --action revenue --period monthly --month 2026-03

# 미완료 주문 조회
python -m src.dashboard.cli --action status --filter pending

# 특정 주문 조회
python -m src.dashboard.cli --action status --order-id 12345

# 마진 분석
python -m src.dashboard.cli --action margin-analysis
```

### 일일 요약 자동화

GitHub Actions 워크플로(`.github/workflows/daily_summary.yml`)가 매일 KST 22:00에 자동 실행됩니다.
수동 실행 시 날짜를 지정할 수 있습니다.

### 추가 필수 Secrets (대시보드용)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: 일일 요약 텔레그램 발송


## 재고 자동 동기화

```bash
# 전체 재고 동기화 (벤더 확인 → 카탈로그 → 스토어)
python -m src.inventory.cli --action full-sync

# 드라이런 (변경사항 확인만, 실제 업데이트 없음)
python -m src.inventory.cli --action full-sync --dry-run

# 특정 SKU 확인
python -m src.inventory.cli --action check --sku PTR-TNK-001

# 특정 벤더만 확인
python -m src.inventory.cli --action check-all --vendor porter

# 동기화 리포트
python -m src.inventory.cli --action report
```

### 재고 자동화 워크플로

GitHub Actions 워크플로(`.github/workflows/inventory_sync.yml`)가 4시간마다 자동 실행됩니다.
수동 실행 시 액션, 드라이런 여부, 벤더 필터를 지정할 수 있습니다.

### 추가 환경변수 (재고 동기화)
- `INVENTORY_SYNC_ENABLED`: 동기화 활성화 (기본 `1`)
- `STOCK_CHECK_DELAY`: 벤더 요청 간격 (초, 기본 `2`)
- `LOW_STOCK_THRESHOLD`: 재고 부족 임계값 (기본 `3`)
- `PRICE_CHANGE_THRESHOLD_PCT`: 가격 변동 알림 임계값 % (기본 `5.0`)
- `INVENTORY_CHECK_TIMEOUT`: HTTP 타임아웃 (초, 기본 `15`)

---

## 실시간 환율

```bash
# 환율 업데이트 (API 조회 → 캐시 → 이력 기록)
python -m src.fx.cli --action update

# 강제 갱신 (캐시 무시)
python -m src.fx.cli --action update --force

# 드라이런 (실제 업데이트 없음)
python -m src.fx.cli --action update --dry-run

# 현재 환율 확인
python -m src.fx.cli --action current

# 최근 30일 이력
python -m src.fx.cli --action history --days 30

# 환율 변동 기반 가격 재계산
python -m src.fx.cli --action recalculate [--dry-run]

# 급변 감지
python -m src.fx.cli --action check-changes --threshold 3.0
```

### 환율 자동화 워크플로

GitHub Actions 워크플로(`.github/workflows/fx_update.yml`)가 하루 4회(KST 09:30, 15:30, 21:30, 03:30) 자동 실행됩니다.
수동 실행 시 액션, 강제 갱신, 드라이런 여부를 지정할 수 있습니다.

### 추가 환경변수 (환율 연동)
- `FX_PROVIDER`: 기본 환율 프로바이더 (`frankfurter` | `exchangerate-api`, 기본 `frankfurter`)
- `FX_USE_LIVE`: 실시간 환율 사용 여부 (기본 `1`)
- `FX_CACHE_TTL`: 환율 캐시 유효 시간 (초, 기본 `3600`)
- `FX_CHANGE_ALERT_PCT`: 환율 급변 알림 임계값 % (기본 `3.0`)
- `EXCHANGERATE_API_KEY`: exchangerate-api.com API 키 (선택, exchangerate-api 사용 시 필요)
- `FX_HISTORY_WORKSHEET`: 환율 이력 시트명 (기본 `fx_history`)
- `FX_RATES_WORKSHEET`: 환율 캐시 시트명 (기본 `fx_rates`)
