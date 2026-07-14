# v70 STEP6 — 테무 보강 소형 창 판정 회수 (v67 STEP2 잔여)

## 브리프 핵심
- 보강 소형 창(활성 창) 방식이 **실기기에서 뜨는지부터**. 안 뜨면 그 지점 수리가 이 STEP의 전부.

## 감사 + 견고화 (`background.js` `_kgpEnrichOne`)
- 창 생성 코드(`chrome.windows.create({type:"popup", 480×640, focused:false})`)는 정상. 다만 **실패 시 폴백이 없어** 정책/환경에서 창이 안 뜨면 그 항목이 조용히 실패(원인 불명).
- **수리(조용한 실패 제거):**
  1. `chrome.windows` 미가용 또는 `create` 실패(정책·팝업 차단) → **백그라운드 탭 폴백**(`chrome.tabs.create({active:false})`)으로 보강 계속 + `console.warn`에 사유(정직).
  2. 창은 떴는데 `win.tabs` 미포함(타이밍) → **`chrome.tabs.query({windowId})`로 탭 id 조회**(id만 — tabs 권한 불요). 그래도 없으면 폴백.
  3. 테무 성공 기준(`_kgpEnrichVerdict`: 가격 실가 + 갤러리 자기 상품 ≥3) 미달·인터스티셜 → **정직 실패**(POST 안 함 = '보강 완료' 처리 0). 창은 finally에서 정리.

## 판정
- 가드 `tests/test_v70_enrich_window.py` (3):
  - 소스계약(창 미가용 폴백·탭 폴백 active:false·창 탭 조회·verdict 게이트·창 정리).
  - **node로 `_kgpEnrichOne` 실증**:
    - A) 창 성공 → 창 사용·서버 `/enrich` POST 1회·창 정리, 탭 폴백 0.
    - B) 창 생성 throw → **백그라운드 탭 폴백(active:false)**·POST 1회·탭 정리(창 remove 0).
    - C) 테무 갤러리 2장(게이트 미달) → **정직 실패**(POST 0, throw)·창 정리.
  - manifest 1.5.81. `test_v67_visible_enrich` 그린(창 방식·verdict 불변).
- **실기기(오너 몫)**: 확장 1.5.81 재로딩 → 테무 2건 벌크 → 보강 창(안 뜨면 폴백 탭) 완주 녹화 + 드로어 가격·썸네일(≥3)·옵션 탭 캡처 → `docs/screens/v70/`. (개발 프록시가 라이브 테무 차단 → 대행 불가.)

## 금지 준수
- 렌더 미보장 상태로 '보강 완료' 0(verdict 게이트) · 조용한 실패 0(폴백 + 사유 로그) · 서버측 직접 크롤 0(확장 DOM).

적용 스킬: (확장 오케스트레이션 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
