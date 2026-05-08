# PRICING_AUTOMATION (Phase 140)

## 환경변수

```env
PRICING_AUTO_APPLY=0
PRICING_AUTO_APPLY_THRESHOLD_PCT=5
PRICING_MIN_MARGIN_PCT=15
PRICING_FX_ALERT_THRESHOLD_PCT=2
PRICING_MONITOR_INTERVAL_MINUTES=30
COMPETITOR_SCRAPE_FALLBACK_PATH=data/competitor_prices.jsonl
```

- 자동 적용은 기본 OFF입니다.
- `PRICING_AUTO_APPLY=1`이어도 변동폭이 `PRICING_AUTO_APPLY_THRESHOLD_PCT` 이내일 때만 적용됩니다.

## 운영 플로우

1. `/seller/pricing/rules`에서 룰 생성
2. `/seller/pricing/competitors`에서 경쟁사 URL 등록 후 즉시 모니터링
3. `/seller/pricing/simulate` 또는 UI 시뮬레이션으로 dry-run 확인
4. 운영자 승인 후 `/seller/pricing/run-now` 실행
5. `/seller/pricing/history`로 변경 이력 점검
6. `/admin/diagnostics` 가격 자동화 카드로 24h 상태 확인
