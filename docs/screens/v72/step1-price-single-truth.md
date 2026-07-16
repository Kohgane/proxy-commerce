# v72(b) STEP1 — 가격 단일 소스 (P0)

## 증상 (오너)
- 수집가가 있는데 드로어 '가격(원가)' **0.00** + 마켓 등록 시 **가격 거부**.

## 스키마 감사 (이원화 지점)
- **세 개의 가격 필드**가 병존: `extra.price`(정본, v72 정규화), `extra.price_original`(파생·일부 경로서 `float 0.0` 기본), 상위 행 `item.price`.
- **append 3경로(quick·bookmarklet·bulk)**가 `str(draft.get("price_original") or draft.get("price"))` — **price_original(파생) 우선** → 파생 0.0/오염값이 정본을 이김.
- **드로어**는 `_EXTRA.price`를 읽어 `<input type="number">`에 그대로 대입 → **"81800."(꼬리 점)·"1,234"(콤마)를 number 입력이 거부** → 빈값 → 0.00. 그 0.00이 `buildProductData`로 마켓 등록에 실려 **가격 거부**.

## 단일화 (수리)
1. **정본 함수** `canonical_price(price, price_original, …)`(collect_sanitize): 후보를 순서대로 `normalize_price` 통과 → 첫 성공값. **price(정본) 우선**. 실패면 `""`(0.00 저장 금지).
2. **append 3경로** → `_canon_price(draft)` 단일 소스(price_original 우선 역전 제거).
3. **마켓 등록**(`collect_upload`) → 디스패치 전 `canonical_price`로 정규화(드로어가 오염값 보내도 거부 소멸).
4. **드로어** → `_normPriceStr`(서버 normalize_price 미러)로 number 입력 전 정규화 + 읽기 순서 `price→price_original→item.price` 통일. 마진계산(`_mcKrw`)도 동일 값.
5. **백필** `scripts/renormalize_prices.py`: 기존 레코드의 `extra.price`·`extra.price_original`을 정규화값으로 **동기화**(수집가 존재+원가 0/공백 정정).

## 판정
- 가드 `tests/test_v72b_price_single_source.py` (10):
  - `canonical_price` 계약 8케이스("81800."→"81800"·price 빈값→price_original·콤마·통화기호·0류→"").
  - 소스계약(3경로 _canon_price·이원화 표현 제거·마켓 정규화·드로어 _normPriceStr).
  - **Playwright 실증**: `<input type=number>`가 "81800." 거부(=0.00 근원 재현) → `_normPriceStr` 후 **"81800" 값 채움**.
- 회귀: collect_preview·upload·margin 365 그린.
- **실기기(오너 몫)**: 알리 81,800 건 드로어 가격 탭 값 채움 + 마켓 등록 가격 거부 소멸 캡처. (개발 프록시 라이브 차단.)

## 금지 준수
- 0.00 저장 0(실패는 빈값) · 수집가 있는데 0.00 표시 0(정규화 후 채움) · 가짜 성공 0.

적용 스킬: (백엔드 단일 소스 + 드로어 표시 정규화 — gogabridj-design 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
