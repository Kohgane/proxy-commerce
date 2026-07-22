# v80 STEP4 — 옵션값 화이트리스트 잔여 (마감 2)

## 증상(오너 실기기 1.5.114)
라쿠텐 옵션에 `日本`·`タイ`(原産地) + 아마존 잔여 1건. sku diff 기반 옵션 추출이 원산지·브랜드 등 **공통축
(스펙 속성)**을 값이 2개 이상이면 옵션으로 통과.

## 근본 원인
v79 STEP3은 **값** 화이트리스트(`_isBadOptValue`) — 화살표·미디어 탭명·순수 품번(숫자)만 배제. 원산지 **값**
`日本`/`タイ`는 숫자/화살표/탭명이 아니라 못 걸렀다. 게다가 sku에 `原産地` 축이 있고 SKU마다 값이 다르면
(日本 vs タイ) diff 2값 → `_skusToOptions`가 옵션으로 채택.

## 수리 — 축명(_isBadOptAxis) 화이트리스트
- **`_isBadOptAxis(name)`**(신설): 축 **이름**이 스펙 속성(원산지·원산국·産地·原産·made in·브랜드·ブランド·
  메이커·メーカー·제조사·manufacturer·품번·品番·型番·모델명·model number·JAN·ASIN·barcode·보증기간…)이면
  옵션 아님. **색상·사이즈·컬러·color·size·수량·종류·타입** 등 진짜 옵션 축은 보존(안전 화이트리스트 밖).
- **sku 경로**(`_collectSkuSpecs.add`): 축이 스펙명이면 값 추가 스킵 → axisMap 미진입 → 옵션 0.
- **DOM 경로**(`_domOptions._push`): name이 스펙명이면 그룹 스킵.

## 계약(브리프)
> STEP 4 — sku 간 diff 기반 옵션 추출이 원산지·브랜드 공통축을 통과시키는 케이스 봉합. 계약: opt오염 지표 전 픽스처 0.

## 판정
- 가드 `tests/test_v80_option_axis_whitelist.py`(4): source-contract(sku/DOM 양경로) + `_isBadOptAxis` 단위
  (스펙축 15종 배제 / 진짜 옵션 11종 보존·오탐 0) + **Playwright**: 라쿠텐식 sku(`原産地` 日本/タイ 2값 diff +
  `色` ブラス/シルバー) → 原産地 축·값 옵션 0, 色 옵션 유지.
- 기존 옵션 하네스(테무 sku·아마존 트위스터·요시다·라쿠텐·실페이지) 그린 — 노드 하네스 새 의존(`_isBadOptAxis`) 명시화.
- **판정 캡처**: `step4-option-axis.png`(BEFORE 原産地 옵션화 → AFTER 축명 배제).
- 전체 **11476 passed / 22 skipped**. manifest 1.5.117→**1.5.118**.

## 금지 준수
- 추출기 변경 = 하네스 계약 동반 · 진짜 옵션(색상·사이즈) 소실 0 · 스펙은 `_domSpecs`로 정직 수집(버림 0).

적용 스킬: (확장 추출기 순수 함수 — UI 없음. impeccable/humanizer CLI 미설치.)
