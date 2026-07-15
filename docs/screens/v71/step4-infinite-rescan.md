# v71 STEP4 — 무한스크롤 재스캔 + 버튼 단일 스펙 (알리 등)

## 증상 (오너 스냅샷 실측)
- 알리: 첫 화면만 버튼, 스크롤 시 미부착 + 버튼 과대. 타 디폴트 마켓 미부착.
- 근원: v55에서 점멸 방지로 주기 재스캔 제거 → 신규 타일에 배지 재부착 경로가 사라짐(오버레이 전체 소실 때만 재마운트).

## 수리 (`content_script.js`)
1. **재스캔 상시화** `kgpRescanTiles()`:
   - `MutationObserver(body)`(신규 타일 유입) + `scroll`/`resize` 리스너(가상화 리스트: childList 무변이 노드 재사용)로 트리거.
   - **디바운스 300ms**, **목록 모드만**(`kgpPageType()==="list"` — 캐시 판정, 재판정 아님 → v55 점멸 방지 유지), 바 닫힘/iframe 스킵.
   - `kgpInjectListing()`은 멱등(배지 있는 카드 스킵).
2. **가상화 재사용 노드**: 카드 요소가 스크롤로 다른 상품에 재사용되면 배지 `dataset.url`을 새 상품 url로 갱신 + 선택 상태 재동기화. 배지 클릭은 **`badge.dataset.url`(갱신 반영)** 사용(옛 클로저 url 아님).
3. **버튼 단일 스펙** (사이트 CSS 간섭 격리): `kgpCardBadgeStyle`·`kgpQuickBtnStyle`의 크기·형태 속성(position·padding·font·border-radius·min/max-height·box-sizing·width/height)에 **`!important`**(인라인+`!important`=최고 특이성) → 알리 등 사이트 CSS가 버튼을 못 늘림. v64 필형(min-height 34) 유지.

## 판정
- 가드 `tests/test_v71_infinite_rescan.py` (4):
  - 소스계약(kgpRescanTiles·목록게이트·scroll/MutationObserver·가상화 dataset.url·!important ≥20).
  - **node로 `kgpCardBadgeStyle`**: 크기/형태 속성 + `!important` ≥6.
  - **Playwright 실브라우저**: 목록 5타일 → 배지 5 → 3타일 유입 → **재스캔이 신규 타일에도 배지(8)**.
- manifest 1.5.85. `test_v45_p3p4p5`·`test_v42_e4_selectall`·`test_v60_hover_default`·`test_v67_universal_tiles` 그린(회귀 0).
- **실기기(오너 몫)**: 알리 검색결과 3화면 스크롤 내내 전 타일 부착 + 버튼 크기 통일 녹화. (개발 프록시 라이브 알리 차단.)

## 금지 준수
- 1회성 스캔 회귀 0(상시 재스캔) · 재판정 점멸 0(목록 캐시 게이트) · 가짜 성공 0.

적용 스킬: (확장 오버레이 위치/재스캔 — 버튼 스타일은 확장 인라인 관행 유지(먹/금/청록 토큰 색). gogabridj-design 토큰은 앱 CSS 전용. impeccable/humanizer CLI 미설치.)
