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

## 작업 방식
- 브랜치 `claude/magical-noether-oo4831`에서 작업 → PR 생성·main 머지(오너 승인됨)로 배포.
- 변경 후 전체 테스트(`python -m pytest tests/ -q`) 통과 확인.
