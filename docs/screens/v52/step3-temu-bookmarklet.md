# v52 STEP3 — 테무 × 북마클릿 (Tier2 클라 추출)

북마클릿은 클릭 시점 페이지 컨텍스트에서 렌더된 DOM을 읽을 수 있다 → outerHTML 슬라이스에 기대지 않고
**클라에서 소형 구조 추출**을 직접 수행해 payload에 동봉(GX/BS/PP/PR 인라인, ~5.6KB, 복사방식 URL 한도 내).

- **타이틀**: `h1` 우선 → og:title → document.title.
- **가격**: 메인 가격 노드(`[class*=price]` 등) 통화패턴, **취소선/정가 제외**(del·s·strike·original·정가·원가·할인전·compare),
  큰 폰트 우선 = 판매가. PP로 통화기호+숫자 파싱(₩·원·$·¥…→KRW/USD/JPY…).
- **이미지**: 갤러리 컨테이너 스코프(gallery/swiper/carousel/preview/main-image) `BS`(currentSrc·data-src·srcset 최고해상),
  추천/연관(`GX`) 제외, **naturalWidth 필터 금지**(추천 이미지 오수집 원인 제거).
- **field_sources** 동봉(tier2/tier3) → 서버 수집 로그. 못 채우는 필드(리뷰 텍스트·전체 sku)는 **부분 수집** + 테무 접속 시
  "확장 권장" 토스트 1회(v51 규약). 확장 Tier1(API 인터셉트)은 v51에서 완료 — 중복 없이 이어짐.

## 로컬 실증
- PP(node): ₩89,000→{89000,KRW}, 89,000원→{89000,KRW}, $12.99→{12.99,USD}, '재고 5개'→null.
- 서버: 북마클릿 field_sources(tier2) → 수집 로그 `Tier2(DOM)`. 못 채운 필드 → 부분 수집.
- 크기 5.6KB(<6000 한도).

## 판정 (오너)
판매중 테무 상품 북마클릿 수집 → 가격 실판매가 일치 + 해당 상품 갤러리 이미지만 저장 + 부분수집 배지 캡처.

## 가드
test_v52_temu_bookmarklet(4): Tier2 소스계약·크기한도·**PP 파싱 node 실증**·서버 field_sources 반영.
