# v76 STEP2 — 알리 갤러리·옵션 완결 (v74 STEP4 종결)

## 배경(오너 하네 기준선)
- 알리: 갤러리3 · 옵션0. (실 스냅샷 미공급 — 합성 픽스처 `ali-detail.html`로 근본 재현·계약, 정직 표기.)

## 진단(합성 픽스처 재현)
현행 추출기를 알리 상세 구조에 돌린 결과 근본 결함 2종:
1. **sku 컬러 스와치 썸네일이 메인 갤러리로 혼입** — `skuModule.productSKUPropertyList[].skuPropertyValues[].skuPropertyImagePath`(색상칩)가
   `_walk` 이미지 라우팅 분기에 잡혀 갤러리로 들어감 → **대표 이미지(첫 장)가 상품이 아닌 색상칩**(엉뚱한 대표).
   BEFORE: `c-pink.jpg`(스와치)가 갤러리 선두.
2. 신 레이아웃 SSR 전역 미커버 — `imagePathList`가 `window.runParams` 외 변형 전역에 있을 때 미소진.

## 수리
- **`_OPT_SWATCH_KEY`**(`skuPropertyImagePath`·`propertyImage`·`swatch`·`optionImage`·`variationImage`…): sku/옵션 스와치
  이미지 키를 **갤러리 라우팅에서 제외** → 이 값은 `_collectSkuSpecs`가 이미 `option_image`(값별 이미지)로 귀속. 갤러리는
  진짜 상품 이미지(`imagePathList`)만. **대표 이미지 = 상품 첫 장** 복원.
- **STATE_KEYS에 알리 SSR 변형 전역 추가**: `_init_data_`·`__AER_DATA__`·`icRenderData`·`_d_c_`(신 레이아웃 imagePathList/
  skuPropertyList 소재). 추가는 가산적(객체만 읽음 — 회귀 위험 0).

## 판정
- 가드 `tests/test_v76_ali_gallery.py`(4): manifest 핀 + source-contract(_OPT_SWATCH_KEY 정의·두 이미지 분기 적용 +
  AE SSR 전역) + **Playwright 실 kgp-extractor**: 갤러리=`imagePathList` 7장(스와치 `c-*.jpg` 혼입 0·대표=`mini-blender-1`) +
  옵션 `Color`[White,Green,Pink] 값 텍스트 + 값별 이미지 `option_image`(갤러리 아님).
- 실페이지 하네스 `ali-detail.expected.json`에 **`images_max:7` + `images_exclude_substr:[c-white/green/pink.jpg]`** 추가 →
  스와치 갤러리 제외 계약 못박음(회귀 방지).
- **판정 캡처**: `step2-ali-gallery.png`(BEFORE 스와치 3장 갤러리 선두=대표 오염 → AFTER 갤러리 7장 스와치 0·대표=상품 첫 장 +
  옵션 Color 값·값별 이미지 option_image).
- manifest 1.5.98→**1.5.99**(재로딩) + 버전핀.

## 정직 표기(미완/한계)
- **값별 가격(per-value price)**: `skus[]` 배열이 sku 객체에 가격 필드가 있을 때 값을 담지만, 합성 픽스처의
  `productSKUPropertyList`(속성 정의)에는 값별 가격이 없어(실가는 `skuPriceList`의 `skuPropIds` 조인) **본 STEP에서 값↔가격
  조인은 미구현**. 실 알리 스냅샷 공급 시 조인 매핑 추가 예정 — **가짜 가격 생성 0**(없으면 빈 채 유지).
- 실 스냅샷 미공급 → 합성 구조 픽스처로 계약(정직). 오너 실기기 알리 1건 드로어 5탭 검증은 오너 몫.

## 금지 준수
- 가짜 성공 0(스와치 제거만 — 없는 갤러리 생성 안 함) · 추출기 변경 = 하네스 계약 동반(realpage + node·Playwright 가드).

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
