# HANDOFF — proxy-commerce 작업 인수인계

> 이 문서는 Kohgane(오너)의 지시사항과 진행 상태를 누적 기록한다.
> **업데이트되는 내용이 생기면 이 파일에 바로바로 반영한다.**
> 최종 갱신: 2026-06-07

---

## 🚦 진행 규칙 (오너 지시)

### ✅ DO — 하라고 한 것
- **택배사 검색형 입력 UI**: 셀러 콘솔 주문관리(배송준비중 내역)의 택배사 입력을
  **드롭다운 → 검색/자동완성(타이핑하면 바로 뜨는)** 방식으로 교체.
  - 사유: 퍼센티는 드롭다운이라 불편하고, 목록에 **없는 택배사도 많음** → 직접 입력(free text)도 허용해야 함.
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
- **테스트 픽스 (커밋 `d8efb7b`)**: Phase 184에서 `SHOPIFY_ACCESS_TOKEN → SHOPIFY_AUTO_TOKEN`으로
  바뀌었는데 `tests/test_shopify_auth.py::TestSecretCheck::test_secret_check_missing`가 옛 이름을
  기대해서 깨져 있었음(9668 passed, 1 failed). 기대값을 실제 코드에 맞춰 수정 → **CD – Staging 다시 그린(success)**.
- **Shopify 시크릿 등록 (오너)**: Render/환경변수에 실제 시크릿 등록 완료. PR #185 머지됨.

### 진행 중
- 없음

### 백로그 (오너 승인 대기 — 먼저 묻지 말 것)
- SaaS 공개 준비 (약관/결제/랜딩) — 2026 Q4. **오너가 지시할 때까지 대기.**

---

## 🔑 Shopify 라이브 연결 메모
- 필수 시크릿: `SHOPIFY_SHOP`, `SHOPIFY_AUTO_TOKEN`(우선, `atk_`), `SHOPIFY_CLIENT_SECRET`
  - 하위호환: `SHOPIFY_AUTO_TOKEN` 미설정 시 `SHOPIFY_ACCESS_TOKEN`(legacy) fallback — `src/utils/secret_check.py`
- 인증 헤더: `X-Shopify-Access-Token`
- 어댑터: `src/markets/adapters/shopify.py` (Admin API 기반 생성/수정, 429 백오프)
- 배포 후 확인 위치: `/admin/diagnostics`, 셀러 마켓 컨트롤 센터(Phase 184).

---

## 🚚 택배사 데이터 소스 (검색 UI 통합 대상)
- `src/seller_console/orders/tracking_trackingmore.py` → `KOREA_COURIERS` (TrackingMore 코드 매핑)
- `src/seller_console/orders/tracking.py` → `COURIER_MAP`
- 동적 확장: TrackingMore `GET /v4/couriers/all`

---

## ✅ 이번 반영 완료 (2026-06-07) — 죽은 버튼 실작동화 + UI/UX 정비

### 감사 리포트
`docs/operations/dead_button_audit.md` 생성 — 전수 감사 결과 표(위치/현재상태/목표동작/연결라우트) 포함.

### 연결한 버튼 목록

| 버튼 | 위치 | 이전 | 이후 |
|------|------|------|------|
| 일괄 승인 | `/seller/returns/inbox` | 죽은 버튼 (onclick 없음) | `POST /seller/returns/bulk-approve` 연결 |
| 거부 | `/seller/returns/inbox` | 죽은 버튼 (onclick 없음) | `POST /seller/returns/bulk-reject` 연결 |
| 부분 환불 | `/seller/returns/inbox` | 죽은 버튼 (onclick 없음) | disabled + 툴팁 "개별 요청을 직접 처리하세요" (honest UI) |

### 행 선택 UX 추가
- 반품 인박스 테이블에 체크박스 열 추가 (개별 선택 + 전체 선택 `chkAll`)
- 체크한 항목만 일괄 승인/거부 처리
- 처리할 항목이 없으면 버튼 자동 disabled (honest UI)

### UX 개선 (alert → toast)
- `/seller/sourcing/watches` — Watch 등록/실행/삭제 결과 `alert()` → 토스트 알림으로 교체
- `/seller/sourcing/candidates` — 승인/거절/등록/전체승인 결과 `alert()` → 토스트 알림으로 교체

### 신규 백엔드 라우트
- `POST /seller/returns/bulk-approve` — 선택 요청 일괄 승인 (partial failure 허용, ok=true)
- `POST /seller/returns/bulk-reject` — 선택 요청 일괄 거부

### 회귀 테스트
`tests/test_dead_buttons_fixed.py` — 17개 테스트 전원 통과
