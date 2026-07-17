# v74 STEP1 — 타일 오탐 필터 (카테고리 내비 제외)

## 증상
요시다 목록에서 **카테고리 아이콘 줄**(가격 없는 카테고리 링크)에 우리 수집 버튼이 오탐 부착.

## 근본
v43-2가 '가격 없어도 상세링크면 상품 인식'으로 완화하며 **느슨한 `_kgpIsDetailHref`**를 자격 판정에 썼다.
그 정규식은 `/products?/`를 통째로 통과 → 카테고리 링크 `/products/bags`(가격 없음)까지 상품으로 오인.

## 수리 (자격 강화 — 완화 아님)
브리프 규칙 그대로: **타일 자격 = [상품 URL 패턴 or 가격 텍스트] 중 1 필수 + 이미지**. 카테고리 내비(가격없음·카테고리 URL)는 제외.
- `_kgpIsCategoryHref` — 카테고리/컬렉션/브랜드/랭킹/리스트 내비 URL 판별(상품 아님).
- `_kgpIsProductHref` — **카테고리 URL 제외** + 명시 상품 식별자(dp/goods_id/g-<n>/item.htm/products/detail·digit·8+자 슬러그)만 인정.
- `_kgpInNavRegion` — nav 태그·role·메뉴/브레드크럼/gnb 클래스 영역이면 상품 타일 아님(구조적 오탐 차단).
- `_kgpGenericCards` 자격을 `_kgpIsDetailHref`→`_kgpIsProductHref`로 교체 + 내비 영역 제외.
- 가격 있는 카드는 URL 무관 그대로 인식(회귀 0) — v43-2의 g-<n> 무가 상품 27건 복구 계약 유지.

## 판정
- 가드 `tests/test_v74_tile_false_positive.py`(3): source-contract + 실 content_script를 요시다 픽스처에 주입 →
  **카테고리 줄 버튼 0 · 상품 타일 6 전부 부착 · 총 배지=6(오탐 0)**.
- 회귀: `test_v43_2_bulk_accuracy`(g-<n> 무가 27 복구·비상품 0)·`test_v63_detection_contract`(제네릭-first)
  헬퍼 deps 갱신 후 그린. 전체 그린.
- **판정 캡처**: `step1-yoshida-category-no-falsepositive.png` — 상단 카테고리 이미지 5장 **배지 0**, 상품 6장
  배지+호버 부착, 벌크바 "메인 6".
- 픽스처 `fixtures/realpages/yoshida-list.html`(카테고리 nav+타일 + 상품 6; 오너 실스냅샷 공급 시 교체).
- manifest 1.5.92→**1.5.93**(재로딩) + 버전핀.
- **실기기(오너 몫)**: 요시다 목록에서 카테고리 줄 오탐 0 + 상품 전부 부착 캡처(확장 1.5.93 재로딩 후).

## 금지 준수
타일 자격 완화 회귀 0(강화만) · 추출기 변경 0(감지 자격 로직) · 가짜 성공 0(실 픽스처 검증).

적용 스킬: (확장 감지 자격 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
