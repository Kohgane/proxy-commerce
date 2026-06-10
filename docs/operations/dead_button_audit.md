# 셀러 콘솔 — 죽은 버튼 전수 감사 리포트

> 최종 갱신: 2026-06-09  
> 감사 범위: `src/seller_console/views.py`, `src/seller_console/templates/`, `src/seller_console/static/`  
> 원칙: **honest UI** — 동작하지 않는 버튼/가짜 기능 노출 금지

---

## 감사 방법론

다음 패턴을 검색하여 비동작 인터랙션을 식별했다.

| 패턴 | 의미 |
|------|------|
| `href="#"` | 네비게이션 없이 페이지 점프만 하는 데드 링크 |
| `type="button"` 인데 `onclick` / `data-bs-*` 없음 | 클릭 핸들러 없는 버튼 |
| `alert(...)` | 브라우저 네이티브 alert — 사용성 나쁨, honest UI 위반 |
| `TODO` / no-op 핸들러 | 구현 예정이나 실제 동작 없음 |

---

## 감사 결과 요약

| # | 위치 | 현재 상태 | 목표 동작 | 연결 라우트 | 우선순위 | 조치 |
|---|------|-----------|----------|-------------|---------|------|
| 1 | `views.py:4832` — `/seller/returns/inbox` 일괄 승인 버튼 | `type='button'` — onclick 없음(죽은 버튼) | 선택한 반품 요청을 승인 처리 | `POST /seller/returns/bulk-approve` | **P0** | ✅ 연결 완료 |
| 2 | `views.py:4833` — `/seller/returns/inbox` 부분 환불 버튼 | `type='button'` — onclick 없음(죽은 버튼) | 부분 환불은 금액이 필요하여 일괄 처리 불가 | N/A | P1 | ✅ disabled + 툴팁으로 honest 처리 |
| 3 | `views.py:4834` — `/seller/returns/inbox` 거부 버튼 | `type='button'` — onclick 없음(죽은 버튼) | 선택한 반품 요청을 거부 처리 | `POST /seller/returns/bulk-reject` | **P0** | ✅ 연결 완료 |
| 4 | `views.py:3998-3999` — 소싱 Watch 등록/삭제/실행 JS | `alert(...)` 사용 — 브라우저 블로킹 팝업 | 토스트 알림으로 사용성 개선 | 기존 라우트 유지 | P1 | ✅ toast로 교체 완료 |
| 5 | `views.py:4173,4181,4187,4194` — 소싱 후보 큐 JS | `alert(...)` 사용 | 토스트 알림 | 기존 라우트 유지 | P1 | ✅ toast로 교체 완료 |
| 6 | `orders.html` — 주문 목록 일괄 처리 | 체크박스/전체선택/UI 부재로 백엔드 일괄 라우트를 못 씀 | 선택 주문 일괄 운송장 등록 + 일괄 상태 변경 | `POST /seller/orders/bulk/tracking`, `POST /seller/orders/bulk/status` | **P0** | ✅ 체크박스/툴바/모달 연결 완료 |
| 7 | `views.py:4857` — `/seller/returns/inbox` 부분 환불 | disabled 안내만 있고 실제 처리 경로 없음 | 개별 요청 금액 입력 모달 + 실제 환불 처리 | `POST /seller/returns/<request_id>/partial-refund` | P1 | ✅ 모달 + 라우트 연결 완료 |
| 8 | `orders.js`, `views.py:4276` — 상태 변경/후보 거절 | `prompt()` 사용 | 모달 대화상자 + 토스트 피드백 | 기존 라우트 유지 | P1 | ✅ prompt 제거 완료 |
| 9 | `auth/templates/auth/login.html:102` | `href=\"#\"` 데드 링크 | 실제 버튼 인터랙션으로 비밀번호 찾기 폼 노출 | `/auth/forgot` 폼 유지 | P2 | ✅ 데드 링크 제거 완료 |

---

## 정상 동작 확인 항목 (no action needed)

| 버튼/링크 | 위치 | 연결 라우트 |
|-----------|------|-------------|
| 주문 동기화(⟳ 지금 동기화) | `orders.html` | `POST /seller/orders/sync` |
| 운송장 저장 | `orders.html` 모달 | `POST /seller/orders/<mp>/<id>/tracking` |
| 상태 변경 | `orders.html` | `POST /seller/orders/<mp>/<id>/status` |
| CSV 내보내기 | `orders.html` | `GET /seller/orders/export.csv` |
| 선택 주문 일괄 운송장 등록 | `orders.html` 툴바/모달 | `POST /seller/orders/bulk/tracking` |
| 선택 주문 일괄 상태 변경 | `orders.html` 툴바/모달 | `POST /seller/orders/bulk/status` |
| 소싱처 즉시 수집 | `sourcing.html` | `POST /seller/collect/preview` |
| 소싱처 저장 | `sourcing.html` | `POST /seller/sourcing/registry/add` |
| 소싱처 재수집 | `sourcing.html` | `POST /seller/sourcing/registry/<domain>/recollect` |
| 마켓 동기화 | `markets.html` | `POST /seller/markets/sync` |
| 가격 비교/계산 | `pricing_console.html` | `POST /seller/pricing/compare` |
| 가격 적용 | `pricing_console.html` | `POST /seller/pricing/apply` |
| 가격 룰 생성/수정/삭제 | `pricing_rules.html` | `POST/PUT/DELETE /seller/pricing/rules/*` |
| 경쟁사 모니터링 | `pricing_competitors.html` | `POST /seller/pricing/competitors/*` |
| 롤백 | `pricing_history.html` | `POST /seller/pricing/rollback/*` |
| Watch 등록/실행/삭제 | `sourcing_watches` 페이지 | `POST/DELETE /seller/sourcing/watches/*` |
| 후보 승인/거절/등록/전체승인 | `sourcing_candidates` 페이지 | `POST /seller/sourcing/candidates/*` |
| 택배사 검색 typeahead | `orders.html` 모달 | 프론트엔드 전용(courier_catalog.py) |
| 알림 테스트 | `notifications.html` | `POST /seller/notifications/test` |
| 반품 부분 환불 | `returns/inbox` 개별 행 모달 | `POST /seller/returns/<request_id>/partial-refund` |

---

## 운영 실동작 검증 반영 (2026-06-09)

- 주문 운영 핵심 루프(`/seller/orders` → 상태 변경 → 운송장 단건/일괄 → CSV export)를
  `tests/test_orders_views.py` 시나리오 테스트로 재검증/보강했다.
- 주문 화면에 **주문 운영 라우트 진단 블록**을 추가해 서비스 미가용(503) 시
  `/admin/diagnostics`로 즉시 점검 경로를 안내한다.
- 상태/운송장/일괄 처리 라우트의 경고/오류 로그를 `action`, `marketplace`, `order_id`, `reason`
  필드 중심으로 통일해 운영 추적성을 보강했다.

---

## 2차 재스캔 메모 / 남은 과제

| 항목 | 상태 |
|------|------|
| `src/seller_console/templates/bookmarklet.html` | 콘솔 측 `alert(...)` → `pcToast`. 외부 사이트에서 실행되는 `javascript:` 북마클릿 코드 내부 `alert(...)`은 의도적 유지(콘솔 밖이라 pcToast 불가). → ✅ 3차 완료 |
| `src/seller_console/templates/me.html` | 회원 탈퇴/오류 처리 `alert(...)` → `pcToast` (탈퇴 성공 시 토스트 후 1.2초 뒤 리다이렉트). → ✅ 3차 완료 |
| `src/seller_console/templates/personal_tokens.html` | 토큰 발급/복사/회수 `alert(...)` → `pcToast`. → ✅ 3차 완료 |
| `src/seller_console/templates/pricing_*`, `discovery*.html` | 가격/디스커버리 서브페이지 `alert(...)` → `pcToast`. → ✅ 3차 완료 |
| `src/seller_console/templates/collect_preview.html` | 사전검증 경고/오류 `alert(...)` → `pcToast`. → ✅ 3차 완료 |

---

## 3차 감사 완료 (alert → 전역 pcToast 토스트)

> 최종 갱신: 2026-06-10 · honest-UI: 차단형 `alert()` → 비차단 전역 토스트

- **전역 토스트 인프라 신설**: `_base.html`에 `#pcToastContainer`(상단 우측, 모든 셀러 페이지 공용),
  `seller.js`에 페이지 독립 `pcToast(message, type)` 헬퍼 추가.
  - 메시지는 `textContent`로 삽입(XSS 방지), 타입별 색/아이콘(`success/error/danger/warning/info`),
    error/danger는 6초·그 외 3.5초 후 자동 소멸, bootstrap 미로딩 시 폴백.
- **교체 대상(8개 페이지)**: `pricing_rules`, `pricing_competitors`, `pricing_fx_impact`,
  `pricing_history`, `discovery`, `discovery_keywords`, `me`, `personal_tokens`, `collect_preview`.
  - 성공/실패 톤 구분, `location.reload()` 직전 성공 토스트는 1.2초 지연 후 새로고침으로 가시성 확보.
- **`bookmarklet.html`의 외부 실행 코드 내부 `alert(...)` 2건은 콘솔 밖 컨텍스트라 유지.**
- **회귀 테스트**: `tests/test_dead_buttons_phase191.py`(전역 토스트/확인 모달 인프라 + 페이지별 검증).

### 추가: 네이티브 confirm() → 전역 확인 모달(pcConfirm)

- **전역 확인 모달 인프라**: `_base.html`에 `#pcConfirmModal`, `seller.js`에 Promise 기반
  `pcConfirm(message, {title, confirmLabel, cancelLabel, danger})` 추가.
  - `await pcConfirm(...)` 형태로 사용, 개행(`\n`) 보존, XSS 방지(textContent),
    bootstrap/모달 미존재 시 네이티브 `confirm` 폴백.
- **전환 대상(11개 호출 / 7개 페이지)**: `pricing_rules`(룰 삭제·로그인 이동·가격 적용 dry/실변경 2단),
  `pricing_competitors`(삭제), `pricing_fx_impact`(재가격), `pricing_history`(롤백),
  `discovery_keywords`(삭제), `me`(탈퇴), `personal_tokens`(회수).
  - 파괴적 동작은 `danger`(빨강 확인), 비파괴(재가격/롤백/로그인 이동)는 `danger:false`(파랑)로 톤 구분.
