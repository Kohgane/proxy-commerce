# v86-O — Shopify·WooCommerce 상세페이지(블록/HTML) 소비 배선

## 배경
v86-N(#583)은 `description_html`을 읽는 마켓(**쿠팡·스마트스토어·11번가**)만 배선했다.
④ 메인 감사에서 나머지 두 마켓의 별건 갭을 확정:

- **Shopify** `_upload_shopify`: plain `description`만 읽음 → 셀러가 꾸민 블록/HTML 미반영.
- **WooCommerce** `_generate_description`: **항상 벤더 템플릿**(제목·브랜드·원산지 + 배송·관부가세·
  교환반품 안내)만 생성 → 셀러의 실제 상세(블록/설명)가 **전면 유실**(선재 결함).

## 수리
- **Shopify**: `_upload_shopify`가 `description_html`(= `_payload_for_market`가 블록에서 렌더,
  shopify 오버라이드 else 공통) **우선** → ShopifyAdapter `body_html`에 반영. 블록 없으면 기존
  plain `description` 폴백(회귀 0).
- **WooCommerce**: `_upload_woocommerce`가 `to_collected(...).description_html`을 catalog_row
  `description`으로 전달. `_generate_description`이 **셀러 상세가 있으면 본문으로 사용**,
  없으면 기존 벤더 템플릿 헤더로 폴백. **배송·관부가세·교환반품 컴플라이언스 안내는 항상 하단 유지.**

정직: 페이지/셀러 편집 콘텐츠만 반영. 신규 UI 0. 블록·설명 없으면 기존 동작 그대로.

## before/after (실행 증거)
동일 블록(자동 3단 우산 · 8K 살대 / 무료배송 강조 / 소재)으로:

**Shopify** (`body_html`)
```
BEFORE: '간단한 원문 설명'                 ← plain description
AFTER : 블록 HTML 348자 (자동 3단 우산 …)   ← 셀러 상세 꾸미기 반영
```

**WooCommerce** (상품 설명 본문)
```
BEFORE: 셀러 상세 없음 (벤더 템플릿 + 관부가세 안내만)
AFTER : 셀러 상세 '자동 3단 우산 · 무료배송 …' 반영 + 관부가세/배송 안내 유지
```

## 판정
- 가드 `tests/test_v86_o_shopify_woo_detail.py`(6): Shopify 블록 승리·plain 폴백,
  woo 셀러본문 우선·템플릿 폴백·prepare_product_data 반영·end-to-end 블록→본문.
- 회귀: upload/dispatch/channel/woo/shopify/vendor 스위트 **884 passed**(기존 woo 템플릿
  계약·shopify 디스패처 무변경). 확장·추출기 무변경.

## 남은 경로
5개 마켓(쿠팡·스스·11번가·Shopify·WooCommerce) 상세 소비 **전부 배선 완료** → 드로어
'상세페이지 꾸미기'가 전 마켓에 실반영. '미리보기 = 실제 등록물' 성립.

적용 스킬: (백엔드 업로드 배선 — 앱 UI/CSS 렌더 변경 없음. 생성 HTML은 마켓 상세용.
impeccable/humanizer CLI 미설치.)
