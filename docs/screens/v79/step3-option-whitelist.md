# v79 STEP3 — 옵션 값 화이트리스트

## 증상(오너 실기기 1.5.108)
- **라쿠텐**: 스펙 전체(브랜드·품번 `900037`·원산지 `日本`)가 옵션값으로 뭉침.
- **아마존**: `←`,`1`,`→`,`Product Image/Video`(캐러셀 컨트롤·미디어 탭)가 옵션값.
- **알리**: `색상: 1pcs`(축명 접두 중복).

## 수리
1. **`_isBadOptValue(v)`**(신설, 전 마켓 공통) — 화살표·내비 글리프, 미디어 탭명(Product Image/Video·이미지·동영상),
   순수 품번(5자리+ 숫자 `900037`)을 옵션 값에서 배제. **사이즈(S/M/38…)·색상은 보존**(≤4자리·문자). sku 경로
   (`_collectSkuSpecs.add`)와 DOM 경로(`_domOptions._push`) **양쪽** 적용.
2. **미디어 캐러셀·스펙표 그룹 제외** — `_domOptions` 그룹 스캔에서 `#altImages`·썸네일·`a-carousel`·
   `aria-roledescription="carousel"`·`table`·`dl`·`[class*=spec]`·`[class*=attribute]` 안의 그룹은 옵션 아님
   (스펙은 `_domSpecs`가 별도 수집·정직). 테무 등 실옵션은 JSON(axisMap) 경로라 무영향.
3. **축명 접두 중복 제거** — `_push`에서 값이 `<축명>: 값`(예 `색상: 1pcs`)이면 접두 제거 → `1pcs`.

## 계약(브리프)
> STEP 3 — 옵션 values에 숫자 품번·화살표·탭명 0. 라쿠텐 색상류만·아마존 캐러셀 제외·알리 라벨 정리.

## 판정
- 가드 `tests/test_v79_option_whitelist.py`(5): source-contract + `_isBadOptValue` 단위(화살표·탭·품번 배제 /
  사이즈 S·38·색상 보존) + **Playwright**:
  - 라쿠텐 픽스처(스펙표 브랜드·`900037`·`日本` + 색상 스와치) → 옵션에 스펙 0, 색상[ブラス,シルバー] 생존.
  - 아마존 픽스처(`#altImages` 캐러셀 `←/1/→·Product Image/Video` + 색상 트위스터) → 캐러셀 컨트롤 0, 색상[White,Pink] 생존.
- 기존 옵션 하네스(테무 sku·아마존 트위스터·요시다·알리) 전량 그린(회귀 0). 노드 하네스는 새 의존(`_isBadOptValue`·
  `_normKey`) 명시화(과거 `_optClean` 과잉캡처 의존 제거).
- **판정 캡처**: `step3-option-whitelist.png`(3마켓 BEFORE/AFTER).
- 전체 **11449 passed / 22 skipped**. manifest 1.5.110→**1.5.111**.

## 금지 준수
- 추출기 변경 = 하네스 계약 동반 · 진짜 옵션(색상·사이즈) 소실 0(회귀 방지) · 스펙은 버리지 않고 `_domSpecs`로 정직 수집.

적용 스킬: (확장 추출기 순수 함수 — UI 없음. impeccable/humanizer CLI 미설치.)
