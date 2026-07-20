# v78 STEP4 — 어댑터 패리티 (field_sources.price)

## 근거(오너 실기기 진단, ext 1.5.102)
아마존 `field_sources.price = tier2` — buybox 어댑터가 현재가($29.99)를 읽었는데도 출처가 'tier2'(제네릭
휴리스틱)로 라벨. `adapterMatched=true`인데 `price=tier2`인 모순.

## 근본 원인 특정 (로드 타이밍·매치 조건·번들 누락 중 → **라벨링 버그**)
어댑터는 실제로 **발동한다**(하네스 amazon-dp 픽스처의 `#corePrice_desktop .priceToPay` 매치 실증). 실기기
아마존은 초기 state JSON을 캡처 못 해 **Tier1(`j.price`)이 빈값** → `_domPrice()`가 `_buyboxPrice()`(스코프
어댑터)로 현재가를 읽는다. 그런데 오케스트레이션이 그 provenance(`scope:true`)를 **버리고**, `fieldSources`가
`j.price ? "tier1" : (price ? "tier2" : "none")`로 **무조건 tier2 라벨**. → 진단에 '어댑터 매치인데 tier2'
모순이 찍히고 '어댑터 미발동'으로 오진 유발.

## 수리 — 가격 출처(priceSrc) 보존
- `_buyboxPrice()` 반환에 **출처 마커** `src: "buybox"`(기존 `scope:true`와 함께), 제네릭 후보에 `src: "dom"`.
- 오케스트레이션: `var priceSrc = j.price ? "tier1" : "";` → DOM 폴백 시
  `priceSrc = (dp.scope || dp.src === "buybox") ? "buybox" : "tier2";`.
- `fieldSources.price = priceSrc ? priceSrc : (price ? "tier2" : "none");` — buybox 어댑터 매치면 **'buybox'**,
  제네릭 휴리스틱이면 **'tier2'**(정직·어댑터 날조 금지), 값 없으면 'none'.
- 콘솔 로그에 `[buybox]`/`[tier2]` 출처 표기(진단 가시성).

## 계약(브리프)
> STEP 4 — 어댑터 패리티: 수리 후 진단 extracted의 `field_sources.price`가 아마존에서 adapter/buybox.

## 판정
- 가드 `tests/test_v78_adapter_parity.py`(4): source-contract(priceSrc 보존·buybox 라벨) + **Playwright**:
  amazon-dp(state JSON 없음, buybox 현재가 29.99) → `price=29.99`·`field_sources.price="buybox"` /
  buybox 스코프 없는 제네릭 상세 → `field_sources.price="tier2"`(어댑터 날조 0).
- 실페이지 하네스에 **`price_source`** 계약 키 추가 + amazon-dp `expected.json`에 `"price_source":"buybox"` —
  하네스가 field_sources.price를 계약으로 못박음.
- **판정 캡처**: `step4-adapter-parity.png`(BEFORE field_sources.price=tier2 모순 → AFTER buybox).
- 전체 **11434 passed / 22 skipped**. manifest 1.5.107→**1.5.108**(재로딩) + 버전핀.

## 금지 준수
- 가짜성공 0(제네릭은 tier2로 정직 표기, buybox 날조 없음) · 추출기 변경 = 하네스 계약 동반(price_source 키).

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
