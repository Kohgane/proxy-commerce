# v62 STEP5 — v61 연동 판정 회수

v61에서 구현한 마켓 연동 3종의 코드는 **전부 배포·가드 완료**. 남은 것은 **라이브 자격증명으로 실행한 판정 캡처**(오너 Render 환경) — 이 개발 환경은 프록시가 라이브 마켓(쿠팡/네이버/Shopify/WC)을 차단하므로 실판정을 대신 낼 수 없다(가짜성공 금지).

## 1) Shopify diagnostics — 코드 그린, 실판정 회수 절차
- **코드:** `market_integration_diagnostics.py::_shopify_read_step()` — GraphQL `shop` 조회로 read 연결 확인, 실패 유형 구분(권한/토큰/네트워크), `_parse_error_code`로 **동어반복 에러 금지**(bare `api_error` 방지).
- **가드(그린):** `test_v61_shopify_diag.py` — `test_check_connection_reports_api_version_on_success`, `test_shopify_read_step_distinguishes_failures`, `test_no_bare_api_error_tautology`, `test_error_summary_masks_and_includes_http`.
- **오너 판정 절차:** 마켓 화면 → **[실연동 재진단]** → `/seller/markets/integration-diagnostics` 실행 → Shopify 행의 녹색(read_connection 성공·api_version) 또는 실패 지점(권한/토큰) 캡처.

## 2) WooCommerce Basic Auth 등록
- **코드:** `market_adapters/woocommerce_adapter.py` — consumer_key/secret **Basic Auth 헤더** + 브라우저 UA(406 회피), `find_by_sku` 빈 결과 시 None(정직).
- **가드(그린):** `test_v61_market_secret.py::test_wc_uses_basic_auth_and_browser_ua`, `test_wc_find_by_sku_empty_returns_none`.
- **오너 판정 절차:** WC 자격증명(`WC_URL`/`WC_KEY`/`WC_SECRET`) 입력 → 상품 1건 등록 → 등록 성공(상품 URL) 캡처. (v14 Phase 214의 빈 호스트·scheme 보정과 연동)

## 3) 스마트스토어 심사중 배지 (약관 준수)
- **코드:** `upload_dispatcher.py::smartstore_approved()` — 커머스솔루션 승인 전 등록 시도 **차단**, `SMARTSTORE_APPROVED=1`(env/admin 토글) 시에만 오픈. 마켓 화면 pending_note `심사중 — 커머스솔루션 승인 후 오픈`.
- **가드(그린):** `test_v61_market_secret.py::test_smartstore_blocked_until_approved`, `test_smartstore_pending_badge_in_template`.
- **오너 판정 절차:** 마켓 화면에서 스마트스토어 **심사중** 배지·비활성 상태 캡처(승인 완료 시 `SMARTSTORE_APPROVED=1`로 오픈).

## 정직 경계
- 자격증명 마스킹(`src/utils/secret_mask.py`, `ck_****d4a7`) — `test_mask_value_format`/`test_mask_text_url_and_header`/`test_mask_literal_secret_anywhere` 그린. **평문 노출 0**(UI·로그·URL).
- v61 관련 가드 **12 passed**(`tests/test_v61_shopify_diag.py`·`tests/test_v61_market_secret.py`).
- 라이브 3종 판정 캡처는 오너 Render 환경(실 키) — 개발 환경 프록시 차단으로 대행 불가. **미완이면 미완으로 보고**.
