# v54 STEP2 — 수집 자가진단 모드 (테무 API를 확장이 스스로 발견)

## 문제
Tier1 인터셉트가 어느 엔드포인트를 잡아야 하는지가 관건 — 하드코딩 URL 패턴은 테무 변경에 취약.
→ **확장이 현장에서 스스로 발견**하게 한다.

## 수리
- **필드 시그니처 채점(kgp-net.js `_kgpScore`)**: 가로챈 **모든** JSON 응답을 [가격(price/amount/salePrice 양수)·
  이미지 배열(url)·sku/스펙·리뷰(텍스트+평점)] 존재로 0~4 채점(하드코딩 URL 아님, 바운드 walk). score 0=버림.
- **자동 채택**: `window.__kgpCaptured`를 **점수순 정렬** → 최고점 응답을 상품 소스로 자동 선택. 추출기가 그
  응답을 walker에 투입하고 **채택 URL을 `tier1_source`에 기록**(sources=tier1:{URL패턴}). 매 방문 재채점 →
  테무가 구조를 바꿔도 재적응.
- **진단 모드(팝업 토글 `kgp_diag`)**: ON이면 content_script가 MAIN world에 주기 요청 → kgp-main이 F12 콘솔에
  `console.table([{url,size,price?,images?,sku?,reviews?,score}])` 출력(후보 확인).
- **매핑**: 가격(sanity KRW<100 거부)·갤러리 전체·옵션 sku·상세 이미지 배열·리뷰 텍스트+평점 → 기존 스키마.
- **Tier2 폴백** DOM 갤러리 스코프 현행 유지 + 상세 영역 img(상세 이미지 배열=테무 상세 본체) 수집 포함(기존 dSel).

## 로컬 실증 (node)
- 채점: 테무형 응답(salePrice·galleryList·skuList·reviews) → **score 4**·4시그니처 true·URL 기록. 비상품
  (PRERENDER_CONFIG/nav) → score 0 → 버림(캡처 1건).
- 추출: 최고점 응답 채택 → price 20605 KRW·갤러리 2·`tier1_source`=goods/detail URL·field_sources.price=tier1.

## 판정 (오너)
판매중 테무 상품에서 진단 모드 콘솔 표 캡처 → 일반 수집 → 드로어 5탭(가격·갤러리·옵션·상세이미지·리뷰) +
sources 로그. 빈 탭 있으면 표에서 어느 시그니처 미발견인지 지목(부분 수집). 확장 1.5.54 재로딩.

## 가드
test_v54_collect_discovery(4): 채점 node·최고점 채택+tier1_source node·진단 모드 소스계약·manifest.
