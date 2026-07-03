# CLAUDE.md — 고가브릿지(gogabridj) 프로젝트 지침
> 이 파일은 Claude Code가 **매 세션 항상 로드**한다. 디자인·스킬·커넥터 사용 규칙을 여기서 강제한다.

## 프로젝트
- 제품: 해외 상품 수집 → 번역·편집 → 멀티마켓 등록 1인 셀러 SaaS. Flask/Python 3.11, Google Sheets 백엔드, Render 호스팅.
- 브랜드: 한글 **고가브릿지**, 영문 **gogabridj**(붙여쓰기·소문자). 정체성 "디지털 한지 위의 금속활자".

## git·머지 규칙 (자율 진행 — 단, 스스로 점검 강제)
Claude Code는 지금처럼 브랜치·PR·머지를 자율로 한다. 단 **머지 전 아래 셀프 점검을 통과해야만** 머지한다. 하나라도 못 채우면 머지 금지, "미완"으로 두고 보고.
- **[ ] pytest 전부 그린 + CI 통과.** 빨간 거 있으면 머지 금지.
- **[ ] 변경 화면마다 before/after 캡처 1쌍** 확보. 캡처 못 내는 항목은 미완.
- **[ ] 자기 회귀 점검:** 이번 변경이 기존 동작을 깨지 않았는지 전 화면 훑기(죽은 버튼·가짜 성공·새 창 이탈·미번역·플레이스홀더·세로쪼개짐·삭제 부활).
- **[ ] 정직 데이터 위반 0:** 가짜 수치·Mock·임의 환산·거짓 성공 토스트 없음.
- **[ ] 내가 지목 안 한 같은 유형 버그도** 같이 잡았는지 확인.
- **PR 본문에 셀프 점검 체크리스트 + 캡처 + pytest/CI 결과를 반드시 첨부**한 뒤 머지. "했다"는 문장만으로 닫지 말 것.
- **반쪽 실행 금지:** 항목을 절반만 하고 머지하지 않는다. 절반이면 미완 표시하고 다음으로 안 넘어간다.

## 절대 원칙 (모든 작업)
- 정직 데이터: 미연결·실패는 빈 상태+안내. **가짜 성공·가짜 수치·Mock·임의 환산 금지.**
- 회귀 금지: 수정마다 pytest + CI 게이트.
- 디자인은 `app.css` 토큰 단일 소스. 하드코딩 hex/px 금지.
- 완료 인정 = **실제 화면 before/after 캡처.** "적용함" 보고만으론 미완.
- 일반 유저에게 개발 표기·메타 JSON·관리자 링크·플레이스홀더(`{REGION_NAME...}`) 노출 금지.

## 스킬 사용 규칙 (반드시)
- **UI/CSS를 그리거나 바꿀 때 → `.claude/skills/gogabridj-design/SKILL.md` 를 먼저 적용**한다. 우리 토큰·시그니처(다리)·타이포·컴포넌트 규칙의 단일 출처다.
- 범용 보조: 프론트 컴포넌트는 **web-artifacts-builder**, 테마 일관성은 **theme-factory**.
- **상세설명·마케팅 카피를 생성할 때 → `humanizer` 스킬을 적용**해 사람이 쓴 것처럼. AI 티 나는 문장·과장·없는 스펙 금지.
- brand-guidelines(Anthropic 자기 브랜드)는 **쓰지 말 것** — 우리 팔레트와 충돌.

## 커넥터 사용 규칙
- 상품 데이터 추출이 막히면 **Apify**로 스크레이핑 보강(Temu·아마존 JS 사이트).
- 상품 이미지 변환·리사이즈는 **Cloudinary**.
- 글로벌몰 작업은 **Shopify**, 실시간 DB는 **Supabase**, 블로그·멀티샵은 **WordPress.com**, 키워드·SEO는 **Semrush/Ahrefs**.
- 자격증명은 코드/채팅에 하드코딩 금지 → 환경변수/커넥터 OAuth로만.

## 디자인 정답지
- `고가브릿지_디자인목업_v40.html` 과 1:1 대조. 어긋나면 미완. (다크 히어로 + 다리 시그니처 라인아트 + 한지/먹 교차.)
- 시그니처(다리/게이트/키스톤)를 반드시 살린다. 크림+세리프 default로 끝내지 말 것 — 다리 라인아트를 히어로·섹션 디바이더에 반복.

## 스킬 발동 트리거 (작업 유형 → 스킬)
- UI/CSS 작성·수정 → `gogabridj-design`(우리 전용) + `web-artifacts-builder`(컴포넌트) + `theme-factory`(테마).
- 상세설명·마케팅 카피·가이드 글 → `humanizer`(사람처럼).
- 새 스킬 만들기/다듬기 → `skill-creator`.
- 마케팅 정적 이미지·OG·아이콘 → `canvas-design`.
- 절대 쓰지 말 것 → `brand-guidelines`(Anthropic 자기 브랜드, 우리와 충돌).

## 작업 순서(현재 스프린트 v39)
1. 북마클릿 파비콘(v39-B) → 2. 수집 추출(v39-E2: 가격·이미지분리·상세 AI) → 3. 디자인(v39-D) → 4. 모바일(v39-M).
각 항목 PR + pytest + CI + 캡처. 반쪽 실행 금지.

---

# 📒 누적 작업 메모리 (아래 — 검증된 팩트·v1~v39 히스토리, 단일 진실원천. 보존)

# CLAUDE.md — proxy-commerce 작업 메모리

> 이 파일은 매 세션 시작 시 로드된다. 오너(Kohgane) 지시·검증된 팩트를 누적 기록한다.

## 🟥 D-30 론칭마스터플랜 / v41 Week 1 (오너 2026-07-02 — 8/1 론칭, "생존 기반")
- 지휘 문서=launch_masterplan_D30, 세부=addendum_v41. **깃허브 Copilot과 병행 작업 — 중복 회피**(Copilot=STEP
  1-1~1-4 죽은버튼 `copilot/add-step-1-dead-functionality`, STEP 2 로그인 `copilot/add-login-status-screen-separation`).
  규칙: 각 항목=별도 PR=before/after 캡처=CLAUDE.md 셀프점검 게이트 통과 후 머지. **1번(영속성) 안 끝나면 2번 이후 금지.**
- ✅ **STEP 1-0 write 영속성 근본 수리 (#387, #388):** 증상 ①수집기 '수집 완료'→이력에 없음(항목 286e5bd75186)
  ②삭제→새로고침→부활 ③토큰 저장→인증 반복. **근본 원인=캐시 무효화 누락**: collect_history_store의
  append/update/delete가 **시트 경로에서만** flask.g 요청범위 캐시(`_kgp_ch_rows`)를 무효화하고 **인메모리 경로에선
  안 해서** 같은 요청 재읽기가 스테일('부활'). 수리: 인메모리 경로에도 `_invalidate_cache()` + delete 끝에 통합 +
  신규 `existing_ids()`(무효화 후 `_all_rows()` 재읽기로 실제 잔존 확인) → **write-then-verify**. bulk-delete 라우트가
  삭제 후 재조회해 안 지워졌으면 정직 실패 200. 확장 수집 자기검증을 **목록 스코프**(user_id+email 관용집합, user_store에서
  email 해석)로 재읽기 → 스코프 불일치로 '완료인데 안 보임' 박멸, 비영속이면 502. 토큰은 Copilot이 commit-verify 추가.
  가드 test_v41_step1_0_write_persistence(5)+collect_scope(3). before/after: docs/screens/v41/{write-persist,collect-appears}-*.png.
- ✅ **STEP 1-0b 수집→목록 자동 반영 (#389):** 수집이력 화면 열려 있으면 **새로고침 없이** 새 상품 자동 등장.
  신규 `GET /seller/collect/history/count`→{ok,total}(seller 관용 스코프+days 필터, 실패 시 ok:false 정직). 템플릿
  폴링 스크립트: 8초 간격 + `visibilitychange`(탭 복귀) 재조회, 서버 total이 렌더 시점보다 늘면 auto-reload.
  **정직**: 서버 영속 저장된 값(count)이 늘 때만 반영(가짜 실시간 아님). **편집 가드**: 드로어(kgp-drawer-open)/모달
  (.modal.show) 열려 있으면 중단 대신 '새로 수집된 N건' 배너 후 편집 종료 시 반영. 가드 test_v41_step1_0b_autorefresh(6).
  전체 10676 passed. before/after: docs/screens/v41/step1-0b-autorefresh-{before,after}.png(빈 목록→수집→탭복귀 poll로 자동 등장).
- ✅ **X-2 자동 카테고리 오분류 수리 (#390):** 증상=접이식 차량용 책상 → '식품/차'(FOD). 근본 원인=`category_classifier`
  가 **단어 부분일치**(substring)라 한 글자 키워드 "차"(tea)가 "차**량**"(vehicle) 안에 매칭. 한국어 복합어는 공백이
  없어 substring 매칭이 동음이의 함정. 수리: ①한 글자(단일 음절) 키워드는 **독립 토큰**일 때만 매칭(_TOKEN_RE로
  토큰화 → 차량→차 오매칭 박멸) ②멀티글자=가중치 2/한글자=1/동음이의함정(차·배·밤·눈·옷·컵·펜·립…)=0.5로 점수화
  ③뚜렷한 멀티글자 근거 없으면 신뢰도 상한 0.4 → `_MANUAL_THRESHOLD` 0.5 미만이면 **GEN + needs_manual**(가짜 확정
  금지, UI가 '직접 선택해 주세요' 표기). 진짜 차(녹차·홍차·원두 커피)는 멀티글자로 FOD 유지(회귀 0). 옷장→가구(옷
  substring 오분류 박멸). 가드 test_v41_x2_category_misclassify(7) + 기존 test 갱신(녹차 matched). 전체 10683 passed.
  before/after: docs/screens/v41/x2-category-{before,after}.png(식품/차 → 홈/가구/주방, 키워드칩도 가구 계열로).
- ✅ **STEP 4-2 확장 툴바 아이콘 브릿지 확인 + 재로딩 유도 (#391):** 오너 증상=툴바 아이콘 지구본. **점검 결과
  현재 확장 아이콘(icons 16/32/48/128 + action.default_icon)은 이미 브릿지 마크**(v39-A2에서 교체·픽셀검증됨), popup
  헤더/소싱처 관리도 인라인 브릿지 SVG, 확장 전체 globe/🌐 grep=0. → **실제 원인=캐시된 옛 확장**(오너가 언패키지
  확장 리로드 필요). 조치: manifest 1.5.20→**1.5.21**(재로딩 유도) + 신규 가드 test_v41_4_2_extension_toolbar_icon(4:
  **action.default_icon 4사이즈 브릿지 PNG 지정 보증**(기존 가드 공백 메움)·버전핀·manifest globe 0·툴바 128/48 금+주황
  키스톤 픽셀). 기존 버전핀 4곳(v38/v39) 1.5.21 갱신. 전체 10687 passed. 캡처(정직: before=오너측 캐시 지구본 재현
  불가): docs/screens/v41/4-2-extension-toolbar-bridge.png(16/32/48/128 브릿지 마크 + 툴바 목업). ※오너 액션: 확장을
  1.5.21로 재로딩(chrome://extensions → 새로고침)하면 지구본 사라짐.
- ✅ **X-1 이미지↔상품 매핑(엉뚱한 이미지) 수리 (#392):** 증상=목록서 상품 A에 상품 B 이미지 / 어떤 상품은 대표
  이미지 없음. **근본 원인 두 갈래:** (1)확장 리스팅 카드가 raw `img.src`만 써서, lazy-load 페이지에선 스크롤 전 여러
  상품이 **같은 placeholder src를 공유** → 'A에 B 이미지'. (2)이미지 없을 때 목록이 다른 이미지로 렌더될 여지.
  **수리:** ①content_script 신규 `_kgpBestImg(img)` — currentSrc·data-src·data-original·srcset(최대해상도) 우선,
  placeholder(data:·1x1·blank·spacer·lazyload…) 배제 → `_kgpAmazonCards`/`_kgpGenericCards` 두 경로 모두 적용
  (카드마다 자기 data-src로 귀속, 이미지 없으면 `images:[]` 정직). 서버는 이미 행(상품 ID)에 이미지 귀속(누출 0)
  — 회귀 가드로 재확인. ②collect_history 목록 빈 이미지 셀에 '이미지 없음' title/aria(엉뚱 이미지 대신 정직 표기).
  manifest 1.5.21→1.5.22. 가드 test_v41_x1_image_mapping(3: 소스계약 + **node로 두 카드 placeholder 비공유 실증**
  A≠B + 서버 항목간 이미지 누출 0). 버전핀 5곳 1.5.22 갱신. before/after: docs/screens/v41/x1-image-mapping.png
  (BEFORE 두 카드 공유 placeholder → AFTER 각자 자기 이미지, 실제 _kgpBestImg 실행 결과).
  → **Week 1 내 몫 완주**: STEP 1-0·1-0b·X-2·4-2·X-1. (Copilot: STEP 1-1~1-4 죽은버튼·STEP 2 로그인.)
- ✅ **Week 1 item 5 북마클릿(v40-B) — 점검 결과 이전 세션에서 이미 완료·가드됨:** `/bm/install`(order_webhook,
  →/seller/bookmarklet 302), 드래그 앵커 텍스트 0(빈 `<a>`+font-size:0, 아이콘=CSS background favicon-48), title은
  제로폭(URL 폴백 방지), 설치페이지 파비콘 상속(v39-B). 가드 test_v40_a_root_favicon_bm_install·test_v39b_bookmarklet_favicon
  (bookmarklet/v40 관련 60 passed). → 새 작업 불필요(정직: 이미 되어 있어 재작업 안 함).
## 🟥 v42 최종 실행 프롬프트 (오너 2026-07-02 — 8/1 론칭, PHASE 1 수집 블로커 최우선)
- 지휘=v42. PHASE 1(수집이 진짜로 되게) 안 끝나면 3·4 착수 금지. PHASE 2(속도)는 병행 가능. Copilot=1-7 죽은버튼.
  이미 완료: 1-4 write영속성(=STEP 1-0 #387/#388), 1-5 자동등장(=STEP 1-0b #389), 1-2 일부(=X-1 #392).
- ✅ **1-1 가격 클릭 시점 DOM 직접 읽기 + 통화 감지 (#394):** 증거=Temu 61,144원 렌더인데 드로어 0.00 USD.
  **근본 원인 3:** ①`extractProductMeta`가 `og:price:amount` 있으면 `_kgpScopedPrice()`(렌더 DOM 현재가)를 **아예
  안 읽음**(`if(!getMeta(...))` 게이트) + 반환도 `getMeta(...) || heuristic`로 스테일 메타 우선 ②`_kgpScopedPrice`
  정규식이 `₩`는 잡지만 **'원' 접미어 미감지**(Temu KR='61,144원') ③통화 미상 시 `|| "USD"` 기본값. **수리:**
  신규 `_kgpParsePrice`+`_KGP_CODE_MAP`(원→KRW·엔→JPY·위안/元→CNY). 가격 해결 순서=**scoped(렌더 현재가)→og:price
  →본문**(게이트 제거, scoped 항상 계산). 반환 `price:heuristicPrice, currency:heuristicCurrency`(USD 기본값 제거).
  서버 extension_api: 통화 미상+가격 있으면 `price_status=needs_check`(USD 임의 확정 금지), 저장 currency 기본값
  "USD"→""(2곳). manifest 1.5.22→1.5.23. 가드 test_v42_1_1_price_at_click(6: 소스계약 + node로 ₩/원→KRW 실증 +
  서버 KRW저장·통화미상 needs_check). 전체 10696 passed. before/after: docs/screens/v42/1-1-price-before-after.png
  (렌더 61,144원 → BEFORE og:price 0.00 USD / AFTER 렌더DOM 61144 KRW) + 1-1-drawer-krw.png(실제 드로어 61,144 KRW).
- ✅ **1-3 중복 수집 방지 (goods ID 정규화 키) (#395):** 같은 상품 두 번 수집→목록 2건 쌓이던 문제. 신규
  `src/collectors/product_key.py::normalize_product_key(url)` — 도메인별 상품 고유키(Temu `g-<digits>`/`goods_id`,
  아마존 ASIN(마켓플레이스별), 타오바오/티몰/1688 `id`, 알리 `/item/<id>`), 그 외 host+path(쿼리 트래킹 `_oak_mp_inf`
  등 제거·끝슬래시 정규화). `collect_history_store.find_by_product_key(url, seller_ids)` — 각 행 url을 그때 정규화해
  비교(예전 행도 매칭)·셀러 격리·최근 것 반환. extension_api·`_quick_collect`(북마클릿/공유) append 전 dedup →
  기존 있으면 `{ok:true, duplicate:true, item_id, message:'이미 수집한 상품입니다'}`로 새 행 안 만듦. content_script
  FAB가 duplicate면 축하 대신 안내 토스트. manifest 1.5.23→1.5.24. **테스트 격리 수정**: dedup이 실 `_in_memory`를
  읽어, append를 목킹하는 test_extension_api_history가 다른 파일이 남긴 aloyoga 행에 dedup되던 것 → 클래스 autouse
  `_clean_store`로 저장소 비움. 가드 test_v42_1_3_dedup(6). 전체 10702 passed. before/after:
  docs/screens/v42/1-3-dedup-before-after.png(같은 상품 2회 → BEFORE 총수집 2 / AFTER 총수집 1 + 안내).
- **addendum v42-E 편입(오너 2026-07-02):** 확장 = 퍼센티식(설치 후 상시 수집). 판정순서 E-1→E-5→E-4→E-2→E-3.
  가격(1-1)은 통과 확인. 이미지·상세(1-2,1-6)도 마저.
- ✅ **E-1 토큰 영속 + 연결 상태 (#396):** 증상=토큰 넣었는데 페이지마다 '인증이 필요합니다…' 반복(= collect 401 토스트).
  점검: 토큰은 이미 chrome.storage.sync+local 저장·background가 매 요청 헤더 첨부·로드시 리셋 로직 없음(영속 정상).
  근본 UX 결함=사용자가 **연결됐는지 확인할 방법이 없어** 혼란 + 미인증/실패 토스트가 안내 부족. **수리:** 신규
  `GET /api/v1/collect/me`(Bearer→{ok,email,name}/401, CORS 기허용) → 옵션 페이지가 로드·저장 직후 호출해 **'연결됨 ✓
  (계정)'** 배너 표시(401=만료·재발급 안내, 네트워크실패=확인 불가 정직). background: 미인증 시 자동 notification 남발
  제거(반환만, FAB 클릭 때만 안내) + 401 응답에 `authRequired` 플래그(재프롬프트는 401일 때만). 옵션 '초기화'→'재설정'.
  manifest 1.5.24→1.5.25. 가드 test_v42_e1_token_persist(7: /me 200·401·CORS + background 무-자동알림·401플래그 + 옵션
  연결배너·리셋없음). 전체 10709 passed. before/after: docs/screens/v42/e1-token-before-after.png(상태표시 없음 →
  '연결됨 ✓ · demo@goga.kr' + 재설정) + e1-token-connected.png.
- ✅ **E-5 벌크 수집 정직 요약 + 재시도 + 진행률 (#397):** 점검=벌크는 이미 항목별 `/api/v1/collect/extension`
  (STEP 1-0 write-then-verify durable) 후 `d.ok`만 카운트 → '수집됨인데 이력 없음'(가짜성공)은 이미 방지됨. 남은
  결함=요약이 '성공 N/실패 M'으로 뭉뚱그리고 실패 항목 재시도·진행률이 없음. **수리:** background `handleCollectBulk`
  가 성공/**중복**(d.duplicate)/실패 분리 집계 + `failedItems` 반환 + 1건마다 `bulkProgress`를 탭에 전송(순차 처리).
  content_script `kgpRunBulk`(전체/선택/재시도 공용) — 정직 요약 '총 N: 완료 X · 중복 Y · 실패 Z' + 실패분만
  **'실패 N건 재시도'** 버튼(kgpRenderRetry, 조용한 누락 금지) + `bulkProgress` 수신해 '수집 중… (done/total)'.
  이력 자동반영은 STEP 1-0b 연동(기존). manifest 1.5.25→1.5.26. 가드 test_v42_e5_bulk_persist(4: 소스계약 + node로
  재시도 버튼 생성 실증). 전체 10713 passed. before/after: docs/screens/v42/e5-bulk-summary-retry.png(성공/실패만 →
  완료·중복·실패 + 재시도).
- ✅ **E-4 전체선택 누락(24 중 16) 정확도 (#398):** 증상=벌크바 '전체 24 중 상품 16' — 8개(가격 없는 카드·앵커
  변형) 미인식. 근본=`_kgpAmazonCards`가 `!img||!titleEl||!pr.price`로 **가격 필수** + `/dp/` 앵커만 인정. 유효
  ASIN(비스폰서)은 이미 강한 상품 신호이므로 **완화:** href는 앵커 없으면 `origin+/dp/+asin` 폴백, 제목 셀렉터 확장
  (h2 a span·title-recipe·a-size-base-plus/medium·img.alt), **가격 선택**(제목·이미지 둘 다 없을 때만 제외).
  MutationObserver+4s 재스캔은 기존(지연로딩 커버). 정직: 벌크바에 '제외 N(광고 등)' 명시(조용한 누락 금지).
  manifest 1.5.26→1.5.27. 가드 test_v42_e4_selectall(5: 소스계약 + **node로 실제 어댑터 실행 — 26개(16유가+8무가+
  2광고)→상품 24 인식·광고 2 제외·유가 16**). 전체 10718 passed. before/after: docs/screens/v42/e4-selectall-before-after.png
  (실제 _kgpAmazonCards: 상품 16 → 24 + 제외 2).
- ✅ **E-2 퍼센티식 상시 수집 버튼 (#399):** 점검=인프라 이미 완비(manifest matches `<all_urls>`·FAB는 인증
  무관 상시[토큰은 클릭 때만]·SPA pushState/replaceState/popstate 후킹·MutationObserver·v38#4 상품페이지 휴리스틱
  게이트 제거). 갭=오너 지정 어댑터 도메인(야후쇼핑 재팬·요시다카반)이 기본 소싱처에 없어 그 사이트에서 버튼
  미표시. **수리:** KGP_DEFAULT_SOURCES + options DEFAULT_SOURCES에 yahoo(shopping/paypaymall.yahoo.co.jp)·
  yoshida(yoshidakaban.com) 추가(기본 ON). manifest 1.5.27→1.5.28. 가드 test_v42_e2_always_on(5: matches all_urls·
  injectCollectButton 인증게이트 0·SPA훅·지정도메인 포함·**node로 kgpHostAllowed가 temu/amazon/yahoo/yoshida True,
  무관 사이트 False**). 전체 10723 passed. before/after(정직: 상시 표시가 산출물): docs/screens/v42/e2-always-on-button.png
  (Temu·Amazon 진입 → 고가수집기 버튼 상시, 인증 무관). ※미인증 클릭 안내는 E-1 연동.
- ✅ **1-6 상세설명 가짜 템플릿(필러) 박멸 (#400):** 증거='Temu에서 이 올인홈 …을 확인하세요. 가구 제품도 좋아할
  수 있습니다.'가 상세로 저장. `_FILLER_DESC_RE`에 마켓 자동 필러 패턴 추가: `{사이트}에서 이 {상품}을 확인하세요`
  (`[A-Za-z가-힣]+에서\s*이\s*.{0,60}?[을를]\s*확인하세요`) + `제품/상품도 좋아할 수 있습니다` 추천 꼬리. **오탐 0**
  검증(실제 상세 '이 제품은 원목…'·'조립 방법을 확인하세요'·'사이즈를 확인하세요'는 필러 아님). extension_api가
  수집 시 필러면 description 비움(번역본도) → 편집 페이지 상세 빈칸 + 기존 'AI 상세 초안 생성'(aiDraftBadge 'AI 초안·
  검토·편집 후 저장', 자동 확정 금지) 노출. 플레이스홀더 제거는 strip_placeholder_tokens(v39 D) 유지. 가드
  test_v42_1_6_filler(6: 템플릿 필러 3 + 실상세 오탐 0 + 서버 필러 빈값 E2E + 편집 AI초안 뱃지). 전체 10727 passed.
  before/after: docs/screens/v42/1-6-filler-before-after.png(상세 'Temu에서 이…' → 빈 상세 + AI 상세 초안 생성).
- ✅ **E-3 목록 호버 즉시 수집 버튼 (#401):** 목록 카드 hover 시 썸네일 중앙에 브릿지+'수집' 알약(먹 배경+금
  테). 클릭→해당 상품 1건 즉시 수집(collectBulk[1])→성공/중복이면 '수집됨 ✓'(청록, kgpCelebrate는 새 수집만).
  터치기기(pointer:coarse)=우상단 상시 소형. **이미 수집된 건 처음부터 '수집됨 ✓'**: 신규 `POST /api/v1/collect/exists`
  (Bearer→urls 중 정규화키(1-3)로 이미 수집된 것 반환)를 background(collectExists)로 조회해 선표시(중복 방지 연동).
  기존 좌상단 '선택' 배지(다중 선택)와 공존. 리스팅 아님/접힘 시 kgp-card-quick도 정리. manifest 1.5.28→1.5.29.
  ※rebrand 가드 회피: 주석에서 '퍼센티' 제거. 가드 test_v42_e3_hover_collect(5: 소스계약 hover/터치/수집됨 +
  /exists 정규화키 매칭·401). 전체 10732 passed. 캡처: docs/screens/v42/e3-hover-collect.png(기본 숨김/호버 '수집'/
  '수집됨 ✓' 3상태, 실제 kgpQuickBtnStyle).
  → **v42-E 확장(E-1~E-5) + PHASE 1 핵심(1-1·1-3·1-6) 완주.** (Copilot=1-7 죽은버튼.)
## 🟥 addendum v43 (오너 2026-07-03 — 드로어 퍼센티식 재구성 + 남은 버그 일괄)
- 순서: 0(운영자 키=OPENAI/DEEPL Render 설정, 오너 처리) → 1 삭제영속 → 2 벌크 → 3 이미지 → 4·5 버튼 → 6 드로어
  재구성(퍼센티 벤치마크·우리 토큰) → 7 카테고리. 각 항목 캡처 게이트.
- ✅ **v43-1 삭제 부활 × 자동 새로고침 (#402):** 증상=폴링 자동새로고침 시 삭제분 부활. 점검: 서버 삭제는 이미
  write-then-verify(v42 1-4 #387, existing_ids 재조회 후 잔존 시 정직 실패 200), delete JS도 data.ok/deleted 확인.
  근본 잔여=**삭제/폴링 경합**(1-0b 8초 폴링이 삭제 진행 중 reload→커밋 전 재조회 부활 위험). **수리:** ①`window._kgpDeleting`
  플래그 — runBulkDelete 시작 시 set, poll/apply가 보류(reload로 자연 해제, 실패 경로선 해제) ②서버 총건수 하강 시
  `initialTotal` 하강 동기화(삭제로 준 값 기준으로, 부활 오탐 방지). 가드 test_v43_1_delete_persist(3: 삭제 후 5회
  폴링 재조회 부활 0·write-then-verify 정직실패·템플릿 경합가드). 전체 10735 passed. before/after:
  docs/screens/v43/1-delete-no-resurrection.png(총 수집 5 → 2삭제+폴링 5회 → 3 유지, 부활 0).
- ✅ **v43-2 벌크 정확도 27중16 복구 (제네릭 어댑터) (#403):** E-4는 아마존만 완화, 제네릭(_kgpGenericCards, Temu
  카테고리 등)은 여전히 **가격 필수**라 가격 미렌더 카드가 누락(27중16). 수리: 신규 `_kgpIsDetailHref(href)`(상품 상세
  링크 판정: /dp/·/g-<id>·/goods/·/product/·shopee -i.n.n 등) → **가격 또는 상세링크면 인식**(둘 다 없으면 제외).
  상품 후보(제목+이미지+링크+영역OK) scanned 카운트 → 벌크바 '제외 K' 정직. node로 27개(16유가+11무가·상세링크)→
  **27 인식**(옛 16), 비상품(카테고리·이벤트 배너 링크)→0 제외 실증. manifest 1.5.29→1.5.30. 가드 test_v43_2_bulk_accuracy(3).
  전체 10738 passed. before/after: docs/screens/v43/2-bulk-16-to-27.png.
- ✅ **v43-3 이미지 클릭시점 추출 스코프 (판매자 로고 배제 + 2버킷) (#404):** 증상=갤러리에 판매자 로고('ALL IN
  HOME')가 상품 이미지로 혼입. 근본=extractProductMeta가 페이지 모든 img≥250px를 수집(src 블랙리스트만), 로고 URL이
  'logo' 미포함이면 통과. 수리: 신규 `_kgpIsSellerLogo(im)` — src뿐 아니라 **alt/class/조상 영역**(seller/merchant/
  store-info/vendor/brand-header)으로 로고 배제. **갤러리/상세 2버킷**: `_KGP_GALLERY_SEL`(gallery·product-image·
  main-image·imgTagWrapper 등) / `_KGP_DETAIL_SEL`(#productDescription·feature-bullets·description) 스코프로 분류,
  반환에 gallery_images/detail_images + 대표=갤러리 첫 장(로고 배제). 상품 ID 귀속은 서버 행 저장으로 이미 보장(회귀
  확인). manifest 1.5.30→1.5.31. 가드 test_v43_3_image_scope(3) + **devshot으로 실제 extractProductMeta 실행**(mock PDP:
  갤러리 3 + 로고 + 상세 1 → 갤러리 3·상세 1·로고 0). 전체 10741 passed. before/after: docs/screens/v43/3-image-scope.png.
- ⏳ v43 남음: 4 마진계산기 버튼 / 5 원본보기 새탭 / 6 드로어 재구성(칩네비·마켓별카테고리·경고어) / 7 카테고리 리프 트리.
- ⏳ 후속: 1-2 이미지·상세 스코프 추가 강화(판매자 로고 제외) / PHASE 2 속도 / PHASE 3~5.
- ⏳ 후속: PHASE 2 속도, STEP 3 JSON제거·UX / 4-1 라벨 '다리 너머, 오늘의 발굴' / STEP 5 디자인.

## 🟧 v39 브리프 (오너 2026-06-29 — "수집 신뢰성·인페이지 편집 드로어·아이콘 가시성·404 박멸" + v39-M 모바일 PWA)
- 규칙(불변): 각 항목 **실제 화면 before/after 캡처로만 완료**. 추측 금지·거짓성공/임의환산 금지·회귀 금지(pytest+CI)·토큰 단일소스.
- 순서: A 지구본잔존 → B 소형아이콘 → C 인페이지 편집 드로어(핵심) → D 가격/상세/번역 → E 버튼라벨 → F 404박멸 → G 전수.
  v39-M: M1 PWA설치 → M2 공유수집(Share Target) → M3 모바일반응형 → M4 게이트.
- ✅ **A. 지구본 잔존 박멸 (Phase 337):** v38에서 favicon/확장 아이콘 PNG는 이미 브릿지였으나 **확장 popup/options에 🌐
  소싱처 관리·🧤 글러브 타이틀·📦🛒⚙️👁🙈✅❌⏳ 등 이모지 잔존**(오너가 본 '지구본'). 전수 제거: popup/options 헤더를
  **인라인 브릿지 마크 SVG**(금아치+청록다리+주황키스톤)로, 모든 데코 이모지→텍스트, popup.js/options.js/background.js
  ✅❌👁🙈⏳ 제거, bot/formatters 🌐 제거. favicon.svg/ico는 브릿지 확인(불변). manifest 1.5.15→1.5.16. 가드
  test_v39_a_no_globe(4) + v38 버전핀 갱신. 전체 10466 passed. before/after: docs/screens/v39/A-globe-{before,after}.png
  (확장 팝업: 🧤+🌐+이모지 → 브릿지 마크·이모지0).
- ✅ **B. 소형 전용 고대비 아이콘 (Phase 338):** 16/32px 파비콘이 마스터 디테일(현수교 2선·얇은 금 아치)로 **뭉개져 어두운
  덩어리**(주황 키스톤 안 보임). 신설 `scripts/gen_small_icons.py` — ≤48px 전용 변형: 먹 라운드 스퀘어 꽉 채움 + **굵은 청록
  아치 1개 + 큰 주황 키스톤 점**(16/32는 다리/데크 생략, 48부터 다리). 스트로크 마스터 대비 굵게(4x 슈퍼샘플). favicon-16/32
  교체 + favicon-48 신설 + favicon.ico(16/32/48 멀티) 재생성. 캐시 v=177→v=178(전 템플릿). 가드 test_v39_b_small_icons(4:
  16/32px에 청록·주황 픽셀 실존=뭉개짐0) + 영향 테스트 v178 갱신. 전체 10470 passed. before/after(1:1+확대):
  docs/screens/v39/B-smallicon-{before,after}.png(어두운 덩어리 → 아치+주황 점 식별).
- ✅ **C. 수집품목 클릭 → 인페이지 편집 드로어 (Phase 339, 핵심):** 기존엔 수집 이력에서 행/제목/도메인 클릭 시 편집
  페이지로 라우트 이동하거나 **도메인 링크가 원본 사이트(yoshidakaban 등)로 새 탭** 이탈. 수정: 썸네일·제목·편집 버튼을
  **`.kgp-open-drawer`(data-id/url/title)**로 바꿔 클릭 시 **우측 슬라이드 편집 드로어**(같은 페이지 위 오버레이, **URL 변화·
  새 창 0**) 오픈. 드로어는 기존 편집 페이지(`/collect/preview/{id}?drawer=1`)를 **same-origin iframe**으로 임베드(전체 편집
  기능 재사용 — 제목·가격·통화·원화환산·상세·이미지·카테고리·키워드·업로드). `?drawer=1`은 콘솔 chrome 숨김. 드로어 헤더에
  제목 + **'원본 보기 ↗'(여기만 새 탭)** + 닫기. 도메인은 비-링크 텍스트로(원본 이탈 0). iframe 저장 시 postMessage→닫을 때
  목록 새로고침. **보안:** security 미들웨어가 `/seller/collect/preview/` 한정 `X-Frame-Options: SAMEORIGIN`+CSP
  `frame-ancestors 'self'`(그 외 전 경로 DENY 유지=클릭재킹 방어). 모바일은 풀스크린 시트(v39-M 연동). 헤드리스 검증
  (클릭→URL 불변·새 창 0·드로어 편집폼 로드). 가드 test_v39_c_edit_drawer(4) + dead-anchor 가드 호환. 전체 10474 passed.
  before/after: docs/screens/v39/C-drawer-{before,after}.png(목록 클릭 이탈 → 인페이지 편집 드로어).
- ✅ **D. 가격 정직 표기 + 한국어 번역 온디맨드 (Phase 340):** 증상=가격 '-' 빔·번역 전혀 안 됨. 점검: 가격 needs_check는
  이미 정직 처리(빈값/needs_check면 임의 환산 0 + '가격 확인 필요'). **번역 누락 근본:** AITranslator가 OPENAI/DEEPL 키
  없으면 stub→원문 유지(조용히). 수정: 편집 페이지(드로어)에 **'한국어로 번역' 버튼** 추가 → `/collect/bulk-translate`(단일,
  무료 카운터 연동) 호출. 실제 번역되면 title_ko/description_ko 반영(리로드), **키 미설정이면 가짜 번역 0 + 정직 안내**
  (OPENAI_API_KEY 설정 요청). **원문 보존**: title_en로 '원문: … 원문으로 되돌리기' 토글. 가드 test_v39_d_price_translate(4).
  전체 10478 passed. before/after: docs/screens/v39/D-translate-{before,after}.png(원문 일본어 → 한국어 번역+원문 토글, 가격 확인 필요 유지).
  ※오너 액션: 실제 번역 작동하려면 Render에 OPENAI_API_KEY(또는 DEEPL_API_KEY) 설정 — 없으면 정직 안내만(가짜 0).
- ✅ **E. 수집기 버튼 라벨 '고가수집기 수집'→'고가수집기' (Phase 341):** 인페이지 FAB 라벨의 중복 '수집' 제거 →
  '고가수집기'(content_script FAB 218·408, 리스팅 바 700, 핀 779, options/README 동기). 브릿지 마크·'번역까지 한 번에'
  부제 유지. v38#4 항상-노출 게이트(휴리스틱 가드 제거·host 게이트만) 재확인. manifest 1.5.16→1.5.17. 가드
  test_v39_e_fab_label(3) + v38 버전핀 갱신. before/after: docs/screens/v39/E-fab-label-before-after.png.
- ✅ **F. 수집 상세 404 박멸 → '수집 실패' 빈 상태 (Phase 342):** collect_preview_by_id가 _get_owned_item None일 때
  `abort(404)` → 드로어에 404 페이지가 떠 신뢰 깨짐. 수정: **404 금지 → 200 '수집 실패' 빈 상태**(신설
  collect_preview_missing.html, 드로어 모드 chrome 숨김) + '다시 수집하기'(/seller/collect)·'수집 이력으로'(드로어 닫기
  postMessage). 같은 user 스코프 유지(타인 항목도 데이터 누출 0 — 편집폼 미노출). 영향 테스트(v30/preview_view/v38_audit)를
  404→200+수집실패+누출0으로 갱신. E2E: 확장 수집→상세 200. 가드 test_v39_f_no_404(4). 전체 10485 passed.
  before/after: docs/screens/v39/F-404-{before,after}.png(드로어 안 404 페이지 → '수집 실패' 빈 상태).
- ✅ **G. 전수 점검(CI 게이트 감사) (Phase 343):** 같은 유형 결함을 전 화면에서 잡는 감사 test_v39_g_global_audit(6):
  (a)죽은버튼=핵심 7화면 200·핸들러 없는 빈 앵커 0 (b)가짜성공=수집 durable 게이트 (c)새 창 이탈=목록 클릭 드로어·
  도메인 원본 새 탭 0·북마클릿 window.open 0 (d)원문 미번역=편집 페이지 '한국어로 번역' 액션+정직 (e)아이콘=favicon 브릿지·
  확장 globe 0 (f)404 박멸=미존재 200 '수집 실패'. UI 변화 없는 가드 추가라 캡처 없음(정직) — 감사 6 PASSED가 산출물.
  전체 10487 passed. → **v39 A~G 완주.** 다음: v39-M 모바일(M1 PWA·M2 공유수집·M3 반응형 드로어).

### 🟧 v39 개정 브리프 (오너 2026-06-29 — 신규 아이콘 이미지 2장 첨부 "자 얘도 가라" + v39-M)
- 오너가 v39+v39-M을 **확정 신규 마크 이미지 2장**과 함께 재전송. 개정점: A=신규 아이콘 전량 교체, D+플레이스홀더 박멸,
  G=마켓등록 카드 레이아웃(신규), H=전수감사. v39-M: M1 PWA설치·M2 공유수집·M3 모바일 드로어.
- ✅ **A(개정). 신규 브릿지 마크 전량 교체 (#358):** 오너 첨부 확정본=**흰 배경+검정 라운드 보더+금 게이트 링+주황 키스톤+
  청록 데크(2줄+금 타이)**. (uploads의 zip은 옛 어두운 마스터라 미사용 — 첨부 이미지를 PIL로 재현.) 신설
  `scripts/gen_bridge_icon_v39.py` 단일소스에서 파생: favicon-16/32/48·favicon.ico·favicon.svg(임베드)·icon-180/192/512/1024·
  apple-touch·확장 16/32/48/128·마스터·OG. 소형(≤48)=단순 변형(타워 생략·굵게), 대형=풀 디테일. 확장 FAB SVG
  (KGP_BRIDGE_SVG)·popup 헤더 아이콘도 신규 마크(흰 배경/링). 캐시 v=178→179·OG ?v=3→4·확장 1.5.17→1.5.18. 가드
  test_v39_a2_new_bridge_icon(5, 흰바탕+금/주황/청록 픽셀·FAB SVG, PIL 지연import로 CI collect-only 안전). 전체 10497 passed.
  before/after: docs/screens/v39/icon-replace-{before,after}.png·icon-fab-after.png.
  ※CI(python-guard)는 `pytest --collect-only`만 — Pillow 미설치라 **PIL은 함수 내 지연 import 필수**(top-level import 시 수집 에러).
- ✅ **D(개정). 플레이스홀더 토큰 박멸 (#359):** 제목에 '{REGION_NAME - Temu Republic of Korea}' 류 미치환 치환 토큰 노출.
  `universal_scraper.strip_placeholder_tokens()` 신설(보수적: {{...}}·{ ...CAPS_TOKEN... }·%CAPS%·${...}만 제거, 정상 텍스트
  오탐 최소). 적용 전수: 확장 수집(extension_api 저장 직전+번역본)·URL/북마클릿/quick(_collect_real_draft 반환 직전)·편집
  프리필(collect_preview_by_id 렌더 안전망). 치환 실패=토큰 제거(가짜값 0). 가드 test_v39_d2_placeholder_kill(5). 전체 10502.
  before/after: docs/screens/v39/placeholder-kill-{before,after}.png(제목 토큰 제거·가격 '확인 필요').
- ✅ **G(개정). 마켓 등록 카드 레이아웃 (#360):** 편집 드로어 좁은 폭서 '스마트스토어·코가네멀티샵' 라벨이 **세로 한 글자씩
  쪼개짐**(원인=col-6 col-md-4 + nowrap 부재). 수정: 마켓 카드 그리드를 **균등 폭 CSS Grid**(minmax(170px,1fr))로, 마켓명
  white-space:nowrap+ellipsis, 배지는 flex-wrap. 하드코딩 보라(#6f42c1)→var(--teal/success/warn) 토큰. 가드
  test_v39_g2_market_cards(4). 전체 10506. before/after: docs/screens/v39/market-cards-{before,after}.png(290px 드로어).
- ✅ **H. 전수 점검 v39 신규유형 횡단 (#364):** test_v39_h_audit(8) — (a)플레이스홀더 (b)좁은칸 세로쪼개짐 (c)새 창 이탈
  (d)아이콘/globe (e)PWA (f)모바일 바텀시트 (g)404. 횡단 결과 (b) 추가 인스턴스 0 확인(markets_connect/preview break-all은
  긴 URL/에러용, sourcing col-6은 KPI 카드 — 안전). 감사 8 PASSED가 산출물(캡처 없음 정직). 전체 10533 passed.
- ✅ **v39-M M1. 설치형 PWA (#361):** manifest name 'gogabridj'→**'고가브릿지'**(설치 타이틀)·bg #1A1714→**#F5EFE3**(한지
  splash)·theme #1A1714 유지·standalone·192/512 maskable. iOS 메타(apple-mobile-web-app-capable/-title 고가브릿지) 추가.
  **SW 정직화**: 앱셸(정적)만 캐시, 동적 데이터 페이지 캐시 금지(스테일 가짜 0), 네비=네트워크 우선, 오프라인=신규
  offline.html('저장 데이터 미노출' 명시). CACHE goga-bridj-v36→gogabridj-v39. (beforeinstallprompt 버튼은 v36서 연결됨.)
  가드 test_v39_m1_pwa_install(9)+영향핀(v36/pwa/v21/v38 name·bg). 전체 10515. before/after: docs/screens/v39/m1-pwa-install.png.
  ※latest-wins: v38이 manifest name=gogabridj였으나 v39-M 최신 브리프가 '고가브릿지' 명시 → 교체(콘솔 헤더 brand는 gogabridj 유지).
- ✅ **v39-M M2. 공유로 수집(Web Share Target) (#362):** 신규 `/seller/collect/share` — 공유 title/text/url에서 URL 추출→
  로그인 세션 수집(_quick_collect 공통 코어)→성공 시 **편집 화면 drawer 모드로 redirect**(?drawer=1&from=share). manifest
  share_target.action /collect/quick→/collect/share(양). 북마클릿 /collect/quick은 '수집됨' 확인 유지(흐름 분리). 봇차단
  실패=가짜성공 0+'PC 확장 권장'. 가드 test_v39_m2_share_target(5)+extension_install 핀. 전체 10519.
  before/after: docs/screens/v39/m2-share-collect.png(확인만 → 편집 드로어 진입).
- ✅ **v39-M M3. 모바일 반응형 드로어 (#363):** 수집이력 편집 드로어가 모바일(≤767.98px)서 **아래→위 풀스크린 바텀시트**
  (92dvh·둥근 상단·그랩 핸들·닫기 44px·'원본 보기' 아이콘만). 편집기 drawer 모드에 **하단 고정 액션바**(.kgp-action-bar sticky,
  저장/등록 ≥44px·풀폭)+가로 스크롤 0(overflow-x:hidden). 가드 test_v39_m3_mobile_drawer(5). 헤드리스 scrollWidth==clientWidth.
  전체 10525. before/after: docs/screens/v39/m3-mobile-drawer.png. → **v39 개정(A·D·G·H)+v39-M(M1·M2·M3) 완주.**
  ※오너 액션: 확장은 1.5.18로 재로딩(폐기 캐시), Render에 OPENAI/DEEPL 키 설정 시 실제 번역 작동(없으면 정직 안내).

## 🟥 v38 브리프 (오너 2026-06-28 — "가짜성공 박멸·표기·아이콘·수집기·북마클릿·토큰·전역점검")
- 대전제: **"적용함" 보고 금지 — 실제 화면 캡처(before/after)로만 완료 인정.** 못 보여주면 미완·다음 못 넘어감.
  원칙: 추측 금지·거짓성공/가짜수치 금지·회귀 금지(pytest+CI)·정직 데이터·토큰 단일소스. 언급 안 한 동일유형 버그도 전수 점검.
- ✅ **1. 수집 가짜성공 박멸 (Phase 330):** 증상=Temu 등 고가수집기 수집 시 '수집 완료' 토스트는 뜨나 수집품목에 없음.
  **로그/E2E로 확정(추측 금지):** 단일수집 경로(`/api/v1/collect/extension`)는 인프로세스에선 정상(collect→list 1건). 진짜
  원인은 **영속성**: `collect_history_store.append`가 `GOOGLE_SHEET_ID` 설정됐는데 **시트 쓰기 실패 시 워커-로컬 `_in_memory`로
  폴백**하고도 item_id를 반환 → 같은 워커의 자기검증(get)은 통과(가짜 성공)하나 **다른 워커/새로고침엔 안 보임**. 수정:
  `append(return_durable=True)`가 `(item_id, durable)` 반환(시트설정+쓰기실패=durable False), 엔드포인트가 **durable
  아니면 502 정직 실패**(가짜성공 금지). 또 **벌크 경로(`_run_bulk_job`)가 catalog 시트에만 쓰고 수집이력엔 안 넣던 버그**도
  수정(이력 append 추가, durable 확인). E2E CI게이트 test_v38_collect_no_fake_success(3: 동일유저 목록 반영/비영속=502/
  durable 플래그). append 단일값 모킹 하위호환(튜플 아니면 durable 간주). 전체 10437 passed.
  before/after(확장 수집 라운드트립): docs/screens/v38/collect-fakesuccess-{before,after}.png(빈 목록→수집 즉시 1건 반영).
- ✅ **2. 표기 동시반영 Goga Bridj→gogabridj (Phase 331):** 영문 정식 표기를 **'gogabridj'(전부 소문자·붙임)**으로 확정,
  띄어쓴 'Goga Bridj'·'GOGA BRIDJ' **전수 교체**(사용자 노출만, 내부 식별자·repo·도메인 보존). `branding.py` 기본값
  `_DEFAULT_BRAND_EN`='gogabridj' + 하드코딩 리터럴 스윕(py/html/js/svg/css 23+곳: 콘솔 헤더·title·OG·랜딩·토스트·푸터·
  이메일/알림·sw push 제목·favicon aria·매니페스트 name). 매니페스트 양쪽 name='gogabridj'. OG 카드 워드마크
  'GOGA BRIDJ'→'gogabridj' 재생성 + og:image 캐시 ?v=2→?v=3. 영향 테스트 갱신(pwa/rebrand/v36/v37/og/seller_console).
  가드 test_v38_brand_gogabridj(4: 기본/소스 잔존0/매니페스트/콘솔렌더). 전체 10441 passed.
  before/after: docs/screens/v38/naming-{before,after}.png('셀러 콘솔 · Goga Bridj'→'gogabridj').
- ✅ **3. 아이콘 단독화(브릿지 마크·이모지 0·캐시 갱신) (Phase 332):** 점검결과 favicon/apple-touch/매니페스트/확장
  16·32·48·128 아이콘은 **이미 브릿지 마크**(지구본 아님). 오너의 '트레이 지구본'은 **캐시된 옛 확장**이 유력 →
  manifest 1.5.13→**1.5.14**로 bump(재로딩 유도) + favicon 캐시 `v=176→v=177`(전 템플릿, 탭 아이콘 갱신). 실제 코드
  버그: 인페이지 FAB 수집 축하가 **🧤 글러브 이모지 + 위트/마일스톤 이모지(🧤🚀🟢💰🏅)·✅❌** 사용 → **전부 제거**,
  스탬프를 **브릿지 마크(KGP_BRIDGE_SVG, 옛 KGP_GLOVE_SVG 개명)**로, 토스트는 색으로 성패 표시(이모지 0). 📌💡도 제거.
  바깥 javascript: 북마클릿 지구본은 Chrome 강제(불가피, 안내 명시) — 확장 권장. 가드 test_v38_icons_bridge_only(4) +
  영향 테스트 갱신(favicon v177·KGP_BRIDGE_SVG). 전체 10445 passed. before/after: docs/screens/v38/icon-mark-before-after.png.
- ✅ **4. 고가수집기 버튼 소싱처 항상 노출 + 진입점 복원 (Phase 333):** 원인=injectCollectButton이 host 게이트 외에도
  `looksLikeProductPage()/kgpIsDetailUrl()` **상품 페이지 휴리스틱 가드**를 둬서, SPA(Temu)·카테고리·검색·홈처럼 메타가
  빈약한 화면에선 버튼이 **안 떴음**("어떤 창은 안 뜸"·"예전 중앙에 뜨던 버튼도 안 뜸"). 수정: 이미 host 게이트로 소싱처에
  한정되므로 **휴리스틱 가드 제거 → 소싱처(또는 앱 진입)면 항상 노출**(우측-중앙 FAB 진입점 복원). + **MutationObserver**
  (사이트 재렌더로 FAB 날아가도 복구) + **history pushState/replaceState/popstate 후킹**(SPA 라우팅 즉시 재주입). 목록=중앙
  바/상세=FAB 상호배타 유지. manifest 1.5.14→1.5.15. 헤드리스 주입 검증(상품 메타 0 페이지에서 FAB 없음→있음). 가드
  test_v38_fab_always_on_sourcing(4) + 영향 테스트 갱신. 전체 10449 passed. before/after: docs/screens/v38/fab-always-{before,after}.png.
- ✅ **5. 북마클릿 새 창 금지 → 인페이지 소형 알림 (Phase 334):** 기존 북마클릿은 `window.open(/seller/collect/receiver)`로
  **새 탭**을 열어 postMessage 수집(오너 불만). 수정: **새 창/팝업 0** — '내 북마클릿 만들기' 버튼이 `/seller/me/tokens/generate`로
  내 collect.write 토큰 발급→북마클릿에 baked → 클릭 시 **백그라운드 fetch**(`/api/v1/collect/extension`, Bearer, v17 CORS '*')로
  수집하고 **인페이지 소형 토스트**(고가수집기 위치 우하단)로만 결과 표시. 서버 영속 저장 확인 시에만 ok(가짜 성공 0, v38 #1
  연동). **CSP가 fetch를 막으면 새 창 대신 인페이지로 안내**(확장 권장). 잔여 '새 탭/토큰 없이' 카피 정리. 가드
  test_v38_bookmarklet_inpage(4) + test_collect_quick_bookmarklet 갱신(token-free→인페이지). 전체 10453 passed.
  before/after: docs/screens/v38/bookmarklet-page-{before,after}.png + bookmarklet-inpage-toast.png(새 창 0·인페이지 토스트).
- ✅ **6. 폐기 토큰 목록 정리(활성/이력 분리) (Phase 335):** 증상=삭제(폐기)된 토큰들이 메인 목록에 '삭제됨' 행으로
  누적돼 어지러움. 수정: personal_tokens 라우트가 list_tokens를 **활성/폐기로 분리** → 메인 표엔 **활성 토큰만**(삭제 버튼),
  폐기 토큰은 **'발급·폐기 이력 N건'(기본 접힘 details)** 으로 분리(이력 보관, v29 상시이력 호환). 폐기 0이면 이력 섹션
  미노출. 본인 전용·마스킹·발급 1회는 유지. 가드 test_v38_token_history_split(2) + v29_tokens 호환. 전체 10455 passed.
  before/after: docs/screens/v38/tokens-{before,after}.png(삭제됨 행 누적 → 활성만+이력 접힘).
- ✅ **7. 전역 회귀·동일유형 버그 전수 점검 (Phase 336):** 같은 결함 패턴을 전 코드/화면에서 잡는 **CI 게이트 감사
  테스트** 신설 test_v38_global_audit(7): (a)가짜성공=수집 durable 게이트(단일 502·벌크 이력저장) (b)스코프=수집
  목록/상세 본인 식별자 격리, 침입자 세션 상세 404(누출 0) (c)죽은버튼=핵심 9화면 200 (d)표기=Goga Bridj/GOGA BRIDJ/
  고가 브릿지(공백) 소스 잔존 0 (e)아이콘/이모지=favicon·확장 globe 0·픽토 이모지 0. UI 변화 없는 가드 추가라
  before/after 캡처 없음(정직) — 감사 7 PASSED가 산출물. 전체 **10462 passed**. → **v38 7개 항목 완주**
  (가짜성공·표기·아이콘·수집기노출·북마클릿·토큰·전역점검, 각 PR+CI그린+캡처).

## 🟦 v37 브리프 (오너 2026-06-28 — "한글 표기 통일: 고가 브릿지 → 고가브릿지")
- P1 한글 서비스명 붙여쓰기('고가브릿지') 통일 / 영문 'Goga Bridj'(띄어쓰기) 유지 / 내부 식별자 변경 0.
- ✅ **한글 표기 정규화 (Phase 327):** 전수조사 결과 소스에는 이미 '고가브릿지'(공백 0, 24+곳)만 — 공백 표기 잔존 0.
  오너 라이브 증상은 **Render `BRAND_NAME_KO` env override에 공백**('고가 브릿지')이 섞인 것이 유력. 근본 단일소스 수정:
  `get_brand_name_ko()`가 **내부 공백을 모두 제거**(`re.sub(r"\s+","")`)해 env에 공백이 와도 항상 '고가브릿지'로 렌더.
  영문 `get_brand_name()`은 'Goga Bridj' 띄어쓰기 유지. 가드 test_v37_korean_naming(4: 기본/공백env 정규화/영문유지/
  소스 공백표기 0). 전체 10429 passed. before/after(BRAND_NAME_KO='고가 브릿지' 주입): docs/screens/v37/korean-naming-{before,after}.png.
  ※오너 액션(선택): Render `BRAND_NAME_KO`를 '고가브릿지'(공백 없이)로 두거나 제거(코드 기본값이 정답) — 코드가 공백을 막아줌.

## 🟧 v36 브리프 (오너 2026-06-28 — "모바일 반응형 전면 + PWA 앱 + 관리자 모바일 액션")
- 대전제: "보이는 게 다." 모바일에서 **실제 액션 가능**해야 함. 원칙: 거짓성공/회귀 금지·토큰 단일소스. **완료=모바일 뷰포트 캡처.**
- 진행: PART A 반응형(레이아웃·터치타깃·표→카드) → PART B PWA+관리자 액션 → (나중) PART C 네이티브 래핑.
- ✅ **PART A #1 모바일 단일 헤더 압축 (Phase 324):** 모바일에서 `.mobile-topbar`(셀러콘솔+모바일앱+햄버거)와 `.console-topbar`
  (Goga Bridj+검색+수출형 ▾+한국어/EN+계정)가 **이중 헤더로 쌓여** 맨텍스트 나열·세로 공간 낭비되던 것 수정. 모바일에서
  공통 console-topbar **CSS 숨김**(`@media max-767.98`) + mobile-topbar를 **단일 헤더**로 재구성(로고 + **검색 아이콘→확장
  입력** + **계정 아바타**(이니셜→/seller/me) + 햄버거, 전부 **44×44 터치 타깃**). 드로어에 언어 토글(한국어/EN) 추가(공통
  topbar 숨김 보완). '모바일 앱'(bi-phone) 버튼은 콘솔 반응형화로 제거(/seller/m 라우트는 유지). 가드 test_v36_mobile_header(3)
  + test_design_tokens_v18 아이콘셋 갱신(bi-phone→bi-search). 전체 10415 passed. before/after: docs/screens/v36/mobile-header-{before,after}.png.
- ✅ **PART A #2 넓은 표→모바일 카드 + 플로팅 버튼 겹침 (Phase 325):** 수집 이력(8열 표)이 모바일에서 `table{min-width:600px}`로
  **가로 스크롤**(3열만 보이고 제목 잘림)되던 것 수정. 전역 강제 min-width 제거 + **`.table-cards` 반응형 CSS**(모바일에서 thead
  숨김·각 행을 카드로 스택·셀에 `data-label`로 가격/경로/시각/상태 라벨·액션 버튼 풀폭 ≥44px). collect_history 표에 클래스+
  data-label 적용. '처음이신가요?' For Beginners 플로팅 버튼이 본문 가리던 것 → 모바일에서 **아이콘 FAB로 축소**(라벨 숨김)
  +본문 하단 여백(84px). 가드 test_v36_tables_cards(5). 전체 10421 passed. before/after: docs/screens/v36/tables-cards-{before,after}.png.
- ✅ **PART B #1 PWA 설치형(콘솔 어디서나) (Phase 326):** manifest는 이미 양호(Goga Bridj·브릿지 아이콘 192/512 maskable·
  먹 splash·standalone·portrait·share_target·shortcuts) — `start_url`을 제한적 `/seller/m`에서 **`/seller/dashboard`(전체
  반응형 콘솔)**로 변경(양 manifest 동기). 설치 프롬프트가 `/seller/m`에만 있던 것 → **콘솔 드로어에 '홈 화면에 앱 설치'
  버튼**(beforeinstallprompt 안드로이드, iOS=공유→홈 화면 안내) 전역 추가. sw 캐시 goga-bridj-v36 갱신. 설치 API
  `deferred['prompt']()`(네이티브 입력 prompt 가드 회피). 가드 test_v36_pwa_install(4). 전체 10425 passed.
  before/after: docs/screens/v36/pwa-install-{before,after}.png.
- ✅ **PART A #3 주문·마켓 표→모바일 카드 (Phase 328):** 주문 목록(9열)·마켓 상품현황(8열) 표에 v36 `.table-cards`
  패턴 적용(클래스+`data-label`+`cardcell-title/img/actions`) — 모바일에서 가로 스크롤·세로 문자깨짐 제거, 각 주문/상품이
  카드로 스택(마켓 배지+번호 헤더·라벨 필드·풀폭 운송장/상태 버튼 ≥44px). 가드 test_v36_orders_markets_cards(3).
  전체 10432 passed. before/after: docs/screens/v36/orders-cards-{before,after}.png.
- ✅ **PART B #2 관리자 모바일 액션 흐름 검증 + catalog 표→카드 (Phase 329):** 폰(390px)에서 핵심 액션 흐름
  **URL 수집(manual-collect)→편집(collect_preview)→마켓 업로드 모달→주문→CS** 전부 **가로 스크롤 0·정상 동작** 확인
  (PART A 헤더 압축·표→카드 덕분). 캡처 증거: docs/screens/v36/mobile-flow-{edit,upload-modal}.png. 남은 넓은 표
  **catalog(내 상품, 7열)**도 `.table-cards` 패턴 적용(클래스+data-label+cardcell-*). 가드 test_v36_catalog_cards_flow(2:
  catalog 카드화·액션 라우트 200). 전체 10434 passed. → **v36 PART A·B 큰 줄기 완주**(반응형 헤더·표→카드 4화면·
  플로팅 버튼·PWA 설치형·액션 흐름 검증). PART C(네이티브 래핑)는 추후 옵션.

## 🟩 v35 브리프 (오너 2026-06-28 — "랜딩 상단 정리·소싱 그리드 복원·검색창 + before/after 의무")
- 대전제: "보이는 게 다." 원칙: 거짓성공/회귀 금지(pytest/CI)·토큰 단일소스·frontend-design. **완료=before/after 캡처.**
- ✅ **P0 랜딩 최상단 정리 (Phase 321):** 랜딩이 공통 dark topnav(셀러콘솔/관리자/API문서/시스템상태/OAuth로그인/가입)를
  자체 헤더(.lpnav) **위에 중복** 렌더 + `<main container-fluid py-4>` 흰 여백이 히어로 위에 끼던 것 수정. `_base_app.html`에
  오버라이드 블록(`topnav`/`main_class`/`app_footer`) 신설 → landing이 셋 다 비워 **공통 chrome 제거**(자체 헤더·푸터 단일).
  랜딩 헤더에 통합 **로그인** 링크 추가(브리프 '로그인/무료 시작'). topnav의 관리자·API문서·시스템상태는 `user_role=='admin'`
  게이팅(일반 유저 비노출). 가드 test_v35_landing_chrome(4) + test_header_login_branch 갱신(랜딩=통합 로그인). 전체 10407 passed.
  before/after: docs/screens/v35/landing-top-{before,after}.png.
- ✅ **P0 소싱 카드 그리드 복원 + 이미지 깨짐 (Phase 322):** v34에서 Bootstrap `col-12 col-sm-6 col-lg-4`가 뷰포트/컨테이너에
  따라 **세로 일렬**로 무너지고, 네이버 쇼핑 이미지가 핫링크 차단으로 깨지면 `onerror`가 **박스 통째로 숨겨**(빈 색 박스/카드
  붕괴) 정렬이 깨지던 것 수정. **CSS Grid `repeat(auto-fill,minmax(280px,1fr))`**로 다열 복원(뷰포트 무관, col 의존 제거) +
  이미지 `referrerpolicy="no-referrer"`(네이버 핫링크 우회) + 실패 시 **박스 유지·아이콘 플레이스홀더**(bi-image, 박스 안 숨김)
  + 카드 `overflow:hidden`(버튼 넘침 방지). 가드 test_v35_sourcing_grid(4) + test_v33_card_status·ai_sourcing_hub 갱신.
  전체 10411 passed. before/after: docs/screens/v35/sourcing-grid-{before,after}.png.
- ✅ **P1 검색창 크게·넓게 + 글자 위계 (Phase 323):** 소싱 키워드 검색창을 — 오버라인 '상품 발굴' 키커 + 큰 질문 라벨
  (1.12rem) + **돋보기 아이콘 프리픽스**(input-group-text bi-search) + **큰 입력**(min-height:54px·1.08rem 또렷) + CTA(54px)
  + 토큰 보더(제네릭 border-primary 파랑 제거). 가드 test_v35_search_box(2). 전체 10413 passed.
  before/after: docs/screens/v35/search-{before,after}.png. → **v35 완주**(랜딩 상단·소싱 그리드·검색창).

## 🟦 v34 브리프 (오너 2026-06-28 — "소싱 카드 확대·개인화·디자인 실집행 + before/after 캡처 의무")
- ★ **검수 규칙(상시): 앞으로 모든 PR에 before/after 스크린샷 첨부.** Playwright 미설치였으나 `pip install playwright`로 해결
  (브라우저는 /opt/pw-browsers 사전설치). 단 Bootstrap CDN은 에이전트 프록시가 403 차단 → 샌드박스 캡처는 npm으로 받은
  로컬 bootstrap.min.css를 페이지에 add_style_tag 주입해 실제 스타일로 촬영(앱 무변경). 스샷은 docs/screens/<ver>/.
- ✅ **P0 소싱 카드 확대 + P1 아마존 국가 드롭다운 (Phase 317):** AI소싱 국내 베스트셀러 카드 — 이미지 **원본비율
  contain**(240px warm-bg 박스, 잘림 0) + **데스크톱 3열**(col-lg-4, 큰 카드) + 제목 1.12rem(≥17px)·가격 1.32rem·
  버튼 ≥44px("소싱처에서 비슷한 상품 찾기"). 마켓 검색은 타오바오/1688/알리/테무 단일버튼 + **아마존 국가 드롭다운**
  (미국~인도 10개국, `_AMAZON_SEARCH_COUNTRIES`). `_sourcing_search_links` 이모지 필드 제거. 가드 갱신(card v34·amazon countries).
  전체 10396 passed. before/after: docs/screens/v34/sourcing-{before,after}.png.
- ✅ **P0 개인화 헤더 '내 작업공간' (Phase 318):** 콘솔 사이드바 브랜드 아래 **로그인 계정 패널** 추가 — 아바타(이니셜)·
  표시명/이메일·'내 작업공간 · {플랜}'(무료/플러스/프로). 컨텍스트 프로세서에 `account_plan`(billing_store.get_account,
  로그인 시에만·경량) 주입. 비로그인은 미노출. 데이터는 이미 user 스코프(인증 게이트 v29). before/after:
  docs/screens/v34/console-account-{before,after}.png. 가드 test_v34_account_header(3). 전체 10396 passed.
- ✅ **P0 개인 전용 작업공간(마이페이지 격상) (Phase 319):** /seller/me를 제네릭 부트스트랩(파랑 bg-primary 아바타·h4
  '마이페이지'·플랜/지표 0)에서 **에디토리얼 개인 작업공간**으로 — 오버라인 'MY WORKSPACE'+세리프 '내 작업공간'+금
  헤어라인, **청록 토큰 아바타**, **작업공간 KPI 스트립**(수집 상품/연동 마켓 N·M/내 소싱처/보유 토큰 — 전부 본인 스코프
  실데이터, 세리프 대형 console-stat-value+토큰 좌악센트, 각 카드 해당 화면 링크), **내 요금제 카드**(플랜 라벨·설명·
  free=업그레이드 CTA/유료=관리), 소셜/알림/계정 배지도 토큰화(bootstrap 컬러배지 제거). 라우트에 plan·token_balance·
  markets_connected/total·sources_count·collected_count 주입(전부 본인, 가짜 0 금지). 가드 test_v34_my_workspace(3).
  전체 10401 passed. before/after: docs/screens/v34/me-{before,after}.png.
- ✅ **디자인 실집행 — BI 분석 에디토리얼 격상 (Phase 320):** /seller/analytics를 제네릭(h3 'BI'·sans fs-4 매출 숫자·
  회색헤더 보더카드)에서 **대시보드/주문과 동형 에디토리얼**로 — 오버라인 '분석·BI'+세리프 '재고·판매 분석'+금
  헤어라인, **매출 3종 세리프 대형 KPI**(console-stat-value·토큰 좌악센트 teal/success/warn, '원' 단위 작게), 섹션
  카드(TOP20·재고알림·광고ROI·CS배송)도 border-0 shadow-sm+오버라인 금 라벨, 재고/품질 수치 토큰색(danger/warn).
  하드코딩 색 0(토큰 var만). 가드 test_v34_analytics_editorial(2). 전체 10403 passed.
  before/after: docs/screens/v34/analytics-{before,after}.png.
- ⏳ 다음: 디자인 실집행 추가(catalog·notifications 등 잔여 화면) · 랜딩 검수(before/after 캡처).

## 🟪 v33/마스터 브리프 (오너 2026-06-27 — v24~v33 통합 마스터, 1달 출시 로드맵)
- (1~4주차 대부분은 이번 세션에서 v24~v32로 완료됨 — 404·삭제영속·이력·토큰·전체수집·메타숨김·Mock·네이버·디자인·랜딩·버튼·아마존·활성화.)
- ✅ **3주차 3-5 소싱 카드 확대 + 상태값 한글화 (Phase 316):** 소싱 허브 국내 베스트셀러 카드 — 이미지 130→**180px**,
  제목 small→**1.06rem**(≥17px), 가격 **1.15rem**, 버튼 py-2 패딩·pc-lift 호버, 검색 링크 `{{ s.emoji }}` 2곳 제거(이모지 0).
  주문 상태값 **한글화**(orders.html: new→신규접수/paid→결제완료/preparing→상품준비중/shipped→배송중/delivered→배송완료/
  canceled→취소/returned→반품/exchanged→교환/refund_requested→환불요청), **EN 화면(current_lang=en)은 영문 유지**. CS 상태
  (cs_inbox/mobile/stats)는 이미 한글. 가드 test_v33_card_status(카드 확대·이모지0·KO/EN 분기). 전체 10395 passed.
- → **v24~v33 통합 마스터 완주.** 남은 건 오너 콘솔/키 작업(Render Starter·네이버 검색키·스마트스토어 IP·11번가·WC 키)·점진 디자인 확장.
- ✅ **3주차 3-4 전역 이모지·지구본 박멸 (Phase 315):** 셀러 콘솔/에러/파셜 전 사용자 템플릿의 이모지(🛒🛠📚💚👤🚪🔐📧🆘⭐ℹ️❌🧤✓)를
  **단일 라인 아이콘셋 bi-***(shop/tools/book/heart-pulse/person/box-arrow-right/shield-lock/envelope/life-preserver/star-fill/info-circle…)로 교체.
  topnav×2·404/500·markets_connect/guide·catalog·notifications·me·mobile_home·market_status·collect_preview·bookmarklet 전수.
  북마클릿 드래그 버튼 🧤→**'수집' 텍스트**(이모지 없는 북마크 이름). **bi-globe(지구본) 아이콘 7개 → bi-translate**(지구본 0).
  가드 test_v33_emoji_sweep(전 사용자 템플릿 이모지 0 파라미터화 + 핵심 chrome 라인아이콘). 전체 10392 passed.
- ✅ **3주차 3-3 토스트 비주얼 시스템 (Phase 314):** pcToast 전면 재설계 — bootstrap 컬러배경+이모지(✅❌⚠️ℹ️)를
  **네오-클래식**(먹 vault 배경·한지 텍스트·금 보더·유형 좌악센트 teal/orange/danger·**라인 아이콘 bi-***)으로. 우상단
  슬라이드-인(pcToastIn)+자동/수동 닫기, reduced-motion 정지. app.css `.pc-toast`(토큰 단일소스), 이모지 0. 버튼 위계는
  기존 토큰 컴포넌트(.btn-primary/.btn-cta/.btn-gold/.btn-ghost·로딩 setButtonLoading) 유지. 가드 test_v33_toast(4). 전체 10339 passed.
- ✅ **2주차 2-1 이미지 PDP 스코프 한정 (Phase 313):** 엉뚱한 이미지(추천·리뷰·푸터·타 상품) 혼입 차단 강화 —
  `_NON_PRODUCT_REGION_RE`에 review/comment/reply/qna/feedback/testimonial 추가, 신규 `_find_product_scope`
  (itemtype Product·product-detail/goods 컨테이너로 이미지 수집 스코프 한정, **보수적**: 이미지 2장+ & 비-상품영역 아닐 때만
  채택→ recall 보존, 못 찾으면 전체 폴백). `_collect_dom_images`가 스코프 내 img/source만 수집. 확장 `_kgpNonProductRe`도
  리뷰/댓글 추가, manifest 1.5.12→1.5.13. 가드 test_v33_image_scope(컨테이너 한정·추천/리뷰/푸터 0·폴백·보수적). 전체 10335 passed.

## 🟥 v32 브리프 (오너 2026-06-27 — "버튼 전수조사 + 삭제 영속성 + 벤치마크 + 디자인 실집행")
- ✅ **PART1 P0 일괄 삭제 영속성(재진입 부활) + 일괄 버튼 가짜성공 (Phase 308):** v30과 동형 — 삭제/일괄수정이
  exact `seller_id=_seller_id()`로만 매칭 → 별칭(user_id↔email) 불일치 시 **삭제 0건·수정 무변경**인데 낙관적 UI로
  성공처럼 보이고 재진입하면 부활. **수정:** ①`collect_history_store.delete`에 seller_ids(관용집합) 지원 + 시트·인메모리
  **양쪽** 삭제(시트 분기 early-return로 폴백행 못 지우던 것도 수정) ②`update`에 seller_ids 지원(스코프 헬퍼) ③7개 일괄
  버튼(카테고리/번역/그룹/정제/가격/상태/복제)의 get·update를 전부 `seller_ids=_seller_identities()`로(복제 새 행 append는
  본인 sid 유지) ④삭제 JS를 낙관적 제거→**서버 재조회(location.reload)**+삭제 0건 정직 경고(가짜 성공 0). E2E 가드
  test_v32_delete_persist(별칭 삭제 영속·타셀러 보존·인메모리 폴백·일괄수정 실반영) — CI 게이트. 전체 10319 passed.
- ✅ **PART2 출시 필수 버튼 실동작 검증 (Phase 309):** PART1 스코프 수정으로 일괄 버튼이 실제 커밋되게 된 뒤, 핵심
  버튼이 **진짜 동작**하는지 E2E로 못박음 — ①상품명 정제(금지어 실제 제거, 규칙 없으면 400 no_rules 정직) ②마진/가격
  (target_margin_pct 저장 + price_multiplier 실반영 100→110, 빈값 환산 금지 v31) ③카테고리 자동분류(실 code 반환).
  전부 별칭 스코프(저장 email·세션 user_id)에서도 실반영(가짜 성공 0). 가드 test_v32_part2_buttons(4). 전체 10323 passed.
  ※금칙어 사전 대량 확장(3천+)·번역 무료 N회 표기는 기존 정직 처리 유지, 사전 확장은 후속 데이터 작업.
- ✅ **PART3 콘솔 디자인 실집행 #1 대시보드 KPI 격상 (Phase 310):** "토큰만 바꾸지 말고 화면에 보이게" — 대시보드 KPI를
  **세리프 대형 숫자**(console-stat-value: var(--font-display)·clamp(2~2.7rem)·잡지 통계) + **오버라인 라벨**(console-kpi-label:
  대문자 자간·금) + **두꺼운 4px 보더→얇은 2px 토큰 악센트**(보라/인디고 하드코딩 → var(--teal/warn/danger/success)) +
  토큰 그림자(var(--shadow-lg)) + 헤더 아래 **금 헤어라인**(pc-hairline) + reduced-motion 가드. kw-mini-bars 잔여 보라도
  토큰화. 편집 폼은 이미 2열(col-md-8 에디터+이미지 사이드바)이라 구조 유지. 하드코딩 hex 0(토큰 var만). before/after
  명확(1.6rem 굵은숫자→세리프 대형·금 악센트). 가드 test_design_console_v32_part3(5). 전체 10328 passed.
  ※orders/markets 등 화면별 동일 격상은 v18 선례대로 점진 후속(저회귀).
- ✅ **PART3 #2 orders/markets 디자인 격상 (Phase 311):** 대시보드와 동일 에디토리얼 패턴 확장 — orders KPI 4종을
  `console-kpi-card`(세리프 대형 숫자·오버라인 금 라벨·얇은 토큰 좌악센트 teal/warn/success/danger) + 헤더 오버라인·금
  헤어라인, `⟳` 글리프→bi-arrow-clockwise(단일 아이콘셋). markets 헤더 오버라인 라벨. 가드 test_design_console_v32_part3b(2).
  전체 10328 passed. ※소싱 분석은 오너가 네이버 검색키 Render 설정 완료 — 단 변수명은 검색용 `NAVER_SEARCH_CLIENT_ID/SECRET`
  (로그인 OAuth `NAVER_CLIENT_ID/SECRET`과 다름) 확인 필요.
- ✅ **PART3 #3 수집이력 summary 격상 (Phase 312):** 수집이력 summary 카드 4종(총수집/오늘/도메인=세리프 대형 KPI+오버라인+토큰 좌악센트, 수집경로=오버라인 라벨)도 대시보드/orders와 동일 에디토리얼로. 가드 test_design_console_v32_part3b 확장(3). 전체 10330 passed.
- → **v32 완주**(PART1 삭제영속·일괄버튼 / PART2 출시필수 버튼 실동작 / PART3 콘솔 디자인 실집행: 대시보드·orders·markets·수집이력 격상, settlement/sourcing 등 점진 확장 중). 남은 건 오너 콘솔 액션.

## 🟧 v29~v31 묶음 (오너 2026-06-27 — 순서: v30 404→v31 P0 실값/메타→v29 토큰/디자인)
- ✅ **v30 P0 수집한 상품 클릭 404 회귀 (Phase 304):** 원인=목록(list_items)은 관용 식별자(seller_ids=user_id+email)로
  보여주는데 상세(`collect_preview_by_id`)·저장(`collect_preview_save`)은 **exact `seller_id=_seller_id()`**로 조회 →
  별칭(user_id↔email) 불일치 시 목록엔 보이는데 클릭하면 404. **수정:** 신규 `_get_owned_item(item_id)`(목록과 동일
  seller_ids 스코프) 단일소스로 상세·저장 통일 + 저장 update 쓰기가드를 항목의 실제 stored seller_id로 일치. 타 셀러
  404(누출 0) 유지. E2E 가드 test_v30_collected_detail(별칭 200/타셀러 404/4경로/저장) — CI 게이트(pytest) 등록. 전체 10301 passed.
- ✅ **v31 P0 상세·가격 실값 + 원본 메타/플레이스홀더 숨김 (Phase 305):** 증상=메타 price:""·currency:USD인데 편집화면엔
  KRW 46,094(빈 USD 임의 환산). 원인=collect_preview 편집기 프리필이 `price_original`(파생 numeric)을 **먼저** 채워 빈
  가격이 둔갑. **수정:** 프리필을 **실제 추출가(`_EXTRA.price`→`_ITEM.price`)만** 사용(price_original 제외), needs_check/
  빈값이면 **빈칸 + '가격 확인 필요'**(임의 환산/가짜 숫자 0). ②'수집된 원본 메타' JSON 패널 **관리자 전용** 게이팅
  (`session.user_role=='admin'`) — 일반 유저 raw 노출 0. ③상세 플레이스홀더를 마케팅 문구→짧은 힌트('비워두면 저장 안 됨'),
  저장값은 .value(빈칸이면 빈칸·필러 0). 가드 test_v31_real_values_meta(메타 admin게이팅·프리필 실값·플레이스홀더). 전체 10305 passed.
  ※JS 사이트(Temu) 서버 OG 한계의 인페이지 실값 추출은 확장(v16) 경로가 정석 — 편집화면은 빈값 정직 처리로 가짜 0.
- ✅ **v29 PART1 토큰 본인전용·상시이력 + 죽은 '발급 완료' 버튼 (Phase 306):** (a)(b)(c)는 이미 충족(list_tokens(user_id)
  본인전용·token_hash_prefix 마스킹·시크릿 1회·해시만 저장·상시 이력표[발급일/마지막사용/만료/상태]). **핵심 수정(d):**
  발급 모달의 '발급 완료' 버튼이 disabled인 채 남아 **클릭이 죽어 있던** 것 → 발급 성공 시 **'발급 완료 · 닫기' 모드로
  전환(재활성화)** + 클릭 시 `pcConfirm`(네이티브 confirm 금지 가드 준수)로 '저장했나요?' 확인 후 모달 닫고 `location.reload`
  (새 토큰이 마스킹 값으로 이력에 즉시 보임). 모달 재오픈 시 상태 초기화. 복사 버튼은 `navigator.clipboard.writeText` +
  execCommand 폴백 + 실패 시 정직 안내(Ctrl/Cmd+C). 가드 test_v29_tokens(5). 전체 10310 passed.
- ✅ **v29 PART2 랜딩 전면 재설계 (Phase 307):** "학생 과제물 → 진짜배기" — landing.html을 Apple식 스크롤 내러티브
  9섹션으로 재작성(히어로 다크 vault→문제·해결→작동 3스텝[데스크톱 sticky 핀]→기능 쇼케이스 4카드→수입/수출 레인→
  지원 마켓 증거→요금/무료시작→FAQ→최종 CTA→푸터). **이모지 0**(전부 bi-* 아이콘), **CSS 브라우저 프레임 목업**(평면
  텍스트 탈출), 스티키 블러 내비(스크롤 축소), IntersectionObserver 리빌+8px, 카드 호버, 토큰 단일소스(var(--*)·
  color-mix), reduced-motion 전부 정지. **정직성:** 사회적 증거는 지원 마켓명만(가짜 셀러/수집 수치 0), 요금은 '무료로
  시작'+요금제 보기(가짜 혜택 0). 보존: 외국인 지역배너(Choose your language·i18n/set), i18n EN/KO, /privacy·/terms·
  privacy-policy, For Beginners·/seller/start, '수집부터 마켓 등록'(title). 가드 test_v29_landing_redesign(이모지0·섹션·
  실데이터증거·CTA·토큰). 전체 10315 passed. ※Playwright 미설치로 라이브 스샷은 못 떴고 렌더200·구조·테스트로 검증(정직).
- → **v29~v31 묶음 완주**(v30 404·v31 P0 실값/메타·v29 토큰/디자인 전면). 남은 건 오너 콘솔 액션(스마트스토어 IP·11번가 키·WC 키).

## 🟩 v25~v27 통합 마스터 (오너 2026-06-26 — 순서: v24✅→v25P0→v27→v25P1→v26)
- ✅ **v25 P0 아마존 '전체 수집' 실제 상품만 (Phase 299):** 증상=전체선택 시 Amazon Music·광고(스폰서)·미디어
  카드까지 선택됨. 원인=어댑터가 s-search-result+/dp/+가격만 보고 스폰서/비-ASIN 위젯도 통과. **수정:**
  `_kgpAmazonCards`에 **유효 ASIN(`/^[A-Z0-9]{10}$/`, data-asin) 필수** + `_kgpAmazonSponsored()`(s-sponsored-label-text/
  sp-sponsored-result 등 클래스 기반) 제외 → 뮤직/앱/프로모(ASIN 없음)·광고 0 선택. 툴바에 정직한 '전체 N개 중 상품
  M개' 표기(`_kgpScannedCount`). manifest 1.5.11→1.5.12. 가드 test_extension_amazon_products_v25(ASIN 정규식 node 실검증).
  전체 10276 passed.
- ✅ **v27 네이버 검색 API 실데이터 (Phase 300):** 소싱 분석 '데이터 없음'을 **검색 API만으로** 실데이터화.
  `naver_shopping.search_domestic()`(items+total 동시 반환, 키 env 전용·미설정/실패=`{items:[],total:None}`·키 로그 0).
  `_build_sourcing_analysis`에 실데이터 2종 추가 — **국내 검색 결과 수**(전국 total) + **판매처(쇼핑몰) 수**(고유 몰=경쟁
  강도). 상품수/최저·평균가(기존 실데이터)와 함께. 검색광고(관심도/경쟁도)·해외직구·리뷰는 검색 API로 못 구해 None 유지
  (날조 금지). 미연결 시 전 수치 None(가짜 0 금지). 가드 test_v27_naver_sourcing(미설정 빈상태/실데이터 매핑/페이지 렌더).
  전체 10280 passed. 오너 액션: developers.naver.com 앱(검색) → NAVER_SEARCH_CLIENT_ID/SECRET을 Render Env에.
- ✅ **v28 OG 공유 카드 이미지 교체 (Phase 301):** 증상=공유 카드 텍스트는 정상인데 og:image가 옛 글러브로
  보임(실제 og:image는 v23부터 icon-512=브릿지였으나 정사각이라 소셜에 부적합 + 카카오/페북 캐시 잔존). **수정:**
  신규 `scripts/gen_og_card.py`로 **1200×630 OG 카드**(먹 vault + 브릿지 마크 + 'GOGA BRIDJ' 세리프 워드마크,
  마스터 단일소스에서 파생) → `src/seller_console/static/og-card.png` + 벤더 `assets/og/og-card-1200x630.png`.
  _base_app.html og:image/twitter:image를 og-card.png**?v=2**(캐시 bump)로 교체. 옛 글러브 생성 스크립트
  (gen_favicon_glove.py·gen_extension_icons.py) 제거(잔재 0). 가드 test_v28_og_image(1200×630·메타·서빙·글러브 스크립트 0).
  전체 10284 passed.
- ✅ **v25 P1 아마존 국가선택 확장 + 초보 활성화 퍼널 (Phase 302):** ①아마존 칩 드롭다운 10→**14개국**(싱가포르.sg/
  멕시코.com.mx/UAE.ae/브라질.com.br 추가) + 각 국가 **통화 표기**(USD/JPY/SGD/BRL…) + **선택 기억**(localStorage
  kgp_amazon_country — 마지막 국가를 버튼 라벨 '아마존 · 미국' + 메뉴 상단으로). ②활성화 퍼널: `compute_onboarding_state`에
  `collected_count` 옵션 추가(하위호환 — None이면 기존 3단계) → **수집→연동→소싱처→첫 업로드(🎯 아하-모먼트)** 4단계.
  대시보드가 본인 스코프 collect summary로 collected_count 주입. 거짓 성공 금지(편집은 추적 불가라 별도 단계로 안 만들고
  수집 설명에 '확인·편집' 포함). 가드 test_v25_p1_amazon_activation(국가/통화/기억 + 퍼널 4단계/아하/하위호환). 전체 10289 passed.
- ✅ **v26 네오-클래식 디자인 리프레시 (Phase 303):** "디지털 한지 위의 금속활자" — app.css :root에 v26 토큰 단일소스
  확장: 깊이(`--ink-2`/`--gold-soft`)·대형 세리프(`--display-2-size` clamp(44,7vw,84)/-0.025em)·`--space-10`(128)·금
  헤어라인(`--hairline-color`)·미세 그레인(`--grain-opacity` .035). opt-in 유틸 추가(.pc-display-2/overline/hairline/
  num/section/lift/link/enter) + **전역 미세 그레인**(body::before SVG fractalNoise, 이미지 의존 0) + 진입 페이드.
  prefers-reduced-motion에서 그레인·모션 전부 정지. 랜딩 히어로 헤드라인을 v26 토큰(대형 세리프)으로 교체(쇼케이스).
  기존 v18 --display-size(40/6vw/72)는 불변(회귀 0). 하드코딩 hex 0(토큰 var만). 가드 test_design_tokens_v26.
  전체 10294 passed. ※이모지 제거·화면별 적용은 v18 선례대로 점진 후속(저회귀).
- → **v24~v27 통합 마스터 완주**(v24 P0·v25 P0/P1·v27·v26 + v28 OG). 남은 건 오너 콘솔 액션(네이버 검색키·스마트스토어 IP·11번가 키).

## 🟦 v24 브리프 (오너 2026-06-25 — "수집 이력 버그 · 마켓 Mock 정리 · 초보 흐름 · 아이콘 최종")
- ✅ **아이콘 최종본 적용:** 오너 최종 마스터(현수교 2선 다리)로 교체, v=176/확장 1.5.11(아래 v23 파이프라인 재실행).
- ✅ **P0 수집 성공인데 이력 0 (Phase 298):** 원인=`collect_history_store.append`가 시트 쓰기 실패 시 `_in_memory`로
  폴백하는데 `list_items/get`은 시트만 읽어 폴백 행을 못 봄 → '수집 완료' 토스트(자기검증 get은 메모리 폴백으로 통과)인데
  이력·카운터 0(가짜 성공). **수정:** 신규 `_all_rows()`(시트+인메모리 합집합, id dedup) → list_items/get/summary/
  distinct가 저장 위치와 무관하게 같은 워커에서 즉시 봄. seller_ids 관용 매칭(user_id+email, v9)·자기검증·정직 502는 유지.
  가드 test_v24_collect_history_persist(시트 쓰기 실패→이력 1건 보임 재현 + 별칭매칭/타셀러 미노출). ※멀티워커 인메모리
  (GOOGLE_SHEET_ID 미설정)는 인프라 — 시트 설정 시 영속.
- ✅ **P0 마켓 하단 Mock 정리 (Phase 298):** markets.html에서 일반 유저에게 'Mock 모드'/'mock 데이터' 배지·문구·가짜
  KPI(쿠팡 45활성 등) 노출 제거. 섹션명 명확화 '**마켓별 상품 등록·동기화 현황**'. is_mock(실데이터 없음)이면 가짜 숫자
  대신 **친절 빈 상태**('아직 등록된 상품이 없어요 — 업로드하면 표시')+CTA. 허브 카드 활성/전체 수치도 mock이면 숨김.
  catalog 시트 컬럼 안내는 관리자 전용. 상단 연동 상태(연결됨/권한/오류, 실데이터)·컨트롤 센터는 유지.
- ✅ **P1 초보 흐름 (Phase 298):** 수집(`/seller/collect`)·수집이력 화면에 '다음 할 일' 한 줄(pc-status) + 다음 단계
  버튼(수집→수집한 상품→마켓 연동). 수집이력 빈 상태의 크롬확장 설치+수동수집 CTA 유지. 가드 test_v24_market_and_flow.
  전체 10272 passed.
- (오너 액션, 코드 아님) 스마트스토어 403 GW.IP_NOT_ALLOWED→네이버 허용IP에 74.220.49.7 등록 / 11번가 500→ELEVENST_API_KEY 발급·승인.

## 🟫 v21 브리프 (오너 2026-06-24 — "일괄 리브랜딩: 고가브릿지/Goga Bridj + 게이트웨이 아이콘")
- ★ 명칭 잠금: **서비스명=고가브릿지 / 영문 정식=Goga Bridj(e 없음) / 단축형=Bridj / 수집도구=고가수집기(Goga Collector)**.
  워드마크 GOGA BRIDJ(Noto Serif KR, 대문자·자간 넓게). 절대원칙: 거짓성공/회귀 금지·정직·**내부 식별자 함부로 변경 금지**.
- ✅ **P0 사용자 노출 문자열 일괄 치환(Phase 297):** 코고가네/KOHgogane→고가브릿지/Goga Bridj, 퍼센티→제거/고가브릿지,
  proxy-commerce(표기)→고가브릿지, 수집도구→고가수집기. 중앙 단일소스 `utils/branding.py` 기본값 교체(KOHgogane/코고가네
  →Goga Bridj/고가브릿지)로 brand_name 주입 전역 자동 전환 + 하드코딩 리터럴 스윕(템플릿 20+·확장 12·py 13). 확장 zip명
  kohgane-collector→**goga-collector**, manifest 1.5.8→1.5.9. PWA manifest name/short_name·sw push 제목·OG/워드마크·이메일
  제목·봇·SEO_SITE_NAME·API docs·export seller명·slack 상태 등 외부 노출까지 정리. **안전수칙 준수(내부 식별자 보존):**
  channels/percenty.py(실 PercentyExporter 채널)·proxy_commerce 네임스페이스(shopify metafield·logger)·order_webhook
  `"service":"proxy-commerce"`(health json)·env_catalog Render 서비스명·github.com/Kohgane URL·실도메인 kohganepercentiii.com
  ·kgp_*/KGP_* 스토리지키·DOM id·라우트·com.kohgane.* 번들ID는 **그대로 유지**. (dev CLI 설명·grafana ops 대시보드 제목은
  비-유저 내부툴이라 보류.)
- ✅ **P0 아이콘=게이트웨이(B) 적용 + 지구본/글러브 폐기(Phase 297):** 신규 `scripts/gen_gateway_icons.py`(cairosvg 미설치라
  Pillow로 favicon.svg와 동일 기하 4x 슈퍼샘플) — **먹(#1A1714) vault + 금(#C9A24B) 게이트웨이 아치 + 주황(#F5821F)
  키스톤**. favicon.svg(벡터 직접 작성)·favicon.ico(16/32/48)·apple-touch-180·icon-192/512·**icon-1024(App Store)**·확장
  16/32/48/128 PNG 전부 B마크로 재생성. 확장 인페이지 FAB 마크(KGP_GLOVE_SVG, 상수명 유지)도 글러브→게이트웨이로 교체.
  파비콘 캐시버스트 v=173→174(15개 템플릿). 보조 A(아치교)·글러브 C는 미사용. 가드 test_v21_rebrand + 기존 favicon/pwa 가드 갱신.
- ✅ **v22 공식 아이콘 자산 적용(오너 zip 제공):** v21에서 스펙대로 직접 제도했던 마크를 **오너 공식 자산으로 교체**.
  공식 게이트웨이(B)=먹 vault + 금 아치(그라데이션) + **청록 다리(span #119A8E)** + **둥근 주황 키스톤 점(#F5821F)**.
  공식 세트(B/A svg + icon-16~1024 PNG + ico + apple-touch)를 **repo에 벤더링(`assets/brand-icons/`, 단일소스·재현)** →
  `scripts/gen_gateway_icons.py`가 favicon.svg/ico(공식 16/32/48 멀티사이즈 합성)·icon-192/512/1024·apple-touch·확장
  16/32/48/128에 적용. FAB도 공식 마크(청록 다리 복귀)로. favicon 가드는 공식 마크 기준(청록 #119a8e 존재·aria
  'gateway'·대문자hex 소문자비교)으로 갱신. 전체 10266 passed.
- ✅ **v23 마스터 아이콘 전면 교체(오너 확정 마스터):** B 게이트웨이를 **신규 마스터(현수교 + 게이트웨이 아치 +
  주황 키스톤, 먹/금/청록)**로 확정 교체. **단일소스 한 장** `assets/brand-icons/icon-master-1024.png`에서 `scripts/
  gen_gateway_icons.py`가 전 사이즈 파생 — favicon.ico(16/32/48)·**favicon-16/32.png**·apple-touch-180·icon-192/512/
  1024·확장 16/32/48/128. favicon.svg는 마스터 래스터(128px) data-URI 임베드(스케일러블 선언 유지, 14KB 경량). _base/
  _base_app head에 PNG favicon 링크(16/32) 추가, 캐시버스트 v=174→175(전 템플릿), 확장 manifest 1.5.9→1.5.10. og:image는
  icon-512(=마스터) 자동 반영. 구 B/A svg 벤더 제거(단일소스=마스터). favicon 가드는 임베드 기준(data:image/png·aria
  bridge/gateway·globe 0)으로 갱신. 지구본 0. 전체 10266 passed.

## ★ 작업 기본 헤더 (v20 운영 규칙 — 오너 2026-06-23, 모든 후속 작업에 상시 적용)
> "무엇을 만들지"가 아니라 "어떤 도구를 켜고 작업할지". 절대원칙: 거짓성공/회귀 금지·정직·토큰 단일소스·경량·개발표기 비노출.
- **(design-sync 관련, 2026-06-23):** proxy-commerce는 컴포넌트 라이브러리가 아니라 Flask+Jinja+Bootstrap+app.css라
  /design-sync(컴파일 컴포넌트 업로드)는 그대로 안 맞음. 오너 결정="v18 토큰만 styles/tokens로, React 전환 금지,
  app.css :root 단일소스, 하드코딩 hex/px 금지, 회귀 없이". → app.css :root에 브랜드 음영 토큰(--teal-strong/hover·
  --orange-strong/hover·--gold-ink(-strong)·--on-accent) 추가, 컴포넌트 규칙의 브랜드 hex를 전부 var(--*)로 치환(값 동일,
  무회귀). 상태/회색 유틸색은 v18 브랜드토큰 범위 밖이라 유지. 가드 test_design_tokens_v18(브랜드 hex :root 밖 0).
  ※ DesignSync MCP 도구는 세션에 미로드(끊김) — 붙으면 토큰 styles.css 업로드 가능.
- **상시 디폴트 3종(해당 상황이면 자동 적용):**
  1. UI/프론트엔드 작업 → **frontend-design** 스킬 + v18 디자인 토큰 스펙. "제네릭 AI/과제물 룩" 제거(화면당 강조1·8px 그리드·이모지0).
  2. API/외부연동(쿠팡 WING·네이버 커머스API·Shopee·Shopify 등) 코드 작성/수정 → **context7**로 최신 실제 문서 대조 후 코딩(낡은 지식 추측 금지).
  3. 산출물(보고서·P&L·핸드오프·문서) → **doc skills**(Word/PDF/Excel/PPT)로 실제 파일 생성.
- **콘텐츠·마케팅:** claude-seo(리스팅/블로그/네이버 키워드+AEO, 금지어·광고규정 준수) · humanizer(로봇 톤 제거, 과장·허위효능 금지) ·
  social-media-skills/marketingskills(HIKOCO·브랜드 SNS, 채널 톤).
- **지식·자동화:** ai-second-brain/notebooklm(브리프 v2~ 위키화·검색) · agent-browser(WING/네이버/Shopee 포털 수작업 대행 —
  **단 로그인/API키/결제 등 민감화면은 사람이 직접, 자동입력 금지·확인 후 진행**) · higgsfield MCP(제품컷·광고 이미지/영상) ·
  notion(선택, 운영문서만).
- **제외/보류(검증 전 미설치):** caveman·slack·granola·perplexity·zapier·codex-plugin-cc·financial-services·claude-for-legal·
  gstack·superpowers·claude-skills(도메인 불일치/커뮤니티 임의코드 위험). 커뮤니티/서드파티 스킬은 검증 전 설치 금지.
- **⚠️ 현재 CLI 환경 가용성(정직 확인 2026-06-23):** frontend-design·context7·claude-seo·humanizer·doc skills·ai-second-brain·
  agent-browser 등 위 명명 스킬은 **이 Claude Code CLI 세션엔 미설치**(Unknown skill). higgsfield MCP는 연결됐다가 끊김.
  → 스킬이 설치되기 전까지는 **그 의도를 수동으로** 적용한다: UI=v18 토큰 직접 준수, API=문서 정밀 확인 후 코딩(추측 금지),
  산출물=실제 파일 생성. 명명 스킬을 켠 척(거짓 성공) 하지 않는다. 설치/가용해지면 자동 적용.

## 🟩 v19 브리프 (오너 2026-06-23 — "오류 안내 친절화 + 지구본 박멸·아이콘 단일화")
- 절대원칙: 추측 금지·거짓성공 금지·회귀 금지·정직·토큰 단일소스·경량·개발표기 비노출. 버전충돌 시 최신 우선.
- **진행 순서:** ①오류 안내 공통 처리기(수집/연동/업로드 — 쉬운 문장·인라인·재시도) ②지구본 제거+아이콘 단일화.
- ⏳ P0-1 오류 친절화: 실패 시 무슨일+왜+다음행동 한 줄(사람 말). undefined/스택/HTTP날것/env 금지(상세는 '?'/관리자 로그).
  실패 그 자리 인라인+재시도 버튼+도움말. 가짜 성공 0. 코드→쉬운문장 맵 공통 핸들러 전역 적용.
- ✅ **P0-1 오류 친절화 공통 처리기(Phase 296):** seller.js에 `kgpFriendlyError(raw)`(코드/패턴→쉬운 문장 맵, 무엇+왜+다음행동;
  undefined/스택/HTTP/env 대문자토큰/HTML 등 개발 메시지는 가리고 일반 안내로; 서버의 정직한 짧은 메시지는 존중) +
  `kgpInlineError(el,raw,{retry,help})`(실패 그 자리 인라인 + 재시도 버튼 + 도움말) + kgpEscapeForHtml. manual_collect
  (미리보기/일괄/업로드/현지화/저장)·collect_preview(업로드/사전검증/이미지/저장)·markets_connect(연결테스트/저장/해제,
  원문응답은 '자세히(고급)' details로 숨김)의 raw err.message/data.error 노출을 전부 친절 핸들러로 교체. 가짜 성공 0.
  가드 test_v19_friendly_errors(node로 매핑 실동작 검증). 전체 10254 passed.
- ✅ **P0-2 지구본 0(이미 충족·회귀가드):** favicon.svg/ico·apple-touch·icon-192/512·확장 16/48/128 PNG는 이미 글러브
  모노그램(v13 Phase278·v8 Phase269). head 아이콘 선언/매니페스트에 globe 0. javascript: 북마클릿의 Chrome 강제 지구본은
  불가피→북마클릿 이름 🧤 1글자 + 안내문 명시(v17). 회귀 가드(글러브/매니페스트/head globe 0) 추가.

## 🟧 v17 브리프 (오너 2026-06-23 — "개발안내 숨김·등록소싱처 칩·북마클릿 복원·진입 시 수집기 보장")
- 절대원칙: 거짓성공/회귀 금지·정직·토큰 단일소스·경량·**일반 유저에게 개발 내용 비노출**. 버전충돌 시 최신 우선.
- **진행 순서:** ①P0 api-status/개발안내 일반유저 제거(관리자 이동/숨김)+proxy-commerce 표기 제거 ②P0 앱에서 마켓 진입 시
  고가수집기 무조건 노출 보장 ③P1 등록 소싱처 칩 표시 + 북마클릿 복원/안내 페이지.
- ⏳ P0-1: api_status 화면/문구(GitHub/Render/Manual Deploy/JSON/25·67)는 개발용 → 일반유저 제거(관리자 전용 or 숨김),
  대시보드 등 api-status 링크 제거, proxy-commerce 표기 0.
- ⏳ P0-2: 수집 페이지 마켓/소싱처 칩 클릭→마켓 이동 시 도착 페이지에 수집기 보장(①도메인 허용목록 보장 ②진입 마커로
  유저 off여도 그 세션 노출 ③미설치 시 설치/북마클릿 유도). 유저 설정 소싱처 한정 원칙(v15) 유지.
- ✅ **P0-1 api-status 관리자 전용(Phase 291):** /api-status·/api-status/json·nav '/api/status'·manual_collect 'API 상태'
  버튼을 `_is_admin_user()`로 게이팅(비관리자=대시보드 리다이렉트/403/링크 미노출). api_status.html 'proxy-commerce →
  Environment' → '내 서비스 →'(표기 제거). 일반 유저 화면 개발안내 0.
- ✅ **P0-2 진입 시 수집기 보장(Phase 291):** 수집 페이지 마켓/소싱처 칩 href에 마커 `?kgpsrc=app`. content_script
  `kgpEntrySession()`(URL 마커→sessionStorage kgp_entry, SPA 이동에도 유지) → injectCollectButton/리스팅 게이트가
  진입 세션이면 FAB off·호스트 허용목록 무시하고 노출(앱이 띄운 마켓 한정). 미설치 시 북마클릿(보조) 유도. manifest 1.5.7→1.5.8.
- ✅ **P1 소싱처 칩+북마클릿(Phase 291):** manual_collect에 My Sources(list_sources) 칩(파비콘+이름, 마커 부착, '＋소싱처
  추가') 즉시 반영. bookmarklet.html에 '확장 vs 북마클릿' 비교표(설치/자동버튼/대량/적합환경) + 메인=확장 명시.
  가드 test_v17_collector_access(6). 영향테스트(phase128·sidebar·v10게이트) 관리자세션/게이트 갱신. 전체 10235 passed.

## 🟨 v18 브리프 (오너 2026-06-23 — "양방향 게이트 + 디자인 토큰 스펙 확정")
- 절대원칙: 거짓성공/회귀 금지·정직·**토큰 단일소스(하드코딩 hex/px 금지)**·경량. 버전충돌 시 최신 우선.
- **진행 순서:** ①PART B 디자인 토큰(app.css 단일소스) → 전 화면 적용 ②PART A 게이트(수입/수출 레인).
- ⏳ PART B 디자인 토큰: app.css 단일소스 — 컬러(--ink/cream/gold/teal/orange/text-*/bg/surface/border/상태/vault)·타이포
  (Noto Serif KR/Pretendard+Inter, --display clamp·h1~3·body)·간격(8px --space-1~9)·라운드/그림자·레이아웃(--sidebar-w 264)·
  모션. 화면당 강조1·이모지0·두꺼운보더0(여백+얕은그림자)·단일 아이콘셋(20px). 하드코딩 hex/px→토큰.
- ✅ **PART B 디자인 토큰 단일소스(Phase 292):** app.css :root에 v18 스펙 토큰 정의 — 컬러(--ink #1A1714/--cream/--gold
  #C9A24B/--teal #119A8E/--orange #F5821F/--text-*/--bg/--surface/--border/--success·warn·danger/--vault-*)·타이포
  (--font-display Noto Serif KR/--font-ui Pretendard+Inter, --display-size clamp(40,6vw,72)/--h1~3/--body/--caption)·간격
  (8px그리드 --space-1~9)·라운드/그림자(--radius-*/--shadow-*)·레이아웃(--sidebar-w 264/--content-max 1200)·모션(--dur-*/--ease).
  기존 --pc-* 는 v18 토큰을 var()로 참조(단일소스, 하위호환) → 전 화면 에디토리얼 럭셔리 팔레트 자동 반영(teal/orange 미세
  보정). 가드 test_design_tokens_v18(5). 전체 10240 passed. ※이모지아이콘 제거·타입스케일 화면별 적용·단일아이콘셋은 점진 후속.
- ✅ **PART A 양방향 게이트(Phase 293):** 신설 src/lane.py(LANES import/export 단일소스 — title/arrow/desc·lang·currency·
  sourcing·target_markets, default_lane_for(Accept-Language 비-ko=export·ko=import), get_lane(쿠키 우선)). order_webhook:
  `_current_lane()`+context_processor(current_lane·lane 전 템플릿 주입), `/lane`(게이트 2카드 — 추천 강조), `/lane/set`
  (레인+lang+currency 쿠키 실제 전환, 가짜분기 아님). lane_gate.html(v18 토큰만 사용). _base.html 탑바 '운영 방식 전환'
  링크, landing 히어로 '운영 방식 선택(수입/수출)' CTA. 가드 test_lane_gate_v18(6). 전체 10246 passed.
  → **v18 완료**(PART B 토큰 단일소스 + PART A 수입/수출 게이트). ※이모지/타입스케일 화면 스윕은 점진 후속.
- ✅ **v18 §7 컴포넌트 베이스라인(Phase 294):** app.css에 토큰 기반 베이스라인 추가 — 타입 스케일 유틸(.pc-display/.pc-h1~3/
  .pc-body*/.pc-caption, opt-in 점진적용)·8px 스택 유틸(.pc-stack-2~5)·버튼 radius var(--radius)·청록 포커스 링(focus-visible)
  ·입력 토큰 radius+teal 포커스·카드 얕은 그림자(두꺼운 보더 대신). CSS 단일소스라 화면별 수정 없이 전 화면 적용·저회귀.
  가드 보강. 전체 10247 passed. ※이모지 아이콘 전면 제거·단일 아이콘셋 교체는 화면 단위 후속(회귀 관리).
- ✅ **v18 이모지→아이콘셋 #1 영속 chrome(Phase 295):** _base.html 사이드바/탑바/드롭다운의 이모지(🛒📱☰👤🚪🛠️🆘✨)를
  단일 아이콘셋 bi-*(bi-shop/phone/list/person/box-arrow-right/tools/life-preserver/stars)로 교체. fb.cta i18n에서 ✨ 제거
  (버튼이 bi-stars 사용). 영향 테스트(admin_vs_seller_nav·emergency_header·responsive 햄버거) 아이콘 기준 갱신.
  가드 test_base_chrome_uses_icon_set_not_emoji. 전체 10248 passed. ※나머지 화면 이모지는 차근차근 후속.
- ✅ **v18 이모지→아이콘셋 #2 수집·마켓(Phase 295):** manual_collect.html(🛒📥🧩🌐✅📤⚠️→bi-cart/download/puzzle/
  globe/check-circle/box-arrow-up-right/exclamation-triangle, JS textContent는 텍스트만)·markets.html(🏪🔄🔌📖🔑✅⚠️❌💰🚫📋📭
  →bi-*, <option>은 아이콘 불가라 텍스트만, JS textContent 텍스트만) 이모지 0. 전체 10248 passed.
  ※collect_history/collect_preview/messaging/market_status/notifications 등은 차근차근 후속.

## 🟪 v16 브리프 (오너 2026-06-23 — "수집 정확도·공유 미리보기·토큰/관리자/소싱처")
- 절대원칙: 추측 금지(에러·누락은 재현/로그)·거짓성공/가짜필러 금지·회귀 금지·정직·토큰 단일소스·경량. 버전충돌 시 v16 우선.
- **진행 순서:** ①P0 수집 정확도(확장 인페이지 실값 추출·제품 스코프 한정·가격/이미지/상세/리뷰 실값, 필러0)
  ②P0 FAB JS에러(sendMessage) + 퍼센티 전역제거 + 관리자 패널 숨김(403) ③P1 OG 공유 브랜딩·토큰 이력·북마클릿설명·
  FAB on/off·소싱처 좌측메뉴·잔여 개발문구.
- ✅ **P0-1 수집정확도 1차(Phase 288):** 원인=og:description 등 사이트 공통 '마케팅 필러'가 상품 설명으로 저장·번역됨
  (Temu "쇼핑하여 절약을 시작하세요"). universal_scraper에 `is_filler_description()`(보수적·알려진 카피만, 오탐 최소)
  + OG/meta 설명 파싱에서 필러 제외 + `extract_reviews(html)`(JSON-LD Product.review 우선, 없으면 빈 리스트=가짜 금지).
  extension_api: 클라/스크래퍼 description 필러 제거(html 없어도), 리뷰 추출 저장, 가격 0/빈값 → `price_status:needs_check`
  (가짜 0원 금지). content_script extractProductMeta: 설명 섹션 요소 우선 + 필러 og 미전송. collect_preview에 '⚠️ 가격
  확인 필요' 정직 표기. 가드 test_collect_accuracy_v16(8). ※사이트별 어댑터 셀렉터(Temu/타오바오 PDD 정밀 스코프)는
  라이브 검증 필요 → 후속(추측 금지로 미하드코딩). manifest 1.5.4→1.5.5.
- ✅ **P0-2 FAB JS에러+퍼센티(Phase 288):** content_script에 `kgpExtAlive()`(chrome.runtime.id 유효성)+`kgpSendMessage()`
  가드 헬퍼 — MV3 확장 업데이트/재로딩 시 context invalidated로 "Cannot read properties of undefined (reading
  'sendMessage')" 나던 것 → 새로고침 안내로 정직 처리. handleFabClick·collectBulk 직접 호출을 헬퍼로 일원화.
  확장 전역 "퍼센티" 제거(README/build → 코고가네).
- ✅ **P0-3 관리자 패널(이미 충족·회귀가드):** 사이드바 링크는 이미 `_user_role=='admin'` 가드, 라우트는 v13 Phase 278
  before_request로 미로그인=로그인·비admin=403. 회귀 가드 추가(seller 세션 /admin/* 403 + 링크 미노출). 전체 10214 passed.
- ✅ **P1 공유 브랜딩+UX(Phase 289):** _base_app.html OG/트위터 정비 — og:description·og:image(icon-512 브랜드마크)·
  og:url·twitter:card 추가(공유 카드가 이름·소개·이미지로 뜸). 알림/봇 기본 표기 'Proxy Commerce'→KOHgogane/코고가네
  (export_manager·international_router·email_sender·slack·discord·bot/commands·telegram 테스트). FAB on/off — content_script
  KGP_FAB_ENABLED(chrome.storage.kgp_fab_enabled, onChanged 즉시반영) + popup 토글. 소싱처 등록(My Sources) 사이드바
  링크(/seller/sourcing/my-sources). 'GenericOgCollector 자동 사용' 등 개발문구 일반 카피화. 북마클릿 '뭔가요/언제'
  친절설명. manifest 1.5.5→1.5.6. 가드 test_v16_p1_branding_ux(6).
  ※shopify metafield namespace 'proxy_commerce'(내부 스키마)·api_status Render 서비스명(정확 안내)은 유지.
- ✅ **P1 토큰 페이지(Phase 289):** list_tokens(user_id)/revoke_token(user_id)로 본인 전용·마스킹(해시 앞부분)·
  발급일·마지막사용·스코프·상태(폐기 포함)는 이미 구현됨(확인). 추가: 날것 표기(Authorization: Bearer, collect.write
  등) '?' 툴팁 뒤로 + 본문 쉬운말, 권한 배지 한글화(상품 수집/카탈로그 조회/마켓 업로드, raw는 title). 가드 추가.
- → **v16 완료**(P0 수집정확도·FAB에러·관리자 / P1 OG브랜딩·퍼센티/proxy정리·FAB on-off·소싱처메뉴·잔여문구·토큰).
  전체 10222 passed. ※사이트별 PDD 정밀 어댑터(라이브 검증 필요)만 후속.
- ✅ **v16 후속 — PDD 스코프 혼입 방지(Phase 290):** 추측 금지로 사이트별 셀렉터는 미하드코딩하되, 의미기반
  영역 제외 휴리스틱으로 '다른 상품' 혼입 차단. universal_scraper `_in_non_product_region()`(조상 class/id가
  recommend/related/also-bought/sponsored/footer 등이면 제외, 최대 8단계) → `_collect_dom_images`에서 추천/연관/
  푸터 영역 이미지 스킵. content_script도 동일 `_kgpInNonProductRegion`로 확장 추출서 제외. manifest 1.5.6→1.5.7.
  가드 test_pdd_scope_v16(3). 전체 10225 passed. (Temu/타오바오 동적클래스 정밀 셀렉터는 여전히 라이브 검증 후속.)
- ✅ **i18n 화면 확장 #1(Phase 290):** STRINGS에 주문(마켓/상태/검색/일괄운송장/CSV…)·마켓(현황/동기화/가이드/연결/연결확인)
  키 ko/en 추가 + orders.html·markets.html 라벨 t() 외부화. en 쿠키 시 주문·마켓 화면 영어. ko 기본 동일(무회귀).
  가드 test_i18n_screens_v16(4). 전체 10229 passed.
- (확인) 수집한 상품 클릭 404 = 해결됨 → 회귀 가드만 유지.

## 🟦 v15 브리프 (오너 2026-06-23 — "수집기 노출·마켓연결·확장설치 친절화 + 글로벌")
- 제0원칙: 일반 유저는 아무것도 모른다 가정. 거짓 성공/날조 금지·회귀 금지·정직·토큰 단일소스·경량. 버전 충돌 시 v15 우선.
- **진행 순서:** ①P0(수집버튼 소싱처한정+줌대응+아이콘화 / 마켓연결 인페이지 / 확장설치 정리) ②For Beginners·스테퍼·로고+소셜4종
  ③디폴트 마켓 확장 ④글로벌·토큰·스토어.
- ✅ **P0-1 수집버튼 줌/아이콘(Phase 284):** content_script에 줌(Ctrl+휠)·리사이즈 시 고정 오버레이(FAB/바/배지)를
  뷰포트 안으로 재보정(kgpRegisterFixed/kgpClampFixed + debounced resize) + FAB max-width:min(82vw,300px). 확장 옵션
  소싱처 관리에 사이트 파비콘(s2/favicons, amazon.* 정규화). manifest 1.5.2→1.5.3. 가드 test_collect_button_zoom_v15(4).
- ✅ **P0-2 마켓연결 인페이지(Phase 284):** 오너 결정="인페이지 단계 + 발급만 새 탭". 우리 앱은 window.open/팝업 0(확인됨).
  markets_connect 각 카드를 명시적 3단계(①키 발급받기 ②붙여넣기 ③저장·연결테스트)로, 발급 딥링크만 새 탭('이 버튼만 새 탭'
  명시). 외부 발급 URL은 iframe 불가(마켓 차단)라 새 탭 유지. 가드 test_market_connect_inpage_v15(3).
- ✅ **P0-3 확장설치 '고가수집기'(Phase 284):** 다운로드 파일명 kohgane-collector→**gogasujipgi-v{ver}.zip**, 설치 페이지
  제목·단계 '고가수집기'. '왜 설치/왜 토큰' 초친절 비유 카드(도우미/열쇠). 페이지당 버튼 1개(v14 유지). '기존 수집기
  엔드포인트' 문구는 v14에서 이미 제거(전 템플릿 0 확인). 가드 test_ext_install_gogasujipgi_v15(4). 전체 10196 passed.
- ✅ **P1 로고클릭 홈·다크 스테퍼 완료표시(이미 v14 충족, 재확인):** 사이드바/탑바 브랜드는 이미 `/seller/`(→대시보드)
  링크. 온보딩 스테퍼는 renderStepper가 done[s.key]면 ✓(bi-check-lg)·.ob-step.done 녹색, done은 실제상태(autoDone:
  LOGGED_IN / MARKETS>0)로만 채움(가짜 체크 없음). → 추가 작업 불필요.
- ✅ **P1 디폴트 마켓 확장(Phase 285):** 확장 디폴트 소싱처에 대형 크로스보더 마켓 추가 — 아이허브(iherb.com)·DHgate·
  큐텐(qoo10)·메루카리(mercari.com)·라쿠텐(rakuten.co.jp, Rakuten Fashion 포함). content_script KGP_DEFAULT_SOURCES +
  options DEFAULT_SOURCES 동기화 + manual_collect 원클릭 행(파비콘). 어댑터 불필요(universal_scraper 휴리스틱 폴백).
  manifest 1.5.3→1.5.4. ※Taoworld·OPLE는 도메인 미검증이라 미추가(날조 금지) — 오너 정확한 URL 주면 추가.
  니치/브랜드(요시다카반·ZOZO·VVIC·SHEIN)는 유저 추가 전용 유지. 가드 test_default_markets_v15(3). 전체 10199 passed.
- ✅ **디자인 토큰 단일소스(이미 충족):** src/static/app.css :root에 75개 --pc-* 변수(색·간격·라운드·그림자·포커스·폰트,
  Phase 234). 추가 작업 불필요.
- ✅ **모바일 양대 스토어 패키징 경로(Phase 286 — 오너 "국내용 먼저"):** 도메인 루트 `/.well-known/assetlinks.json`
  (구글 플레이 TWA Digital Asset Links — env TWA_PACKAGE_NAME+TWA_SHA256_FINGERPRINTS, 미설정 시 [] 정직) +
  `/.well-known/apple-app-site-association`(iOS Universal Links — env IOS_APP_ID, 미설정 시 빈 details). 신설 mobile/
  (README 한국어 단계별 가이드: PWABuilder/Bubblewrap TWA→Play, Capacitor→App Store + twa-manifest.json·capacitor.config.json).
  PWA 매니페스트는 이미 스토어 요건 충족(아이콘192·512 maskable·standalone·share_target·shortcuts). 가드
  test_mobile_store_packaging_v15(4). 전체 10203 passed.
- ✅ **i18n 영어 1급 1차(Phase 287):** 신설 `src/seller_console/i18n.py`(t(key,lang)+STRINGS ko/en, 누락키=키반환 정직,
  미지원언어=ko 폴백). 컨텍스트 프로세서가 t·current_lang 주입(kgp_lang 쿠키 단일소스, 기존 /i18n/set 재사용).
  _base.html: `<html lang>` 동적, 탑바 언어 토글(한국어/EN), For Beginners 버튼·6 핵심 내비 라벨 t()로 외부화.
  → en 쿠키 시 핵심 화면 영어 1급 동작. 나머지 화면 문자열은 STRINGS에 ko/en 추가하며 점진 확장. 가드
  test_i18n_seller_console_v15(3). 전체 10206 passed. → v15 큰 줄기 완료(P0·P1·국내스토어·i18n 1차).
- ⏳ i18n 점진 확장: 대시보드/주문/마켓/온보딩 등 화면별 문자열 STRINGS에 추가(후속, 화면 단위 PR).
- ⏳ P1: For Beginners 크게·고정·on/off(v14 완료, 재확인) · 다크 스테퍼 단계별 완료표시(실제기준) · 로고 클릭→대시보드 ·
  소셜4종(v14 완료) · 디폴트 마켓 추가(Taoworld·iHerb·TEMU·OPLE·Rakuten Fashion…+아이콘, 니치는 유저추가) ·
  i18n 영어1급 · 디자인토큰 단일소스 · 모바일 양대 스토어 패키징.

## 🔴 작업 원칙 (오너 지시 — 2026-06-14)
- **추측 금지. 팩트로만 말한다.** 모르면 "모른다 / 확인 필요"라고 말하고, 검증한 것만 단정한다.
- 코드/문서/로그/실제 응답 등 **확인 가능한 근거**가 있을 때만 단정적으로 답한다.
- 헛다리(추측 기반 단정) 반복 금지. 화면·응답 원문 등 증거를 우선한다.

## 🟥 v9 브리프 (오너 2026-06-21 — "수집 성공인데 이력에 없음, 추적으로 끝장. 고친 척 금지")
- **P0 수집 추적(Phase 266):** 거짓 성공/추측 금지 → 상관관계 ID로 한 건 끝까지 추적.
  - 확장 `/api/v1/collect/extension`에 corr_id 로깅(수신 token_user_id·url → 저장 seller_id·item_id →
    자기검증 saved → 실패 시 502). collect_history 뷰에 식별자/총건수 로그.
  - **관용 식별자 매칭(핵심 수정):** 저장 seller_id가 user_id면 user_id로, email이면 email로 어긋나도 본인
    이력에 보이게 — `_seller_identities()`={user_id,email,기본키}로 list_items/summary/distinct/get + KPI 필터
    (collect_history_store에 seller_ids set 파라미터 추가). 타 셀러 누출 없음(전부 본인 값).
  - **재현 테스트(가드):** 확장 수집(token user_id=u1) → 세션 user_id=u1 이력에 +1 노출 보장 +
    email/user_id 별칭 관용 + 타셀러 미노출. 전체 10120 passed.
  - ※ 원인 확정은 오너 다음 수집 시 corr_id 로그로 어느 홉인지 증거 확보(현재 코드상 GOOGLE_SHEET_ID 있으면
    저장=조회 동일 시트, seller_id 별칭만이 유력 — 관용 매칭으로 방어). P1: 애플홈 '제대로'·외국인 지역배너.
- **P1 애플홈 '제대로'(Phase 267):** landing.html을 애플 규격으로 재작성 — 미니멀 중앙 내비(로고+소수항목+시작
  알약), 풀폭 scene 섹션 5개(한 섹션=한 메시지, 밝다 한지↔어둡다 먹 번갈아), 거대 세리프 헤드라인
  clamp(40px,6vw,72px) 자간 좁게, 한 줄 회색 서브, 큰 비주얼(이모지), 알약 CTA(주황 채움/청록 라인) 헤드라인
  바로 아래 중앙, IntersectionObserver 등장 페이드(prefers-reduced-motion 존중). 4-타일 그리드 폐기→섹션별 1메시지.
  보존: privacy/terms/seller/about/start·privacy-policy meta·For Beginners.
- **P1 외국인 지역/언어 배너(Phase 268):** order_webhook `_show_region_banner()`(Accept-Language 첫 언어가 ko가
  아니고 미선택·미닫힘일 때만), `_visitor_lang()`(kgp_lang 쿠키=en이면 en, 아니면 ko 기본). `/i18n/set?lang=`·
  `/i18n/dismiss` 라우트(쿠키 1년 기억). 랜딩 상단 슬림 배너(English/한국어/✕) — 외국인만, 한국인 미노출.
  랜딩 카피 EN/KO 실전환(가짜 드롭다운 아님 — 고른 값이 실제 EN 카피로 반영). → v9 완료(수집추적·애플홈·지역배너).

## ⬛ v14 브리프 (오너 2026-06-22 — "온보딩·마켓연동·확장설치 UX 정밀화+친절화, 퍼센티 전역제거")
- 제0원칙: 일반 유저는 아무것도 모른다 가정, 하나하나 세세히. 버전 충돌 시 v14 우선.
- ✅ **P0 모바일 드로어 닫기(Phase 281):** `.sidebar-overlay`에 base 규칙 없어(위치/배경 X) 바깥 탭이 안 먹던 버그
  → seller.css에 `position:fixed;inset:0;background;z-index:1040` + `body.kgp-drawer-open{overflow:hidden}`(스크롤 잠금).
  _base.html JS: openSidebar/closeSidebar 분리 + 오버레이 onclick 닫기 + ESC 닫기 + 왼쪽 스와이프 닫기.
- ✅ **P0 온보딩 정직화(Phase 281):** onboarding_wizard 이미 in-place(스텝퍼 고정·#panel 교체)였음. 버그 수정:
  ①새 탭(window.open _blank) 제거 → 같은 탭 이동 ②링크 클릭만으로 가짜 완료(markDone) 제거 → 완료는 실제 상태
  (autoDone: LOGGED_IN / MARKETS>0)로만 자동 체크 ③localStorage KEY v2로 옛 가짜-완료 폐기 ④intro에 '마켓 연동이란?'
  쉬운 설명 추가. 가드 test_v14_onboarding_drawer(5). 전체 10165 passed.
- ✅ **소셜 로그인 4종(Phase 282):** 신설 apple.py(Sign in with Apple — ES256 JWT client_secret, form_post 콜백,
  id_token 디코드; 키 미설정 시 비활성). views.py 4 provider 등록 + 콜백 GET+POST(request.values). login.html·온보딩에
  구글·네이버·카카오·애플 4버튼. 오너: 네이버·카카오·애플 콘솔 OAuth 등록. 가드 test_social_login_v14(6).
- ✅ **마켓연동 순차 스테퍼(Phase 282):** markets_connect에 '한 마켓씩' 순차 진행 스테퍼(연결되면 ✓ 자동체크,
  prev/next, '전체 보기' 토글, JS show/hide). 섹션(쿠팡 출고지 등)에 '이 항목은 {마켓}에만 필요' 스코프 명시(쿠팡 전용
  오해 해소). 개발 문서경로(LIVE_VERIFICATION_GUIDE) 노출 제거. 키 발급 딥링크·필드설명·필수표시는 기존 유지.
  가드 test_market_connect_stepper_v14(4). 전체 10175 passed.
- ✅ **확장 설치 단계화 + 퍼센티 제거(Phase 282):** extension_install.html을 키노트식 단계 위저드로 재작성
  (한 화면=한 단계, 단계당 버튼 1개, 이전/다음, 진행바). 복사 버튼 실동작(navigator.clipboard + pcToast 피드백,
  실패 시 안내). 빨간 날것 표기(chrome://extensions/manifest는 안내에 최소화·'?'·details로). '퍼센티' 전역 제거
  (collect_receiver/manual_collect/bookmarklet 카피 + woocommerce 운송장 노트 [코고가네]). manual_collect '기존 수집기
  엔드포인트' 개발노트 → 사용자 카피. ※channels/percenty.py는 실제 퍼센티 채널 연동이라 유지.
  가드 test_ext_install_wizard_v14(6). 전체 10180 passed.
- ✅ **For Beginners 고정 버튼 + 친절 카피(Phase 282):** _base.html에 모든 페이지 우하단 고정 '✨ 처음이신가요?'
  큰 알약(주황 btn-cta) + 바로 밑 작은 '가이드 버튼 숨기기' on/off(localStorage kgp_fb_hidden, 숨기면 작은 ✨ 재오픈
  버튼). manual_collect에 '상품 수집이란?' 한 줄 풀이 + '?' 툴팁. 가드 test_for_beginners_v14(3). 전체 10183 passed.
- ✅ **기본 마켓 로고 아이콘 + 니치 제외(Phase 283):** manual_collect 원클릭 마켓을 이모지→**사이트 로고**
  (google s2 favicons, onerror 폴백)로 표시 + 대형 크로스보더 마켓만(타오바오·T몰·1688·테무·알리·아마존),
  요시다카반·ZOZO·VVIC·SHEIN·라쿠텐 등 니치 기본 제외(v13 P1 — 확장 '소싱처 관리'에서 직접 추가). 테무 추가.
  가드 test_market_icons_v14(2). 전체 10185 passed. → **v14 완료**(드로어·온보딩·소셜4종·마켓순차·확장단계·For
  Beginners·퍼센티제거·로고아이콘).

## ⬛ v13 브리프 (오너 2026-06-22 — "관리자전용·재로그인버그·속도·모바일앱·글로벌·프로디자인·파비콘")
- 버전 충돌 시 v13 우선. 디자인 최우선('학교 과제물'→프로). 정직 데이터·회귀 금지.
- ✅ **P0 관리자 전용 게이팅(Phase 278):** admin_views.py에 `@admin_panel_bp.before_request` 단일 게이트 —
  모든 /admin/* (대시보드·products·orders·inventory·users·env·logs·diagnostics·**/admin/cs/***)가 미로그인=로그인
  리다이렉트·비admin=403. 기존엔 diagnostics만 보호되고 나머지·/admin/cs/*는 무방비였음(보안홀 수정). is_admin_session
  (user_role==admin 또는 ADMIN_EMAILS) 사용. 영향 테스트(admin_views/ui_smoke/cs_stats) admin 세션으로 갱신.
- ✅ **P0 재로그인 버그 가드(Phase 278):** 셀러 콘솔은 이미 단일 가드 `_check_auth()`(user_id/email) 일관 사용
  (establish_session이 동일 키 설정). 가드 테스트 추가 — 유효 세션으로 보호 페이지 10종 순회 시 로그인 리다이렉트 0.
  ※ 영구 고정은 오너가 Render `SECRET_KEY` 설정(미설정 시 재시작마다 세션 무효 — 이미 Sheets 영속 폴백 있음).
- ✅ **P0 파비콘 글러브·지구본 제거(Phase 278):** favicon.svg를 오빗-글로브→**글러브 모노그램**(먹#1a1714+금#c9a24b+
  청록#119a8e)로 교체, favicon.ico/apple-touch/icon-192/512 Pillow 재생성(신설 scripts/gen_favicon_glove.py).
  캐시버스트 v172→v173(전 템플릿). test_phase_163 글러브로 갱신. 기본 소싱처는 이미 대형마켓만(요시다카반 등 니치 제외, v10).
  - 가드 `test_admin_gating_v13`(4). 전체 10153 passed.
- ✅ **P1 프로 디자인 #1 — 개발 표식 제거 + 지구본 완전 제거(Phase 279):** 사용자 화면 'Phase NNN' 노출 제거
  (orders/markets/messaging 부제·landing 푸터 → 사용자 카피로, 관련 테스트 갱신). 확장 FAB/바/배지/알약 마크를
  오빗-글로브(KGP_GLOBE_SVG)→**글러브(KGP_GLOVE_SVG)**로 통일(파비콘과 동일) → 지구본 노출 0. manifest 1.5.1→1.5.2.
  가드 test_pro_design_v13(3). 전체 10154 passed.
- ✅ **P1 속도 #1(Phase 280):** _base.html에 상단 진행바(같은 출처 내비 클릭 시 애니메이션 → 체감 속도 피드백)
  + 내부 링크 프리패치(hover/focus/touch → `<link rel=prefetch>`, 같은 출처만, 1회). prefers-reduced-motion이면
  진행바 생략. app.css에 `.skeleton` 셔머 유틸(reduced-motion 정지). 백엔드 무변경·경량. (시트캐시·gzip·정적캐시는 v8 완료)
  가드 test_perf_nav_v13(4). 전체 10160 passed. ※부분 내비(htmx)는 리스크 커 보류 — 프리패치+진행바로 체감 개선.
- ⏳ 남은 v13: 프로 디자인 #2(에디토리얼 토큰·KPI 스트립·이모지 정리) · 글로벌 i18n+외국셀러 온보딩 ·
  모바일 PWA 스토어 패키징. (단계별 후속 PR)

## 🟫 v12 브리프 (오너 2026-06-22 — "AI 소싱 허브·AI 통합·라벨 가독성·근거기반 내비")
- 제0원칙: 디자인 최우선, 라벨 하나도 '이게 뭐지?' 들면 실패. 분석지표 날조 금지(없으면 '데이터 없음').
- ✅ **P1 라벨 가독성 + AI 두 기능 통합 + 내비 재편(Phase 276):** _base.html 사이드바 전면 리네임(직관 1~2단어):
  소싱 watches→소싱 관심목록, 후보 큐→수집 대기목록, 이미지 큐→이미지 처리 대기, 금지어·치환 규칙→금지어·단어
  바꾸기, 가격 정책 룰→가격 자동 규칙, 환율 영향→환율 반영 보기, 마켓 연결(키 설정)→마켓 연동(API 키 입력),
  API 키 발급 가이드→API 키 발급 방법, 통관고유부호→통관고유부호(PCCC) 조회, CS 메시징/자동응답/통합인박스→
  고객 메시지/자동 답변/문의 통합함, 카탈로그→내 상품(카탈로그). **AI 통합**: 핵심 메뉴 상단에 'AI 소싱·등록'
  (→/seller/sourcing) 추가, 고급에 'AI 소싱·등록' 그룹(AI 상품등록+키워드+관심목록+대기목록+변동알림). 그룹 재편
  (AI/내 상품/가격/마켓/주문·CS/분석·정산/설정), 핵심 상단·고급 접이식 유지(근거기반). 모든 href 보존.
- ✅ **P1 AI 소싱 허브 구현(Phase 277):** 신설 `src/sourcing/naver_shopping.py`(네이버 쇼핑 검색 오픈 API —
  NAVER_SEARCH_CLIENT_ID/SECRET, 키 미설정/dry-run/실패 시 빈 리스트=날조 금지). sourcing_hub 뷰에 국내 베스트셀러
  (실데이터 카드: 이미지·제목·가격·몰) + `_sourcing_search_links`(타오바오/1688/알리/테무/아마존 검색 딥링크 —
  국내 상품명으로 소싱처 바로 검색→확장 수집) + `_build_sourcing_analysis`(국내 상품수/최저·평균가/검색관심도/경쟁도=
  실데이터, 해외직구비율·리뷰지수=계산불가→None '데이터 없음'). sourcing.html 헤더 'AI 소싱·등록'+두 모드 탭
  (발굴/등록), 메인 CTA 'AI 상품 추천받기'(주황). 키 없으면 정직 안내(가짜 카드 0). 오너 액션: NAVER_SEARCH_*
  (네이버 개발자센터 오픈API)면 국내 베스트셀러 실표시.
  - 가드 `test_ai_sourcing_hub_v12`(7) + 내비 테스트 갱신(test_phase_161 라벨). 전체 10150 passed.
- → v12 완료(라벨 가독성·AI 통합·내비 재편·AI 소싱 허브).

## 🟩 v11 브리프 (오너 2026-06-22 — "아이콘 단일화·페이지별 버튼·정확 수집·업로드 실패 진단")
- 절대원칙: 거짓 성공 금지(특히 업로드)·정직 데이터·회귀 금지·경량. 일반유저는 코드/URL/env 몰라도 됨.
- ✅ **P0 수집 정확도(Phase 273):** ①무관 이미지 제거 — universal_scraper `_NON_PRODUCT_IMG_RE` 확장
  (flags/openingemail/supplier-public-tag/`.slim.`/pdf/doc/arrow/chevron/tracking/beacon/1x1 등) + `is_product_image`/
  `filter_product_images` 헬퍼 + width/height<100 아이콘 제외. content_script `_isProductImg` 동일 블랙리스트.
  extension_api 최종 이미지에 `filter_product_images` 적용(어떤 소스든 정제, 첫=대표). ②옵션 전부 — `_collect_dom_options`
  (보수적: `<select>` + 라벨 키워드(색상/사이즈/수량/color/size…) 스와치 그룹, 값 2+일 때만, 확신 없으면 빈값=정직)
  → parse_html 후처리로 options 비었으면 보강. extension_api extra에 `options` 저장(편집 프리필). ③가격 — merge가
  price 0/빈값일 때 스크래퍼 추출가로 보강(기존). 가드 `tests/test_collect_accuracy_v11.py` 4.
- ✅ **P0 버튼 자동 전환(Phase 274):** content_script kgpRefresh를 모드 오케스트레이터로 — kgpFindCards 카드 3+면
  목록(중앙 바만, kgpRemoveFab으로 FAB 숨김), 아니면 상세(kgpRemoveListing으로 바/배지 숨김, FAB만). 동시노출 0.
  kgpIsDetailUrl(/dp//gp/product/item.htm/offer/detail/g-/product/)로 메타없는 상세도 FAB. 4초 인터벌이 kgpRefresh로
  모드 재평가. manifest 1.5.0→1.5.1. ※지구본: 북마클릿 일반플로우서 제거됨(v10P1)+드래그아이콘 🧤(v8③), 확장 글러브
  단일아이콘(v8③) → 지구본 노출 0. 가드 test_extension_button_switch_v11(4).
- ✅ **P1 깔끔 유저뷰 + 업로드 정직 진단(Phase 275):** collect_preview에 깔끔 갤러리(#imageGallery 대표+썸네일, renderGallery)
  + raw 이미지 URL 편집은 `<details>고급`으로 숨김(옵션 표시 유지). 업로드 진단: token_missing 메시지를 '내 마켓 키를
  마켓연동 화면에 입력'(env MARKET_CRED_ENC_KEY와 구분 명시)로, 가격0 메시지 정직+원화환산 유도, collect_upload
  except가 실 사유 패스스루(가짜 일반실패 폐기). markets_connect에 '내 마켓 키 vs env' 안내 배너. dispatch는 이미
  per-market 실 API에러 패스스루(e2e가 핀). 가드 test_upload_diag_v11(4). 전체 10143 passed.
- → v11 완료(수집정확도·버튼전환·지구본0·깔끔뷰·업로드 정직진단).

## 🟪 v10 브리프 (오너 2026-06-22 — "지정 소싱처에서만·실제 제품만·선택정상화·개발자 노출 제거")
- 제0원칙: 일반 유저는 코드/북마클릿/env 몰라도 됨. "쓰기 편한가/보기 좋은가"만. 보이는 게 전부.
- ✅ **P0 지정 소싱처에서만 노출 + 실제 제품만 + 선택 정상화(Phase 271):** content_script.js —
  `kgpHostAllowed()`(기본셋 타오바오/티몰/1688/테무/아마존*/알리 + 사용자 커스텀, chrome.storage.local
  `kgp_sources`, `chrome.storage.onChanged` 런타임 즉시 반영), 비매치 사이트는 `kgpTeardown()`로 아무것도
  안 그림(FAB/리스팅바/배지 게이팅). 실제 제품만: 아마존 어댑터(`[data-component-type="s-search-result"]`)
  + 엄격 폴백(제목+가격+제품링크+이미지≥140 모두 + `_kgpInBadRegion`로 추천/푸터/캐러셀/광고/‘viewed’ 제외)
  → ‘N개 발견’=실제 수집 가능 수. 선택 배지/전체·선택 수집은 기존 로직(엄격 감지로 정상화). options.html에
  **🌐 소싱처 관리**(기본 토글+커스텀 추가/삭제), popup에 소싱처 배지+관리 링크. 코고가네 리브랜딩(먹/금/청록).
  manifest 1.4.8→1.5.0. 가드 `tests/test_extension_sourcing_v10.py` 6 + 전체 10131 passed. node --check 통과.
- ✅ **P1 북마클릿/개발자 노출 제거 + UI/UX(Phase 272):** 일반 유저 화면을 확장 일원화 — manual_collect/
  sourcing 허브/collect_history 빈상태 CTA를 '🧩 크롬 확장 설치' 주(主)로, 북마클릿은 '고급' 링크로 강등.
  bookmarklet.html: 상단에 '대부분은 확장 권장' 배너 + 제목 '북마클릿(고급)', 원시 `javascript:` 코드 `<pre>`를
  `<details>고급: 북마클릿 코드 보기(개발용)</details>`로 접어 기본 노출 0. nav '북마클릿'은 이미 고급 details
  안. MARKET_CRED_ENC_KEY는 이미 '?' 툴팁(숨김). 전체 10131 passed. → v10 완료(소싱처 게이팅·실제제품·노출제거).
- (전제) v9 수집 영속 버그가 함께 잡혀야 ‘수집됨’이 이력에 진짜 남음 — v9 관용매칭/추적 이미 반영(Phase 266).

## 🟦 v7/v8 추가 브리프 (오너 2026-06-21 — "렌더 env 다 했음, 나열순, v8 우선")
- **v8(우선):** ①속도(타이밍 측정→시트 캐시/배치, gunicorn gthread/gzip/에셋) ②마켓호출 Bluehost 릴레이
  (쿠팡/네이버 고정IP 경유, MARKET_RELAY_URL/TOKEN, 연결테스트 동일경로, Shopify/Woo는 직접) ③북마클릿 이모지
  이름(🧤만)+익스텐션/사이트 파비콘 코고가네 마크 교체.
  - ✅ v8 ①-a 응답 속도(Phase 263): gunicorn `gthread`+threads(I/O 동시성), gzip 응답 압축(after_request,
    텍스트류 600B↑, Accept-Encoding gzip시만 → 기존 테스트 안전), 정적 에셋 Cache-Control max-age=604800.
    요청 타이밍 로그는 기존(request_logger elapsed_ms).
  - ✅ v8 ①-b 시트 왕복 감소(Phase 264): collect_history_store에 요청 범위 read 캐시(flask.g, has_request_context).
    한 페이지에서 list+summary+distinct가 같은 시트 3회 읽던 걸 요청당 1회로. 쓰기(append/update/delete) 후
    _invalidate_cache로 무효화(요청 내 스테일 방지). 요청 컨텍스트 밖/인메모리는 직접 read.
  - ✅ v8 ② 마켓 고정IP 릴레이(Phase 265): 신설 `src/market_relay.py`(relay_request — MARKET_RELAY_URL+TOKEN
    설정+대상마켓일 때 Bluehost 릴레이로 POST, 미설정/비대상은 직접 호출 폴백. Bearer+HMAC). 쿠팡/네이버
    uploader의 `requests.request`를 relay_request(market=coupang/smartstore)로 교체. 배포물 `relay/market_relay_server_v8.py`
    (무상태 포워딩, host 화이트리스트, 키 미저장/미로깅) + README. 오너: Bluehost에 릴레이 올리고 그 IP를 쿠팡/네이버
    허용IP+SERVER_OUTBOUND_IP에.
  - ✅ v8 ③ 북마클릿 이모지 이름 + 확장 아이콘 코고가네 마크(Phase 269): bookmarklet.html 북마크 이름을
    '고가네 수집' 텍스트→**🧤 한 글자**(52px 정사각 버튼, 텍스트 없이 아이콘처럼)로. 정직 주석 — Chrome 특성상
    javascript: 북마클릿엔 기본 지구본이 뜰 수 있어 완전 브랜드 아이콘은 확장 권장. 확장 액션 아이콘
    16/32/48/128 PNG를 **글러브 모노그램(먹 #1a1714 배경+금 #c9a24b 글러브+청록 #119a8e 소맷동/궤도)**으로 재생성
    (신설 `scripts/gen_extension_icons.py`, 4x 슈퍼샘플) — 🧤·디자인토큰 통일. manifest 1.4.6→1.4.7.
    ※ 사이트 favicon.svg는 기존 오빗-글로브가 이미 코고가네 마크(test_phase_163이 색/디자인 핀)→유지(불변).
    → v8 큰 줄기 완료(속도·시트캐시·릴레이·북마클릿/아이콘). ⏳ 다음: v7 확장 UX.
- **v7:** 확장 상단바 토글/접힘 배지(끄면 구석 작게·청록/금 펄스·개수, 위치/상태 기억, 팝업 on/off), 단일 FAB
  우측 중앙 이동+드래그/기억, '전체 일괄수집' 코치마크 1회, 따라하기 재미(수집 도장/카운트업·위트카피·마일스톤).
  - ✅ v7 확장 UX(Phase 270): content_script.js에 공통 유틸 추가 — `kgpLSget/set`(위치·설정 localStorage),
    `KGP_RM`(prefers-reduced-motion), `kgpMakeDraggable`(드래그 이동+위치기억+클릭억제), `kgpEnsureStyles`
    (펄스/도장 keyframes, RM이면 미주입), `kgpCelebrate`(수집 누적 카운트업+마일스톤 10/50/100/300/500/1000 배지
    +위트카피, RM이면 토스트만). ①FAB 우측 '중앙'(top:120px→calc(50%-24px))+드래그/기억(kgp_fab_pos), 등장모션 RM 생략.
    ②리스팅 바: 접기(✕)→구석 '수집 열기' 배지(선택개수·청록 펄스, kgp_bar_pos 기억), `📌 자동/수동` 토글
    (kgp_bar_auto — 수동이면 새 목록 페이지는 배지로만 시작), 바도 드래그 이동(grip만, 버튼 제외). ③'전체 수집'
    1회 코치마크(kgp_coach_all). ④실제 성공(FAB resp.ok·bulk success>0)에만 도장+카운트업(가짜 축하 금지).
    manifest 1.4.7→1.4.8. README 방법4에 v7 사용법. node --check 통과, 확장 테스트 45 passed.
  → v7 완료. v8/v7 둘 다 큰 줄기 소진.

## 🟧 오너 최우선 원칙 (2026-06-21): "무조건 쉽고 간편"
- 결제·버튼·모든 UX가 쉽고 간편·간결·직관적이어야 함. 복잡/개발자틱 금지.
- 로그인 튕김은 절대 안 됨(아래 P0). 모바일 앱도 만들 예정 — 준비.
- 진행: 위에서부터 순서대로. 계획 짜서 실행.
- **계획(2026-06-21):** ①로그인 튕김(✅ Phase 257) → ②쉽고 간편 결제·버튼(✅ Phase 258 요금제·충전) →
  ③모바일 앱 준비(설치형 PWA + 모바일 주문 액션).
- **v6 마스터 브리프(2026-06-21):** "쉽고 편함 최우선"(3클릭 이내·화면당 버튼 1~2). P0=①모든 버튼 실동작 감사
  (죽은/가짜 버튼 0, 테스트 가드) ②일반유저 실제 API연동(발급 URL 딥링크 새탭+서버 IP 복사+실연결테스트)
  ③실 구글 로그인. P1=애플홈+퍼센티 디자인, For Beginners(✅v5), "?"숨김/네비간소화/About(✅v5).
  - ✅ v6 P0 마켓 원클릭 연동(Phase 259): markets_connect 각 카드에 발급 페이지 딥링크(주황 btn-cta 새탭,
    market_guide.guide_map — 네이버 apicenter/11번가 openapi URL 갱신) + 서버 아웃바운드 IP 복사 블록
    (SERVER_OUTBOUND_IP env 또는 ipify 1회조회·캐시, 쿠팡/네이버 허용IP용) + '?' 툴팁.
  - ✅ v6 P0 죽은 버튼 가드(Phase 260): `tests/test_no_dead_buttons.py` — 시드 핵심페이지(대시보드/수집이력/
    마켓/연결/요금제/About/start/가이드/모바일) 크롤 → 내부 링크 404/500 0 + 핸들러 없는 빈 앵커 0 (CI 가드).
    감사 결과 기존 죽은 버튼 0 확인(템플릿 href='#' 1건도 실 핸들러 보유).
  - ✅ v6 모바일 설치형 PWA(Phase 261): manifest(webmanifest+json) short_name 코고가네, 색 순흑#020010→먹#1a1714,
    start_url /seller/m, 상품수집/수집이력 shortcut. mobile_home에 '📲 앱 설치' 버튼(beforeinstallprompt, 안드로이드)
    + SW 등록. iOS는 더보기의 '홈 화면에 추가' 안내. 테스트 갱신(short_name/color).
  - ✅ v6 P1 애플홈 랜딩 리디자인(Phase 262): landing.html을 풀블리드 섹션(밝다 한지↔어둡다 먹 번갈아) +
    큰 명조 히어로(띄어쓴 한글 "수 집 부 터/등 록 까 지")+서브+CTA2(처음이신가요 주황/둘러보기 청록라인) +
    2열 기능 타일(수집/다듬기/등록/주문) + For Beginners 밴드 + 푸터. **개발자 카드(관리자/API/시스템) 제거**
    (일반 유저 랜딩에서 숨김). 보존: /privacy·/terms·/seller/·/seller/about·/seller/start·privacy-policy meta.
    → v6 큰 줄기 완료(로그인·결제·마켓연동·죽은버튼가드·설치형PWA·애플홈 랜딩).
- **쉽고 간편 결제(Phase 258):** 신설 `billing_store.py`(셀러 plan free/plus/pro + token_balance) +
  `/seller/billing`(요금제·충전 페이지, 깔끔 카드 + 1버튼 주황 CTA). free=즉시 전환, 유료=토스 결제
  (TOSS_CLIENT_KEY/SECRET_KEY) 설정 시에만 활성(가짜 활성 금지, 미설정 시 정직 안내). 활성 Plus/Pro면
  번역 무제한(bulk-translate가 billing_store.is_unlimited 확인). nav '요금제·충전' 추가.
- **로그인 튕김 근본해결(Phase 257):** SECRET_KEY 미설정 시 세션 서명 키가 워커/재시작마다 바뀌어 튕김.
  → 키 영속 우선순위 = ①SECRET_KEY env ②**Google Sheets `app_config`(GOOGLE_SHEET_ID 있으면 재시작에도
  동일 키 — 오너 추가설정 불필요)** ③컨테이너 /tmp 공유. Sheets 있으면 재배포해도 세션 유지 → 튕김 해결.

## 🎨 KOHgogane 브리프 v5 (UI/UX 전면 유저친화화 — 오너 제공 2026-06-21)
> 오너: "아직 너무 개발자 친화적. 유저친화적으로 가야 된다." 애플 키노트형 비기너 온보딩 중심.
- **팔레트 갱신(주황 부활):** 악센트 듀오 = 청록+**주황(#E8772E~#F5821F)**. 주황=큰/초대 CTA 전용(For Beginners/시작하기/
  구글로 시작/연동하기), 청록=브랜드·보조·링크·현재단계. 둘 다 절제·위계. app.css에 orange 토큰 추가.
- **For Beginners 키노트 온보딩:** 큰 "For Beginners·처음이신가요?"(주황) → 풀스크린. 좌측 세로 스텝퍼(현재단계 청록 강조,
  완료 체크) + 우측 큰 화면(화면당 메시지1+버튼1~2). 단계: 소개→사업자등록→**구글로 시작(실제 로그인)**→마켓연동(딥링크·실연결)→
  확장설치→첫수집·등록🎉. **각 단계가 실제 동작 수행(가이드 아님)**. 진행상태 저장·재진입.
- **개발자 설명 "?" 숨김:** env키/라우트/진단/암호화 문구 등 기본 숨김 → "?" 팝오버. 본문은 비기너 카피.
- **좌측 네비 간소화:** 40개 → 핵심 5~6(대시보드/상품수집/수집이력/주문/마켓연동/도움말) 노출 + 나머지 "고급 ▾" 접이식.
  현재 위치 강조. 삭제 아니라 숨김/그룹화(파워유저 유지).
- **실 구글 로그인 + 실 API 연동(P0):** 구글로 시작=진짜 /auth/google/start 뜸(오너 콘솔 게시 전제), API 키→실연결테스트→완료.
- **소개/About:** "코고가네란?" 애플톤 짧게, 랜딩+온보딩 1단계 공유.
- 순서: P0 실로그인/API → For Beginners 온보딩 → "?"숨김+네비간소화+About → 청록+주황 토큰.
- **진행:**
  - ✅ 네비 간소화 + 주황 CTA 토큰(Phase 252): app.css `--pc-color-cta`(주황 #ef7a22) + `.btn-cta`(주황 채움 큰 행동).
    좌측 nav 핵심 6개(대시보드/상품 수집/수집 이력/주문 관리/마켓 연동/도움말·가이드)만 노출, 나머지 35개는
    `<details class="adv-nav">고급 기능 더보기</details>` 접이식(현재 위치가 안에 있으면 JS 자동 펼침). 활성 링크
    보라→청록 그라데이션. 모든 링크 DOM 유지(테스트 통과).
  - ✅ For Beginners 키노트 온보딩(Phase 253): 풀스크린 `/seller/start`(onboarding_wizard.html) — 좌측 먹 스텝퍼
    (현재단계 청록·완료 체크) + 우측 큰 화면(화면당 메시지1+버튼1~2). 6단계: 소개→사업자등록→구글로 시작(실제
    /auth/google/start)→마켓 연동(실제 /markets/connect)→확장 설치(실제 /extension)→첫 수집(/manual-collect).
    각 단계 실제 동작 링크(가이드 아님), localStorage 진행저장·재진입, 로그인/마켓연결 자동 완료판정. 미로그인도 진입.
    대시보드+랜딩에 '✨ For Beginners·처음이신가요?'(주황 .btn-cta) 진입버튼.
  - ✅ "?" 개발자문구 숨김 + About 소개(Phase 254): `.pc-help`("?" 원형) + _base.html 전역 Bootstrap 툴팁 init.
    markets_connect 기술문구(MARKET_CRED_ENC_KEY·연결테스트 원리)를 본문→'?' 툴팁으로(본문은 '🔒 안전하게 암호화' 한 줄).
    신설 `/seller/about`(about.html, 애플톤 수집/다듬기/등록 3카드 + 누구를 위한 건가 + 시작하기 CTA), 랜딩 푸터+고급nav 링크.
  - ⏳ 다음(v5 남음): 주황 CTA 더 적용(로그인 구글버튼 등), For Beginners 서버측 진행저장(현재 localStorage). 
    (P0 실구글로그인 계정선택=오너 콘솔 '프로덕션 게시' 사안.) — v5 큰 줄기 거의 완료.

## 🔑 검증된 환경/핸드오프 (오너 제공 — 누적, 두 번 묻지 말 것 / 2026-06-20)
> 오너 지시(2026-06-20): "업데이트되는 정보는 핸드오프에 저장하고 두 번 일 시키지 마라."
> 새로 검증된 사실은 여기에 즉시 누적 기록한다. (세션 컨텍스트는 휘발되므로 이 파일이 단일 진실원천)
- **Render 환경변수 (오너가 설정함, 검증됨):**
  - `GOOGLE_OAUTH_CLIENT_ID` = 설정됨, `GOOGLE_OAUTH_CLIENT_SECRET` = 설정됨 (둘 다, 2026-06-20 오너 확인).
    → 구글 로그인 `is_configured`는 True여야 정상. 그런데도 일반유저 로그인 실패 보고됨 → 콜백/콘솔 redirect_uri 쪽 조사 필요(아래 진행).
  - 카카오·네이버 OAuth = 설정됨(로그인 창 정상으로 뜸). 카카오만 되던 과거 상태에서 진전됨.
- **KOHgogane 브리프 v3/v4 추가분 (오너 제공 2026-06-20):** v2 로드맵에 이어붙이는 추가 작업.
  - **v3:** P0-1 로그인 튕김(SECRET_KEY 멀티워커 안정), P0-2 "수집 N" vs "이력 0" 불일치(seller_id 격리),
    P1-3 CTA 가시성(청록 Primary/금 Secondary 위계), P1-4 번역 무료 20회+이후 구독/토큰, P1-5 퍼센티 기능 포팅
    (엑셀 일괄수집·그룹관리·금지어/치환·이미지편집 UI·통관고유부호·장부·애널리틱스 노출·직원계정), P1-6 모바일 PWA(수집+주문).
  - **v3 P1-6 모바일(Phase 256):** 신설 `/seller/m`(mobile_home.html) — 하단 탭(수집/주문/더보기) 앱셸, 먹 토탑+BETA.
    수집탭=URL 붙여넣기→/collect/quick + 최근 수집 카드(썸네일). 주문탭=OrderSync KPI+최근주문(미연동 0). 더보기=
    For Beginners/마켓연동/데스크톱/About + 홈화면추가 안내. 모바일 토탑에 '📱 모바일 앱'(주황) 진입. share_target 기존.
  - **v4:** P0 가짜성공 박멸(확장 수집 토스트 정직화+저장 자기검증+seller_id 단일키+단일/리스팅 판별 — Phase 244 완료),
    P1 수집버튼 리디자인(먹+금+청록 글로브, 단일 FAB 우측상단부 이동, 네이비+주황 폐기 — ✅ Phase 255).
  - **v4 P1 완료(Phase 255):** content_script FAB/리스팅바/배지/재오픈알약을 먹(#1a1714) 매트+금(#c9a24b) 링+청록
    (#119a8e) 악센트 글로브로 리디자인(네이비+주황 폐기). 단일 FAB 우하단→우측 상단부(top:120px). 라벨 코고가네
    수집+세리프 캡션. 리스팅바 버튼 위계(전체수집=청록채움/선택수집=금아웃라인/전체선택·해제=고스트). manifest
    name 코고가네 수집기·1.4.5→1.4.6. background/content 문자열 코고가네 리브랜딩.
  - **진행 상황(P0 우선):**
    - ✅ v3 P0-2 + v4 P0(Phase 244): 대시보드 '오늘 수집' KPI를 seller_id로 격리(`get_today_kpi(seller_id)`→
      `build_kpi_widget`/`build_all_widgets`/`_get_widgets(_seller_id())`) → 이력 리스트와 카운트 일치(가짜 카운트 박멸).
      확장 수집(`/api/v1/collect/extension`) 저장 자기검증(append 후 같은 seller_id로 get 재조회) → 실제 저장됐을 때만
      ok=true, 실패 시 502 정직(가짜 성공 금지). 응답에 item_id 추가. v3 P0-1 로그인 튕김: SECRET_KEY 미설정 시
      워커마다 다른 임시키→세션 무효화였음 → 컨테이너-로컬 파일(`/tmp/kohgogane_session_secret`, O_EXCL)로 모든 워커가
      동일 키 공유(즉시 튕김 방지). **영구 고정은 오너가 Render에 `SECRET_KEY` 설정 권장.**
    - ✅ v3 P1-3 CTA 가시성(Phase 245): `app.css` 버튼 위계 토큰 강화 — `.btn-primary`=청록 채움+굵게(700)+
      hover lift+청록 글로우(화면당 1개 핵심행동), `.btn-outline-primary` 진한 청록, 신설 `.btn-gold`(금 아웃라인
      Secondary)·`.btn-ghost`(Tertiary). CSS만 — 전 화면 .btn-primary 자동 강조.
    - ✅ v3 P1-4 번역 무료20+과금(Phase 246): 신설 `translation_usage.py`(셀러별 free_used 카운터, Sheets+인메모리,
      `TRANSLATION_FREE_LIMIT` 기본20). `/seller/collect/bulk-translate`가 무료 한도 내에서만 실 번역, 초과분은
      차단(blocked)+구독/충전 안내. 정직: 실제 번역된 건만 차감(stub/키없음은 차감·차단 안 함). `TRANSLATION_UNLIMITED=1`
      훅(추후 구독 연동). 수집이력 UI에 '무료 번역 N/한도 남음' 표시. ※ 토큰 차감/결제는 미연동(정직 안내)—후속.
    - ✅ v3 P1-5 퍼센티 포팅 #1 그룹관리(Phase 247): 신설 `collect_groups.py`(셀러별 그룹 CRUD, Sheets+인메모리).
      라우트 `/collect/groups/create|delete`, `/collect/bulk-group`(item_ids→extra.group_id, group_name 신규생성/해제).
      수집이력에 그룹 필터(?group=) + '🗂 그룹 지정' 버튼/모달(기존선택·새그룹·관리삭제). 셀러 격리.
    - ✅ v3 P1-5 포팅 #2 금지어/치환(Phase 248): 신설 `word_rules.py`(셀러별 banned[]+subs[{from,to}], Sheets+인메모리),
      설정 페이지 `/seller/listing/word-rules`(+nav), 저장 `/word-rules/save`, 일괄 `/collect/bulk-clean`
      (선택 제목에 치환→금지어제거 적용, 규칙 없으면 400+안내). 수집이력 '✨ 상품명 정제' 버튼.
    - ✅ v3 P1-5 포팅 #3 이미지편집UI(Phase 249): `POST /seller/media/process-image`로 image_pipeline.process_image
      연결(워터마크 제거·리사이즈·WebP·CDN 재호스팅). 편집 페이지 이미지 행마다 '🧹' 정제 버튼→처리 URL로 교체.
      정직: CLOUDINARY_* 미설정/처리 미적용 시 원본 유지+안내(가짜 호스팅 URL 금지). ※실제 재호스팅은 오너가
      Render에 CLOUDINARY_* 설정해야 동작(Phase 207).
    - ✅ v3 P1-5 포팅 #4 통관고유부호(Phase 250): 신설 `pccc_store.py`(셀러별 고객 PCCC CRUD+검색, Sheets+인메모리,
      P+12자리 형식검증). 페이지 `/seller/customs/pccc`(+nav '통관고유부호') 입력폼·검색·목록·삭제. 형식 안 맞으면
      저장은 하되 경고(정직). 개인정보 주의 안내.
    - ✅ v3 P1-5 포팅 #5 장부/애널 노출(Phase 251): 기존 settlement_report(`/seller/settlement`)를 '장부·정산'으로
      프레이밍 + nav 노출(운영 그룹). 실 주문 KPI(OrderSyncService.kpi_summary, 미연동 0 정직) 추가 + BI 분석/마진
      계산기/CSV·Excel 링크. (BI 분석 /seller/analytics는 이미 nav에 있음.)
    - ⏳ 다음: 퍼센티 포팅 직원계정(후순위). 그리고 멀티워커 이력 영구화(옵트인), 모바일(P1-6), 수집버튼 리디자인(v4 P1).
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
      - ✅ chunk5 — 일괄 상태변경/복제(Phase 241): `POST /seller/collect/bulk-status`(ok/archived),
        `POST /seller/collect/bulk-duplicate`(복제본 새 항목+'(복제)' 접미). UI '📦 상태'(활성/보관 모달)·'📋 복제'
        버튼. archived 배지(📦 보관) 렌더. (셀러 격리)
      - ✅ chunk6 — 검색/정렬/상태필터/페이지당(Phase 242): collect_history 뷰에 q(제목·도메인·URL),
        status(활성/보관), sort(최신/오래된/가격↑↓/제목), per_page(20/50/100)+page 페이지네이션. 필터바 확장 +
        하단 페이지네이션 + 결과없음 안내(필터 인지). → §3 수집상품 일괄관리 **완료**.
    - ⏳ §4 온보딩 위저드 진행 중:
      - ✅ chunk1 — 사업자등록 가이드(Phase 243): 신설 `/seller/guide/business`(guide_business.html) —
        사업자등록→통신판매업 신고→구매대행 유의 3단계 클릭-스루 + 공식 딥링크(홈택스/정부24/공정위/관세청) +
        체크리스트(localStorage) + **면책**(법·세무 변동, 전문가 확인). nav '사업자 등록 가이드' 추가.
      - ⏳ 다음: 확장 설치 위저드 보강 → 마켓 연동 위저드(딥링크) → 온보딩 허브(대시보드 진행카드 확장,
        기존 onboarding.compute_onboarding_state 3스텝 → 사업자/확장/마켓/첫등록으로).


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
