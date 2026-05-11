# KEYWORD_OPTIMIZATION.md — 키워드 입찰 최적화 가이드 (Phase 144)

## 개요

키워드별 검색량/경쟁도/CPC 추정 → 상품-키워드 매칭 점수 →
입찰가 추천 (목표 CPA 기반) + 네거티브 키워드 자동 제안.

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `KEYWORD_OPT_PROVIDER` | `mock` | `mock` \| `naver_searchad` \| `coupang_ads` |
| `ADS_TARGET_ROAS` | `3.0` | 목표 ROAS (네거티브 기준) |

---

## 주요 함수

### 1. 검색량/경쟁도/CPC 추정 (`get_keyword_metrics`)

```python
from src.ads.keyword_optimizer import get_keyword_metrics
metrics = get_keyword_metrics(["유니클로", "나이키"])
for m in metrics:
    print(m.keyword, m.monthly_search, m.avg_cpc_krw)
```

- `KEYWORD_OPT_PROVIDER=mock`: 내부 DB 기반 mock 데이터 반환
- 알 수 없는 키워드: `monthly_search=5000, competition=0.5, avg_cpc=200` 기본값

### 2. 상품-키워드 매칭 점수 (`match_keywords_to_product`)

```python
from src.ads.keyword_optimizer import match_keywords_to_product
ranked = match_keywords_to_product("나이키 에어포스 240", candidate_keywords)
# 매칭 점수 높은 순 정렬
```

- Jaccard 유사도 (상품명 토큰 ∩ 키워드 토큰) + 검색량 보정
- 실제 운영: OpenAI embedding 유사도로 교체 가능

### 3. 입찰가 추천 (`recommend_bids`)

```python
from src.ads.keyword_optimizer import recommend_bids
bids = recommend_bids(metrics, target_cpa_krw=5000)
for b in bids:
    print(b["keyword"], "→", b["recommended_bid_krw"], "원")
```

**공식**:
- `est_cvr = max(0.005, 0.03 × (1 - competition))`
- `recommended_bid = target_cpa × est_cvr`
- 클리핑: `avg_cpc × 0.7 ≤ bid ≤ avg_cpc × 1.3` (최소 50원)

### 4. 네거티브 키워드 제안 (`suggest_negative_keywords`)

```python
from src.ads.keyword_optimizer import suggest_negative_keywords
performance_data = [
    {"keyword": "짝퉁 브랜드", "cost_krw": 5000.0, "revenue_krw": 0.0},
    ...
]
negatives = suggest_negative_keywords(performance_data)
```

**네거티브 기준**:
- 비용 발생 + 매출 = 0
- ROAS < `ADS_TARGET_ROAS × 0.1`

---

## Mock 키워드 데이터베이스

| 키워드 | 월간 검색량 | 경쟁도 | avg CPC |
|---|---|---|---|
| 유니클로 | 85,000 | 0.70 | 320원 |
| 나이키 | 120,000 | 0.85 | 450원 |
| 무인양품 | 42,000 | 0.55 | 280원 |
| 아디다스 | 95,000 | 0.80 | 390원 |
| 에어포스 | 35,000 | 0.75 | 520원 |
| 플리스 자켓 | 18,000 | 0.45 | 210원 |
| 에코백 | 27,000 | 0.40 | 180원 |
| 트레이닝 팬츠 | 32,000 | 0.60 | 250원 |
| 일본직구 | 65,000 | 0.65 | 300원 |
| 해외직구 | 180,000 | 0.90 | 550원 |

---

## 테스트

```bash
python3 -m pytest tests/test_keyword_optimizer.py -v
```

---

## 실제 API 연동 (향후)

`KEYWORD_OPT_PROVIDER=naver_searchad`:
- 네이버 검색광고 API: `https://api.naver.com/keywordstool`
- API 키: `NAVER_SEARCHAD_API_KEY`, `NAVER_SEARCHAD_API_SECRET`

`KEYWORD_OPT_PROVIDER=coupang_ads`:
- 쿠팡 ADS API (별도 계약 필요)
