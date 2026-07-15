# v71 STEP2 — sku 매퍼 수리 (버그② [object Object]+이미지 URL)

## 증상 (오너 스냅샷 실측)
- 테무 옵션 값 = **"[object Object]" + 이미지 URL** — sku 객체 매핑 실패. 근원: 스펙 객체 배열을 `sv.map(String)`로 통짜 문자열화.

## 수리 (`kgp-extractor.js` `_fromJson`)
1. **구조 추출** `_collectSkuSpecs(so, axisMap, SPEC_KEY)`: sku 스펙 객체에서 필드로 추출 —
   - 축명(`_OPT_AXIS_KEY`: specKeyName·propName·attrName…), 값 텍스트(`_OPT_VAL_KEY`: specValueName·value…), 값 이미지(`_OPT_VIMG_KEY`: image·thumbUrl…).
   - 평면 sku(축·값 필드 직접) + 중첩 specs 배열/객체 둘 다.
2. **오염 차단**: `add()`가 값에 **URL(`^https?://`)·"[object Object]"**를 명시 거부. 값 텍스트만 `values`에.
3. **값 이미지 분리**: 값→이미지는 `option_image` 필드로(브리프: values 아님).
4. 옵션은 sku 스펙 **축별**(색상·사이즈…)로 빌드(값 2+). 옛 flat "옵션" 합치기 + `sv.map(String)` 제거.

## 판정
- 가드 `tests/test_v71_sku_mapper.py` (3): 소스계약(구조 추출·URL/Object 거부·option_image·map(String) 제거) + **node 실증** — 테무식 skus(specs 객체 배열 + 평면 sku) → `색상=[블랙,화이트,레드]`·`사이즈=[L,M]`·option_image 분리·값에 `[object`/`http` 0.
- **실페이지 하네스** `synthetic-temu-detail`(전역 상태 skuList): 실 크로미움에서 `색상=[블랙,베이지]`·`사이즈=[대형,소형]` + **하네스 공통 계약(옵션 값 "[object"/"http" 금지)** 그린.
- manifest 1.5.83. `test_v62_temu_goods_match`·`test_v58_extract_contract`·`test_v52_temu_bookmarklet` 그린.
- **실기기(오너 몫)**: 테무 옵션 상품 → 드로어 옵션 탭 = 실제 옵션명·값 텍스트. (개발 프록시 라이브 테무 차단.)

## 금지 준수
- Object 문자열화 0 · URL 값 0(option_image로 분리) · 가짜 옵션 0(값 2+, 값 텍스트 못 찾으면 미수집).

적용 스킬: (확장 추출 로직 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
