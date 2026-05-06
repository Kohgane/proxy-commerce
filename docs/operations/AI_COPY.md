# AI 카피라이터 운영 가이드

## 개요

Phase 134에서 구현된 AI 카피라이터는 해외 상품 메타데이터를 입력받아 마켓별 최적화 한국어 카피를 자동 생성합니다.

## 흐름

```
상품 수집 (URL)
    ↓
수집 결과 미리보기 (/seller/collect)
    ↓
"AI 카피 생성" 버튼 클릭 (variants=1~5 선택)
    ↓
캐시 조회 (Sheets ai_cache)
    ↓ miss
예산 확인 (BudgetGuard)
    ↓ 통과
OpenAI gpt-4o-mini 호출 (또는 DeepL 폴백)
    ↓
금지어 검사 (ForbiddenTermsFilter)
    ↓
캐시 저장 + 예산 기록
    ↓
변형 1/2/3 탭 표시 → 선택 → catalog 저장
```

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | P1 | OpenAI API 키 (gpt-4o-mini 기본) |
| `OPENAI_MODEL` | 선택 | 기본값: `gpt-4o-mini` |
| `AI_MONTHLY_BUDGET_USD` | 선택 | 월 예산 상한 (기본: `100`) |
| `DEEPL_API_KEY` | P2 | DeepL 폴백 번역 키 |
| `ADAPTER_DRY_RUN` | 개발 | `1` 설정 시 샘플 응답 반환 |
| `AI_CACHE_TTL_DAYS` | 선택 | 캐시 TTL (기본: `30`일) |

## 마켓별 프롬프트 커스터마이즈

프롬프트 파일 위치: `src/ai/prompts/`

| 파일 | 마켓 |
|---|---|
| `coupang.txt` | 쿠팡 |
| `smartstore.txt` | 네이버 스마트스토어 |
| `11st.txt` | 11번가 |
| `wc.txt` | 코가네멀티샵 (WooCommerce) |
| `default.txt` | 공통 폴백 |

프롬프트를 직접 수정하면 다음 AI 호출부터 반영됩니다 (캐시 TTL 내 기존 결과는 유지).

## 캐시

Sheets `ai_cache` 워크시트에 저장됩니다.

| 컬럼 | 설명 |
|---|---|
| `cache_key` | 요청 해시 키 |
| `source_hash` | 원문 해시 (16자) |
| `result_json` | JSON 직렬화 결과 |
| `provider` | `openai` / `deepl` / `stub` |
| `created_at` | 생성 시각 (ISO 8601) |
| `hits` | 캐시 조회 횟수 |
| `tokens` | 총 토큰 사용량 |
| `cost_usd` | 비용 (USD) |

TTL 초과 또는 상품 정보 변경 시 `AICache.invalidate(cache_key)` 호출로 무효화.

## 예산 관리

- **월 예산**: `AI_MONTHLY_BUDGET_USD` (기본 $100)
- **80% 경고**: 텔레그램으로 경고 알림
- **100% 초과**: OpenAI 호출 차단 + 텔레그램 긴급 알림 + DeepL 폴백 시도
- **비용 기록**: Sheets `ai_spend` 워크시트
- **현황 확인**: `/seller/ai-budget` (JSON API)

## 금지어 정책

다음 표현은 금지어 필터에 의해 경고 처리됩니다:

| 카테고리 | 금지어 예시 | 대안 |
|---|---|---|
| 의료 | 치료, 예방, 효능, 질병 | 케어, 관리, 효과 |
| 과장 | 최고, 1위, 절대, 완벽 | 인기, 베스트셀러 |
| 비교광고 | 타사 대비, 경쟁사 | (삭제) |
| 법규 | 다이어트, 지방 분해 | 체형 관리, 관리 |

`ForbiddenMatch.suggestion`이 있는 경우 자동 대체 제안됩니다.

## A/B 변형

`variants=3` 지정 시 3개 카피 후보를 동시 생성합니다.
- 동일 캐시 키에 모두 저장
- `/seller/collect` 미리보기에서 탭으로 확인
- "이 변형으로 등록" 클릭 → catalog 저장
