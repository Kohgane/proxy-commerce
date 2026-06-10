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
- **죽은 버튼 감사 3차**: `dead_button_audit.md` 재스캔에서 남은 `bookmarklet`/`me`/`personal_tokens`/`pricing`/`discovery`
  계열 `alert(...)` 정리.
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
