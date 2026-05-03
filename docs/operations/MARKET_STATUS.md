# 마켓 상태 실연동 운영 가이드 (Phase 127)

## 개요

셀러 대시보드의 마켓 상태 카드를 Google Sheets 기반 실 데이터로 교체한 Phase 127 구현 설명서.

---

## 데이터 흐름

```
[마켓 API]          [Google Sheets]       [셀러 콘솔 UI]
    ↓                      ↓                      ↓
MarketAdapter     MarketStatusSheetsAdapter   widgets.py
(Phase 130 예정)  (catalog 워크시트 읽기)   (build_market_status_widget)
    ↓                      ↓                      ↓
fetch_inventory()  →  bulk_upsert()   →   AllMarketStatus
                       (upsert_item)       .to_legacy_dict()
                            ↓
                   MarketStatusService
                   (5분 캐시 + 폴백)
                            ↓
                   /seller/markets/status (JSON API)
                   /seller/markets        (HTML 페이지)
```

---

## Google Sheets `catalog` 워크시트 컬럼 정의

| 컬럼 | 타입 | 설명 | 예시 |
|---|---|---|---|
| `product_id` | string | 상품 고유 ID (필수) | `CP-001` |
| `sku` | string | SKU | `ALO-LGG-001` |
| `title` | string | 상품명 | `Alo Yoga 레깅스 블랙 M` |
| `marketplace` | string | 마켓 코드 | `coupang` / `smartstore` / `11st` / `kohganemultishop` |
| `state` | string | 상품 상태 | `active` / `out_of_stock` / `error` / `price_anomaly` / `suspended` |
| `price_krw` | integer | 판매가 (원) | `29900` |
| `last_synced_at` | datetime | 마지막 동기화 시각 | `2026-05-03T10:00:00` |
| `error_message` | string | 오류 메시지 (state=error 시) | `API 인증 실패` |

### 상태 값 정규화

시트에 다양한 표현이 허용됩니다:

| 시트 입력값 | 정규화 결과 |
|---|---|
| `active`, `활성`, `on_sale` | `active` |
| `out_of_stock`, `품절`, `soldout` | `out_of_stock` |
| `error`, `오류`, `fail` | `error` |
| `price_anomaly`, `가격이상` | `price_anomaly` |
| `suspended`, `정지`, `inactive` | `suspended` |
| 기타 알 수 없는 값 | `error` |

---

## 워크시트 자동 생성 (AUTO_BOOTSTRAP)

기본적으로 `catalog` 워크시트가 없으면 에러를 반환합니다.

자동 생성을 원하면 환경변수를 설정하세요:

```bash
AUTO_BOOTSTRAP_SHEETS=1
```

활성화 시 다음 워크시트가 자동 생성됩니다:
- `catalog` — 마켓 상품 상태 (Phase 127)
- `orders` — 주문 데이터
- `fx_rates` — 현재 환율
- `fx_history` — 환율 이력

---

## API 엔드포인트

### GET /seller/markets/status

모든 마켓 상태 요약 JSON 반환.

**응답 예시:**
```json
{
  "summaries": [
    {
      "marketplace": "coupang",
      "label": "쿠팡",
      "active": 45,
      "out_of_stock": 3,
      "error": 1,
      "price_anomaly": 0,
      "suspended": 0,
      "total": 49,
      "last_synced_at": "2026-05-03T10:00:00",
      "source": "sheets"
    }
  ],
  "fetched_at": "2026-05-03T11:00:00",
  "source": "sheets"
}
```

### POST /seller/markets/sync

라이브 동기화 트리거.

**요청 body:**
```json
{"marketplace": "coupang"}
// 또는
{"marketplace": "all"}
```

**응답:**
```json
{"coupang": 12}
// 또는
{"coupang": 12, "smartstore": 0, "11st": 0, "kohganemultishop": 0}
```

> Phase 127에서는 모든 어댑터가 stub이므로 항상 0 반환.
> Phase 130에서 실 API 연동 후 실제 갱신 수 반환.

---

## 마켓별 어댑터 활성화 시점

| 마켓 | 어댑터 파일 | 활성화 Phase |
|---|---|---|
| 쿠팡 | `market_adapters/coupang_adapter.py` | Phase 130 |
| 스마트스토어 | `market_adapters/smartstore_adapter.py` | Phase 130 |
| 11번가 | `market_adapters/eleven_adapter.py` | Phase 130 |
| 코가네멀티샵 | `market_adapters/kohgane_multishop_adapter.py` | 향후 예정 |

---

## Mock 폴백 동작

다음 상황에서 자동으로 mock 데이터를 반환합니다:

1. `GOOGLE_SHEET_ID` 환경변수 미설정
2. Google Sheets 연결 실패 (권한 오류, 네트워크 오류 등)
3. `catalog` 워크시트 없음 (AUTO_BOOTSTRAP 비활성화 시)
4. `catalog` 워크시트 비어있음

Mock 데이터:
- 쿠팡: 활성 45 / 품절 3 / 오류 1
- 스마트스토어: 활성 38 / 품절 5 / 오류 0
- 11번가: 활성 22 / 품절 2 / 오류 2

---

## 샘플 데이터 추가 방법

1. [proxy_catalog Google Sheets](https://docs.google.com/spreadsheets/d/) 열기
2. `catalog` 워크시트 선택
3. 아래 샘플 데이터 추가:

```
product_id  sku          title                    marketplace  state         price_krw  last_synced_at        error_message
CP-001      ALO-LGG-001  Alo Yoga 레깅스 블랙 M  coupang      active        89000      2026-05-03T10:00:00
SS-002      LUL-ALN-002  lululemon Align 28" 네이비  smartstore  out_of_stock  125000     2026-05-03T09:00:00
11S-003     PTR-TNK-003  Porter Tank 숄더백        11st         active        45000      2026-05-03T08:00:00
```

4. `/seller/markets` 페이지 새로고침 → 실 데이터 표시 확인

---

## 사용자 후속 액션

1. Sheets에 샘플 데이터 1~2줄 추가 후 `/seller/dashboard` 새로고침
2. "지금 동기화" 버튼 클릭 → 동기화 완료 토스트 확인
3. `/seller/markets` 상세 페이지에서 필터링/검색 테스트
4. Phase 130 완료 후 각 마켓 API 인증 정보 환경변수 추가
