# Week1 P0 이슈 티켓 세트 (복붙용)

> 아래 9개 이슈를 순서대로 GitHub에 등록하세요.  
> **라벨**과 **마일스톤**을 먼저 생성한 뒤 이슈를 등록하면 바로 할당할 수 있습니다.  
> 참고: `docs/ISSUE_LABEL_TAXONOMY.md` → `docs/MILESTONES_WEEK1_WEEK2.md` → 이 문서 순으로 실행

---

## Issue 1 — Product Schema 표준화

**Title**
```
[P0] Product Schema 표준화 (Pydantic)
```

**Body**

### Background
수집 소스(ALO, lululemon, 타오바오 등)가 달라도 WooCommerce 업로드 가능한 단일 상품 스키마를 고정한다.  
스키마 없이 수집기를 늘리면 publisher에서 필드 불일치가 반복 발생한다.

### Scope
- `schemas/product.py` — Pydantic 모델
- `schemas/enums.py` — StockStatus, Currency 등 열거형
- `tests/test_product_schema.py`

### Acceptance Criteria
- [ ] 필수 필드 모두 포함: `source`, `source_product_id`, `source_url`, `brand`, `title`, `description`, `currency`, `cost_price`, `sell_price`, `images[]`, `thumbnail`, `options[]`, `stock_status`
- [ ] 가격 validator: `sell_price >= cost_price > 0`
- [ ] 이미지 validator: 최소 1개 이상
- [ ] 옵션 validator: size/color/variant 구조
- [ ] 스키마 검증 실패 시 표준 `ValidationError` 반환
- [ ] 샘플 fixture 10개 통과

### Tasks
- [ ] Pydantic v2 `BaseModel` 작성
- [ ] validator 3종 작성 (가격/이미지/옵션)
- [ ] fixture 파일 작성 (`tests/fixtures/products/`)
- [ ] 단위테스트 작성

### Dependencies
- 없음 (첫 번째로 착수)

### Labels
`P0` `type:feature` `component:schema` `status:ready` `biz:revenue`

### Milestone
`Week1 - MVP 판매준비`

---

## Issue 2 — Collector Pipeline 공통화

**Title**
```
[P0] Collector Pipeline 공통화 (fetch → parse → normalize → validate)
```

**Body**

### Background
소스별 수집기가 각자 다른 방식으로 구현되면 유지보수 비용이 급증한다.  
공통 파이프라인 추상화로 각 수집기는 `parse()` 만 구현하면 되도록 한다.

### Scope
- `collectors/base.py` — `BaseCollector` 추상 클래스
- `collectors/pipeline.py` — 파이프라인 실행기
- `collectors/exceptions.py` — 수집 전용 예외

### Acceptance Criteria
- [ ] `BaseCollector` 인터페이스: `fetch()`, `parse()`, `normalize()` 구현 강제
- [ ] stage별 로깅 (fetch / parse / normalize / validate)
- [ ] 실패 항목 dead-letter 저장: `logs/failed_items.jsonl`
- [ ] retry/backoff 지원 (`max_retries`, `backoff_factor` config)
- [ ] CLI 실행: `python -m app.collect --source alo`

### Tasks
- [ ] `BaseCollector` 추상 클래스 구현
- [ ] pipeline runner 구현
- [ ] retry decorator 추가
- [ ] dead-letter 저장 로직
- [ ] 단위테스트

### Dependencies
- Issue 1 (Product Schema) 완료 후 착수

### Labels
`P0` `type:feature` `component:collector` `status:ready` `biz:revenue`

### Milestone
`Week1 - MVP 판매준비`

---

## Issue 3 — ALO Collector MVP

**Title**
```
[P0] ALO Collector MVP (title/price/images/options/url)
```

**Body**

### Background
ALO 요가/스포츠웨어 상품을 자동 수집한다.  
메인 판매 채널로 우선 수집 대상에 포함.

### Scope
- `collectors/alo.py`
- `tests/test_alo_collector.py`
- raw 저장: `data/raw/alo/`
- normalized 저장: `data/normalized/alo/`

### Acceptance Criteria
- [ ] 최소 20개 상품 수집 성공
- [ ] 필수 필드 누락률 < 5%
- [ ] 스키마 검증 통과율 ≥ 95%
- [ ] raw JSON + normalized JSON 저장
- [ ] 이미지 URL 유효성 체크 (404 제외)
- [ ] 키워드 자동 생성: 상품당 최소 5개 키워드 (카테고리 + 브랜드 + 핵심 속성 조합)

### Tasks
- [ ] `AloCollector(BaseCollector)` 구현
- [ ] fetch/parse 로직 (requests + BeautifulSoup or Playwright)
- [ ] 이미지/옵션 파싱
- [ ] normalize 매핑 (ALO 필드 → ProductSchema)
- [ ] test fixture 및 단위테스트

### Dependencies
- Issue 1, 2 완료 후 착수

### Labels
`P0` `type:feature` `component:collector` `status:ready` `biz:revenue`

### Milestone
`Week1 - MVP 판매준비`

---

## Issue 4 — lululemon Collector MVP

**Title**
```
[P0] lululemon Collector MVP (title/price/images/options/url)
```

**Body**

### Background
lululemon 프리미엄 스포츠웨어 상품 자동 수집.  
ALO와 함께 Week1 수집 대상 2종.

### Scope
- `collectors/lululemon.py`
- `tests/test_lululemon_collector.py`
- raw 저장: `data/raw/lululemon/`

### Acceptance Criteria
- [ ] 최소 20개 상품 수집 성공
- [ ] 스키마 검증 통과율 ≥ 95%
- [ ] 이미지 URL 유효성 체크 포함
- [ ] 대표 이미지 1개 + 상세 이미지 N개 분리

### Tasks
- [ ] `LululemonCollector(BaseCollector)` 구현
- [ ] normalize 매핑 (lululemon 필드 → ProductSchema)
- [ ] 통합테스트

### Dependencies
- Issue 1, 2 완료 후 착수 (Issue 3와 병렬 가능)

### Labels
`P0` `type:feature` `component:collector` `status:ready` `biz:revenue`

### Milestone
`Week1 - MVP 판매준비`

---

## Issue 5 — Pricing Engine

**Title**
```
[P0] Pricing Engine — 마진/수수료/환율/배송비 자동 계산
```

**Body**

### Background
원가 + 국제배송 + 수수료 + 환율을 반영한 자동 판매가 산출.  
마진 미달 상품은 WooCommerce 업로드 전 자동 차단.

### Scope
- `pricing/engine.py`
- `config/pricing.yaml` — 정책 프리셋
- `tests/test_pricing_engine.py`

### Acceptance Criteria
- [ ] `calculate_sell_price(cost, exchange_rate, shipping_fee, fee_rate, target_margin_pct) → float`
- [ ] `calculate_margin_rate(cost, sell_price, shipping_fee, fee_rate) → float`
- [ ] 정책 프리셋 3종: 입문(20%), 표준(28%), 공격(35%)
- [ ] 최소마진 하한선(`MIN_MARGIN_PCT`) 미달 시 `MarginBelowThresholdError` 발생 → publish 차단
- [ ] 환율 변수 주입 가능 (기본: `FX_USDKRW`)
- [ ] 단위테스트 커버리지 ≥ 90%

### Tasks
- [ ] pricing service 구현
- [ ] `config/pricing.yaml` 작성
- [ ] `MarginBelowThresholdError` 예외 정의
- [ ] 단위테스트 (엣지케이스 포함)

### Dependencies
- Issue 1 (ProductSchema)

### Labels
`P0` `type:feature` `component:pricing` `status:ready` `biz:revenue`

### Milestone
`Week1 - MVP 판매준비`

---

## Issue 6 — WooCommerce Draft Publisher

**Title**
```
[P0] WooCommerce Draft Publisher — normalized 상품 자동 draft 업로드
```

**Body**

### Background
수집 → 정규화된 상품을 WooCommerce에 draft 상태로 자동 등록.  
수동 검수 승인 후 publish 전환.  
Primary 스토어: `WC_*` (kohganemultishop.org)

### Scope
- `publishers/woocommerce.py`
- `publishers/client.py` — WooCommerce REST API 클라이언트
- `tests/test_woocommerce_publisher.py`

### Acceptance Criteria
- [ ] `WC_URL`, `WC_KEY`, `WC_SECRET` 환경변수 사용
- [ ] 상품 create / update 지원
- [ ] 중복방지 키: `meta.source + meta.source_product_id`
- [ ] 업로드 결과 로그: `logs/upload_history.jsonl`
- [ ] dry-run 모드 지원 (`--dry-run` flag)
- [ ] 마진 미달 상품 자동 skip

### Tasks
- [ ] `WooCommerceClient` 구현 (woocommerce 패키지 활용)
- [ ] idempotency 처리 (중복 체크)
- [ ] draft publish CLI command
- [ ] dry-run 모드

### Dependencies
- Issue 1 (Schema), Issue 5 (Pricing Engine)

### Labels
`P0` `type:feature` `component:publisher` `status:ready` `biz:revenue` `risk:payment`

### Milestone
`Week1 - MVP 판매준비`

---

## Issue 7 — Taobao Seller Whitelist Gate

**Title**
```
[P0] Taobao Seller Whitelist Gate — 신뢰 판매자만 업로드 허용
```

**Body**

### Background
타오바오 상품은 판매자 신뢰도 검증 없이 업로드 시 위조품/품질불량 리스크가 높다.  
화이트리스트 통과 판매자 상품만 파이프라인 통과 허용.

### Scope
- `compliance/seller_whitelist.py`
- `data/seller_whitelist.json` — 초기 화이트리스트 데이터
- `tests/test_seller_whitelist.py`

### Acceptance Criteria
- [ ] 화이트리스트 저장소: `data/seller_whitelist.json` (seller_id, name, trust_score, added_at)
- [ ] 판매자 미등록 시 자동 reject + 사유 로깅
- [ ] `trust_score` threshold 설정 가능 (config)
- [ ] 브랜드 위조 리스크 키워드 자동 차단
- [ ] 초기 신뢰 판매자 ≥ 20개 등록
- [ ] reject report export (CSV)

### Tasks
- [ ] `SellerWhitelistGate` 구현
- [ ] whitelist JSON loader
- [ ] gate validator (trust_score + keyword 체크)
- [ ] reject report exporter
- [ ] 단위테스트

### Dependencies
- Issue 2 (Pipeline) — 파이프라인 내 gate step으로 삽입

### Labels
`P0` `type:feature` `component:taobao-gate` `status:ready` `risk:policy`

### Milestone
`Week1 - MVP 판매준비`

---

## Issue 8 — Stock/Price Watcher + Alert

**Title**
```
[P0] Stock/Price Watcher + Alert — 품절/가격변동 감지 및 텔레그램/슬랙 알림
```

**Body**

### Background
등록된 상품의 품절 전환, 가격 급변, 비정상 상태를 주기적으로 감시하고 알림 발송.  
매출 손실(품절 미감지) 및 가격 오류(과소/과다 판매) 방지.

### Scope
- `monitoring/watcher.py`
- `monitoring/notifier.py` — 텔레그램 / 슬랙 통합
- `tests/test_stock_price_watcher.py`

### Acceptance Criteria
- [ ] 스케줄러 1시간 간격 실행 (APScheduler or cron)
- [ ] 품절 전환 감지: `in_stock → out_of_stock`
- [ ] 가격변동 감지: 변동률 `PRICE_CHANGE_THRESHOLD_PCT` 이상 시 알림
- [ ] 알림 채널: 텔레그램(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) or 슬랙(`SLACK_WEBHOOK_URL`)
- [ ] 노이즈 억제: 동일 알림 24시간 중복 발송 금지
- [ ] 알림 메시지 포맷 통일 (상품명 / 변동 내용 / 원문 URL)

### Tasks
- [ ] `StockPriceWatcher` 구현
- [ ] notifier 통합 (텔레그램 우선)
- [ ] dedup 로직 (last_alerted_at 기반)
- [ ] 스케줄러 등록
- [ ] 단위테스트 (mock 알림)

### Dependencies
- Issue 1 (Schema), Issue 6 (Publisher — 등록된 상품 목록 필요)

### Labels
`P0` `type:feature` `component:monitoring` `status:ready` `biz:revenue` `risk:shipping`

### Milestone
`Week1 - MVP 판매준비`

---

## Issue 9 — CS 자동 응답 템플릿

**Title**
```
[P0] CS 자동 응답 템플릿 — 반품/교환/환불/배송지연 4종
```

**Body**

### Background
배송 실수, 품질 문제, 지연 등 발생 시 고객 대응이 늦으면 환불/CS 비용이 급증한다.  
사전에 주문 상태별 자동 응답 템플릿을 마련해 응답 속도와 품질을 동시에 확보한다.

### Scope
- `cs/templates/` — 한국어 템플릿 파일 4종
- `cs/renderer.py` — 변수 치환 렌더러
- `cs/router.py` — 주문 상태 → 템플릿 매핑
- `tests/test_cs_templates.py`

### Acceptance Criteria
- [ ] 템플릿 4종 완성:
  - `return.md` — 반품 안내
  - `exchange.md` — 교환 안내
  - `refund.md` — 환불 처리 안내
  - `delay.md` — 배송 지연 안내
- [ ] 치환 변수 지원: `{{customer_name}}`, `{{order_id}}`, `{{product_name}}`, `{{expected_date}}`
- [ ] 주문 상태 → 템플릿 자동 매핑 (예: `shipping_delayed` → `delay.md`)
- [ ] 한국어 기본 + 영문 fallback (`return_en.md` 등)
- [ ] CLI: `python -m app.cs render --template refund --order-id ORD-001`

### Tasks
- [ ] 템플릿 파일 4종 작성 (한/영)
- [ ] `CSRenderer` 구현 (Jinja2 or 단순 str.format)
- [ ] `CSRouter` 구현 (상태 → 템플릿 매핑)
- [ ] CLI command 추가
- [ ] 단위테스트

### Dependencies
- 없음 (독립 작업, Issue 8과 병렬 가능)

### Labels
`P0` `type:feature` `component:cs` `status:ready` `risk:shipping` `biz:conversion`

### Milestone
`Week1 - MVP 판매준비`

---

## 이슈 일괄 등록용 gh CLI 참고

```bash
# 이슈 등록 예시 (본문은 위 각 이슈의 Body를 파일로 저장 후 사용)
gh issue create \
  --title "[P0] Product Schema 표준화 (Pydantic)" \
  --body-file /tmp/issue1_product_schema.md \
  --label "P0,type:feature,component:schema,status:ready,biz:revenue" \
  --milestone "Week1 - MVP 판매준비" \
  --repo Kohgane/proxy-commerce

# 나머지 8개도 동일한 패턴으로 반복
```
