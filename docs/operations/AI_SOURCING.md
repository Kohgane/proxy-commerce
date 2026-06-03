# AI_SOURCING.md — AI 소싱 허브 가이드 (Phase 160)

## 개요

`/seller/sourcing` 페이지는 키워드 한 줄 입력 → AI 소싱 후보 추천 → 원클릭 수집/등록 플로우를 제공합니다.

세 축이 통합됩니다:
1. **키워드 트렌드** (`keyword_optimizer`) — 검색량·경쟁도 기반 추천
2. **Discovery 봇** — 신규 쇼핑몰 발견 후보
3. **기존 후보 큐** (`sourcing.pipeline`) — 이미 발견된 소싱 후보

---

## 주요 기능

### 1. AI 소싱 후보 추천
- POST `/seller/sourcing/recommend` → `{keyword}` 입력 → 후보 목록 JSON 반환
- 규칙 기반 추천 (LLM 키 없어도 동작, `OPENAI_API_KEY` 설정 시 향후 LLM 강화 가능)
- 각 후보: `name`, `source`(trend/discovery/queue), `reason`, `margin_hint`, `url`

### 2. 원클릭 범용 수집
- **POST `/seller/sourcing/collect`** — URL 붙여넣기 → 즉시 수집
  - 도메인 자동 감지 → `dispatcher.collect()` → 결과 반환
  - 신규 도메인은 자동으로 Discovery `discovery_candidates`에 등록
- **GET `/seller/sourcing/collect?url=...`** — URL 수집 후 수동 수집기로 리다이렉트

### 3. My Sources 즐겨찾기
- GET `/seller/sourcing/my-sources` — 목록 조회 (JSON)
- POST `/seller/sourcing/my-sources/add` — 추가
- POST `/seller/sourcing/my-sources/remove` — 삭제
- `GOOGLE_SHEET_ID` 설정 시 Sheets `my_sources` 워크시트에 영속화, 미설정 시 인메모리

### 4. Discovery 연계
- 소싱 허브 우측 카드에서 Discovery 신규 발견 쇼핑몰 최근 5개 노출
- 원클릭으로 해당 도메인 수집 시작

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `GOOGLE_SHEET_ID` | — | Sheets 영속화 (My Sources, Discovery) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | — | Sheets 인증 |
| `ADAPTER_DRY_RUN` | `0` | `1` 설정 시 실제 수집 없이 mock |
| `KEYWORD_OPT_PROVIDER` | `mock` | 트렌드 데이터 소스 |

---

## HTTP API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/seller/sourcing` | AI 소싱 허브 (HTML) |
| `GET` | `/seller/sourcing?keyword=키워드` | 특정 키워드로 추천 결과 포함 |
| `POST` | `/seller/sourcing/recommend` | AI 소싱 후보 추천 (JSON) |
| `POST` | `/seller/sourcing/collect` | 원클릭 범용 수집 (JSON) |
| `GET` | `/seller/sourcing/collect?url=...` | URL 수집 → 수집기 리다이렉트 |
| `GET` | `/seller/sourcing/my-sources` | My Sources 목록 (JSON) |
| `POST` | `/seller/sourcing/my-sources/add` | My Sources 추가 (JSON) |
| `POST` | `/seller/sourcing/my-sources/remove` | My Sources 삭제 (JSON) |

### POST `/seller/sourcing/recommend`

```json
// Request
{"keyword": "플리스 자켓"}

// Response
{
  "ok": true,
  "recommendations": [
    {
      "name": "플리스 자켓 관련 상품 소싱",
      "source": "trend",
      "source_label": "트렌드",
      "reason": "월 검색량 18,000, 경쟁도 45%",
      "margin_hint": "CPC ₩210 기준 마진 추정",
      "url": null
    }
  ]
}
```

### POST `/seller/sourcing/collect`

```json
// Request
{"url": "https://somebrand.com/products/jacket-01"}

// Response (성공)
{
  "ok": true,
  "title": "플리스 재킷 블랙",
  "price": "29000",
  "image_url": "https://...",
  "preview_url": "/seller/collect/preview-result?url=..."
}
```

---

## My Sources 저장소 (`src/seller_console/my_sources_store.py`)

```python
from src.seller_console.my_sources_store import MySourcesStore

store = MySourcesStore()
store.add("brand.com", label="브랜드몰", url_example="https://brand.com/products/1")
entries = store.list()
store.remove("brand.com")
```

- `GOOGLE_SHEET_ID` + `GOOGLE_SERVICE_ACCOUNT_JSON` 설정 시 Sheets `my_sources` 워크시트 사용
- 미설정 시 프로세스 내 인메모리 (재시작 시 초기화)

---

## 수집 흐름

```
URL 입력
  └─ dispatcher.detect_collector(url)
       ├─ amazon.com → AmazonCollector
       ├─ rakuten.co.jp → RakutenCollector
       ├─ 기타 → GenericOgCollector  ← 브랜드몰/소규모몰 전용
  └─ collector.collect(url) → CollectorResult
  └─ 신규 도메인 → DiscoveryScout.add_candidate(domain)
  └─ 결과 반환 / 미리보기 리다이렉트
```

---

## 테스트

```bash
python -m pytest tests/test_phase_160_keyword_sourcing.py::TestSourcingRoutes -v
python -m pytest tests/test_phase_160_keyword_sourcing.py::TestMySourcesStore -v
```

---

## 관련 문서

- [`KEYWORD_TRENDS.md`](KEYWORD_TRENDS.md) — 키워드 트렌드 대시보드
- [`COLLECTORS.md`](COLLECTORS.md) — 범용 수집기 아키텍처
- [`DISCOVERY.md`](DISCOVERY.md) — Discovery 봇
- [`KEYWORD_OPTIMIZATION.md`](KEYWORD_OPTIMIZATION.md) — Phase 144 키워드 최적화
