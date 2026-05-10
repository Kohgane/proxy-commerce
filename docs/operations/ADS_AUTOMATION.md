# ADS_AUTOMATION.md — 광고 자동 운영 가이드 (Phase 144)

## 개요

등록된 상품 중 매출 잠재력 높은 SKU를 자동 추출하여 쿠팡 ADS / 네이버 쇼핑검색광고
캠페인을 자동 생성하고, 키워드 입찰가를 목표 ROAS 기준으로 자동 조정합니다.

**기본값: 광고 자동 launch OFF** (`ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=0`)

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `ADS_AUTO_CAMPAIGN_ENABLED` | `0` | `1` = 자동 운영 활성화 |
| `ADS_AUTO_CAMPAIGN_AUTO_LAUNCH` | `0` | `1` = 캠페인 자동 launch (기본: 수동 승인) |
| `ADS_DAILY_BUDGET_KRW` | `20000` | 일일 광고 예산 (원) |
| `ADS_TARGET_ROAS` | `3.0` | 목표 ROAS |
| `ADS_BID_ADJUST_MAX_PCT` | `20` | 최대 입찰가 조정 비율 (%) |
| `KEYWORD_OPT_PROVIDER` | `mock` | `mock` \| `naver_searchad` \| `coupang_ads` |

---

## 주요 기능

### 1. 캠페인 추천 (`recommend_campaigns`)

```python
from src.ads.auto_campaign import recommend_campaigns
recs = recommend_campaigns(roas_target=3.0)
```

- 마진율 × 검색량 기반 잠재 ROAS 추정
- ROAS 기대값이 `roas_target × 0.5` 미만이면 제외
- 쿠팡/네이버 채널별 추천 생성
- 일일 예산은 `ADS_DAILY_BUDGET_KRW ÷ 4` 이하

### 2. 캠페인 생성 (`create_campaign`)

```python
from src.ads.auto_campaign import create_campaign
campaign_id = create_campaign(rec, channel="coupang")
```

- `ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=0` (기본): `PENDING-{rec_id}` 반환, 수동 승인 대기
- `ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=1`: 즉시 채널 API 호출, `launched` 상태
- `KEYWORD_OPT_PROVIDER=mock`: 실제 API 미호출

### 3. 입찰가 조정 (`adjust_bids`)

```python
from src.ads.auto_campaign import adjust_bids, PerformanceData
perf = PerformanceData(campaign_id="...", cost_krw=5000, revenue_krw=15000)
result = adjust_bids(campaign_id, perf)
```

| ROAS 상태 | 조정 |
|---|---|
| 0 (노출 없음) | 최대 인하 (`ADS_BID_ADJUST_MAX_PCT`) |
| 목표 × 0.8 미만 | 비율 인하 (최대 인하율 이내) |
| 목표 미만 | 소폭 인하 |
| 목표 × 1.5 초과 | 비율 인상 (최대 인상률 이내) |
| 목표 근접 | 유지 |

### 4. 성과 부진 캠페인 일시정지 (`pause_low_performers`)

```python
from src.ads.auto_campaign import pause_low_performers
paused = pause_low_performers(min_roas=0.5)
```

---

## 셀러 콘솔 UI

### `/seller/ads/campaigns`

- 추천 캠페인 목록 (SKU, 채널, 키워드, 예상 ROAS, 일일 예산, 상태)
- 활성 캠페인 목록 (캠페인 ID, 상품, 채널, 예산, 상태)
- "추천 갱신" 버튼 → `POST /seller/ads/recommend`
- 24h 통계 카드 (활성 캠페인 수, ROAS, 광고비, 매출, 추천 대기)

---

## Admin Diagnostics

`/admin/diagnostics` → 섹션 12 "광고 자동 운영 (Phase 144)":

- 자동 운영 ON/OFF 상태
- Launch 모드 (자동/수동 승인)
- 일일 예산, 목표 ROAS, 키워드 최적화 공급자
- 24h 성과 (활성 캠페인, 채널별, ROAS, 광고비, 매출)
- 추천 대기 건수

---

## 테스트

```bash
python3 -m pytest tests/test_ads_auto_campaign.py tests/test_ads_bid_adjustment.py -v
```

---

## 운영 순서

1. 환경변수 설정:
   ```
   ADS_AUTO_CAMPAIGN_ENABLED=1
   ADS_DAILY_BUDGET_KRW=20000
   ADS_TARGET_ROAS=3.0
   ```

2. `/seller/ads/campaigns` 접속 → "추천 갱신" 클릭 → 추천 캠페인 확인

3. 추천 캠페인 검토 후 수동 승인 (기본 모드)

4. 자동 launch 활성화 시 (주의):
   ```
   ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=1
   ```

5. `/admin/diagnostics` → 섹션 12에서 성과 모니터링
