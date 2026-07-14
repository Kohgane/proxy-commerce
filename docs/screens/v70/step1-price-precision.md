# v70 STEP1 — 가격 정밀도 (현행범 버그①)

## 증상 (오너 실측 — jsdom + 실아마존 HTML + 라이브 run.js)
- 가격 32.99 오채택. 출처는 광고 위젯의 정가 표기(`a-price a-text-price`), 실판매가는 29.99.
- 근원: 취소선 제외가 `a-text-price` 클래스를 안 거름 + 폰트 크기 우선순위 무력 상황에서 광고 모듈이 buybox를 이김.

## 수리 (`kgp-extractor.js`)
1. **후보 제외 강화**
   - `_isListPriceNode(el)` = 클래스에 `a-text-price` 있으면 정가로 배제(전역·스코프 양쪽).
   - `_nonProdRegion` 조상 검사에 광고·추천 컨테이너 패턴 추가: `sims`·`multi-brand`·`video`·`sp_detail`·`octopus`(기존 sponsored·carousel과 합류).
2. **우선순위 재설계**
   - `_buyboxPrice()` = 어댑터 buybox 스코프 최우선: `#apex_desktop`·`#corePrice_desktop`·`#corePriceDisplay_*`·`#buybox`·`.priceToPay`·`.apexPriceToPay`. 스코프 안에서 `.a-price:not(.a-text-price)` 현재가만 채택 → 스코프 성공 시 전역 휴리스틱·폰트크기 불요.
   - 스코프 실패 시에만 전역 휴리스틱. **폰트 크기는 동률 보조로 강등** — 정렬 키 `(문서순서 asc) → (폰트 desc)`. 현재가는 buybox라 문서 상단, 광고는 하단이라 순서로도 자연 우선.
3. **로그 유지**: `(buybox)가격 채택: 29.99 USD [path]` 또는 `(DOM)가격 후보(N): ...` (현 포맷 유지).

## 판정
- 가드 `tests/test_v70_price_precision.py` (3):
  - 소스계약(_buyboxPrice·a-text-price 배제·sims/multi-brand·폰트 강등 정렬).
  - **node로 실아마존 구조 재현**: sims 광고 `a-text-price` 32.99 vs buybox `.priceToPay` 29.99 →
    - 케이스1 buybox 스코프 → **29.99 채택**(scope:true, 광고 32.99 무시).
    - 케이스2 스코프 없음(전역 폴백) → a-text-price 32.99 배제 → **29.99 채택**.
  - manifest 1.5.76.
- **실기기(오너 몫)**: 확장 1.5.76 재로딩 → 동일 상품 상세 → 드로어 가격 탭 29.99 캡처 + F12 `[고가수집기] (buybox)가격 채택: 29.99` 로그. (개발 프록시가 라이브 아마존 차단 → 대행 불가.)

## 금지 준수
- a-text-price 채택 0(배제) · 가짜 성공 0(스코프·전역 둘 다 통화 있는 실가만) · 서버측 직접 크롤 0(확장 DOM).

적용 스킬: (확장 추출 로직 — UI/CSS 렌더 변경 없음 → gogabridj-design 불요. impeccable/humanizer CLI 미설치.)
