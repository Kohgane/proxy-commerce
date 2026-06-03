# KEYWORD_TRENDS.md — 키워드 트렌드 대시보드 가이드 (Phase 160)

## 개요

`/seller/keywords` 페이지에서 키워드별 **검색량·경쟁도·상품수·추정 CPC·추세**를 실시간/일/주/월/년 기간별로 확인합니다.

기존 `src/ads/keyword_optimizer.py` (Phase 144)의 `get_keyword_metrics`를 기반으로,  
Phase 160에서 시계열 트렌드(`get_keyword_trends`), 급상승 키워드(`get_rising_keywords`), 연관/롱테일 키워드(`get_related_keywords`)를 추가했습니다.

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `KEYWORD_OPT_PROVIDER` | `mock` | `mock` \| `naver_searchad` |
| `NAVER_SEARCHAD_API_KEY` | — | 네이버 검색광고 API 키 (PROVIDER=naver_searchad 시 필요) |
| `NAVER_SEARCHAD_API_SECRET` | — | 네이버 검색광고 API 시크릿 |
| `NAVER_SEARCHAD_CUSTOMER_ID` | — | 네이버 검색광고 고객 ID |
| `ADS_TARGET_ROAS` | `3.0` | 목표 ROAS |

---

## 주요 함수 (Phase 160 추가)

### `get_keyword_trends(keywords, period)`

```python
from src.ads.keyword_optimizer import get_keyword_trends

result = get_keyword_trends(["유니클로", "나이키"], period="month")
for r in result:
    print(r["keyword"], r["monthly_search"], r["trend_pct"], r["series"])
```

**반환 필드:**
- `keyword`: 키워드
- `monthly_search`: 월 검색량
- `competition`: 경쟁도 (0.0~1.0)
- `avg_cpc_krw`: 추정 CPC (원)
- `product_count`: 경쟁 상품수 (추정)
- `trend_pct`: 전기간 대비 증감률 (%)
- `series`: 기간별 검색량 시계열 리스트
- `period`: 요청된 기간

**기간별 시계열 포인트 수:**
| period | 포인트 수 | 단위 |
|---|---|---|
| `realtime` | 24 | 시간별 |
| `day` | 30 | 일별 |
| `week` | 12 | 주별 |
| `month` | 12 | 월별 |
| `year` | 5 | 연별 |

---

### `get_rising_keywords(limit=8)`

급상승 키워드 목록 반환.

```python
from src.ads.keyword_optimizer import get_rising_keywords
rising = get_rising_keywords(limit=5)
# [{"keyword": "플리스 집업", "change_pct": 142, ...}]
```

---

### `get_related_keywords(keyword)`

연관/확장/롱테일 키워드 추천.

```python
from src.ads.keyword_optimizer import get_related_keywords
result = get_related_keywords("유니클로")
# {
#   "related": [...],
#   "expanded": [...],
#   "longtail": ["유니클로 추천", "유니클로 구매", ...]
# }
```

---

## 네이버 검색광고 API 연동

`KEYWORD_OPT_PROVIDER=naver_searchad` 설정 시 실제 API를 호출합니다.

```bash
KEYWORD_OPT_PROVIDER=naver_searchad
NAVER_SEARCHAD_API_KEY=your_key
NAVER_SEARCHAD_API_SECRET=your_secret
NAVER_SEARCHAD_CUSTOMER_ID=your_customer_id
```

- API 미지원 기간(`realtime`)은 자동으로 mock fallback
- API 호출 실패 시 mock fallback (화면 깨지지 않음)

---

## HTTP API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/seller/keywords` | 키워드 트렌드 대시보드 (HTML) |
| `GET` | `/seller/keywords?q=키워드&period=month` | 특정 키워드 검색 |
| `POST` | `/seller/keywords/search` | 키워드 트렌드 JSON API |

### POST `/seller/keywords/search`

```json
// Request
{"keywords": ["유니클로", "나이키"], "period": "week"}

// Response
{
  "ok": true,
  "period": "week",
  "metrics": [
    {"keyword": "유니클로", "monthly_search": 85000, "trend_pct": 12.3, "series": [...], ...}
  ]
}
```

---

## 테스트

```bash
python -m pytest tests/test_phase_160_keyword_sourcing.py::TestGetKeywordTrends -v
```

---

## 관련 문서

- [`KEYWORD_OPTIMIZATION.md`](KEYWORD_OPTIMIZATION.md) — Phase 144 기존 키워드 최적화
- [`AI_SOURCING.md`](AI_SOURCING.md) — AI 소싱 허브
- [`DISCOVERY.md`](DISCOVERY.md) — Discovery 봇
