# v88-C 쿠팡 기등록 → 고가브릿지 → 멀티채널 복제 파이프라인

> 오너 지시: 신규 소싱 아님. 쿠팡 두 계정(고가네 A01381223·우주대행 A01504840) **판매중 상품**을 sourcing_map으로
> 조인 → 소싱 URL을 고가브릿지 수집 이력으로 벌크 인입 → 번역·분류·가격까지 자동, **마켓 등록 직전 정지**(등록은 오너 클릭).
> 코어 = `src/pipeline/coupang_replicate.py`(순수 로직·오프라인 테스트). 계약 `test_v88_c_coupang_replicate`(18).

## ⚠️ 접근성 보고 (정직 — 이 서버에 없는 자산·자격)
오너 "이 서버에 없으면 조회 경로부터 확인" 지시대로 실측:
| 자산/자격 | 이 서버 | 라이브 조인/파일럿 필요 | 오너 액션(조회 경로) |
|---|---|---|---|
| **sourcing_map.json**(ASIN→소싱 URL, 1,046건) | **없음**(find 0) | 필수(조인 키) | LinkLynk/Bluehost 계보 자산 → 서버에 `data/sourcing_map.json` 배치 또는 `SOURCING_MAP_PATH` 설정 |
| **쿠팡 자격 ×2계정** | 없음(env 미설정) | 필수(판매중 목록 read) | **정본 접미(코드베이스 표준)** = `COUPANG_GOGANE_ACCESS_KEY`·`COUPANG_GOGANE_SECRET_KEY`·`COUPANG_GOGANE_VENDOR_ID`(고가네 A01381223) · `COUPANG_WOOJOO_ACCESS_KEY`·`_SECRET_KEY`·`_VENDOR_ID`(우주대행 A01504840). ※축약형(`_ACCESS/_SECRET/_VENDOR`)도 허용(둘 다 감지 — v88-C 결함 수리). **무접두 `COUPANG_*`(Render 기존 키, 마켓 Health 그린)**는 `VENDOR_ID`로 **한 계정에만 흡수**(`resolve_base_account` — 이중화 금지). VENDOR_ID가 두 계정과 불일치면 미상(오너 확인). |
| **릴레이 고정 IP** | 없음 | 필수(쿠팡 IP 허용) | **정확 키 = `MARKET_API_RELAY_URL`**(mkt.php 릴레이, 오너 50.6.34.63 설치 — **mkt.php 전체 URL** 예: `https://<host>/…/mkt.php`) + `MARKET_API_RELAY_KEY`(또는 `MARKET_RELAY_TOKEN`) = 릴레이 공유키(헤더 `X-KGP-Relay-Key`, URL에 토큰 파라미터 없음). ※구 경로 `MARKET_RELAY_URL`(베이스만, 코드가 `/relay` 자동 부착) + `MARKET_RELAY_TOKEN`도 인정. `relay_ready()`가 두 규약 모두 감지. 릴레이 IP를 두 계정 Wing 허용 IP에 등록. |

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

## 파일럿 배선 (v88-C, 오너 모집단 승인 396)
- **모집단(결정적)**: `build_pilot_population` — coupang_sid truthy **636** → sid 그룹핑 → sid당 대표 1 = **distinct 396**(감쇄 240). 대표 우선순위 ①krw+usd 보유 ②sources ship_usd ③ASIN 사전순. 난수 0(재현성 검증). 산출 `data/pilot_population.json`(396, 선정 사유 필드). 원본 sourcing_map 불변.
- **50 선정**: `select_pilot` — sid 오름차순 stride(결정적, 난수 0).
- **검수표**(`build_review_row`): sid·ASIN·번역제목(원본 name_ko)·현행가/원가·마진%·타겟채널·**금지 85 필터 판정(사유)**·중복제거 근거. 금지 미통과=`excluded_table`에 사유와 함께(조용한 탈락 금지). 85 리스트는 오너 자산 → `data/coupang_blacklist85.json` 주입(레포 미보유, 카테고리+금지어는 상시).
- **admin 트리거**: `POST /admin/coupang-pilot`(오너 세션 인증) → 396→50→검수표. 라이브 조인(쿠팡 현행가·재고·판매상태 재조회, 저장 스테일값 신뢰 금지)은 쿠팡 자격+릴레이(Render)일 때만; 미충족=sourcing krw(원가, 현행가 아님)+access 보고.
- **하드 정지 → 해제(오너 최종 승인 "전부가라", 2026-08-20)**: `PILOT_REGISTER_APPROVED=True`. 안전은 **카나리 게이트**로 이관.
계약 `test_v88_c_pilot`(396 결정성·대표우선순위·50 결정성·승인/가드·검수표/블랙리스트·admin 게이트·등록 카나리/배치/롤백/메타).

## 파일럿 등록 실행 (카나리 게이트 · draft · 롤백 금지)
- **자격 경로(실측):** WooCommerce 등록은 **env `WC_URL`/`WC_KEY`/`WC_SECRET`(또는 `WOO_BASE_URL/WOO_CK/WOO_CS`)** — 호출 시점 글로벌 env(`upload_dispatcher`/`woocommerce_client`). 셀러콘솔 "WooCommerce 미연결"은 셀러 저장 자격(`market_credentials`)이라 **env 경로와 무관**. 자격 없으면 dispatch가 정직 실패(가짜 성공 0).
- **executor** `register_pilot_rows(rows, *, dispatch_fn, n, batch_ok, status="draft", enrich_fn, ...)`: `batch_ok=False`면 **첫 1행(Ystudio)만**(카나리), 47 전량은 오너 육안 확인 후 `batch_ok=True`로만. **행별 registered:true/false+사유**(조용한 실패 금지)·**롤백 금지**(부분 실패 시 성공분 유지)·draft(되돌림성)·레이트리밋 예의(호출 간격). suspect/cjk 플래그 행도 등록하되 비노출 메타(`_kgp_title_suspect`·`_kgp_cjk_residual`·`_kgp_pilot_sid`)에 남겨 후속 제목 보정 대상. enrich_fn = 소싱 URL 수집(기존 `_collect_real_draft` 재사용)→이미지 2장 캡+상세.
- **admin 등록 라우트** `POST /admin/coupang-pilot/register`(오너 세션): 모집단→검수표→`register_pilot_rows`(dispatch=UploadDispatcher, draft). 기본 카나리 1건, `?batch_ok=1&n=47`로 46건 속행. blacklist 0건이면 등록 중단(빈 필터 등록 금지).
- **불변:** draft 등록(publish 아님) → 오너 스토어서 육안 검수 후 publish. dispatch/enrich 주입식(오프라인 계약 테스트). 라이브 등록은 **Render 전용**(WC 자격 Render, 샌드박스 호출 불가) — 오너가 배포 앱서 트리거.

## 제목 정제 `clean_title_ko` (검수 반려 수리, 실데이터 계약)
`build_review_row`가 `title_ko`에 적용 → 행에 `title_truncated`·`title_truncated_suspect`·`title_cjk_residual`·`title_cleaned` 노출. `collect_sanitize.sanitize_title`(마켓/브랜드/카테고리 꼬리) 재사용 + 파일럿 잡문 처리.
- **별점/평점(한·영):** `_RATING_RE` — `★☆`, `4.8 out of 5 stars`, `4.8/5 stars`, `rating details`, `1,234 ratings/reviews`, 한글 평점. (실데이터: FELCO B00511984W.)
- **지명 잡문 꼬리:** `_PLACE_TAIL_RE` — `– City, ST …`를 **US 주 코드(_US_STATES)일 때만** 제거(오탐 방지). (실데이터: 덴버글라스 "– Denver, CO Map".)
- **절단 판정(조용히 자르지 않음):** 하드 `truncated` = 말줄임표/대시끝/100자 초과(정제 전 포착). 소프트 `truncated_suspect` = **영문 마지막 토큰이 완결 화이트리스트(`_COMPLETE_TAIL`) 밖 2~7자 단편 또는 단일 문자**(사전 부재 → 화이트리스트, 8+자·한글 꼬리는 무판정). 소싱맵 name_ko 자체가 절단원(더 긴 원본 없음)이라 길이 대조 불가 → 휴리스틱, **불확실=suspect 정직 표기**(발명 0). (실데이터: "Insulated Stai"·"PEN CLI"·"w updat"·"Scisso"·"Patente"·"…Aluminum W".) 과탐은 등록 직전 검수로 흡수(미탐이 더 위험).
- **CJK 한자 정책(오너 보고):** 일문 **가나**는 제거(`_JP_KANA_RE`), **한자(漢字)는 삭제하지 않는다**. 근거 = ①번역 소관(万年筆→만년필은 translate_fn이 렌더, 삭제하면 제품명 자체 소실) ②CJK 한자는 ja/zh/ko 공유라 브랜드·제품 정보일 수 있어 삭제=파괴적. 대신 `title_cjk_residual=True`로 **잔존 표기**(번역 미완 신호) — 재번역/검수로 해소. (실데이터: 세일러 "万年筆".)
계약 `test_v88_c_coupang_replicate`(별점 영문·중간절단 6실데이터·완결 꼬리 오탐0·지명꼬리·CJK 잔존).
