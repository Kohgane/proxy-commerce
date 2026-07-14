# v70 STEP2 — 옵션: 수량 제외·변형 수집 (현행범 버그②)

## 증상 (오너 실측)
- 옵션 = "Quantity 1~30" — 수량 드롭다운을 옵션으로 오인, 정작 색상 변형(twister) 미수집.

## 수리 (`kgp-extractor.js` `_domOptions`)
1. **수량 명시 제외**
   - `QTY_RE = /(수량|개수|갯수|数量|qty|quantity|amount|count)/i` — 라벨·id·name이 수량류면 옵션 후보에서 제외.
   - `_looksLikeQty(vals)` — 값이 순수 1..N 연속 정수열이면(라벨 없어도) 수량으로 판정·제외.
   - 적용 경로 3곳: `<select>` 루프 / 아마존 트위스터 값 필터 / 제네릭 라디오·버튼 그룹.
2. **아마존 twister 변형 수집**
   - 행 셀렉터: 신형 `[id^="inline-twister-row-"]` + 구형 `[id^="variation_"]` + `#twister .twisterTextDiv`.
   - 값 정제 `_twVal`: **img[alt] → aria-label → title → 텍스트** 순(스와치 색명은 img alt), `_twClean`이 'Click to select {값}'·'Select {값}' 접두 제거.
   - 축명: 행 id 표준축(color/size…) → 한글(색상/사이즈) 매핑, 없으면 `.a-form-label` 텍스트.
   - 값 스와치 셀렉터 확장: `li[id]`·`li[data-asin]`·`ul li`·`[role=radio]`·`button[data-asin]`·`.a-button-toggle`.
3. **무변형 = 단일 상품 중립**(v67 STEP3 규약 — 경고색 금지). 이번 STEP은 옵션 추출 로직만 손봄(드로어 배지 규약 불변).

## 판정
- 가드 `tests/test_v70_option_variants.py` (4):
  - 소스계약(QTY_RE·_looksLikeQty·_twVal/_twClean·variation_·Click to select).
  - **node로 실증**: 수량 select(1~30) + 색상 트위스터 4값(Black/Navy/Red/Green, Click-to-select 접두) → **수량 미수집** + **색상 = 4값**.
  - `_looksLikeQty` 단위(1..N=수량 True / 색상·사이즈·비연속·단일=False).
  - manifest 1.5.77.
- 회귀 갱신: `test_v58_options_version`(수량 라벨 그룹 제외로 정정)·`test_v62_amazon_twister`(트위스터 값 필터 QTY_RE 참조·variation_ closest 가드).
- **실기기(오너 몫)**: 색상 4종 상품(BENKS류) → 드로어 옵션 탭 = 색상 4값 캡처. (개발 프록시 라이브 아마존 차단.)

## 금지 준수
- 수량=옵션 0(명시 제외) · 무변형 경고색 0(v67 규약) · 가짜 옵션 0(값 2+·확신 없으면 미수집).

적용 스킬: (확장 추출 로직 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
