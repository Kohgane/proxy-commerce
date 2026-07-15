# v72 STEP2 — 가격 정규화 단일 관문

## 증상 (오너 캡처)
- "81800."(꼬리 점) → 드로어 0.00(숫자 변환 사망). 저장 직전 정규화가 없어 오염 문자열이 그대로 저장·전파.

## 수리 (`src/collectors/collect_sanitize.py`)
1. **단일 정규화 함수** `normalize_price(raw) → (정규화값, ok)`:
   - `_PRICE_NUM_RE`(`\d[\d,]*(?:\.\d+)?`)로 **머리·꼬리 비숫자 제거**(통화기호·문자·공백) → **천단위 콤마 제거** → **소수점 1개만 검증** → `Decimal` 확정.
   - 꼬리 점은 정규식이 배제(`\.\d+` 필수): `"81800."`→`"81800"`. `"1,234"`→`"1234"`. `"29.99"`→`"29.99"`. `"₩81,800"`→`"81800"`. 실패/0 → `("", False)`.
2. **`sanitize_price`가 관문 사용**: 정규화 성공 시 **정규화값 저장**(옛 코드는 raw 반환 → 콤마·꼬리점 오염). 실패 → `""` + `needs_check`(**0.00 저장 금지**, 원문은 호출측 extra 보존). 통화 미상·비상식 하한(9 KRW) 폐기(v55 유지).
3. **저장 경로 봉인**: `sanitize_payload`(extension_api·views 두 수집 경로 모두 호출)가 in-place 정규화.
4. **기저장 오염 마이그레이션**: `renormalize_price_field`/`renormalize_all`(주입식) + `scripts/renormalize_prices.py`(1회 배치) — 이미 저장된 `"81800."`·`"1,234"` → 정규화 갱신. 원문 보존(파싱 실패·빈값 미변경).

## 판정
- 가드 `tests/test_v72_price_normalizer.py` (20): **계약 파라미터라이즈**(꼬리 점·콤마·소수·통화기호·꼬리문자 8케이스 + 실패 8케이스) + sanitize_price 정규화 저장·0.00 금지·비상식폐기 + sanitize_payload in-place + renormalize_price_field/renormalize_all 배치.
- `test_v55_tier1_sanity` 그린(회귀 0).
- **실기기(오너 몫)**: "81800." 케이스 → 드로어 **81,800 KRW** 표기 캡처. (개발 프록시 라이브 차단.)

## 금지 준수
- 0.00 저장 0(실패는 빈값+needs_check) · 원문 보존(파싱 실패 미변경) · 가짜 성공 0.

적용 스킬: (백엔드 정규화 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
