# v64 STEP6 — 번역 경로 진단

## 근본 원인 (팩트)
- `_translate_openai`/`_translate_deepl`가 **모든 예외를 삼켜** `provider="openai-fallback"`(원문 유지)로 조용히 반환.
- 라우트 `collect_bulk_translate`는 번역 0건이면 **무조건** "번역기(OPENAI/DEEPL)가 설정되지 않았습니다"를 표기 → **키가 설정돼 있는데 호출이 실패한 경우도 '키 미설정'으로 오귀인**(실제 원인 은폐 = 무음 실패).

## 수리
### 1) 실패 원인 분류 (`classify_translate_error`)
- 인증(401/403·invalid_api_key) → "API 키가 잘못됐거나 만료됐어요"
- 쿼터(429·insufficient_quota) → "API 사용량·결제 한도를 초과했어요"
- 모델(404/400 model·does not exist) → "설정한 모델명(OPENAI_MODEL)이 잘못됐어요"
- 타임아웃 → "응답이 지연됐어요" / 네트워크 → "연결하지 못했어요"
- 그 외에도 **빈 문자열 반환 없음**("호출에 실패했어요") — 무음 금지.

### 2) 원인 전달 (translator → route → toast)
- fallback 결과 dict에 `error`(분류 원인) + 서버 로그에 원인 기록.
- 라우트가 `fail_reason`을 포착 → 응답 `fail_reason` + 메시지:
  - **키 있음 + 실패** → `번역에 실패했어요 — {원인}`(오귀인 방지).
  - **키 없음** → 기존 "키 미설정" 안내.
  - 키 있는데 결과만 빈 경우 → "잠시 후 재시도" 안내.

## 판정
- 가드 `tests/test_v64_translate_diag.py` (6): 인증/쿼터/모델/타임아웃·네트워크/일반 분류 + **키 있고 401 실패 시 translate_product 결과에 원인(error) 실림**(무음 아님).
- 실기기(영문 상품 1건 번역 성공 + 자연문)는 오너가 **유효 OPENAI/DEEPL 키** 설정 시 — 코드는 실패 시 원인을 정직 표기. `docs/screens/v64/step6-translate-diag.md`.

## 금지 준수
- 무음 실패 제거(원인 표기·로깅) · 가짜 성공 0 · 자격증명 평문 0(키 값 미로깅).

적용 스킬: (백엔드 진단 로직 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
