# v53 STEP1 — 확장 수집 버튼 컨텍스트 자동 감지

## 증상
단일 상품 페이지에 중앙(벌크) 버튼이 떠 수집·선택 불가. 원인: 옛 판정 `isList = cards.length >= 3` —
단일 상품 페이지도 갤러리·추천 이미지가 카드로 잡혀 3개+면 목록으로 오판.

## 수리 — 점수제 페이지 타입 감지기 `kgpDetectPageType()`
- **URL 어댑터 매치 최우선(가중치 3)**: 상세 `KGP_DETAIL_URL_RE`(temu `-g-{id}`·쿠팡 `/vp/products/`·아마존
  `/dp/`·`item.htm`·알리 `/item/`·`/products/{slug}` 등), 목록 `KGP_LIST_URL_RE`(`/search`·`?q=`·`/category`·
  `/best`·`/ranking` 등).
- **DOM 보조**: h1 1개(+1)·갤러리 캐러셀(+1)·ld+json `@type=Product`(+2)/`ItemList`(+2)·카드 그리드 6개+(+3)/3~5개(+1).
- 판정: `list > single`→목록 / `single > list`→단일 / **동점·무신호→unknown**.
- **표시(상호배타, 동시 금지)**: 목록 → 중앙 벌크 바만(1.5배 기존). 단일/unknown → **우측 단건 FAB만(안전 기본값)**.
- **SPA**: history 후킹 + MutationObserver **디바운스 500ms** 재판정.
- **수동 오버라이드**(감지 실패 탈출구): 버튼 **롱프레스(≥600ms)·우클릭** → 이 페이지를 단일↔목록 강제 토글
  (경로 단위 sessionStorage 기억), 최우선 적용.

## 로컬 실증 (node)
- URL 어댑터: temu `-g-601099`·쿠팡 `/vp/products/`·아마존 `/dp/` → 상세 매치. temu `search_result`·아마존 `/s?k=` → 목록(상세 아님).
- 점수제(mock document): 상품상세+Product ld+json+h1+갤러리 → **single**. 검색+카드8+ItemList → **list**. 오버라이드 → 강제 우선.

## 판정 (오너)
테무 단일 상품(우측만)·테무 검색 목록(중앙만)·SPA 목록→상품 이동 시 버튼 전환, 3캡처. (확장 1.5.53 재로딩.)

## 가드
test_v53_button_context(4): 소스계약(옛 카드-3 제거·디바운스500·상호배타)·URL 어댑터 node·점수제 node·manifest.
