# CLAUDE.md — proxy-commerce 작업 메모리

> 이 파일은 매 세션 시작 시 로드된다. 오너(Kohgane) 지시·검증된 팩트를 누적 기록한다.

## 🔴 작업 원칙 (오너 지시 — 2026-06-14)
- **추측 금지. 팩트로만 말한다.** 모르면 "모른다 / 확인 필요"라고 말하고, 검증한 것만 단정한다.
- 코드/문서/로그/실제 응답 등 **확인 가능한 근거**가 있을 때만 단정적으로 답한다.
- 헛다리(추측 기반 단정) 반복 금지. 화면·응답 원문 등 증거를 우선한다.

## 📌 마켓 연동 — 검증된 팩트 (2026-06-14)
- **연결 완료(✅)**: 쿠팡, WooCommerce, **Shopify**(아래 해법으로 연결됨, 2026-06-15).
- **남은 2개(마켓 측 설정)**: 스마트스토어=네이버 허용 IP 미등록(3칸 제한), 11번가=OpenAPI 승인/키.
- **쿠팡**: 차단 원인은 **IP 허용목록**이었음 — 서버 아웃바운드 IP(예 74.220.49.7)를
  Wing 'API 호출 허용 IP'에 등록해야 함(쉼표로 다중 가능). 서명/키 정상.
- **WooCommerce**: ✅ 연결됨. 과거 406은 User-Agent/Accept 헤더 누락이 원인(수정됨).
- **스마트스토어(네이버)**: 인증·서명 정상. 차단 원인 = **네이버 허용 IP(앱당 최대 3개)에 서버 IP 미등록**.
  bcrypt 전자서명(client_secret_sign) 필요(수정됨).
- **11번가**: 997 "등록된 API 정보 없음" = 키/OpenAPI 승인 문제(IP 아님).
- **Shopify** (해법 확정 — 오너 제공, 2026-06-14):
  - `atkn_…`(앱 자동화 토큰)은 **Admin API 액세스 토큰으로 인식 안 됨** → 버린다.
  - **해법**: 앱의 `SHOPIFY_CLIENT_ID`/`SHOPIFY_CLIENT_SECRET`(=암호 `shpss_…`)으로
    `POST https://{shop}/admin/oauth/access_token` (grant_type=`client_credentials`) 호출 →
    `shpat_…` 액세스 토큰 발급 → `X-Shopify-Access-Token`에 사용.
  - 구현: `ShopifyAdapter.fetch_token_via_client_credentials()` (캐시), `_access_token()`이
    client_id/secret 있으면 client_credentials 우선·없으면 직접 토큰 폴백. 연결확인은 GraphQL.
  - 오너 액션: Render에 `SHOPIFY_CLIENT_ID`=`68aa23f3…`, `SHOPIFY_CLIENT_SECRET`=`shpss_…` 설정
    (atkn_ SHOPIFY_AUTO_TOKEN은 없어도 됨).

## 🛠 인앱 마켓 연결 (셀프서비스)
- `/seller/markets/connect`(+`/<market>` 단독) — 셀러별 Fernet 암호화 저장(`market_credentials.py`).
- `/seller/markets/guide` — 그림 포함 발급 가이드.
- `data/` 저장은 Render 재배포 시 초기화됨(ephemeral) → durable은 Render 환경변수.

## 🧑‍🤝‍🧑 멀티유저(소비자 로그인) — 진행 로드맵 (오너 지시 2026-06-15, 위→아래 순서)
오너 지시: 나(오너) 외 실제 사용자들도 로그인·마켓연동·수집·업로드 가능해야 함.
퍼센티 벤치마킹하되 우리 색을 입히고 더 쉽게. 순서대로 진행:
1. ✅ **멀티유저 로그인 enforce + 수집 이력 셀러별 격리** (완료, commit 68e5b3c)
   - 로그인 시스템은 **이미 구현됨**: `src/auth/`(카카오/구글/네이버 OAuth + 이메일/비번,
     bcrypt, 구글시트 `users`). 단 셀러 콘솔 `_check_auth()`가 stub이었음 → 실제 세션 체크로 교체.
   - **오너 액션(durable)**: Render에 `SELLER_CONSOLE_AUTH=1` 설정해야 강제 활성화됨.
   - 수집 이력 `collect_history_store`에 `seller_id` 컬럼·필터 추가(사용자별 격리). 마켓 자격증명은 이미 셀러별.
2. ✅ 마켓 선택 체크박스 → 타일 전체 클릭(commit b481db0).
3. ✅ **실 상세 추출 + 번역** (완료): `/collect/preview`에서 목업(`ManualCollectorService`) 폴백 제거.
   파이프라인 `_collect_real_draft()`(views.py) = 도메인 dispatcher(`collectors/dispatcher.py`) →
   범용 스크래퍼(`collectors/universal_scraper.py`, JSON-LD/OG/Microdata/Heuristic + 색상·옵션) →
   한국어 번역(`ai/translator.py` AITranslator: title_ko/description_ko/마켓카피). 실데이터 못
   얻으면 목업 대신 `manual_entry` 정직한 안내. stub 번역 시 원문 유지·더미카피 미노출.
   ※ 번역 실작동은 Render에 `OPENAI_API_KEY`(또는 `DEEPL_API_KEY`) 필요 — 없으면 원문 유지.
   ※ 벌크수집(`/seller/collect/bulk`)도 동일 `_collect_real_draft` 파이프라인으로 전환 완료(Phase 203,
     목업 제거). 추출 실패 시 목업 대신 실패로 기록. 죽은 `_get_collector_service` 제거.
   ※ Phase 204(코드품질 정리): 죽은 목업 모듈 `manual_collector.py`(ManualCollectorService + `[Mock]`
     어댑터 9종, 호출처 0) **완전 삭제** + 해당 테스트(`TestManualCollectorService`) 제거,
     미사용 `_get_trust_checker` 헬퍼 제거. (TaobaoSellerTrustChecker 본체·테스트는 실구현이라 유지.)
     ※ 감사결과 나머지 mock(마켓 어댑터/배송/data_aggregator)은 API 미연동 시 의도된
       graceful 폴백 — 대시보드는 `DASHBOARD_SHOW_MOCK=0`(기본)에서 이미 숨김.
     ※ realtime API 정직성: `/api/v1/realtime/stream` 가짜 connected→정직한 501, `/metrics` is_demo 명시,
       `/subscribe` persistent:false 명시. (백킹 모듈은 실 인메모리 구조라 유지.)
     ※ Phase 205(소싱 모니터링 실연동): `source_monitor/checkers.py`의 가짜 랜덤 가격(`random.uniform`) 제거 →
       `source_url`에서 범용 스크래퍼로 실 가격/재고 추출(키 불필요). 추출 실패·URL없음·`ADAPTER_DRY_RUN=1` 시
       가짜 변동 대신 '변화 없음'으로 처리(거짓 알림 방지). 마켓 어댑터(쿠팡/11번가/네이버) `markets/adapters/`
       스캐폴드는 실 업로드 경로(`channel_sync` 업로더) 아님 — 비대면 인터페이스 테스트용이라 사용자 영향 없음.
4. ✅ **수집→확인·수정→업로드 중간 편집 페이지** (완료): `collect_preview.html`을 편집형으로 교체.
   제목·가격·통화·상세설명·이미지(추가/삭제)·옵션(색상/사이즈) 인라인 편집 → 💾저장
   `POST /collect/preview/<id>/save`(`collect_history_store.update()` 신설, 셀러 격리·extra_json 머지)
   → 같은 폼 데이터로 사전검증·업로드(buildProductData 단일화). 대표이미지 실시간 미리보기.
   ※ Render 환경변수 정렬: AITranslator 모델=`OPENAI_MODEL`, 스크래퍼 UA=`SCRAPER_USER_AGENT`,
     수집기 타임아웃=`SCRAPER_TIMEOUT_SEC` 반영(commit 후속).
5. ✅ **크롬확장 인페이지 '수집' 버튼 + 번역** (완료, v1.1.0):
   - `content_script.js`: 상품페이지 휴리스틱(og:product/가격메타/JSON-LD Product) 통과 시
     우하단 보라색 🛒 '수집' FAB 주입 → 클릭 시 메타추출 → background `collect` → 인페이지 토스트.
     SPA URL변경 감지 재주입, iframe 제외.
   - 서버 `/api/v1/collect/extension`: 수집 시 AITranslator로 한국어 번역(`_translate_payload`,
     키 없으면 원문 유지) → 이력 `extra`에 title_ko/description_ko/images/brand/provider 저장 →
     편집 페이지(④) 즉시 프리필. `translate:false`로 끌 수 있음. 이력 상위 title=한국어.
   - manifest 1.0.0→1.1.0. README 사용법(방법3) 추가.

## 🚀 로드맵 소진 후 — 후속 작업 (오너 지시 2026-06-16, "1,2,3 순서대로 가라")
번호 로드맵(멀티유저 1~5) 전부 완료 후 후속 3건을 순서대로 진행:
1. ✅ **Shopify 주문수집 + 배송추적** (완료, Phase 206): Shopify는 업로드만 됐고 주문/배송 미연동이었음.
   - `seller_console/market_adapters/shopify_adapter.py`에 `fetch_orders`/`fetch_orders_unified`(GraphQL
     orders 커서 페이지네이션 → 통합 주문 dict, 구매자 마스킹) + `update_tracking`(fulfillmentOrders 조회
     → `fulfillmentCreateV2`) 추가. 토큰은 검증된 client_credentials 경로 재사용(markets 어댑터에 공개
     `graphql()` 추가). `OrderSyncService.adapters`에 `"shopify"` 등록 → 4개 마켓처럼 풀 펀넬.
   - 정직성: GraphQL errors/userErrors/HTTP 오류·미설정 시 거짓 성공 금지(빈 리스트/False). dry-run 안전.
   - 오너 액션: 없음(Shopify는 이미 연결됨). 단 read_orders/write_fulfillments 스코프 필요할 수 있음.
2. ✅ **이미지 처리 실구현** (완료, Phase 207): 파이프라인(`media/image_pipeline.py`)은 워터마크
   감지·제거(OpenCV)·리사이즈/크롭·WebP(Pillow)까지 실제 처리했으나 **마지막 CDN 업로드가 stub**
   (`processed_url = image_url`)이라 결과물을 버렸음. → `_upload_to_cdn()` 신설: 처리본 바이트를
   Cloudinary(`cloudinary` 1.41.0 기존 의존성)에 업로드해 `secure_url` 발급, `processed_url`에 반영.
   `ImageProcessResult.cdn_uploaded` 추가, stats에 `cdn_uploaded`/`cdn_configured` 노출.
   - 정직성: `CLOUDINARY_*` 미설정·라이브러리 미설치·`ADAPTER_DRY_RUN=1`·업로드 실패 시 None →
     **원본 URL 유지**(거짓 호스팅 URL 미보고). `IMAGE_CDN_UPLOAD_ENABLED`(기본1)로 토글.
   - 오너 액션(durable): Render에 `CLOUDINARY_CLOUD_NAME`/`CLOUDINARY_API_KEY`/`CLOUDINARY_API_SECRET`
     (+선택 `CLOUDINARY_FOLDER`) 설정해야 실제 재호스팅됨. 없으면 원본 URL 그대로 사용.
3. ✅ **자동발행 실 업로더 연동** (코드-온리 부분 완료, Phase 208): `listing/auto_publish.py`의
   `auto_publish()`가 쿠팡=**mock 퍼블리셔**(`CoupangPublisher`, 가짜 uuid), 스마트스토어/11번가=
   **가짜 UUID stub**으로 발행을 흉내냈음(#2와 같은 '작업 버림' 패턴). → `_upload_to_channel`을
   수동 업로드(UploadDispatcher)와 **동일한 실 업로더**(`channel_sync.{coupang,smartstore,elevenst}_uploader`
   → `src.uploaders.*`)로 재배선. 자격증명 미설정·API 실패 시 가짜 성공 대신 **success=False+사유**(정직).
   - 오너 액션(durable): 실 자동발행하려면 `LISTING_AUTO_PUBLISH=1` + 각 채널 자격증명
     (`COUPANG_ACCESS_KEY/SECRET/VENDOR_ID`, `NAVER_CLIENT_ID/SECRET`(+네이버 허용IP), `ELEVENST_API_KEY`).
   - **외부 승인에 막힌 항목(코드 아님, 오너측)**: Amazon SP-API / eBay / Shopee = 셀러 등록·OAuth 승인·
     키 발급 필요(`markets/adapters/{amazon,ebay,shopee}.py`는 스캐폴드 stub 유지). 승인 완료 후 실연동 착수.

## 🔧 UI/디테일 보완 (오너 지시 2026-06-16, 라이브 화면 스크린샷 기반 — 퍼센티 벤치마킹)
오너가 실제 화면(kohganepercentiii.com)을 보고 지적한 디테일들을 순차 처리:
1. ✅ **쿠팡 업로드 NoneType 크래시** (PR #224): 쿠팡 응답 `data`가 sellerProductId 숫자(또는
   거부 시 null)인데 `result.get('data',{}).get(...)`가 None/int에서 크래시. dict/int/str/None 안전
   처리 + data=null·비성공코드는 가짜 성공 대신 정직한 실패. `get_categories`도 동일 수정.
2. ✅ **편집 페이지 원화 환율 계산기 + 상세설명 확대** (PR #225): 수집가가 외화/0일 때 셀러가 원화
   감 못 잡던 문제 → `collect_preview_by_id`에 `get_fx_rates()` 주입, '≈원화 약 N원' 실시간 표시 +
   '↻원화로 환산' 버튼(가격×환율→KRW). KRW·미지원통화는 정직 안내. 상세설명 rows 4→14 전체폭+글자수.
3. ✅ **대시보드 KPI 목업 제거 + 실데이터** (Phase 209): `data_aggregator.py`의 하드코딩 목업
   (오늘수집 5/주문 12/등록대기 3/[Mock] 알림) 제거. 오늘 수집 건수는 `collect_history_store.summary().today`
   실 집계, 주문수는 OrderSync:kpi(이미 실), 나머지는 실 모듈 없으면 정직하게 0/빈목록(가짜 값 금지).
   ※ 마켓 등록/동기화 표·재고부족은 이미 Sheets catalog 실연동(미설정 시 0) — 그대로 유지.
4. ✅ **수집 페이지 '원클릭 수집 지원 마켓' 행 + 인페이지 수집 안내** (Phase 210): 퍼센티의 '원클릭
   수집 지원 마켓' 벤치마킹 → `/seller/collect`(manual_collect.html) 상단에 타오바오/T몰/알리/1688/VVIC/
   라쿠텐/ZOZO/아마존/SHEIN/요시다카반 바로가기 버튼 행(`oneclick_markets` 뷰 주입). 상품 페이지에서
   크롬확장 🛒'수집' 버튼(이미 v1.1.0 구현)으로 원클릭 수집·번역됨을 안내(설치 가이드 링크).
- **남은 후속(이 지시)**: 실 가격 추출 개선 — yoshidakaban 등 일부 사이트 봇차단(403)으로 외부에서
  가격 마크업 확인 불가. 편집 페이지 환율 계산기로 외화/0 보정은 제공됨(#225). 사이트별 셀렉터는 별도 검토.

## 🔧 UI/디테일 보완 2차 (오너 지시 2026-06-16, 라이브 스크린샷)
1. ✅ **AI 수집기(`/seller/listing/ai-create`) 실발행 + 마켓 추가 + 마켓 링크** (Phase 211): `ai_listing/
   multi_publisher.py`가 존재하지 않는 `publish_to_channel` import 실패 → 항상 가짜 `MOCK-COUPANG-…`
   성공으로 폴백했음. → `_publish_to_market`을 수동 업로드와 동일한 `UploadDispatcher`(실 업로더)로 재배선.
   `PublishJob.product_url` 추가 → 결과에 '마켓 페이지 열기' 링크. 마켓 목록에 shopify/woocommerce/
   shopee/amazon 추가(쇼피/아마존은 미연동 시 정직한 실패). 11st→elevenst 코드 매핑. 자격증명 없으면
   가짜 성공 대신 정직한 실패.
- **남은 후속(이 지시)**: ① 봇 차단(403) 사이트 수집 — 크롬확장이 브라우저 DOM을 서버로 보내 파싱하는
  경로 필요(any-site 수집). ② 편집 페이지 풀 편집(키워드/썸네일 선택) 보강. ③ Google 로그인 '안 눌림'은
  코드 정상(=`/auth/google/start` 라우트·provider 정상) → 구글 콘솔 redirect_uri/client 설정 문제로 추정
  (로그인 페이지 '🔧 OAuth 콜백 URI 확인' 펼치기로 자가진단). 순차 진행 예정.

### 나열순 후속 — 차례대로 진행 (오너 지시 2026-06-16)
1. ✅ **봇 차단 사이트도 수집** (Phase 212): 서버 직접 fetch는 403 차단됨 → 크롬확장이 **브라우저 페이지
   HTML(`document.documentElement.outerHTML`, 600KB 상한)을 함께 전송** → 서버가 `UniversalScraper.parse_html()`
   (신설, 네트워크 fetch 없이 JSON-LD/OG/Microdata/Heuristic 파싱)로 가격/통화/이미지/제목/옵션 보강.
   `/api/v1/collect/extension`이 `html` 수신 시 `_merge_scraped_into_payload`로 **빈 값·가격0만 보강**
   (사용자 값 우선, 대용량 html은 이력에 미저장). 확장 manifest 1.1.0→1.2.0.
   → 사용자가 브라우저로 볼 수 있는 어떤 사이트(봇차단 포함)든 인페이지 🛒'수집'으로 수집 가능.
2. ✅ **편집 페이지 풀 편집 — 키워드/태그 + 썸네일 선택** (Phase 213): `collect_preview.html`에
   '키워드/태그'(쉼표구분) 입력 추가 → `buildProductData`/저장에 `keywords`+`tags` 반영(`extra` 머지).
   이미지 행마다 '⭐대표' 버튼 → 클릭 시 해당 이미지를 맨 위(대표/썸네일)로 이동(`refreshImageBadges`).
   `buildProductData.thumbnail`=대표이미지. (제목/가격/통화/상세/이미지/옵션은 이미 편집 가능)
3. ✅ Google 로그인 — 코드 정상 확인(라우트/provider OK), 구글 콘솔 redirect_uri 등록 안내(오너 설정 사안).

## 🔧 등록/수집 오류 일괄 수정 (오너 지시 2026-06-16, 라이브 스크린샷 3종 — "저런 오류들도 다 잡자")
오너 화면: ①AI상품등록(`/ai-create`)에서 yoshidakaban URL `HTTP 500` 접근불가(같은 URL이 수집기에선 성공)
②쿠팡 등록 옵션·반품지 필수값 누락 대량 실패 ③WooCommerce `https:///` 빈 호스트 실패.
1. ✅ **AI상품등록 URL 접근/스크래핑이 봇 UA로 차단** (Phase 214): `ai_listing/url_scraper.py`의
   `head_check_url`이 **봇 UA(`ProxyCommerceBot/1.0`) + HEAD**로만 확인 → yoshidakaban 등이 403/406/500 반환.
   → 수집기(universal_scraper)와 동일한 **브라우저 UA(`_PROBE_USER_AGENT`) + Accept 헤더**로 HEAD 시도,
   막히면 **GET 폴백(기본 ON)** 으로 재확인하고 `<400`이면 접근 가능 판정. `scrape_product_page`의 실제
   GET도 동일 `_PROBE_HEADERS`로 통일 → 접근확인과 실제 수집 동작 일치. (env `AI_LISTING_URL_PROBE_USER_AGENT`로 UA 조정)
2. ✅ **쿠팡 등록 옵션/반품지 필수값 누락** (Phase 214): `uploaders/coupang_uploader.py` 페이로드가
   옵션(items[]) 필수값(`taxType`/`adultOnly`/`unitCount`/`maximumBuyForPersonPeriod`/`overseasPurchased`/
   `notices`(고시정보)/`contents`(상세)/이미지타입)을 null·빈값으로 둬서 쿠팡이 전부 거부. 이미지타입도
   잘못된 `PRODUCT`였음(→ 첫 장 `REPRESENTATION`, 나머지 `DETAIL`). 상품 레벨 `unionDeliveryType`/
   `remoteAreaDeliverable`/반품지(주소·우편번호·담당자·연락처·배송비)/출고지/`vendorUserId`도 누락.
   → 표준값·고시정보 5항목·상세컨텐츠를 채우고, **셀러 고유 출고지/반품지/Wing ID는 추측 불가라 환경변수로
   받음**. 미설정 시 가짜 성공 대신 **사전 차단+누락 env 안내**(정직). 사전검증(upload_dispatcher)에도 추가.
   - 오너 액션(durable): Render에 Wing>업체정보>배송정보 값으로 `COUPANG_VENDOR_USER_ID`,
     `COUPANG_RETURN_CENTER_CODE`, `COUPANG_OUTBOUND_SHIPPING_PLACE_CODE`, `COUPANG_RETURN_ZIP_CODE`,
     `COUPANG_RETURN_ADDRESS`(+선택 `COUPANG_RETURN_ADDRESS_DETAIL`), `COUPANG_RETURN_CHARGE_NAME`,
     `COUPANG_COMPANY_CONTACT_NUMBER`(+선택 `COUPANG_RETURN_CHARGE` 기본5000, `COUPANG_OVERSEAS_PURCHASED`) 설정.
3. ✅ **WooCommerce `https:///` 빈 호스트 실패** (Phase 214): `vendors/woocommerce_client.py`가 ①모듈
   import 시점에 `BASE` 고정 → seller_market_env 주입을 못 봄, ②`WOO_BASE_URL`만 읽고 셀러가 연결한
   `WC_URL`은 무시, ③scheme 검증 없음 → `urljoin(None,…)`로 `/wp-json/...` 상대경로 → 'No scheme supplied'.
   → `_woo_base()`/`_woo_ck()`/`_woo_cs()`/`_woo_endpoint()` **호출 시점 읽기**로 전환, `WC_URL`·`WOO_BASE_URL`
   (키도 `WC_KEY`/`WOO_CK`, `WC_SECRET`/`WOO_CS`) 둘 다 지원, scheme 없으면 `https://` 보정, base 미설정 시
   정직한 RuntimeError. → 인앱 `WC_URL`로 연결한 셀러도 실제 업로드 성공.

## 작업 방식
- 브랜치 `claude/magical-noether-oo4831`에서 작업 → PR 생성·main 머지(오너 승인됨)로 배포.
- 변경 후 전체 테스트(`python -m pytest tests/ -q`) 통과 확인.
