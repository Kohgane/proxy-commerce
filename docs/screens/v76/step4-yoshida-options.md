# v76 STEP4 — 요시다 옵션(컬러 스와치) + 갤러리 스코프 재확인

## 배경(오너 하네 기준선)
- 요시다: 옵션0. 갤러리 스코프(연관상품 혼입)는 점검 대상. (실 스냅샷 미공급 — 합성 픽스처 `yoshida-detail.html`.)

## 진단
- **옵션0 근본**: 색상 스와치가 `<a data-color="ブラック"><img alt="ブラック"></a>` 구조 →
  기존 스와치 그룹 값 수집 셀렉터(`data-value`/텍스트)에 안 걸려 값 0 → 옵션 미수집.
- **갤러리 스코프**: 재확인 결과 이미 정상 — 연관상품(`related-products`)·스와치 썸네일(`/sw/`)은
  `_galleryExcluded`·컨테이너 스코프로 혼입 0(상품 갤러리 6장만). 회귀 계약으로 못박음.

## 수리 — 스와치 옵션
- **스와치 값 확장**(`_domOptions` v58 그룹 경로): 후보 셀렉터에 `a[data-color]·[data-color]·[data-option]·
  [data-name]·li a` 추가 + 값 읽기를 `data-color`/`data-option`/`data-name`·자식 `img[alt]`까지 확장
  (텍스트 없는 스와치도 값 수집).
- **부모 라벨 보완**: 라벨이 그룹(`ul.color-swatch`) 밖 형제/부모(`.item-color-select > span.label`)에 있으면
  부모 컨테이너에서 라벨 보완 → 옵션명 복원.
- **일본어 축명 인식·정규화**: `OPT_LABEL`에 `カラー/サイズ/タイプ/スタイル/色` 추가 + `_normAxis`(カラー/色→색상·
  サイズ→사이즈…)로 축명 한글 통일. 결과: 옵션 `색상`[ブラック·ネイビー·シルバー].

## 판정
- 가드 `tests/test_v76_yoshida_options.py`(3): manifest 핀 + source-contract(스와치 값 셀렉터·`img[alt]`·
  `data-color`·일본어 축명·`_normAxis`) + **Playwright 실 kgp-extractor**: 옵션 `색상`(opt≥1, 값=색상명) +
  갤러리 6장(연관상품 `/rel/`·스와치 `/sw/` 제외·대표=상품 첫 장) + 3핵심 + 제목 사이트명 0.
- 실페이지 하네스 `yoshida-detail.expected.json`에 **`options:{색상:[...]}` 재추가 + `images_max:6` +
  `images_exclude_substr:[/rel/,/sw/]`**(STEP1에서 STEP4로 미룬 옵션 계약 종결).
- **판정 캡처**: `step4-yoshida-options.png`(옵션0 → 색상 스와치 opt≥1[ブラック·ネイビー·シルバー] + 갤러리 6장·
  연관상품·스와치 제외).
- manifest 1.5.100→**1.5.101**(재로딩) + 버전핀.

## 정직 표기(한계)
- 실 요시다 스냅샷 미공급 → 합성 구조 픽스처로 계약. 옵션 없는 상품은 여전히 opt=0(값 2+ 확신 없으면 미수집=정직).

## 금지 준수
- 가짜 성공 0(스와치 값 없으면 미수집) · 갤러리 스코프 유지(연관상품 혼입 0) · 추출기 변경 = 하네스 계약 동반.

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
