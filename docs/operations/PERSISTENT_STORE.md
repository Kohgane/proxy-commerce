# Persistent Store 가이드 (Phase 141)

## 공통 원칙

- 1순위: Google Sheets
- 2순위: JSONL 폴백 (`tmp -> fsync -> os.replace` atomic write)
- 같은 워커 내 동시성: `threading.Lock`/`RLock`
- 멀티워커: 호출 시점마다 파일 재조회 (인메모리 영구 캐시 금지)

## 적용 범위

- `src/utils/persistent_store.py`
- `src/pricing/rule.py` (`PricingRuleStore`)
- `src/pricing/competitor_store.py` (`CompetitorStore`)

## 운영 점검

1. `PRICING_RULES_FALLBACK_PATH`, `COMPETITOR_SCRAPE_FALLBACK_PATH` 경로 쓰기 가능 확인
2. Sheets 실패 시에도 JSONL이 갱신되는지 확인
3. 멀티워커 환경에서 생성/수정 후 새로고침 시 데이터 유지 확인
