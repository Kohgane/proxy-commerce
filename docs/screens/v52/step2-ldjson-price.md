# v52 STEP2 — 북마클릿 가격 수리 (ld+json 1차)

## 수리
서버 파서에 **ld+json 1차** 추가(`state_json.parse_ldjson`): 수신 html의 `<script type="application/ld+json">`
전수 파싱 → schema.org **Product**(`offers.price`/`priceCurrency`·`image`·`aggregateRating`·`description`·`review`).
AggregateOffer·`@graph`·중첩 offers 지원. 대부분 쇼핑몰이 ld+json을 실으므로 **북마클릿 가격 미수집의 본체 수리**.

- **우선순위**: ld+json → 초기상태 JSON(비-테무) → og/DOM(UniversalScraper). 빈 필드만 보강(클라 값 우선).
- **가격 sanity 동일**: KRW<100 등 → needs_check(재고·리뷰 숫자 오인 거부).
- **출처 기록**: ld+json이 채운 필드는 `sources=ldjson` → 서버 `_srv_src`로 collect_status에 병합 → 수집 로그에 `ld+json` 표기.

## 로컬 실증
- 파서: Product(offers.price 89000 KRW·image 2·rating 4.6·reviewCount 152·review 1) 매핑. AggregateOffer lowPrice 12000.
- E2E: 북마클릿형 html(ld+json) → `/api/v1/collect/extension` → **DB price=89000 KRW·images 2·rating 4.6**, price/images 출처=`ld+json`. KRW 9 → needs_check.

## 판정 (오너)
ld+json 있는 일반 쇼핑몰 1곳 북마클릿 수집 → 가격·이미지 저장 + 드로어 수집 로그 `ld+json` 캡처.

## 가드
test_v52_ldjson_price(6): 파서·AggregateOffer·빈상태·E2E 출처·sanity·소스계약.
