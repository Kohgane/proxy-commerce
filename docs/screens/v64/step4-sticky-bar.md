# v64 STEP4 — 벌크바 sticky (퍼센티식)

## 현황
- 목록 상단 벌크바(전체선택·선택수집·전체수집·광고 포함…)는 이미 `position:fixed; top:12px; left:50%; z-index:2147483647`로 **뷰포트 상단 고정**(스크롤 추적 sticky) + **최상위 z-index**(사이트 헤더 위). `documentElement` 직속 마운트(v45 P4)로 body transform도 회피.

## 이번 STEP 하드닝
- **고전 버그 대응**: 일부 사이트는 `<html>`/`<body>` 조상에 `transform`/`filter`를 걸어 `position:fixed` 기준을 바꿔 바가 콘텐츠와 함께 스크롤돼 버린다. → `_kgpKeepBarPinned()`가 스크롤 시(120ms 스로틀) 바의 실제 `getBoundingClientRect().top`을 측정, 의도값(12px)에서 밀린 만큼 `translateY`로 보정해 **항상 뷰포트 상단 고정**.
- **드래그 존중**: 사용자가 바를 옮겨 위치를 저장했으면(`kgp_bar_pos`) 자동 재핀하지 않음.
- **마운트 즉시 보정**: `kgpInjectListing`에서 마운트 직후 1회 `_kgpKeepBarPinned()` 호출.
- 스크롤 리스너는 `__kgpBarScrollBound`로 1회만 바인딩(passive) — 중복 방지·리플로우 최소화.

## 판정
- 가드 `tests/test_v64_sticky_bar.py` (4):
  - 바 스타일 `position:fixed + top:12px + z-index 2147483647`(사이트 헤더 위).
  - 하드닝 배선(`_kgpKeepBarPinned`·스크롤 바인딩·드래그 존중·translateY 보정·마운트 재핀).
  - **node**: 조상 transform으로 top 72(기대 12)로 밀린 바 → `translateY(-60px)` 보정 적용, 드래그된 바는 미변경(존중).
  - manifest 1.5.67.
- 실기기(긴 목록 스크롤 중 벌크바 상단 고정 녹화)는 오너 환경 — 프록시 라이브 차단.

적용 스킬: (확장 오버레이 위치 로직 — 인라인 스타일, 우리 토큰 색 유지. impeccable/humanizer CLI 미설치.)
