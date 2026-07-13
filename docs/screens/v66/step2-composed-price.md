# v66 STEP2 — 테무 가격: 합성 텍스트 추출

## 근본 원인
- 테무 등은 통화·숫자를 여러 span으로 분절(`₩|1|,|899`)하거나 사이에 공백/개행을 넣는다. `parsePriceStr`의 숫자부 `[\d,]+`는 공백을 못 넘어 span-split 텍스트에서 매칭 실패 → 0.00.

## 수리 (`kgp-extractor.js::_composedPrice`)
- 가격 후보 컨테이너에서 후보 문자열을 조립: `content`·`data-price`·**`aria-label`** 속성 + `textContent`를 **공백·개행 제거(`.replace(/\s+/g,"")`)** → 통화 패턴 매칭. span 분절 조립 대응.
- `_domPrice`가 `_composedPrice(el)` 사용(노드 단위 → 컨테이너 합성).
- **취소선 제외**(`_priceOriginal`)는 컨테이너 단위 유지(원가/할인전 배제).
- **통화 추정 금지**: 통화 기호가 전무하면 가격으로 잡지 않음(랜덤 숫자 오인 방지). 통화 감지됐으나 미상이면 하류 `_priceSanity`가 `needs_check`(정직 표기, 현 UX 유지).
- **옵션**: 테무 스와치(색·수량 버튼 그룹)는 기존 `_domOptions`(`[class*=sku/option/variant/spec/swatch i]`)가 구매박스 스코프에서 텍스트로 수집(v58/v62). 정본 경로(extractProductMeta→kgpExtractProduct) 공유.

## 판정
- 가드 `tests/test_v66_composed_price.py` (3):
  - 소스계약(`_composedPrice`·aria-label·공백제거·`_domPrice` 사용·취소선 컨테이너).
  - **node**: span 분절 `₩ 1 , 899`→**1899 KRW** / aria-label `₩61,144`→**61144 KRW** / 통화 없음→**미추출**(추정 0).
  - manifest 1.5.73.
- 실기기(테무 상세 2건 → 가격 실가·통화·옵션 표 · 0.00 재발 불합격)는 오너 환경 — 프록시 라이브 차단.

## 금지 준수
- 통화 추정 저장 0(기호 없으면 미추출) · 서버측 직접 크롤 0(확장 렌더 DOM) · 가짜성공 0.

적용 스킬: (확장 추출기 — 우리 토큰 무관. impeccable/humanizer CLI 미설치.)
