# CLAUDE.md — proxy-commerce 작업 메모리

> 이 파일은 매 세션 시작 시 로드된다. 오너(Kohgane) 지시·검증된 팩트를 누적 기록한다.

## 🔴 작업 원칙 (오너 지시 — 2026-06-14)
- **추측 금지. 팩트로만 말한다.** 모르면 "모른다 / 확인 필요"라고 말하고, 검증한 것만 단정한다.
- 코드/문서/로그/실제 응답 등 **확인 가능한 근거**가 있을 때만 단정적으로 답한다.
- 헛다리(추측 기반 단정) 반복 금지. 화면·응답 원문 등 증거를 우선한다.

## 🔑 검증된 환경/핸드오프 (오너 제공 — 누적, 두 번 묻지 말 것 / 2026-06-20)
> 오너 지시(2026-06-20): "업데이트되는 정보는 핸드오프에 저장하고 두 번 일 시키지 마라."
> 새로 검증된 사실은 여기에 즉시 누적 기록한다. (세션 컨텍스트는 휘발되므로 이 파일이 단일 진실원천)
- **Render 환경변수 (오너가 설정함, 검증됨):**
  - `GOOGLE_OAUTH_CLIENT_ID` = 설정됨, `GOOGLE_OAUTH_CLIENT_SECRET` = 설정됨 (둘 다, 2026-06-20 오너 확인).
    → 구글 로그인 `is_configured`는 True여야 정상. 그런데도 일반유저 로그인 실패 보고됨 → 콜백/콘솔 redirect_uri 쪽 조사 필요(아래 진행).
  - 카카오·네이버 OAuth = 설정됨(로그인 창 정상으로 뜸). 카카오만 되던 과거 상태에서 진전됨.
- **KOHgogane 브리프 v2 (전면 리디자인 로드맵, 오너 제공 2026-06-20):** 코가네 퍼센티→**코고가네/KOHgogane** 리브랜딩 +
  catdyy식 디자인 토큰(먹/한지/금 + 청록 Primary) + Pretendard/Noto Serif KR + 수집상품 일괄관리(퍼센티 동등) +
  온보딩 위저드 + 게임화 + 구독 + PWA/베타. 순서: 디자인→일괄관리→온보딩→게임화→구독→앱. (대형 — 덩어리별 PR)
  - **진행 상황(누적):**
    - ✅ §2 chunk1 — 디자인 토큰·폰트(Phase 234): `app.css` 토큰을 먹(#1a1714)/한지(#f5efe3)/금(#c9a24b) + **청록 Primary(#0f9d8c)**로
      교체, Noto Serif KR(디스플레이)·Pretendard(본문) 로드, h1/디스플레이=세리프. `console.css`가 토큰 상속(콘솔=한지 라이트).
      ※ CSS만 — 브랜드 문자열/템플릿 구조 미변경(다음 chunk). 랜딩/로그인 먹 다크 vault도 다음 chunk.
    - ✅ §2 chunk2 — 로그인·랜딩 먹+금 다크 vault(Phase 235): `auth/login.html`·`templates/landing.html`을
      먹(#1a1714) 다크 + 금빛 글로우 + 한지 텍스트 + 청록 CTA로. 로그인 운영자 OAuth 진단은 일반 첫 화면에서
      숨김 → `?diag=1` 또는 관리자 세션에서만(`login()` 게이트). theme-color 순흑#020010→먹#1a1714.
      landing은 _base_app 공유(에러페이지)라 다크는 landing head에 스코프. 랜딩에 Beta 배지.
    - ✅ §2 chunk3 — 리브랜딩 문자열(Phase 236): `branding.py` 기본값 `Proxy Commerce`→**`KOHgogane`** +
      신설 `get_brand_name_ko()`→**`코고가네`**(context processor에 `brand_name_ko` 주입). 사용자노출
      문자열 전수 교체: _base/_base_app/topnav(×3)/auth(login·signup·reset·magic) 타이틀·브랜드,
      manifest(.json/.webmanifest) name, sw.js, 이메일 제목(코고가네), service_name, push, 확장 가이드,
      markets_guide SVG, admin navbar, api docs title. 테스트 갱신(pwa·seller_console). 전체 10015 passed.
      ※ 남은 잔재(비-UI, env override 가능, 후속): CLI 설명·slack/discord bot username·grafana json·
        SEO_SITE_NAME·SMTP_FROM_NAME·export_manager sender 등 13곳(.py) — 사용자 화면 아님.
    - ⏳ §3 수집상품 일괄관리(퍼센티 동등) 진행 중:
      - ✅ chunk1 — 일괄 삭제(Phase 237): `collect_history_store.delete(item_ids, seller_id)`(셀러 격리, 시트/메모리),
        `POST /seller/collect/bulk-delete`, collect_history.html에 '🗑 선택 삭제' 버튼+확인 모달+행 즉시 제거,
        액션바 sticky(pc-bulk-toolbar). (일괄 마켓 등록·전체선택은 기존)
      - ✅ chunk2 — 일괄 카테고리 지정(Phase 238): `POST /seller/collect/bulk-category`(item_ids + category_code,
        또는 auto=자동분류 category_classifier). 각 항목 extra_json에 category_code 머지(셀러 격리). UI '🏷 카테고리
        지정' 버튼+모달(드롭다운 CATEGORY_OPTIONS + 🔮자동분류 체크).
      - ✅ chunk3 — 일괄 번역(Phase 239): `POST /seller/collect/bulk-translate`(AITranslator 재사용,
        제목/설명 한국어 → extra_json title_ko/description_ko, 실번역 시 표시 제목 갱신). 정직성: 키 미설정
        (stub/none) 시 원문 유지 + 안내 메시지(가짜 번역 없음). UI '🌐 한국어 번역' 버튼 → 행 제목 즉시 갱신.
      - ✅ chunk4 — 일괄 가격/마진(Phase 240): `POST /seller/collect/bulk-price`(target_margin_pct→extra 저장,
        price_multiplier→수집가 배수 적용, 둘 중 1+). 비숫자 가격은 가격 건너뛰고 마진만 적용(정직). UI '💰 가격/마진'
        모달(마진율·배수 입력) → 행 가격 즉시 갱신. 범위 검증(마진 0~90, 배수>0).
      - ⏳ 다음: 일괄 상태변경/복제 + 검색/정렬/페이지당.


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

### 후속 — 쿠팡 출고지/반품지 셀프 입력 + 가이드 + CI 수정 (오너 지시 2026-06-16 "안내를 잘 해야돼")
- **CI 머지 실패 수정**: `test_market_credentials::test_secret_not_plaintext_on_disk`가 CI에서 실패 —
  `cryptography`가 requirements.txt에 없어 CI 미설치 → `_fernet()` None → 자격증명 **평문 저장**(테스트 실패
  이자 **실제 운영 보안버그**). → `requirements.txt`에 `cryptography>=42.0,<49` 추가(전 마켓 자격증명 실암호화).
- **쿠팡 출고지/반품지 셀프서비스 입력**(멀티유저): `MARKET_CRED_FIELDS["coupang"]`에 7개 배송필드
  (`COUPANG_VENDOR_USER_ID`/`OUTBOUND_SHIPPING_PLACE_CODE`/`RETURN_CENTER_CODE`/`RETURN_ZIP_CODE`/
  `RETURN_ADDRESS`/`RETURN_CHARGE_NAME`/`COMPANY_CONTACT_NUMBER` + 선택 상세주소·반품배송비) 추가.
  `required:False`(API키만으로 is_connected/연결테스트 불변) + `section`/`help`로 폼에 ‘📦 출고지·반품지’
  구분선·도움말 렌더. 셀러가 인앱 저장 시 `seller_market_env`로 주입돼 사전검증·업로드 통과 → 오너 Render
  설정 없이도 셀러별 등록 가능.
- **발급 가이드 보강**(`market_guide.py`+`markets_guide.html`): 쿠팡 항목에 `shipping` 섹션 신설 —
  ‘어디서 찾나(윙 5단계)’ + 입력칸/어디값/**예시**/env 표 + SVG 그림(윙 배송정보→코드 복사→입력칸). 누구나
  한눈에 따라하도록. 사전검증/업로더 오류문구는 누락 env를 그대로 안내(정직).

## 🔧 AI 소싱 허브 UX 보강 (오너 지시 2026-06-16, 라이브 스크린샷 — "수집된건지 표시·버튼 다 동작·안내 섬세하게")
- **‘즉시 수집’이 이력에 저장 안 돼 결과가 사라짐** (Phase 215): `/collect/preview`에 `save` 옵션 추가 →
  true면 `collect_history_store.append`로 **수집 이력에 저장**하고 `id`/`preview_url`/`history_url` 반환.
  소싱 허브 JS가 `save:true`로 호출 → 성공 시 **‘✅ 수집 완료·이력 저장됨(ID)’ 배너 + 썸네일/가격 +
  [확인·수정·등록]([편집 페이지]) / [수집 이력에서 보기]** 링크로 결과 위치를 명확히 표시. 실패 시
  목업 대신 **정직한 안내(무엇이/왜/다음 단계: 상세URL 확인·확장수집·직접입력)** + 확장설치/직접입력 버튼.
  (`save` 미전달 기존 호출은 불변 — manual_collect 등 영향 없음.)
- **북마클릿 버튼이 큼** → 북마크바에 긴 이름 대신 **🛒 아이콘만** 뜨도록 드래그 링크 텍스트를 이모지 하나로,
  44×44 작은 버튼으로 축소(`bookmarklet.html`). 소싱 허브의 토큰/북마클릿 버튼도 아이콘+간결 안내로 정리.
- **버튼 실동작 확인**: 추천 CTA·소싱처·재수집·키워드/디스커버리 링크 타깃 라우트(`/collect`,`/me/tokens`,
  `/bookmarklet`,`/discovery`,`/keywords`,`/sourcing/{watches,candidates}`) 전부 존재 확인. 안내 카피 섬세화.

## 🔧 수집 안 됨(CORS)·소싱처 변화 모니터링·인간친화 카피 (오너 지시 2026-06-17, 라이브 스크린샷)
오너 지적: ①북마클릿 `Failed to fetch`로 수집 안 됨 ②"회수"같은 딱딱한 단어 ③토큰 설명 부재
④북마클릿 버튼 큼 ⑤수집상품 소싱처 변화(품절/가격/사이즈/재고) 실시간 연동 희망.
1. ✅ **북마클릿 수집 `Failed to fetch`** (Phase 216): CORS가 `/health/*`에만 설정돼 임의 쇼핑몰에서
   `/api/v1/collect/extension`으로 보내는 크로스오리진 POST의 preflight가 막혀 수집 실패. → `order_webhook.py`
   CORS에 `/api/v1/collect/*`(origins `*`, POST/OPTIONS, Content-Type/Authorization) 추가. Bearer 인증이라
   `*` 안전. 북마클릿이 페이지 HTML도 함께 전송(600KB 상한)해 봇 차단 사이트도 서버 파싱으로 수집.
2. ✅ **인간친화 카피** (Phase 216): 토큰 "회수"→**"삭제"**(badge/버튼/확인창/토스트). 고가네퍼센티는 인간친화 우선.
3. ✅ **토큰 설명** (Phase 216): `personal_tokens.html`에 '토큰이 무엇이고 무슨 일을 하나'(①쓰는법 ②동작=Bearer
   ③안전=해시저장·삭제로 무효화) 카드 + 스코프 뜻 안내.
4. ✅ **북마클릿 버튼 → 고가네퍼센티 파비콘** (Phase 216): 🛒 이모지 대신 `favicon.svg`(글로브) 이미지 48×48
   아이콘 버튼으로. 북마크바에 파비콘으로 표시.
5. ✅ **수집상품 소싱처 변화 모니터링** (Phase 216): 신규 `/seller/sourcing/monitor`(+nav '소싱처 변화').
   내 수집 이력 상품의 소싱처를 `UniversalScraper`로 재확인 → 수집 당시 가격/옵션과 비교해 **가격 ▲▼·품절·
   옵션/사이즈 소진** 판정. 추출 불가(봇차단/네트워크)는 거짓 알림 대신 **'확인 불가'**(정직). 결과는
   `collect_history_store.update`로 extra_json에 저장(다음 방문 시 마지막 상태 표시). `POST /sourcing/monitor/check`
   단건/전체. ※ 현재는 온디맨드(버튼) 확인 — 정기 자동확인은 추후 스케줄러로 확장 예정.

## 🔧 인페이지 수집버튼 직관화 + 소싱처 자동확인 (오너 지시 2026-06-17, Temu 스샷 — 퍼센티 벤치마킹 "똑같지 않게·바로")
1. ✅ **확장 인페이지 수집 버튼 브랜딩/직관화** (Phase 217): `content_script.js` FAB를 🛒→**고가네 글로브
   아이콘(네이비+주황/초록 궤도, 파비콘 모티프) + "고가네 수집/번역까지 한 번에"** 라벨, 네이비+주황테
   pill로 강화(경쟁사 파란 막대형과 구분). 첫 등장 시 살짝 강조 애니메이션. manifest 1.2.0→1.3.0.
2. ✅ **소싱처 변화 자동확인** (Phase 217): ①페이지 자동확인 — `/seller/sourcing/monitor` 열 때 '자동 확인'
   토글(기본 ON, localStorage)로 미확인 상품 자동 점검(상한 20). ②서버 정기확인 — `run_auto_source_monitor()`
   (최근 N일 수집상품 일괄 재확인, only_stale_hours 이내 스킵) + `POST /cron/sourcing-monitor`(X-Cron-Secret,
   Render Cron). 변화건은 alerts로 요약. 정직성 유지(확인 불가는 변화 아님).

## 🔧 북마클릿 실작동(CSP 우회)+아마존 국가선택+수집화면 파비콘 (오너 지시 2026-06-17, /seller/collect 스샷)
1. ✅ **북마클릿 토큰 발급해도 수집 안 됨 → 실작동** (Phase 218): 원인은 토큰이 아니라 **임의 쇼핑몰의 CSP**가
   북마클릿 `fetch`(`/api/v1/collect/extension`)를 막은 것(Temu/아마존 등). → 북마클릿을 **fetch 대신 '새 탭
   네비게이션'** 방식으로 교체: 페이지 메타(u/t/img/p/c)를 쿼리로 담아 `window.open('/seller/collect/quick?…')`.
   새 탭은 **로그인 세션**으로 열려(토큰 불필요) CSP/CORS 영향 없음 → 실제 수집됨. 신설 `GET /seller/collect/quick`:
   세션 인증 → `_collect_real_draft` 서버수집(상세·번역), 막히면 **페이지 메타로 폴백 수집**(정직) → 수집 이력
   저장 → 편집 페이지로 redirect. 둘 다 실패 시 `collect_quick_result.html`로 직접입력/확장 안내. (구 토큰 fetch
   북마클릿 제거. 크롬 확장은 그대로 — 봇 차단 사이트는 확장 권장.)
2. ✅ **아마존 국가 드롭다운** (Phase 218): `oneclick_markets`의 아마존을 `countries`(미국/일본/독일/영국/프랑스/
   캐나다/이탈리아/스페인/호주/인도) 드롭다운으로 — 국가별 사이트 선택 후 열기.
3. ✅ **수집 화면 파비콘 + 카피 갱신** (Phase 218): `/seller/collect` '인페이지 수집' 안내에 favicon.svg 노출 +
   '보라색 수집 버튼'→'고가네 퍼센티 아이콘+고가네 수집'으로 갱신, 북마클릿(토큰 불필요) 링크 추가.

## 🔧 북마클릿 Percenty급 수집(이미지·상세·리뷰)+번역선택+일괄1000 (오너 지시 2026-06-17)
1. ✅ **북마크 짧은 라벨** (Phase 219): 북마크바에 긴 js 코드 대신 한 단어 **‘고가네수집’**(드래그 링크 텍스트)로 표시.
2. ✅ **클릭 시 편집페이지 새탭 X → ‘수집됨’만 표시** (Phase 219): 결과를 내 계정 **수집 이력**에서 확인.
   `/collect/quick` 성공도 redirect 대신 confirmation 페이지(collect_quick_result ok=True).
3. ✅ **이미지·상세설명·리뷰까지 수집** (Phase 219): 북마클릿을 **postMessage 방식**으로 — 새 탭
   `/seller/collect/receiver`(로그인 세션 인증)를 열고 페이지 **HTML(800KB)·이미지·메타**를 postMessage 전달
   → 같은 출처로 `POST /seller/collect/receive` 저장. 서버가 `UniversalScraper.parse_html`로 이미지/상세/옵션
   추출 + `_extract_reviews`(JSON-LD review 우선 + 보수적 휴리스틱, 없으면 빈 리스트=정직) → 수집 이력 저장.
   CSP가 fetch를 막는 사이트(Temu/아마존)도 동작(페이지 이동·postMessage는 CSP connect-src와 무관).
4. ✅ **번역 사용자 선택** (Phase 219): 북마클릿 페이지에 ‘수집할 때 한국어 자동 번역’ 토글(기본 ON) → 북마클릿에
   baked, `receive`가 `translate` 존중(off면 원문 유지·번역함수 미호출).
5. ✅ **일괄수집 100→1000** (Phase 219): `/collect/bulk`(30→1000), `/api/v1/collect/bulk`(100→1000), UI 문구 갱신.

## 🔧 사람친화 수정: 편집 썸네일·오류창·파비콘·이미지필터·로그인 (오너 지시 2026-06-17, 편집/업로드 스샷)
1. ✅ **편집 페이지 이미지 썸네일** (Phase 220): `collect_preview.html` 이미지 URL 행마다 46px **썸네일**(클릭 시 원본)
   표시 — URL만 보이던 걸 사람이 이미지로 바로 확인(대표 선택 쉬움). `addImageRow` 썸네일+동기화.
2. ✅ **마켓 등록 오류창 정리** (Phase 220): WC 406 등 긴 오류 URL(consumer_secret 포함)이 모달 밖으로 튀어나오던 문제
   → `#uploadResults` word-break/overflow-wrap + `modal-dialog-scrollable`로 박스 안에서 줄바꿈.
3. ✅ **북마클릿 파비콘 표시** (Phase 220): 북마크바에 글로브 파비콘만 작게(텍스트 라벨 제거). (hover 시 js URL 노출은
   북마클릿 본질상 불가피 — 외부 스크립트 로딩은 CSP에 막혀 인라인 유지.)
4. ✅ **북마클릿 이미지 필터** (Phase 220): `document.images`에서 logo/sprite/icon/avatar/banner/placeholder/300px미만
   제외(`G()`) → 배너·로고 대신 상품 이미지 위주 수집.
5. ✅ **북마클릿 로그인 튕김 방지** (Phase 220): `/seller/collect/receiver` 페이지 렌더의 인증 게이트 제거(저장 POST만 인증)
   → 새 창이 로그인 폼으로 점프하지 않고, 미로그인 시 receiver 안에서 친절한 '로그인' 안내(401 처리).
- **남은 후속(이 지시)**: ① **리스팅/검색 페이지에서 여러 상품 한 번에·취사선택 수집** — 북마클릿/페이지 한계로
  **크롬 확장**(상품카드별 버튼 주입)이 정석. 다음 단계로 확장에 구현 예정. ② Temu 등 SPA의 가격/옵션/리뷰는
  표준 메타(JSON-LD/OG)가 빈약해 추출이 제한적 — 사이트별 파서 보강 필요(별도 작업).

## 🔧 크롬 확장: 리스팅/검색 페이지 다중 상품 수집 (오너 지시 2026-06-17 "크롬확장 가자")
- ✅ **목록 페이지 다중 취사선택 수집** (Phase 221): `content_script.js`에 리스팅 모듈 추가 —
  `kgpFindCards()`(img≥120px + 앵커 + 카드 텍스트에 가격패턴 있는 블록을 상품카드로 휴리스틱 감지, href 중복제거),
  카드 ≥3개면 리스팅 모드로 판단. 카드마다 좌상단 **‘수집’ 배지**(클릭=✓선택, 주황 아웃라인) + 상단 고정
  **고가네 수집 바**(전체선택/선택해제/선택수집/전체수집/상태). 선택분을 `background.collectBulk`로 전송 →
  토큰으로 `/api/v1/collect/extension` 순차 호출(background fetch라 페이지 CSP 무관) → 수집 이력 저장.
  무한스크롤 대응 4초 재스캔, SPA URL변경 재주입. manifest 1.3.0→**1.4.0**.
  ※ 목록 수집은 카드 정보(제목·이미지·가격·링크) 수준 — 상세·옵션·리뷰는 상세페이지 ‘고가네 수집’ 권장(README 방법4).
- 인앱 `/seller/collect` 안내·확장 README에 ‘검색/목록 페이지 여러 상품 한 번에 수집’ 추가.

## 🔧 상품 이미지 전체 수집 (오너 지시 2026-06-17 "모든 이미지 수집해야돼")
- ✅ **이미지 전체 수집** (Phase 222): `universal_scraper`가 이미지를 `src`만·5개로만 받던 걸 →
  신설 `_collect_dom_images()`로 `src`+lazy(`data-src`/`data-original`/`data-lazy`)+`srcset`/`<source>` 최대해상도까지
  수집, 로고/아이콘/배너/플레이스홀더 패턴 제외, 상대경로 절대화·중복제거. JSON-LD/OG 경로도 갤러리 이미지를
  머지(캡 10→40). 확장 `content_script.extractProductMeta`도 og 하나가 아니라 페이지의 모든 상품 이미지(≥250px,
  로고/배너 제외) 수집. manifest 1.4.0→1.4.1.
- **남은 후속(오너 화면, 코드 아닌 사안/대형 기능)**: ① 구글/네이버 로그인 = OAuth 키 미설정(카카오만 설정됨) —
  로그인 페이지가 이미 ‘설정 경로/redirect_uri/client_id’ 진단 표시. 오너가 `GOOGLE_CLIENT_ID/SECRET`,
  `NAVER_CLIENT_ID/SECRET` 설정 + 콘솔 redirect_uri 등록해야 활성화. ② 북마클릿 아이콘/hover URL = 브라우저가
  `javascript:` 북마클릿에 강제하는 동작이라 커스터마이즈 불가 → 크롬 확장(브랜드 아이콘·hover 정상) 권장.
  ③ 마켓별 카테고리 선택 + 자동 카테고리 분류 = 대형 기능(퍼센티 벤치마킹) — 별도 PR로 진행 예정.

## 🔧 나열순 후속 ① 마켓 연동 상태 “눈에 확” 표시 (오너 지시 2026-06-17 "나열순대로 가라")
- ✅ **편집/업로드 화면 마켓 연동 배지** (Phase 223): `collect_preview_by_id`가 셀러별 `mc.is_connected`로
  shopify/coupang/smartstore/elevenst/woocommerce 연결 여부 계산 → 업로드 모달 ‘1. 마켓 선택’ 각 타일에
  **✅ 연결 / ❌ 미연결** 배지(미연결은 클릭 시 `/seller/markets/connect/<market>` 새 탭) + 상단 ‘연동 N/5’ 요약.
  연결 타일 초록 테두리, 미연결 흐리게 — 보이는 것 위주, 과하지 않게. (가격/썸네일/이미지/상세/옵션/키워드 편집은 이미 지원)
## 🔧 나열순 후속 ② 카테고리 자동 분류 + 편집 선택 (Phase 224)
- ✅ **카테고리 자동 분류**: 신설 `category_classifier.py`(키워드 규칙 → 정규화 코드 BAG/CLO/BTY/FOD/ELC/DIG/
  HOM/HLT/SPT/TOY/BBY/PET/OFC/GEN, confidence 포함, 미일치=GEN 정직). 편집 페이지에 **카테고리 드롭다운 +
  🔮 자동 분류 버튼**(`POST /collect/classify`) 추가, 로드 시 제목/키워드로 자동 추천 표시. 저장 시 `category_code`를
  extra_json에 보관 → 각 마켓 업로더가 매핑(coupang CATEGORY_MAP 등). ※ 마켓별 풀 카테고리 트리(퍼센티식 마켓별
  드롭다운)는 각 마켓 카테고리 API 연동 필요(대형) — 정규화 코드+자동분류로 MVP, 트리 연동은 후속.
- 후속 ③ 구글/네이버 로그인 = 관리자 1회 OAuth 앱 등록을 화면에서 클릭만으로 따라하도록(소비자는 클릭만으로
  로그인 — 키 없이 작동하는 코드는 OAuth상 불가, 등록은 1회).

## 🔧 세션/로그인 — 새 세션마다 재로그인 + 자동 로그인 옵션 (오너 지시 2026-06-17)
오너: 소비자는 새로 올 때마다(브라우저 종료/캐시 갱신) 재로그인해야 개인정보 보호+개인화됨. 자동 로그인도 제공. 관리자(오너)는 예외.
- ✅ **세션 영구화 조건부** (Phase 225): `establish_session()`이 `session.permanent=True`를 **무조건** 설정하던 걸 →
  **`remember`(자동 로그인) 또는 role=='admin'일 때만 영구**. 그 외 소비자는 **브라우저 세션 쿠키**(브라우저 종료 시
  자동 로그아웃 → 공용PC/개인정보 보호). 이메일/소셜(카카오·구글·네이버) 로그인 모두 `remember` 전달
  (이메일=hidden, 소셜=oauth_start→callback 세션 보관). `PERMANENT_SESSION_LIFETIME` 기본 14일(`SESSION_REMEMBER_DAYS`).
- ✅ **로그인 화면 ‘자동 로그인’ 체크박스**: 기본 꺼짐(공용 PC 보호), 마지막 선택 localStorage 기억. 소셜 링크에 remember 부착.
- 로그아웃은 이미 동작(`/auth/logout`, 셀러 콘솔 헤더 버튼). 로그인=이메일+카카오/구글/네이버(구글/네이버는 오너 1회 OAuth 등록 필요).
- **오너 액션(개인화 강제)**: 소비자 로그인 강제는 `SELLER_CONSOLE_AUTH=1`(Render)로 켜짐 — 켜야 콘솔이 로그인을
  요구하고 수집/마켓연동/소싱처가 셀러별 개인화됨(자격증명은 이미 셀러별, 수집이력 seller_id 격리).

## 🔧 크롬 확장 실제 설치 + 모바일 수집 (오너 지시 2026-06-17 "설치가 실제로 되어야지, 모바일도")
- ✅ **확장 다운로드 + 설치 가이드** (Phase 226): 앱에 확장 배포 경로가 없어 설치 불가였음 → 신설
  `GET /seller/extension/download`(서버가 `extensions/chrome-collector`를 즉석 ZIP 패키징·`kohgane-collector/…`
  구조로 내려줌) + `GET /seller/extension` **설치 가이드 페이지**(다운로드→압축풀기→`chrome://extensions`→개발자모드
  ON→압축해제된 확장 로드→토큰 입력→수집버튼 등장, 단계별·복사버튼). 수집 페이지 안내에 ‘🧩 확장 설치하기’ 링크.
  ※ 정석은 크롬 웹스토어 게시(오너 1회)지만, 그 전에도 ‘압축해제 로드’로 즉시 설치 가능.
- ✅ **모바일 수집(PWA share_target)** (Phase 226): 모바일은 확장 미지원 → 앱 PWA 매니페스트(json+webmanifest 동기)에
  `share_target`(GET `/seller/collect/quick`, params title/text/**u**) 추가 → 안드로이드에서 쇼핑앱 **공유 → 고가네
  퍼센티**로 URL 전송 시 로그인 세션으로 수집. `/collect/quick`이 `u`/`url`/`text`(텍스트 내 URL 추출)도 허용.
  설치 가이드에 ‘URL 붙여넣기/공유하기’ 모바일 방법 명시. (URL 붙여넣기 수집은 기존에도 모바일 동작)

## 🔧 확장 다운로드 404 + 북마클릿 라벨/목록경고 (오너 지시 2026-06-19, 스샷)
- ✅ **확장 다운로드 404 수정** (Phase 227): `/seller/extension/download`가 배포에서 404였음 — **Dockerfile이 `src/`만
  복사하고 `extensions/`를 안 넣어** 런타임에 확장 디렉토리가 없어서. `COPY extensions/ ./extensions/` 추가 → 다운로드 동작.
- ✅ **북마크 이름이 JS코드로 노출** (Phase 227): 북마클릿 앵커가 이미지만 있어 드래그 시 북마크 이름이 `javascript:…`
  코드로 잡혔음(hover에 코드 노출). → 앵커에 **‘고가네수집’ 텍스트** 추가 → 북마크 이름·hover가 ‘고가네수집’으로 표시.
  (※ javascript: 북마클릿의 **아이콘은 브라우저 기본 모양**이라 커스텀 불가 — 브랜드 아이콘은 크롬 확장에서 표시됨을 명시.)
- ✅ **목록 페이지 북마클릿 경고** (Phase 227): 북마클릿이 상품 목록/검색 페이지에서 눌리면 페이지 전체를 1개로 수집해
  이미지가 뒤섞였음 → 북마클릿에 **목록 감지(이미지 포함 a ≥8개) confirm 경고**(‘상품 1개 상세용, 여러 상품은 크롬 확장’)
  추가. 수집은 정상 동작(수집 이력 저장·편집 가능) — 목록에서의 혼란만 경고로 방지.
- 남은 후속: 소비자 친화 위해 크롬 웹스토어 게시(오너 1회)면 ‘설치’ 한 번으로 끝(현재는 압축해제 로드).

## 🔧 확장 설치 실패·브랜드 아이콘·정직한 마켓 배지 (오너 지시 2026-06-19, 스샷)
- ✅ **확장 설치 실패 '매니페스트 없음' 수정** (Phase 228): 다운로드 ZIP이 파일을 `kohgane-collector/` 하위폴더에
  넣어, 압축 풀고 그 폴더 선택 시 루트에 manifest.json이 없어 크롬이 거부했음 → ZIP **루트에 manifest.json**(하위폴더
  제거, `arcname=name`)으로 패키징 → 압축 푼 폴더 그대로 ‘압축해제 로드’ 성공. 가이드 문구도 갱신.
- ✅ **확장 브랜드 아이콘** (Phase 228): icons/16·32·48·128.png를 고가네 글로브(네이비+파랑 지구+주황/초록 궤도,
  파비콘 모티프)로 새로 생성(Pillow). chrome://extensions에서 고가네 고유 프로그램으로 식별. manifest 1.4.1→1.4.2.
- ✅ **마켓 연동 배지 정직화** (Phase 228): is_connected가 ‘키 존재’만 보는데 ‘연결’이라 단정해(실제 업로드는 실패)
  오해를 줬음 → ‘✅ 키 설정됨 / ❌ 미설정’ + ‘키 설정 N/5’로 변경, 실제 연결은 사전검증/등록에서 확인됨을 툴팁 명시.
- **남은 후속(이 지시)**: ① 로그인 강제(개인화) = `SELLER_CONSOLE_AUTH=1`(오너 env) — 안 켜면 로그인 없이 콘솔 접근.
  ② 좌측 nav 일부 버튼 동작 점검 ③ 수집 상품 목록(퍼센티식 한눈에) 보강 ④ 마켓 등록 실패(자격증명/토큰 만료=오너측)
  ⑤ 모바일 수집버튼(PWA share_target 적용됨, 더 쉽게).

## 🔧 나열순 ① 로그인 강제(개인화) 기본 ON (Phase 229)
- ✅ `SELLER_CONSOLE_AUTH` 기본값 `0`→**`1`**(views.py `_AUTH_ENABLED`). 미설정 시 **로그인 강제** → 소비자별
  로그인 + 수집/마켓/소싱처 개인화(seller_id 격리). 끄려면 `SELLER_CONSOLE_AUTH=0`. Phase 225(세션 비영구+자동로그인+
  관리자예외)와 합쳐 ‘새 세션마다 재로그인, 자동로그인 옵션, 오너 예외’ 완성.
- 테스트는 `tests/conftest.py`에서 `SELLER_CONSOLE_AUTH=0` 주입(세션 없이 페이지 직접 호출하므로). `test_collect_receiver`의
  reload-after-delenv 오염(기본 ON이라 삭제 시 켜짐) → finally에서 `setenv "0"`으로 복원하도록 수정.
## 🔧 나열순 ②③④ (Phase 229)
- ✅ **② 수집 상품 목록 퍼센티식** : `collect_history.html` 테이블에 **썸네일 컬럼**(52px, 클릭→편집) + 제목/도메인/
  가격/경로/시각/상태 정리 + ‘✏️ 편집·등록’ 버튼. 내가 수집한 걸 이미지로 한눈에 보고 바로 편집·등록.
- ✅ **③ 좌측 nav 점검**: 사이드바 40개 링크 라우트 전수 확인 — 404/500 없음(전부 정상). 미로그인 시 로그인으로
  가는 건 ①인증 강제(의도). 특정 버튼이 여전히 이상하면 화면 지정 필요.
- ✅ **④ 모바일 수집**: PWA `share_target`(Phase 226)으로 안드로이드 공유→고가네 수집 + URL붙여넣기 + 북마클릿
  (네비게이션 방식이라 모바일 동작). 확장 설치 페이지에 모바일 방법 명시.

## 🔧 확장 선택수집 실작동 + 키워드 추천 + 북마클릿 라벨 (오너 지시 2026-06-19, 스샷)
- ✅ **확장 리스팅 전체선택/선택수집 미작동 수정** (Phase 230): `content_script.js`가 4초마다 재스캔하며
  `KGP_SELECTED.clear()`로 **선택을 지우고** 배지를 통째로 재생성 → ‘전체 선택’ 후에도 ‘선택된 상품 없음’.
  → 선택을 **URL 키 기반**(`_kgpCardByUrl`)으로 바꾸고, 재스캔 시 **선택 유지** + 배지 없는 카드에만 주입.
  전체선택/선택해제/선택수집/전체수집 정상 동작. manifest 1.4.2→1.4.3.
- ✅ **카테고리별 키워드 자동 추천(칩)** (Phase 230): `category_classifier.suggest_keywords(code,title)` 신설
  (카테고리별 일반 검색어 + 제목 단어 보강). `classify` 응답·편집 뷰에 `suggested_keywords` 포함 → 편집 페이지에
  ‘추천:’ **키워드 칩**(클릭 담기, ＋전체추가). 자동분류하면 그 카테고리 키워드로 칩 갱신. 직접 입력도 가능.
- ✅ **북마클릿 라벨 ‘고가네 수집’**(띄어쓰기) (Phase 230): 북마크 이름/hover가 ‘고가네 수집’으로.
- 남은 후속(이 지시, 대형/사이트별): 수집 추출 품질(가격/옵션/리뷰 — Temu/yoshida SPA), 확장 FAB가 클릭 없이
  자동 노출(이미 content_script 자동주입이나 사이트별 점검), 좌측 빈약한 페이지 데이터 연동.

## 작업 방식
- 브랜치 `claude/magical-noether-oo4831`에서 작업 → PR 생성·main 머지(오너 승인됨)로 배포.
- 변경 후 전체 테스트(`python -m pytest tests/ -q`) 통과 확인.
