# v56 STEP3 — AI 상세 초안 정직화

## 버그
"- k: v" 플레이스홀더 출력 + "AI 키 미설정" 안내. 원인: 키없음 폴백이 specs를 `f"- {label}: {value}"`로
무조건 렌더 → 빈/1글자('k'/'v') placeholder까지 그대로 출력. (키 부재 자체는 오너가 Render env 확인 중.)

## 수리
- **`_structured_draft()`**: 키 없음 모드 = 확인된 정보(제목·브랜드·카테고리·키워드·옵션·스펙)만으로 **구조 초안**
  (■특징 불릿 · ■옵션·상세 표 · ■안내 틀). **실키·실값만 렌더, 빈/1글자 플레이스홀더 행 생략, 창작 0.**
- **키 있음 모드**(`_describe_openai`): 제목·카테고리·옵션·키워드에서 자연 상세문 생성 — 프롬프트에 "확인된
  정보만, 없는 수치·소재·인증·원산지 창작 금지" 명시(기존 유지) + "AI 초안·검토 후 저장" 배지.
- **키 감지 요청 시점**: `AITranslator()`를 엔드포인트에서 매 요청 생성 → `_select_provider`가 `env_present`로
  os.environ을 **런타임에** 읽음(부팅 캐시 아님). 런타임에 키 설정 시 즉시 openai 전환.
- **env 명칭 단일**: 코드 전역 `OPENAI_API_KEY`(오타·이명 0) — grep 확인.

## 로컬 실증
- 키없음: '접이식 책상 / GOGA · 홈·리빙 / ■특징 차량용·접이식 / ■옵션·상세 색상: 블랙,화이트 · 소재: ABS ·
  무게: 1.2kg / ■안내 …' — **`- k: v` 재발 0**, 빈·1글자 행 생략.
- 키감지: 키 없음→stub, 런타임 `OPENAI_API_KEY` 설정→openai, 제거→stub(요청시점 읽기 실증).
- E2E: `/collect/preview/{id}/ai-description` → provider stub·is_draft·실데이터.

## 판정 (오너)
동일 상품 키없음/키있음 초안 각 캡처(k:v 재발 0). Render OPENAI_API_KEY 설정 시 자연문 출력 실기기 캡처.

## 가드
test_v56_ai_draft(5): 플레이스홀더 0·키없음 stub·요청시점 키감지·env 단일명칭·E2E.
