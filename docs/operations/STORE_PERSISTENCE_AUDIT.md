# Store 영구 저장 점검 (Phase 136.1)

| Store | 위치 | 백엔드 | 멀티워커 안전? | 조치 |
|---|---|---|---|---|
| PricingRuleStore | `src/pricing/rule.py` | Sheets + JSONL | ✅ | 이번 PR에서 JSONL 영구 저장 폴백 적용 |
| CollectHistoryStore | `src/seller_console/collect_history_store.py` | Sheets + 인메모리(`_in_memory`) | ❌ | 다음 PR에서 JSONL 폴백 전환 필요 |
| PersonalTokenStore | `src/auth/personal_tokens.py` | Sheets only (미설정 시 기능 비활성) | ✅ | 현재 인메모리 폴백 없음 |
| AICacheStore (`AICache`) | `src/ai/cache.py` | Sheets only (미연결 시 캐시 skip) | ✅ | 현재 인메모리 폴백 없음 |
| MessageLog | `src/messaging/log.py` | 해당 파일 없음 | - | Phase 136 기준 메시지 로그 집계는 `src/dashboard/admin_views.py`에서 처리 |

## 메모
- 이번 hotfix 우선순위는 `PricingRuleStore` 멀티워커 유실 해결.
- `collect_history_store`는 동일 유형(인메모리 폴백) 이슈 가능성이 있어 후속 PR에서 일괄 개선 권장.
