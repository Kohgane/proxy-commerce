# TRACKING.md — TrackingMore 운송장 추적 설정 가이드 (Phase 133)

## 개요

SweetTracker에서 **TrackingMore v4 API**로 교체.

---

## 환경변수

| 변수명 | 설명 |
|---|---|
| `TRACKINGMORE_API_KEY` | TrackingMore API 키 |

---

## TrackingMore 설정

1. [my.trackingmore.com](https://my.trackingmore.com) → 가입
2. Settings → API Key → 키 복사 → `TRACKINGMORE_API_KEY`

---

## 한국 택배사 코드 매핑

| 택배사 | TrackingMore 코드 |
|---|---|
| CJ대한통운 | `cj-korea` |
| 한진택배 | `hanjin` |
| 롯데택배 | `lotte` |
| 우체국 | `korea-post` |
| 로젠택배 | `logen` |
| 대신택배 | `daesin` |
| 경동택배 | `kdexp` |

> 정확한 코드는 `POST /v4/couriers/detect` 또는 `GET /v4/couriers/all`로 확인.

---

## 운송장 자동 등록 흐름

1. 주문 입고 → `tracking_no` + `courier` 저장
2. Cron `GET /cron/track-shipments` (30분 폴링):
   - `TrackingMoreClient().get_status()` 호출
   - `delivery_status == "delivered"` → orders 시트 갱신
   - 텔레그램 알림 발송

---

## 배송 상태 코드

| 코드 | 설명 |
|---|---|
| `pending` | 접수 대기 |
| `transit` | 배송 중 |
| `pickup` | 픽업 완료 |
| `delivered` | 배송 완료 |
| `undelivered` | 배송 실패 |
| `exception` | 예외 상황 |
| `expired` | 추적 만료 |

---

## 폐기된 서비스

- `SweetTracker` → TrackingMore로 교체
- `SWEETTRACKER_API_KEY` → Render에서 **삭제 권장**
- `src/seller_console/orders/tracking_sweet.py` → deprecated stub (백워드 호환)

---

## 헬스 체크

```
GET /health/deep
→ {"name": "trackingmore", "category": "logistics", "status": "ok"|"missing", "couriers": N}
```
