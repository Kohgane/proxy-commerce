# v65 STEP3 — 수집 버튼 앵커 수리

## 증상
- 호버 [수집] 버튼이 카드 우측 **허공에 부유** — 카드 전체 기준 중앙 앵커라, 이미지가 카드 한쪽에 몰린 레이아웃에선 이미지 옆 빈 공간에 뜸.

## 수리 (`content_script.js`)
- `_kgpCardImage(card)` — 카드 내 **가장 큰 상품 이미지 요소**(≥60×60, 아이콘 제외) 탐색.
- 버튼을 카드가 아니라 **이미지 요소의 부모**에 append(`host = imgEl.parentElement`), 부모를 `position:relative`로. → 버튼 앵커(중앙/7시/5시)가 **이미지 영역 기준**으로 뜬다.
- **폴백**: 이미지를 못 찾으면 `mode='corner'` → 카드 **좌상단**(top:6px·left:6px)에 붙임(허공 금지).
- `_kgpAnchorCss(mode)`·`kgpQuickBtnStyle(collected, mode)`로 모드 전달. `q.dataset.anchorMode`에 저장 → 수집됨 재스타일·호버 앵커 변경 시에도 모드 보존.

## 판정
- 가드 `tests/test_v65_button_anchor.py` (4):
  - 소스계약(`_kgpCardImage`·이미지 부모 host·corner 폴백·anchorMode 보존).
  - **node**: `_kgpCardImage`가 아이콘 제외 최대 이미지 채택·이미지 없으면 null / `_kgpAnchorCss('corner')`=좌상단·기본=이미지 중앙.
  - manifest 1.5.70. v64 button-spec 시그니처 계약 갱신.
- 실기기(아마존·테무·요시다에서 버튼이 이미지 위에 뜨는 3캡처)는 오너 환경 — 프록시 라이브 차단.

## 금지 준수
- 허공 버튼 제거(이미지 앵커 + 좌상단 폴백) · 토큰 색 유지(먹/금/청록).

적용 스킬: **gogabridj-design**(버튼 먹/금/청록 토큰 유지). impeccable/humanizer CLI 미설치→의도 수동.
