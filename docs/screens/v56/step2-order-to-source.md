# v56 STEP2 — 주문 → 소싱처 원클릭

## 데이터 연결
주문 항목 → `items[].sku` → `CatalogLookup.lookup_by_sku(sku).src_url`(수집 원본). 끊긴 경우(수동 등록·sku
미매칭)는 **'원본 미연결' 배지 + '수동 연결'**(카탈로그로 유도).

## 기능 (`_order_source_info`)
- **[소싱처에서 주문]**: 새 탭으로 원본 상품 URL(`target=_blank`).
- **[주문 정보 복사]**: 옵션·수량·**마스킹 수취인**을 클립보드(소싱처 주문서 붙여넣기용). clipboard API +
  execCommand 폴백 + 복사 토스트.
- **'소싱 주문 완료' 토글**: `POST /orders/<mp>/<oid>/sourced` → notes에 `[소싱완료]` 마커 넣고/빼서 **영속**
  (상태값 불변) — 뭘 시켰고 뭘 안 시켰는지 추적. 버튼 색/라벨 즉시 갱신.
- **데스크톱·모바일 공용**: `.cardcell-actions`(v36 .table-cards) → 모바일 카드에서도 1탭 접근 + 복사 토스트.

## 로컬 실증
- 역참조: sku BAG-1 → src_url taobao/item/999·linked. copy_text '가방 [색상:블랙] x2 / 수취인: 홍*동'.
- 미연결: sku 없음 → linked False. notes `[소싱완료]` → sourced True.
- 토글 E2E: POST → notes에 [소싱완료] 추가·status 불변(paid 유지).

## 판정 (오너)
주문 1건 → [소싱처에서 주문] 원본 도달 + 정보 복사 토스트 + 상태 토글. 데스크톱·모바일 각 캡처.

## 가드
test_v56_order_source(6): 역참조·미연결/소싱플래그·템플릿 버튼·JS 복사/토글·sourced 엔드포인트·페이지 200.
