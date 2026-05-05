# Phase 129 — 주문 관리 통합 (Order Management Integration)

## 개요

4개 마켓(쿠팡, 스마트스토어, 11번가, 코가네멀티샵)의 주문을 통합 관리하는 시스템.  
Google Sheets `orders` 워크시트가 단일 진실의 원천(source of truth).

---

## 아키텍처

```
[마켓 API]  →  fetch_orders_unified()  →  UnifiedOrder
                                            ↓
                                     OrderSheetsAdapter.bulk_upsert()
                                            ↓
                                      Sheets `orders` 워크시트
                                            ↓
                               OrderSyncService.list_orders() / kpi_summary()
                                            ↓
                                      /seller/orders (UI)
```

---

## 파일 구조

```
src/seller_console/orders/
├── __init__.py          # UnifiedOrder, OrderStatus 등 public API
├── models.py            # 도메인 모델 + 개인정보 마스킹 함수
├── sheets_adapter.py    # Google Sheets CRUD 어댑터
├── sync_service.py      # 마켓별 동기화 + Sheets 통합 서비스
└── tracking.py          # 운송장 추적 stub
```

---

## 주요 컴포넌트

### `UnifiedOrder` (models.py)

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_id` | str | 마켓별 주문 번호 |
| `marketplace` | Literal[...] | coupang / smartstore / 11st / kohganemultishop |
| `status` | OrderStatus | 주문 상태 enum |
| `placed_at` | datetime | 주문 일시 |
| `total_krw` | Decimal | 총 결제금액 (원화) |
| `items` | list[OrderLineItem] | 주문 상품 목록 |
| `courier` | str | 택배사 코드/이름 |
| `tracking_no` | str | 운송장 번호 |
| `buyer_*_masked` | str | 마스킹된 구매자 정보 |

### `OrderStatus` enum

`new` → `paid` → `preparing` → `shipped` → `delivered`  
`canceled` / `returned` / `exchanged` / `refund_requested`

### 개인정보 마스킹

- 이름: `홍길동` → `홍*동`
- 전화번호: `010-1234-5678` → `010-****-5678`
- 주소: `서울시 강남구 테헤란로 123 456호` → `서울시 강남구 ***`

---

## Google Sheets `orders` 워크시트

### 컬럼 구조

```
order_id | marketplace | status | placed_at | paid_at |
buyer_name_masked | buyer_phone_masked | buyer_address_masked |
total_krw | shipping_fee_krw | items_json |
courier | tracking_no | shipped_at |
landed_cost_krw | margin_krw | margin_pct | last_synced_at | notes
```

### 복합 키

`(order_id, marketplace)` 로 upsert → 중복 없이 갱신.

---

## API 라우트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/seller/orders` | 주문 목록 페이지 (KPI + 필터 + 테이블) |
| POST | `/seller/orders/sync` | 모든 마켓 동기화 트리거 |
| GET | `/seller/orders/<marketplace>/<order_id>` | 주문 상세 (JSON) |
| POST | `/seller/orders/<marketplace>/<order_id>/tracking` | 운송장 등록 |
| POST | `/seller/orders/bulk/tracking` | 일괄 운송장 등록 |
| GET | `/seller/orders/export.csv` | CSV 내보내기 |

---

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `GOOGLE_SHEET_ID` | Google Sheets 문서 ID | (필수) |
| `COUPANG_VENDOR_ID` | 쿠팡 벤더 ID | (stub 모드) |
| `COUPANG_ACCESS_KEY` | 쿠팡 액세스 키 | (stub 모드) |
| `COUPANG_SECRET_KEY` | 쿠팡 시크릿 키 | (stub 모드) |
| `NAVER_COMMERCE_CLIENT_ID` | 네이버 커머스 클라이언트 ID | (빈 목록) |
| `NAVER_COMMERCE_CLIENT_SECRET` | 네이버 커머스 시크릿 | (빈 목록) |
| `ELEVENST_API_KEY` | 11번가 API 키 | (빈 목록) |
| `ADAPTER_DRY_RUN` | 1이면 API 호출 차단 | `0` |
| `SWEET_TRACKER_API_KEY` | 스윗트래커 API (운송장 추적) | (stub) |

---

## 동작 모드

### 쿠팡 (GOOGLE_SHEET_ID 미설정 시)
API 키 없음 → **mock 3건** 반환 (테스트/데모용).  
`ADAPTER_DRY_RUN=1` → 빈 목록 반환.

### 스마트스토어 / 11번가
API 키 없음 → 빈 목록 반환.

### 코가네멀티샵
향후 실연동 예정 — 현재 stub (빈 목록).

---

## 운송장 추적 (tracking.py)

현재 stub 구현. `SWEET_TRACKER_API_KEY` 등록 시 실시간 추적 지원 예정.

### 택배사 코드

| 이름 | 코드 |
|------|------|
| CJ대한통운 | 04 |
| 한진 | 05 |
| 롯데 | 08 |
| 우체국 | 01 |
| 로젠 | 06 |

---

## 프론트엔드 (orders.js)

- **5분 자동 폴링** (`setInterval(refreshOrders, 5 * 60 * 1000)`)
- `syncNow()` — POST /seller/orders/sync 호출
- `openTrackingModal(marketplace, orderId)` — 운송장 입력 모달
- `saveTracking()` — POST /seller/orders/{mp}/{id}/tracking 호출
- `showToast(message, type)` — Bootstrap 5 토스트 알림

---

## 주의사항

- `ADAPTER_DRY_RUN=1` 환경 설정 시 운송장 등록 API 호출이 **차단**됨
- 개인정보(이름, 전화번호, 주소)는 **저장 전 마스킹** 처리됨
- 한 마켓 동기화 실패 시 다른 마켓은 **영향 없음**
- Google Sheets 미설정 시 모든 Sheets 연산은 **graceful 폴백**
