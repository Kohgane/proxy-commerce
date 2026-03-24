# API 레퍼런스 (API Reference)

## 인증 방법

관리자 API (`/api/*`)는 `X-API-Key` 헤더 인증이 필요합니다.

```http
X-API-Key: your-api-key-here
```

환경변수 `DASHBOARD_API_KEY`에 API 키를 설정합니다.

---

## 웹훅 엔드포인트

### POST `/webhook/shopify/order`

Shopify 주문 웹훅 수신.

**인증**: `X-Shopify-Hmac-Sha256` 헤더 (HMAC-SHA256)

**요청 헤더**:
```
X-Shopify-Hmac-Sha256: <base64(HMAC-SHA256(body, SHOPIFY_CLIENT_SECRET))>
Content-Type: application/json
```

**응답**:
- `200 OK` — 처리 성공
  ```json
  {"ok": true, "tasks": {"total_tasks": 1, "by_vendor": {"porter": 1}}}
  ```
- `200 OK` (중복) — 이미 처리된 주문
  ```json
  {"ok": true, "skipped": "duplicate"}
  ```
- `400 Bad Request` — 검증 실패
  ```json
  {"error": "validation_failed", "details": ["missing field: id"]}
  ```
- `401 Unauthorized` — HMAC 검증 실패
  ```json
  {"error": "Invalid signature"}
  ```
- `429 Too Many Requests` — Rate limit 초과

---

### POST `/webhook/woo`

WooCommerce 주문 웹훅 수신.

**인증**: `X-Wc-Webhook-Signature` 헤더 (HMAC-SHA256) 또는 `WOO_WEBHOOK_SECRET` 미설정 시 인증 생략

**요청 헤더**:
```
X-Wc-Webhook-Signature: <base64(HMAC-SHA256(body, WOO_WEBHOOK_SECRET))>
Content-Type: application/json
```

**응답**:
- `200 OK` — 처리 성공
  ```json
  {"ok": true, "tasks": {...}}
  ```
- `401 Unauthorized` — 시크릿 검증 실패

---

### POST `/webhook/forwarder/tracking`

배대지 배송 추적 업데이트 수신.

**요청 본문** (JSON):
```json
{
  "order_id": "12345",
  "tracking_number": "JP1234567890",
  "status": "shipped",
  "estimated_delivery": "2026-04-01"
}
```

**응답**:
- `200 OK`
  ```json
  {"ok": true}
  ```

---

### POST `/webhook/telegram`

텔레그램 봇 업데이트 수신 (봇 커맨드 처리).

**응답**: `200 OK`

---

## 헬스 엔드포인트

### GET `/health`

기본 헬스체크.

**응답** `200 OK`:
```json
{
  "status": "ok",
  "version": "13.0.0",
  "uptime_seconds": 3600.5
}
```

---

### GET `/health/ready`

준비 상태 확인 (로드 밸런서용).

**응답**:
- `200 OK` — 준비 완료
  ```json
  {"status": "ready", "sheets": true, "telegram": true}
  ```
- `503 Service Unavailable` — 준비 안 됨

---

### GET `/health/deep`

심층 헬스체크 (외부 서비스 연결 포함).

**응답** `200 OK`:
```json
{
  "status": "ok",
  "checks": {
    "google_sheets": "ok",
    "shopify": "ok",
    "telegram": "ok"
  },
  "timestamp": "2026-03-24T14:00:00Z"
}
```

---

## 관리자 대시보드 API

모든 엔드포인트는 `X-API-Key` 헤더 인증 필요.

### GET `/api/dashboard/summary`

전체 운영 현황 요약.

**응답** `200 OK`:
```json
{
  "orders": {"total": 42, "paid": 10, "shipped": 30, "completed": 2},
  "revenue": {"total_krw": 15400000, "margin_avg_pct": 22.5},
  "inventory": {"total_skus": 15, "low_stock": 3},
  "fx": {"USDKRW": 1380, "JPYKRW": 9.2, "EURKRW": 1500}
}
```

---

### GET `/api/dashboard/orders`

주문 목록 조회.

**쿼리 파라미터**:
- `status` — 주문 상태 필터 (paid, shipped, completed, cancelled)
- `page` — 페이지 번호 (기본: 1)
- `per_page` — 페이지당 항목 수 (기본: 20, 최대: 100)

**응답** `200 OK`:
```json
{
  "orders": [...],
  "pagination": {"page": 1, "per_page": 20, "total": 42}
}
```

---

### GET `/api/dashboard/orders/<order_id>`

주문 상세 조회.

**응답**:
- `200 OK` — 주문 정보
- `404 Not Found` — 주문 없음

---

### GET `/api/dashboard/revenue`

매출 데이터 조회.

**쿼리 파라미터**:
- `period` — 기간 (7d, 30d, 90d, all)

**응답** `200 OK`:
```json
{
  "period": "30d",
  "total_krw": 15400000,
  "orders_count": 42,
  "margin_avg_pct": 22.5,
  "by_vendor": {"porter": 8400000, "memo_paris": 7000000}
}
```

---

### GET `/api/dashboard/inventory`

재고 현황 조회.

**쿼리 파라미터**:
- `low_stock` — `true`이면 재고 부족 상품만

**응답** `200 OK`:
```json
{
  "products": [...],
  "summary": {"total": 15, "in_stock": 12, "low_stock": 3, "out_of_stock": 0}
}
```

---

### GET `/api/dashboard/fx`

환율 현황 + 변동률 조회.

**응답** `200 OK`:
```json
{
  "rates": {"USDKRW": 1380, "JPYKRW": 9.2, "EURKRW": 1500},
  "updated_at": "2026-03-24T12:00:00Z"
}
```

---

### GET `/api/dashboard/health`

시스템 상태 종합 조회.

---

## 설정 API

### GET `/api/config/status`

현재 설정 상태 조회 (민감 값 마스킹).

**인증**: `X-API-Key` 필요

**응답** `200 OK`:
```json
{
  "config": {
    "GOOGLE_SHEET_ID": "1BxiM...",
    "SHOPIFY_SHOP": "test-store.myshopify.com",
    "SHOPIFY_ACCESS_TOKEN": "****",
    "APP_ENV": "production",
    "CONFIG_HOT_RELOAD_ENABLED": "0"
  },
  "schema_count": 35,
  "reload_enabled": false
}
```

---

### POST `/api/config/reload`

설정 강제 재로드.

**인증**: `X-API-Key` 필요

**응답** `200 OK`:
```json
{"ok": true, "message": "설정이 재로드되었습니다."}
```

---

### GET `/api/config/validate`

현재 설정 검증 결과 반환.

**인증**: `X-API-Key` 필요

**응답** `200 OK`:
```json
{
  "is_valid": true,
  "warnings": ["SHOPIFY_ACCESS_TOKEN is not set"],
  "errors": []
}
```

---

## 메트릭 엔드포인트

### GET `/api/metrics`

시스템 성능 메트릭 (METRICS_API_ENABLED=1 시 활성화).

**인증**: `X-API-Key` 필요

**응답** `200 OK`:
```json
{
  "request_count": 1234,
  "error_count": 5,
  "avg_response_time_ms": 45.2,
  "slow_requests": 3
}
```

---

## 에러 코드

| HTTP 코드 | 의미 |
|-----------|------|
| `200` | 성공 |
| `400` | 잘못된 요청 (검증 실패) |
| `401` | 인증 실패 (HMAC/API Key) |
| `404` | 리소스 없음 |
| `429` | Rate limit 초과 |
| `500` | 서버 내부 오류 |
| `503` | 서비스 비활성화 |

---

## Rate Limiting

| 엔드포인트 그룹 | 기본 제한 |
|----------------|-----------|
| 웹훅 (`/webhook/*`) | `RATE_LIMIT_WEBHOOK` (기본: 60/분) |
| 헬스 (`/health/*`) | `RATE_LIMIT_HEALTH` (기본: 120/분) |
| API (`/api/*`) | `RATE_LIMIT_DEFAULT` (기본: 60/분) |

`RATE_LIMIT_ENABLED=0`으로 비활성화 가능.
