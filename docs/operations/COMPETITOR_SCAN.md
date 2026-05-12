# COMPETITOR_SCAN (Phase 152)

우선순위:
1. 키워드 최적화 결과 재사용(가능 시)
2. 마켓 검색 API(`src/pricing/competitor_scout.py`)
3. fallback mock 데이터

정리 규칙:
- 상위 N개 가격 수집
- IQR(사분위) 기반 이상치 제거
- 캐시 TTL 기본 12시간 (`PRICING_COMPETITOR_SCAN_TTL_HOURS`)
