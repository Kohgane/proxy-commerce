# 셀러 BI 대시보드 (Phase 141)

## 경로

- `/seller/analytics`

## 위젯

- 매출 요약(오늘/이번주/이번달)
- 베스트셀러 TOP 20
- 재고 알림(임박/과잉)
- 광고 ROI(요약)
- CS/배송 품질 요약

## 환경변수

```env
ANALYTICS_CACHE_TTL_SECONDS=300
ANALYTICS_FALLBACK_PATH=data/analytics_cache.jsonl
```
