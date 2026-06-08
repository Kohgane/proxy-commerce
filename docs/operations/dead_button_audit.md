# 셀러 콘솔 — 죽은 버튼 전수 감사 리포트

> 최종 갱신: 2026-06-07  
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

---

## 정상 동작 확인 항목 (no action needed)

| 버튼/링크 | 위치 | 연결 라우트 |
|-----------|------|-------------|
| 주문 동기화(⟳ 지금 동기화) | `orders.html` | `POST /seller/orders/sync` |
| 운송장 저장 | `orders.html` 모달 | `POST /seller/orders/<mp>/<id>/tracking` |
| 상태 변경 | `orders.html` | `POST /seller/orders/<mp>/<id>/status` |
| CSV 내보내기 | `orders.html` | `GET /seller/orders/export.csv` |
| 일괄 운송장 등록 API | `views.py:1451` | `POST /seller/orders/bulk/tracking` |
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

---

## 비고 / 향후 과제

| 항목 | 상태 |
|------|------|
| `auth/templates/auth/login.html:102` `href="#"` 링크 | 인증 페이지 범위 — 셀러 콘솔 외부, 별도 검토 필요 |
| 반품/환불 "부분 환불" 기능 | 금액 입력 UI(모달) 구현 시 개별 요청 행에서 처리 가능; 현재 disabled + 툴팁으로 정직하게 안내 |
| `prompt()` 사용(거절 사유, 상태 변경) | 접근성 개선 여지 있음 — 모달 대화상자로 교체 가능(별도 Phase) |
| 주문 일괄 처리 UI(체크박스) | 백엔드 `POST /seller/orders/bulk/tracking` 라우트는 존재함; UI 체크박스 추가는 다음 Phase |
