# v88-C 쿠팡 기등록 → 고가브릿지 → 멀티채널 복제 파이프라인

> 오너 지시: 신규 소싱 아님. 쿠팡 두 계정(고가네 A01381223·우주대행 A01504840) **판매중 상품**을 sourcing_map으로
> 조인 → 소싱 URL을 고가브릿지 수집 이력으로 벌크 인입 → 번역·분류·가격까지 자동, **마켓 등록 직전 정지**(등록은 오너 클릭).
> 코어 = `src/pipeline/coupang_replicate.py`(순수 로직·오프라인 테스트). 계약 `test_v88_c_coupang_replicate`(18).

## ⚠️ 접근성 보고 (정직 — 이 서버에 없는 자산·자격)
오너 "이 서버에 없으면 조회 경로부터 확인" 지시대로 실측:
| 자산/자격 | 이 서버 | 라이브 조인/파일럿 필요 | 오너 액션(조회 경로) |
|---|---|---|---|
| **sourcing_map.json**(ASIN→소싱 URL, 1,046건) | **없음**(find 0) | 필수(조인 키) | LinkLynk/Bluehost 계보 자산 → 서버에 `data/sourcing_map.json` 배치 또는 `SOURCING_MAP_PATH` 설정 |
| **쿠팡 자격 ×2계정** | 없음(env 미설정) | 필수(판매중 목록 read) | `COUPANG_고가네_{VENDOR_ID,ACCESS_KEY,SECRET_KEY}` · `COUPANG_우주대행_*` (또는 단일 `COUPANG_*`) |
| **릴레이 고정 IP** | 없음(`MARKET_RELAY_URL`) | 필수(쿠팡 IP 허용) | Bluehost 릴레이 IP를 두 계정 Wing 허용 IP에 등록 |

→ **자산·자격이 없어 라이브 조인 수치표·파일럿 50건은 이 세션에서 산출 불가.** `access_status()`가 게이트로 막고
`run_inventory_join()`은 **가짜 수치 대신** access 보고를 낸다(정직 데이터 원칙). 위 3개가 채워지면 코어가 즉시 실행.

## 1. 인벤토리 조인 (수치표 — 스키마, 값은 라이브에서)
`join_inventory(coupang_items, sourcing_map)` → 순수 함수. 매칭 키 = **externalVendorSku(ASIN 계보)**.
```
{ 판매중: n,  매칭: m,  미매칭: k,  소스분포: {shopify_d2c: …, amazon: …, rakuten: …, other: …} }
```
> ※ 쿠팡 `seller-products` 목록 엔드포인트는 `sellerProductCode`는 주지만 `externalVendorSku`는 상세에 있다 →
> 라이브 글루가 계정별 `fetch_inventory`를 externalVendorSku 포함으로 확장(구현 트랙, 읽기 전용).

## 2. 서버측 수집 인입 + 3. 파일럿 오케스트레이션
매칭 소싱 URL → 기존 수집 경로(`_collect_real_draft`/`/collect/bulk`)로 벌크 인입. **별도 우회 경로 발명 0** —
수집 5필드 판정·번역 체인·분류·간이/부분 정직 표시 전부 기존 파이프라인 통과.

`run_pilot_ingest(pilot_rows, *, channel, collect_fn, prevalidate_fn, existing_source_keys, blacklist)` —
파일럿 행을 **취급금지 스킵 → 기존 채널 중복 스킵 → collect(기존 경로) → 이미지 2장 캡 → 원가기준 가격 → 사전검증**까지
돌리고 **`registered=False` 불변(등록은 절대 안 함)**. collect_fn/prevalidate_fn 주입식(발명 0·오프라인 테스트). 외화 원가는
fx 미상 시 가짜 환산 0(price ok=False). 반환 summary = {ingested·skipped_forbidden·skipped_duplicate·failed_collect·prevalidate_ok/fail}.

## 3. 파일럿 50건 (등록 직전 정지)
`plan_pilot(join_rows, n=50, prefer="shopify_d2c", exclude_sources=("rakuten",))`:
- **Shopify D2C 소스 우선**(수집 신뢰도 최고 — /products.json 정상), **라쿠텐 제외**(서버 42바이트 차단 — 확장/수동 분리).
- 수집→번역→분류→**가격(원가 기준 재계산)**→사전검증까지 자동, **마켓 등록 직전 정지**. 오너 검수 후 일괄 등록 클릭(비가역 게이트).
- 가격: `recalc_channel_price(cost_krw, channel, margin_rate=27.4)` = `원가/(1-수수료율/100-마진율/100)`, 100원 올림.
  - 쿠팡 판매가 **역산 아님**(오너 명시). 채널 수수료: 멀티샵(WC 국내)=**3.0%**(확정). Shopify(글로벌)=`SHOPIFY_FEE_RATE`(오너 설정 — 미설정 시 가짜 0 대신 ok=False).
  - 공식 출처 = `MarginCalculator.reverse_calculate` 문서식 재사용(단 복제는 원가=랜딩코스트 → 국제배송 미가산).

## 4. 중복 방지 (멱등)
`dedup_decision(sourcing_url, existing_source_keys)` → `normalize_product_key`(v42 1-3)로 이미 수집/등록분이면 `update`,
아니면 `new`. 재실행 시 같은 소스 재인입 = 기존 레코드 갱신(멱등). Shopify/WC 기존 상품(SUPERONE 등) 스킵 판정에 활용.

## 5. 취급금지 필터 (인입 단계)
`is_forbidden(title, category, blacklist=…)`:
- 금지 카테고리(오너 확정): 향수·캔들·애플/apple·CASETiFY.
- 금지어 사전: `check_forbidden_terms`(기존 모듈) 재사용.
- **쿠팡 85 blacklist는 오너 자산 → 주입식**(하드코딩 금지 — 없는 목록 발명 0). 오너가 목록 제공 시 `blacklist=`로 주입.

## 재사용 맵 (발명 최소)
| 기능 | 재사용 |
|---|---|
| 수집 인입 | `_collect_real_draft`/`/collect/bulk` (기존 서버 수집) |
| 중복 키 | `src/collectors/product_key.normalize_product_key` |
| 가격 공식 | `src/margin/calculator.MarginCalculator.reverse_calculate`(문서식) |
| 금지어 | `src/ai/forbidden_terms.check_forbidden_terms` |
| 릴레이 | `src/market_relay.relay_request` (쿠팡 read, 고정 IP) |

## 금지·불변 (오너)
- **자동 등록 금지**(사전검증까지만, 등록은 오너 클릭) · **쿠팡 데이터 무변경**(읽기만) · **이미지 2장 초과 금지**
  (Bluehost 디스크 4중 재발방지) · **라쿠텐 서버 크롤 강행 금지**(차단 리스크 — 분리 보고만) · **API 호출 제한 준수**(릴레이 스로틀).

## 구현 트랙 (오너 자산 제공 후)
1. 계정별 `fetch_inventory`(externalVendorSku 포함, 읽기 전용) 글루 + `run_inventory_join` 라이브 배선 → **수치표 산출**.
2. 파일럿 50건: `plan_pilot` → 인입→번역→분류→가격→사전검증 배치, 등록 직전 정지 UI(오너 검수 목록).
3. 실증: 1항 수치표(판매중 n·매칭 m·미매칭 k·소스분포) + 파일럿 상태 분포(5/5·부분·실패 각 n).
