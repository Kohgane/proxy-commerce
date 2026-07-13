# v66 STEP4 — 번역 파이프라인 종결

## 진단 (실원인 특정 — 추측 수리 금지)
- 무료횟수 카운터(`translation_usage`) 감사: `get_used`/`remaining`/`increment` 정상(실 번역만 차감, n≤0 무변화) — **카운터 버그 없음**.
- 실패 실원인 = **키 있음·호출 실패**(401/429/모델/타임아웃) 시 v64 STEP6 `classify_translate_error`가 분류하나, 확장·북마클릿 collect 경로(`_translate_payload`)는 raw 예외만 로깅 → **원인 은폐**가 잔여였음.
- 북마클릿 `translate=true` 경로 확인: `/api/v1/collect/extension` → `_translate_payload` → `AITranslator().translate_product` **실제 서버 번역 태움**(무료 카운터 미적용 = 수집 시 항상 시도).

## 수리
- `_translate_payload`(확장·북마클릿): 키 있는데 호출 실패(fallback `error`) 또는 예외 시 **`classify_translate_error`로 분류한 원인을 서버 로그 + `translate_error` 필드**로 남김(무음·오귀인 제거).
- 벌크 번역 라우트: 결과 항목별 **`reason`**(실 번역기 실패 원인 / 무료 한도 소진) 명시.
- 프론트(collect_history): **진행 `N/total`** + 실패 항목 수·**사유** 토스트. 전건 실패 시 키 있으면 원인, 없으면 키 미설정 안내(오귀인 금지).

## 판정
- 가드 `tests/test_v66_translate_pipeline.py` (4) + 기존 `test_v64_translate_diag`(6):
  - collect 경로 원인 표기·벌크 항목별 사유·프론트 진행/사유 계약.
  - **키 있고 401 실패 → `_translate_payload` 결과에 `translate_error`(키 원인)** 실증(무음 아님).
- 실기기(아마존 영문 3건 벌크 번역 → 자연 한국어 상품명 + 실패 0)는 오너가 **유효 OPENAI/DEEPL 키** 설정 시 — 코드는 실패 시 원인 정직 표기. 원인 로그는 `[collect 번역]`·`번역 실패(원인)` 서버 로그.

## 금지 준수
- 추측 수리 없음(원인 분류 후 표기) · 무음 실패 0 · 자격증명 평문 0(키 값 미로깅) · 가짜성공 0.

적용 스킬: (백엔드 진단 + 프론트 토스트 — 우리 토큰 유지. impeccable/humanizer CLI 미설치.)
