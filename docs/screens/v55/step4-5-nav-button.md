# v55 STEP4 (내비 안정화) + STEP5 (버튼 감지 안정화)

## STEP4 — 내비 "명령 못 잡음" 안정화
증상: 반응은 빠른데 클릭 간헐 무시. 원인: body 스왑 후 페이지 스크립트가 document/window 리스너를 **스왑마다
재바인딩 → 중복 발화**, 또는 DOMContentLoaded 기반 init이 스왑-인 시 안 떠 요소 바인딩 유실.
- **document 위임**(엔진은 이미) + **`window.kgpInitOnce(key)` 멱등 가드** 신설 → 페이지 스크립트의 document/window
  리스너를 1회만 바인딩(위임이라 스왑 후에도 현재 DOM에 동작). 수집이력의 drawer-click·hover·keydown·message에 적용.
- **상태의존 리스너**(폴링 visibilitychange/message)는 teardown에 등록해 스왑-이탈 시 제거(누적 방지, 새 closure 재실행).
- **DOMContentLoaded → readyState 즉시실행**: 스왑-인 시 '전체선택'·행 체크박스가 죽던 것 수리(요소 단위 재바인딩).
- **인터셉트 범위 축소**: 좌클릭+무수정키+동일오리진 `<a>`만. 링크 내부 button/input/select/textarea/contenteditable/
  data-no-swap 클릭이면 스왑 안 함(컨트롤이 처리). **2초 fetch 타임아웃(AbortController)** + **2.5초 스톨 워치독** →
  즉시 일반 내비 강등(busy 고착·클릭 무시 방지).
- **prerender 이중동작**: v53부터 Speculation Rules는 **prefetch**(prerender 아님) — 문서만 캐시 워밍, 스왑 엔진과 충돌
  0(prerender 활성화 경합 없음). 유지.

## STEP5 — 수집 버튼 감지 안정화
증상: 개별 상품 페이지 우측 버튼 미표시, 중앙 버튼 점멸.
- **재판정 URL 변경 시로 한정**: history pushState/replaceState 훅 + popstate. **주기적 4초 always-refresh 제거**(점멸 근원).
- **DOM 변이 기반 재판정 제거**: MutationObserver는 **재마운트 전용**(우리 오버레이가 사이트 재렌더로 사라졌을 때만
  캐시 판정 그대로 재주입) — 재판정 아님.
- **테무 URL 하드매치 최우선(결정적)**: `-g-{숫자}` 포함 → **single**(우측), `/search` 등 → **list**(중앙). URL이 애매할
  때만 DOM 휴리스틱 1회.
- **URL별 판정 캐시(`KGP_PT_CACHE`, 세션 내 불변 = 히스테리시스)**: 같은 URL은 재판정 안 함 → DOM이 바뀌어도 번복 0.
  오버라이드 롱프레스만 예외. inject*/remove*는 멱등(이미 마운트면 no-op).

## 로컬 실증 (node)
- kgpPageType: temu `-g-601099` → **single**, 카드 50개로 늘어도 캐시로 **불변**(점멸 0), `/search?q=` → **list**.

## 판정 (오너)
주요 4페이지 30클릭 연속 왕복 — 무시 0·콘솔 에러 0. 테무 상세 3회 우측 즉시+유지, 목록 3회 중앙, 점멸 0 녹화.
(확장 1.5.55 재로딩 + `curl /health` build 해시.)

## 가드
test_v55_nav_button(4): 엔진 안정화 계약·수집이력 멱등 리스너·DOM변이 재판정 제거·URL결정+캐시 node 실증.
