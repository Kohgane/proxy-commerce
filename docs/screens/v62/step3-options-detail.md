# v62 STEP3 — 옵션·상세 완성도 (확장 기준)

## 감사 결과 (이미 충족분)
| 항목 | 상태 | 근거 |
|---|---|---|
| Tier1 sku 스펙 → 옵션 | ✅ v56/v58 | `_fromJson` sku.spec 축 병합 → `options[{name:"옵션",values}]` |
| Tier2 구매박스 옵션 UI (select/radio/swatch) | ✅ v58 STEP2 | `_domOptions` — select + `[role=radiogroup]/[class*=sku/option/variant/spec/swatch i]` 그룹 텍스트 |
| 상세 desc_text·desc_images 분리 | ✅ v60 | 아마존 feature-bullets+A+ / 테무 상세이미지 배열 / 제네릭 ld+json→본문, 확장 경로 동일 |

## 이번 STEP 수리 — 아마존 트위스터 축 이름 정확화
- **증상:** v58 스와치 경로가 트위스터 값(Black/White·S/M)은 잡지만 축 이름이 `옵션`으로 뭉개짐.
- **수리(`kgp-extractor.js::_domOptions`):**
  - `[id^="inline-twister-row-"]` 행을 별도 스캔 → 행 id의 표준 축(`color_name`→**색상**, `size_name`→**사이즈**, style/pattern/flavor/model/material/edition)을 `_TW_ID`로 한글 매핑. 비표준 행은 `.a-form-label`(`Color:` 등) 텍스트로 폴백.
  - 값은 스와치 li/버튼 title·aria-label·텍스트에서 추출(회귀 0 — v58과 동일 값).
  - **중복 배제:** 제네릭 스와치 경로가 같은 `ul.swatches`를 다시 `옵션`으로 넣지 않도록 `grp.closest('[id^="inline-twister-row-"]')` 가드.
- **정직:** 값 2개 미만이면 미수집(확신 없으면 빈값), 담기/구매 버튼 텍스트 제외.

## 판정
- 가드 `tests/test_v62_amazon_twister.py` (3):
  - 소스 계약(트위스터 셀렉터·`_TW_ID`·closest 중복가드)
  - **node로 mock 트위스터 DOM 실행** → `색상=[Black,White,Blue]`·`사이즈=[S,M]`, 축명 정확·값 유지·중복 0.
  - manifest 1.5.63.
- 실기기(아마존 variation 상품 확장 수집 → 옵션 표 색상/사이즈 축명) 캡처는 오너 환경(프록시가 라이브 아마존 차단).

적용 스킬: (확장 추출기 — 우리 토큰 무관 로직. impeccable/humanizer CLI 미설치.)
