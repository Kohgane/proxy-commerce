# v80 STEP1 — 선택 체크박스 투명 렌더 수리 (P0)

## 증상(오너 실기기 1.5.114)
좌상단 선택 UI가 기능은 작동(선택 성공)하나 **시각적으로 미표시** — I빔(텍스트) 커서 + 무스타일 텍스트 노드.

## 근본 원인
선택 배지가 **light-DOM 텍스트 배지**(`.textContent = "선택"` + `all:initial` 인라인). `_KGP_RESET`의
`all:initial !important`가 **비-!important 속성**(`cursor:pointer`·`box-shadow`)을 initial로 스트립 →
커서가 I빔(text)으로, 그림자 소실. 사이트 CSS 상속·경합에도 취약해 '무스타일 텍스트만 렌더'.

## 수리
1. **shadow DOM 자체 렌더**: 신규 `_kgpBuildCheckbox(host, selected)` — 호스트에 `attachShadow`를 달고
   체크박스를 shadow 안에서 그림(사이트 CSS·`all:initial` 취약성에서 완전 격리).
2. **스타일 이중 주입**: `adoptedStyleSheets`(`new CSSStyleSheet().replaceSync`) **+ `<style>` 인라인 폴백**
   (항상 주입). adoptedStyleSheets 미지원 시 **콘솔 경고** + 인라인 폴백으로 렌더 보장.
3. **자체 그린 체크박스**(토큰 준수): 미선택=**먹 반투명 원**(`rgba(26,23,20,.82)`)+**금 테**(`#c9a24b`),
   선택=**청록 박스**(`#119a8e`)+**금 체크**(`#f0d68a` SVG). **22px** 고정, 이미지 위 대비 보장(반투명 백킹).
4. 호스트는 위치·크기 컨테이너만(`position/width:22px/height:22px/cursor:pointer` 전부 **!important** —
   I빔 근원 봉인). 텍스트 배지 폐기.

## 계약(브리프)
> STEP 1 — shadow root 스타일 이중화 + 자체 그린 체크박스(먹 원+금 체크, 22px, 반투명 백킹). 판정: 미선택/선택 두 상태 육안 확인.

## 판정
- 가드 `tests/test_v80_checkbox_render.py`(3): source-contract(shadow·이중 주입·자체 그린·텍스트 배지 폐기·
  cursor:pointer !important) + **Playwright**: shadow 체크박스 실렌더 — 미선택 박스 배경 투명 아님(무스타일 아님)·
  체크 숨김 / 클릭→선택 시 `.b.on`·체크 표시·배경 청록(`rgb(17,154,142)`)·22px·cursor pointer.
- 기존 배지 하네스(`test_v71_infinite_rescan`·`test_v73_button_render`·`test_v72_button_isolation`) 갱신·그린
  (텍스트 배지→shadow 계약).
- **판정 캡처**: `step1-checkbox-render.png` — **실제 Playwright 렌더**(이미지형 그라데이션 위): 미선택 먹 박스+금
  테, 선택 청록 박스+금 체크. 두 상태 육안 구분.
- 전체 **11466 passed / 22 skipped**. manifest 1.5.114→**1.5.115**.
- 오너 최종 판정: 확장 재로딩 후 아마존·알리·요시다 목록에서 미선택/선택 캡처 3장.

## 금지 준수
- 추출기 무변경(오버레이 렌더만) · 토큰 준수(먹/금/청록) · 이모지 0(SVG 체크).

적용 스킬: (확장 오버레이 shadow DOM 렌더 — 인라인/shadow 스타일 관행, 앱 CSS 토큰은 색만 준수. impeccable/humanizer CLI 미설치.)
