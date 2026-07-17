# v74 STEP2 — 벌크바 대비 자립 (다크/라이트 헤더 동일 가독)

## 증상
다크 헤더(요시다) 위 벌크바 버튼이 저대비로 **유령화**(텍스트 안 보임).

## 근본
벌크바 버튼 스타일이 `all:initial`(v72 격리) 뒤에 `color:#e7ddc9` 등을 **비-`!important`**로 줬다.
`all:initial !important`가 `color:initial`(=검정)을 !important로 세팅 → 비-!important 버튼색을 이겨 **버튼 텍스트=검정**.
다크 바(#1a1714) 위 검정 텍스트 = 유령화. (v73 STEP1의 위치 오프셋과 동일 계열 — 이번엔 색.)

측정(수리 전): 벌크바 버튼 `getComputedStyle.color = rgb(0,0,0)`.

## 수리 (자립 스타일)
벌크바 **배경(먹 #1a1714)·텍스트(웜화이트 #f5efe3)·버튼 색/보더 전부 `!important`** — all:initial과 사이트 색
규칙(`button{color:…!important}`)을 모두 이겨 자립. 다크·라이트 헤더 무관 동일 렌더. z-index 최상위(기존).
- ghost `#e7ddc9`·gold `#e8d6a8`·teal `#fff`/`#119a8e`·그립 `#ecdcb0`·카운트/상태 `#f5efe3`·재시도 버튼 전부 !important.

## 판정
- 가드 `tests/test_v74_bar_contrast.py`(4): source-contract(색 전부 !important) + **적대적 CSS**
  (`button,span,strong{color:#111!important}` 다크 / `#fff!important` 라이트) 하에서 벌크바 버튼이 **우리 색 유지**
  (ghost=rgb(231,221,201)·gold=rgb(232,214,168)·teal=흰색·바 배경=먹) — 다크/라이트 2케이스 파라미터.
- 회귀: `test_v64_sticky_bar`·`test_v45_collect_ui`·`test_v72_button_isolation` 그린. 전체 그린.
- **판정 캡처 2장**: `step2-bar-yoshida-dark.png`(다크 헤더 — 전 버튼 가독), `step2-bar-amazon-light.png`(라이트 헤더).
- manifest 1.5.93→**1.5.94**(재로딩) + 버전핀.
- **실기기(오너 몫)**: 요시다(다크)·아마존(라이트) 벌크바 전 버튼 가독 캡처 2장(확장 1.5.94 재로딩 후).

## 금지 준수
사이트 CSS 상속 벌크바 0(자립 !important) · 추출기 변경 0 · 가짜 성공 0(적대적 CSS 하 실측).

적용 스킬: **gogabridj-design**(먹/금/청록/웜화이트 토큰·자립 격리). impeccable/humanizer CLI 미설치→의도 수동.
