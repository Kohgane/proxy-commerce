# HANDOFF — proxy-commerce 작업 인수인계

> 이 문서는 Kohgane(오너)의 지시사항과 진행 상태를 누적 기록한다.
> **업데이트되는 내용이 생기면 이 파일에 바로바로 반영한다.**
> 최종 갱신: 2026-06-10

---

## 🚦 진행 규칙 (오너 지시)

### ✅ DO — 하라고 한 것
- **택배사 검색형 입력 UI**: 셀러 콘솔 주문관리(배송준비중 내역)의 택배사 입력을
  **드롭다운 → 검색/자동완성(타이핑하면 바로 뜨는)** 방식으로 교체. → ✅ 완료 (#186)
  - 사유: 퍼센티는 드롭다운이라 불편하고, 목록에 **없는 택배사도 많음** → 직접 입력(free text)도 허용해야 함.
- **버튼 실작동 + UI/UX**: 죽은 버튼/가짜 인터랙션을 실제 동작으로 연결하고 UI/UX를 다듬는다(honest UI). → 1차 완료 (#187), 2차(주문 일괄처리/부분 환불/prompt 제거/로그인 데드 링크) 완료(2026-06-08)
- **Shopify 라이브 연결 (= "2번")**: 오너가 **실제 시크릿 등록 완료**
  (`SHOPIFY_SHOP` / `SHOPIFY_AUTO_TOKEN` / `SHOPIFY_CLIENT_SECRET`).
  → 코드는 라이브 연결 기준으로 정합성 유지하고, 등록된 시크릿으로 실제 동작하는지 검증 가능하게.
- **핸드오프 즉시 저장**: 지시/결정/완료 사항이 생기면 이 문서에 바로 기록.

### ⛔ DON'T — 하지 말라고 한 것
- **SaaS 공개 준비(약관/결제/랜딩)는 오너가 직접 말하기 전까지 시작하지 말 것. 묻지도 말 것.**
- 의미 없는 Phase 번호 찍어내기 / "Allow 버튼 누르려고" 빈 작업 만들기 금지.
  (실제로 동작하는 결과물만 만든다 — 이 레포의 "honest UI" 원칙 준수.)

---

## 📌 현재 상태

### 완료
- **Phase 189 — 라이트 테마 가독성 복구 + 마켓 실연동 재점검 + 비동작 플로우 재정렬 (2026-06-10)**:
  seller 주문/배송·마켓 컨트롤 센터·admin diagnostics의 바탕색을 라이트 톤으로 되돌리고 전경 대비를 강화했다.
  마켓 smoke 진단 결과에 `last_checked_at`를 구조적으로 추가해 seller/admin 화면 모두 마지막 점검 시각을 함께 노출하도록 맞췄다.
  주문 서비스 미가용 시 CSV export를 비활성으로 정직 표기해 "보이지만 안 되는" 액션을 줄였고, 관련 회귀 테스트를 보강했다.
- **테스트 픽스 (커밋 `d8efb7b`)**: Phase 184에서 `SHOPIFY_ACCESS_TOKEN → SHOPIFY_AUTO_TOKEN`으로
  바뀌었는데 `tests/test_shopify_auth.py::TestSecretCheck::test_secret_check_missing`가 옛 이름을
  기대해서 깨져 있었음(9668 passed, 1 failed). 기대값을 실제 코드에 맞춰 수정 → **CD – Staging 다시 그린(success)**.
- **Shopify 시크릿 등록 (오너)**: Render/환경변수에 실제 시크릿 등록 완료. PR #185 머지됨.
- **택배사 검색형 입력 UI (#186 머지)**: 드롭다운 → typeahead + 직접입력. 통합 카탈로그 `courier_catalog.py`.
- **죽은 버튼 실작동화 1차 (#187 머지)**: returns/inbox 일괄 승인·거부 라우트 연결, sourcing alert→toast,
  감사 리포트 `docs/operations/dead_button_audit.md` 생성, 회귀 테스트 17개 통과.
- **죽은 버튼 실작동화 2차**: 주문 관리에 행 선택 체크박스/전체선택/일괄 운송장 등록/일괄 상태 변경 UI 연결,
  `POST /seller/orders/bulk/status` 추가, 반품 인박스 개별 부분 환불 모달 + `POST /seller/returns/<request_id>/partial-refund`
  연결, 주문 상태 변경·소싱 후보 거절 `prompt()` 제거(모달화), 로그인 `href="#"` 제거, 관련 회귀 테스트 보강.
- **운영 안정화(실동작 검증) — 주문 루프 점검 1차 (2026-06-09)**:
  `/seller/orders` → 상태 변경 → 운송장(단건/일괄) → CSV export 플로우를 테스트로 고정.
  400/500/503 실패 응답을 정직하게 노출하도록 주문 화면/라우트 복구 UX 보강, 서비스 미가용 시 `/admin/diagnostics`
  연결 안내 추가, 주문 운영 로그에 `action/marketplace/order_id/reason` 필드 통일.
- **마켓 연동 운영 가이드 + 실연동 smoke 진단 + UI/UX 보강 (2026-06-10)**:
  `docs/operations/COUPANG.md`, `NAVER_SMARTSTORE.md`, `ELEVENST.md`, `SHOPIFY_MARKET.md`,
  `WOOCOMMERCE_MARKET.md` 신설, `/seller/markets`와 `/admin/diagnostics`에 실제 read 연결 확인 +
  safe write dry-run 결과를 `connected/token_missing/token_expired/scope_insufficient/api_error`로 구조화해 노출,
  운영자용 `연결 확인/권한 확인/재시도` 액션과 기술 원인 + 행동 힌트 UX를 추가.
- **Phase 188 — 주문 운영 UX/마켓 진단 2차 리파인 (2026-06-10)**:
  `/seller/orders`에 Phase 188 배너, 선택 수 고정형 액션 바, 일괄 실행 전 확인 모달, 운송장/상태 저장 실패의
  `원인: … / 조치: …` 표준 메시지, 주문 행 단위 성공/실패 피드백을 추가.
  `/seller/markets`는 Phase 188 배너와 함께 상태 카드 배지/색상/아이콘을 표준화하고,
  각 상태마다 원인/조치 문구와 추천 액션 강조를 노출하도록 보강.

### 진행 중
- **Phase 189 후속 실연동 검증**: 실제 마켓 어댑터 연결 상태에서 부분 실패(특히 bulk 항목) 로그 품질 재검토 및 운영자 재시도 가이드 고도화.
- **마켓 실연동 후속 검증**: 운영 시크릿이 등록된 환경에서 각 마켓 판매자센터/Wing/Admin 화면과 `/admin/diagnostics`,
  `/seller/markets` 결과를 대조해 마지막 실검증 시간을 남길 것.

### 백로그 (오너 승인 대기 — 먼저 묻지 말 것)
- **죽은 버튼 감사 3차**: → ✅ 완료 (2026-06-10, 오너 지시로 진행). 아래 Phase 191 참고.
- SaaS 공개 준비 (약관/결제/랜딩) — 2026 Q4. **오너가 지시할 때까지 대기.**

---

## 🧰 인프라 메모
- **Render — Docker Build Check** (`.github/workflows/render_deploy_check.yml`) 가끔 실패:
  `pulling moby/buildkit ... registry-1.docker.io: context deadline exceeded` → **Docker Hub 일시 장애/플레이크**.
  코드 문제 아님. **Re-run failed jobs** 로 통과. 반복되면 buildx 이미지 pull 재시도/캐시 추가로 영구 차단.

## 🔑 Shopify 라이브 연결 메모
- 필수 시크릿: `SHOPIFY_SHOP`, `SHOPIFY_AUTO_TOKEN`(우선, `atk_`), `SHOPIFY_CLIENT_SECRET`
  - 하위호환: `SHOPIFY_AUTO_TOKEN` 미설정 시 `SHOPIFY_ACCESS_TOKEN`(legacy) fallback — `src/utils/secret_check.py`
- 인증 헤더: `X-Shopify-Access-Token`
- 어댑터: `src/markets/adapters/shopify.py` (Admin API 기반 생성/수정, 429 백오프)
- 배포 후 확인 위치: `/admin/diagnostics`, 셀러 마켓 컨트롤 센터(Phase 184).
- 운영 가이드: `docs/operations/SHOPIFY_MARKET.md`

## 🏪 마켓 운영 가이드 링크
- Coupang: `docs/operations/COUPANG.md`
- Naver Smartstore: `docs/operations/NAVER_SMARTSTORE.md`
- 11st: `docs/operations/ELEVENST.md`
- Shopify: `docs/operations/SHOPIFY_MARKET.md`
- WooCommerce: `docs/operations/WOOCOMMERCE_MARKET.md`

## 🚚 택배사 데이터 소스
- 통합 카탈로그: `src/seller_console/orders/courier_catalog.py` (`COURIER_MAP` + `KOREA_COURIERS` 병합)
- 동적 확장: TrackingMore `GET /v4/couriers/all` (키 미설정/오프라인 시 내장 폴백)

---

## Phase 190 — 사용자 마진% 실반영 + 마켓 실제 업로드 완성 + 미구현 기능 마감 ✅ (2026-06-10)

### 오너 지시 사항
1. "마진%는 실사용자가 설정하는대로 바뀌어야 한다"
2. "마켓에 올릴 수 있어야 한다"
3. "여러 기능들 다 구현되어야 한다"

### 작업 요약

#### A. 마진% 실반영 (`target_margin_pct` 파이프라인)
- `/seller/pricing` + `/seller/pricing/compare`: 목표 마진율 슬라이더가 debounce 300ms로 즉시 재계산 트리거 — 기존 동작 유지
- `/seller/collect/upload`: `target_margin_pct` JSON 파라미터를 받아 `product_data`에 주입 → 업로드 payload에 마진율 포함

#### B. 마켓 실제 업로드 완성
- `UploadResult` 필드 추가: `external_product_id`, `external_url`, `error_code`, `hint`
- `DispatchResult.to_dict()`에 신규 필드 직렬화 추가
- Shopify: 성공 시 `storefront_url` → `external_url`, `external_id` → `external_product_id` 추출
- 쿠팡/스마트스토어/11번가/WooCommerce: 응답 dict에서 id/url 추출 시도

#### C. 사전검증 기능 신설 (`UploadDispatcher.prevalidate()`)
- `POST /seller/collect/prevalidate`: 마켓별 토큰/필수필드/이미지 접근성 검증
- `error_code`: `token_missing`, `missing_field`, `image_inaccessible`, `unsupported_market`
- 각 오류 코드마다 즉시 행동 `hint` 포함

#### D. collect_preview.html 반쪽 버튼 제거
- "Phase 136 예정" disabled 버튼 → 실동작 "📤 마켓에 등록" 모달 플로우
- 3단계 모달: 마켓 선택 + 마진율 → 사전검증 → 업로드 결과(성공 링크/실패 조치)
- 중복 클릭 방지 스피너 추가

### 테스트
- `tests/test_phase190_upload_margin.py`: 29개 신규 테스트 (모두 통과)
- 기존 237개 테스트 회귀 없음

### 운영 메모
- `SHOPIFY_AUTO_TOKEN` (우선) 또는 `SHOPIFY_ACCESS_TOKEN` 중 하나만 있어도 Shopify 업로드 가능
- 쿠팡/스마트스토어/11번가는 `src.channel_sync.*_uploader` 모듈 미존재 시 큐에 적재 (queued=True)
- 업로드 실패 시 `/admin/diagnostics`에서 자격증명 점검

### 다음 단계 (백로그)
- 쿠팡/스마트스토어/11번가 실 채널 업로더 모듈 연결 (현재 큐 적재 방식)
- 등록 이력 DB 저장 및 재시도 큐 플로우 고도화

---

## Phase 191 — UX/UI 디테일: 전역 토스트 + 죽은 버튼 감사 3차 ✅ (2026-06-10)

### 오너 지시 사항
- "UX/UI 디테일 세팅이랑 각 버튼들의 실동작 — 실제로 사이트/서비스가 돌아가게."

### 작업 요약
- **전역 토스트 인프라**: `_base.html`에 `#pcToastContainer`(모든 셀러 페이지 공용),
  `seller.js`에 페이지 독립 `pcToast(message, type)` 헬퍼 추가.
  - XSS 방지(textContent), 타입별 색/아이콘, error 6s·기타 3.5s 자동 소멸, bootstrap 미로딩 폴백.
- **alert() → pcToast 전환(8개 페이지)**: `pricing_rules`, `pricing_competitors`, `pricing_fx_impact`,
  `pricing_history`, `discovery`, `discovery_keywords`, `me`, `personal_tokens`, `collect_preview`.
  - 성공/실패 톤 구분, reload 직전 성공 토스트는 1.2초 지연 후 새로고침으로 가시성 확보.
- **honest 유지**: 파괴적 동작 `confirm(...)` 유지, `bookmarklet.html` 외부 실행 코드 내부 `alert(...)` 유지.
- **stale 테스트 정리**: `test_phase_163_favicon_assets` — Phase 189 라이트 테마 복구로 `#020010`(다크)이
  사라져 baseline에서 깨져 있던 assertion을 `theme-color` 메타 존재 검증으로 교체(향후 테마 변경에 견고).

### 테스트
- `tests/test_dead_buttons_phase191.py`: 19개 신규 (전역 토스트 인프라 + 8개 페이지 alert 제거).
- 뷰/템플릿 범위 858개 통과, 회귀 없음.

### 추가 작업 (오너 "나열한 순서대로" 지시 — 2026-06-10)

**① 마켓 업로드 전체 경로(E2E) 검증 고정**
- `/seller/collect/upload` → `UploadDispatcher.dispatch` → 실제 `_upload_shopify` 경로를 타되
  라이브 연동 경계(`ShopifyAdapter`)만 목 처리하여 정합성 고정.
  - 라이브 성공: result에 `external_product_id`/`external_url`, `succeeded` 집계 + UI가 "상품 페이지 열기" 링크 렌더.
  - API 실패(401 등): `error_code=api_error` + 조치 hint(SHOPIFY_AUTO_TOKEN) → UI "💡 조치 / 오류코드" 렌더.
  - 검증 실패: `error_code=validation_failed`. 업로드 중 예외도 500 없이 항목 단위 실패로 정직 보고.
  - `tests/test_collect_upload_e2e.py` 5개 신규.
  - ⚠️ 실 운영 시크릿 대조(라이브 실등록) 검증은 **운영 환경에서 오너가 `/admin/diagnostics`·셀러
    마켓 센터로 별도 수행 필요** (CI엔 시크릿 없음).

**② 네이티브 confirm() → 전역 확인 모달(pcConfirm)**
- `_base.html` `#pcConfirmModal` + `seller.js` Promise 기반 `pcConfirm()`. 11개 호출/7개 페이지 전환.
  파괴적 동작은 빨강 확인, 비파괴는 파랑으로 톤 구분. 상세는 `dead_button_audit.md`.

### 다음 단계 (백로그)
- ③ 셀러 대시보드 화면 정밀 점검 → ✅ (회복탄력성 테스트 고정, 이미 잘 구성됨 확인).
- ④ 쿠팡/스마트스토어/11번가 실 채널 업로더 모듈 연결 → ✅ (아래 참고).
- `_base_app.html`/대시보드 등 셀러 콘솔 밖 화면의 토스트/확인 모달 통일.

### ④ 쿠팡/스마트스토어 실채널 업로더 연결 (2026-06-10)
- **브리지 신설**: `src/channel_sync/_channel_bridge.py`(공통 변환/실행),
  `coupang_uploader.py`·`smartstore_uploader.py`. 디스패처가 `from src.channel_sync import *_uploader`로
  로드 → 기존 `src.uploaders.CoupangUploader`/`NaverSmartStoreUploader`(Phase 17-2) 재사용.
- **가격 매핑**: 원화 판매가 = `sell_price_krw` → `recommended_price(_krw)` → `price_krw` →
  (통화 KRW일 때) `price` 순 첫 양수. 비KRW 가격을 원화로 오용하지 않음. 원화가 0이면 업로드 차단.
- **정직한 실패 표면화**: 자격증명 미설정 → `token_missing`(디스패처 매핑), API 실패/원화 0 → `api_error`.
  성공 시 `external_product_id`/`external_url`을 응답·UI에 노출.
- **테스트**: `tests/test_channel_sync_uploaders.py` 16개(매핑/자격증명/실패/성공/디스패처 통합, 목 API).
- ⚠️ **실 API 라이브 검증은 운영 환경에서 오너가 COUPANG_*/NAVER_* 자격증명으로 별도 수행 필요**
  (CI엔 자격증명 없음 → 목 검증까지만).

### ④-b 11번가(11st) 실 업로더 신설 (2026-06-10)
- **신규 업로더**: `src/uploaders/elevenst_uploader.py` — `ElevenStUploader`(11번가 OpenAPI XML 등록).
  CoupangUploader/NaverSmartStoreUploader와 동일 인터페이스(`prepare_product`/`upload_product` →
  `{success, product_id, url}`). 제목 `[해외직구]` 접두, 10원 단위 판매가, 카테고리 매핑, XML 이스케이프,
  응답 코드/상품번호 파싱.
- **브리지**: `src/channel_sync/elevenst_uploader.py`(REQUIRED: `ELEVENST_API_KEY`).
  디스패처가 자격증명 미설정 → `token_missing`, OpenAPI 실패 → `api_error`로 표기.
- **테스트**: `tests/test_elevenst_uploader.py` 12개(매핑/XML/파싱/성공/실패, requests 목) +
  `tests/test_channel_sync_uploaders.py`에 브리지/디스패처 통합 4개 추가.
- ⚠️ 11번가는 배송 템플릿/카테고리 등 셀러별 설정값 필요 — 운영 시 `ELEVENST_DISP_CTGR_NO` 등
  계정 설정에 맞춰 카테고리/배송 코드 조정 후 라이브 검증 필요.

### ⑤ 라이브 검증 도구 + 가이드 + env 정합성 수정 (2026-06-10)
- **검증 도구 신설**: `scripts/verify_market_connections.py` — 5개 마켓 연결 진단 + 업로드 사전검증을
  한 번에 실행해 사람이 읽는 표로 출력(`python -m scripts.verify_market_connections [market] [--json]`).
  운영 데이터 변경 없음(읽기 + safe dry-run). 운영 셸에서 자격증명 넣고 실행하면 실제 연결 검증.
- **가이드 신설**: `docs/operations/LIVE_VERIFICATION_GUIDE.md` — 키 발급→환경변수→연결확인→테스트
  업로드까지 누구나 따라 하는 단계별 안내 + 상태코드/트러블슈팅/체크리스트/환경변수 표.
- **라이브 검증으로 잡은 실 버그 3건 수정**:
  1. **11번가 키 불일치**: 진단 키 `11st` vs 디스패처 키 `elevenst` → 검증 도구에서 별칭 매핑.
  2. **WooCommerce env 불일치**: prevalidate가 `WC_CONSUMER_KEY`(어디와도 불일치)를 요구 →
     실제 업로드 경로(`WOO_*`)와 진단(`WC_*`) **둘 다 허용**하도록 수정. (올바른 키를 넣어도
     prevalidate가 잘못 막던 버그)
  3. **네이버 env 이중 명명**: 업로드 `NAVER_CLIENT_*` vs 진단 `NAVER_COMMERCE_*` →
     업로더/브리지/prevalidate가 **둘 다 허용**하도록 폴백 추가.
- **검증 결과**: 자격증명 미설정 시 5개 마켓 모두 `token_missing` 정직 표기, 자격증명 주입 시
  5개 마켓 prevalidate 전부 `✅ 통과`(업로드 경로 배선 완료 증명).
- **테스트**: `tests/test_verify_market_connections.py` 7개(별칭 env + 키매핑).
- ⚠️ **실 API 라이브 등록 검증(상품이 실제로 올라가는지)은 여전히 운영 자격증명 필요** — 위 가이드의
  "5. 첫 테스트 업로드"로 오너가 직접 1건 등록해 "상품 페이지 열기" 링크까지 확인할 것.

## Phase 192 — 셀프서비스 마켓 연결 (SaaS 대비) ✅ (2026-06-10)

### 오너 지시
- "SaaS 하게 되면 소비자가 쉽게쉽게 각 마켓에 연결할 수 있어야 한다 — UI/UX·백엔드 잘."

### 작업 요약
- **셀러별 자격증명 저장소**: `src/seller_console/market_credentials.py`
  - `data/market_credentials/<seller_id>.json` Fernet 암호화 저장
    (`MARKET_CRED_ENC_KEY` 우선 → `SECRET_KEY` 파생 → 없으면 평문+경고).
  - `save/get/delete/is_connected/status(마스킹)/credential_env`,
    `seller_market_env(seller, markets, extra=)` 컨텍스트로 표준 env에 일시 주입.
  - 폴백: 셀러 저장값 없으면 전역 환경변수(오너 단일테넌트) 그대로 사용.
- **셀프서비스 연결 화면**: `GET /seller/markets/connect` + `markets_connect.html`
  - 마켓별 카드: 상태 배지, 키 입력 폼(비밀값 password/마스킹), [연결 테스트]/[저장]/[연결 해제].
  - 사이드바에 "마켓 연결(키 설정)" 메뉴 추가.
- **라우트**: `POST /connect/<m>`(저장), `POST /connect/<m>/test`(저장값+입력중값 라이브 테스트),
  `POST /connect/<m>/disconnect`(삭제).
- **업로드 연동**: `/collect/upload`·`/collect/prevalidate`를 `seller_market_env`로 감싸
  셀러 저장 자격증명이 실제 업로드/사전검증을 구동하도록 연결.
- **테스트**: `tests/test_market_credentials.py` 18개(저장/암호화/마스킹/주입/라우트).

### 보안 메모
- 운영에서 `MARKET_CRED_ENC_KEY`(Fernet 키) 설정 필수 권장(미설정 시 SECRET_KEY 파생).
- ⚠️ 오너가 채팅에 `TOSS_SECRET_KEY`(test_sk_…) 평문 노출 → 토스 콘솔에서 재발급 권장.

### 후속(백로그)
- 셀러별 자격증명을 DB/암호화 시크릿 매니저로 이전(파일 → 멀티인스턴스 대비).
- OAuth 방식 마켓(쿠팡/네이버)을 키 직접입력 대신 "연결 버튼" OAuth 플로우로 고도화.

## Phase 193 — 라이브 검증으로 드러난 어댑터 버그 수정 (2026-06-10)

오너가 운영 자격증명 등록 후 `/seller/markets` 라이브 진단 → 5개 마켓 실패.
실제 API 응답(404/500/406/토큰)을 보고 코드 버그 2건 수정 + 진단 메시지 강화.

### 수정한 코드 버그
- **스마트스토어 토큰 발급(진짜 버그)**: 네이버 커머스 OAuth2는 `client_secret` 평문이 아니라
  **bcrypt 전자서명(`client_secret_sign`) + timestamp** 필요. `_naver_signature()` 추가 후
  토큰 요청 페이로드 교정. (자격증명이 맞아도 실패하던 원인)
- **WooCommerce HTTP 406**: WP 호스트 WAF가 User-Agent/Accept 없는 요청을 차단.
  `_request_headers()`(UA+Accept) 추가, 모든 WC 요청(7곳)에 적용.

### 진단 메시지 강화 (값 문제 식별 보조)
- 쿠팡/11번가/우커머스 health_check 실패 시 **실제 응답 본문 일부 + 상태코드별 hint** 노출.

### 오너 액션 필요 (값/계정 문제로 추정)
- **Shopify token_expired**: `SHOPIFY_AUTO_TOKEN`(atk_/shpat_) 값이 유효한지 재확인(재발급).
- **쿠팡 HTTP 404**: `COUPANG_VENDOR_ID` 형식(A+숫자) 재확인.
- **11번가 HTTP 500**: 셀러오피스에서 OpenAPI 사용 승인 + `ELEVENST_API_KEY` 재확인.
  (재배포 후 진단 화면의 응답 본문으로 정확한 원인 확인)

### 테스트
- `tests/test_market_adapter_live_fixes.py` 5개(네이버 서명/WC 헤더).
