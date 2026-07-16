# v72(b) STEP4 — 알리 호버 버튼 자식 격리 + 확장 신선도 배너

## 1) 알리 '수집' 호버 알약 과대 — 근본 감사
- v72 STEP4는 버튼 **루트**만 `all:initial`(+고정 px !important) 격리했다. 그런데 호버 알약(`.kgp-card-quick`)의
  **자식 span**(브릿지 아이콘 + `.kgp-q-label` 텍스트)은 인라인 보호가 없어, 알리 등 사이트의 **직접**
  `span{ font-size/width … !important }` 규칙에 **직접 매칭**돼 폭주 → 버튼 `width:auto`가 따라 폭주.
  (루트의 all:initial은 상속 오염만 막고, 자식을 직접 겨냥하는 사이트 규칙은 못 막는다.)
- **수리**: 자식 span도 인라인 `all:initial !important` + 고정 스펙(`font:800 15px`·`width:auto`·`white-space:nowrap`)
  으로 박음(`_kgpQuickIconSpan`·`_kgpQuickLabelSpan`). 인라인 !important는 캐스케이드 최상위 → 사이트
  스타일시트 !important도 못 이김. 알리·테무·아마존 호버 버튼 픽셀 동일.

## 2) 확장 신선도 배너(콘솔)
- content_script가 설치 버전을 `documentElement[data-kgp-ext]`에 **각인**(호스트 게이팅 무관, 모든 페이지·우리
  콘솔 포함). 수집 이력 페이지가 이 값을 최신(서버 manifest)과 대조:
  - 낮으면 `pc-status-warning`: '설치 vX < 최신 v1.5.90 — chrome://extensions에서 재로딩'.
  - 같으면 `pc-status-success`: '고가수집기 최신 버전 ✓'.
  - 미감지(3초 내 미각인): `pc-status-info`: '확장 미감지 — 설치·재로딩 방법'.
- 버전 비교는 **숫자 semver**(1.5.9 < 1.5.90, 문자열 비교 아님). 서버가 버전 못 읽으면 배너 생략(가짜 금지).
- 수집 품질 이슈(가격 '-'·구스코프)의 최다 원인=구버전 캐시 확장 → 오너가 눈으로 신선도 확인.

## 판정
- 가드 `tests/test_v72b_ali_button_isolation.py` (8):
  - source: 자식 헬퍼 all:initial·호버 innerHTML 헬퍼 사용·버전 각인·배너/뷰 주입.
  - **node**: 배너 cmp 숫자 비교(1.5.9<1.5.90 = -1, 동일=0, 상위=1).
  - **Playwright 3사이트**(알리·테무·아마존): 적대적 `span{80px!important;width:600px!important;line-height:5}`
    하에서 호버 라벨 = **우리 스펙 15px**·버튼 폭 <220px·높이 ≤46px(자식 격리 실증).
- manifest 1.5.89→**1.5.90**(재로딩 유도) + 버전핀 34곳 갱신.
- 회귀: 전체 그린.
- **실기기(오너 몫)**: 알리·아마존·테무 목록서 호버 '수집' 버튼 동일 크기 3캡처 + 콘솔 신선도 배너(구버전/최신) 캡처.

## 금지 준수
가짜 성공 0(서버가 버전 못 읽으면 배너 생략) · 하드코딩 색 0(pc-status 토큰) · 이모지=✓만(체크, bi-* 아이콘).

적용 스킬: **gogabridj-design**(배너=pc-status 토큰·확장 버튼 인라인 스타일 관행 유지). impeccable/humanizer CLI 미설치→의도 수동.
