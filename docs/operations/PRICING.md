# 가격 정책 룰 운영 가이드

## 개요

자동 가격 조정 엔진(Phase 136)은 설정된 룰에 따라 상품 가격을 자동으로 조정합니다.
기본적으로 `PRICING_DRY_RUN=1`(시뮬레이션 모드)로 동작하며, 실제 가격 변경은 명시적으로 비활성화해야 합니다.

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PRICING_DRY_RUN` | `1` | `1`=시뮬레이션만, `0`=실제 적용 |
| `PRICING_MIN_MARGIN_PCT` | `15` | 최소 마진율 (%) |
| `PRICING_FX_TRIGGER_PCT` | `3` | 환율 변동 트리거 임계값 (%) |
| `PRICING_NOTIFY_THRESHOLD_PCT` | `10` | 가격 변동 알림 임계값 (%) |
| `PRICING_CRON_HOUR` | `3` | 일일 cron 실행 시각 (KST) |
| `CRON_SECRET` | (없음) | `/cron/reprice` 인증 헤더 값 |
| `PRICING_RULES_FALLBACK_PATH` | `data/pricing_rules.jsonl` | Sheets 미연결/오류 시 룰 JSONL 영구 저장 경로 |

---

## 트리거 종류

| kind | 파라미터 예시 | 설명 |
|---|---|---|
| `min_margin_pct` | `{"kind": "min_margin_pct", "op": "<", "value": 15}` | 마진율이 15% 미만이면 트리거 |
| `fx_change_pct` | `{"kind": "fx_change_pct", "currency": "USD", "op": ">=", "value": 3}` | USD 환율이 7일 전 대비 ±3% 이상 변동 시 |
| `stock_qty` | `{"kind": "stock_qty", "op": "<=", "value": 5}` | 재고가 5개 이하이면 트리거 |
| `weekday` | `{"kind": "weekday", "in": ["sat", "sun"]}` | 주말이면 트리거 |
| `season` | `{"kind": "season", "value": "summer"}` | 여름(6~8월)이면 트리거 |
| `date_range` | `{"kind": "date_range", "start": "2026-12-01", "end": "2026-12-31"}` | 날짜 범위 안이면 트리거 |
| `competitor_min_lt_self` | `{"kind": "competitor_min_lt_self", "margin_pct": 5}` | 경쟁사 최저가 < 자사가 × (1 - 5%) |
| `days_since_listing` | `{"kind": "days_since_listing", "op": ">=", "value": 30}` | 등록 후 30일 이상 경과 |

### 비교 연산자 (`op`)
`<`, `<=`, `>`, `>=`, `==`, `!=`

---

## 액션 종류

| action_kind | action_value | 설명 |
|---|---|---|
| `set_margin` | `15` | 마진율을 15%로 재산정 (원가 필요) |
| `multiply` | `1.05` | 가격 × 1.05 (+5%) |
| `add` | `-10000` | 가격 - 10,000원 |
| `match_competitor` | `1000` | 경쟁사 최저가 + 1,000원 |
| `notify_only` | (없음) | 가격 변경 없이 텔레그램 알림만 |

---

## 자주 쓰는 룰 예시

### 1. 최소 마진 15% 가드
```json
{
  "name": "최소 마진 15% 가드",
  "triggers": [{"kind": "min_margin_pct", "op": "<", "value": 15}],
  "action_kind": "set_margin",
  "action_value": "15",
  "action_floor_krw": 10000,
  "dry_run": true
}
```

### 2. 환율 변동 자동 재산정
```json
{
  "name": "USD 환율 3% 변동 재가격",
  "triggers": [{"kind": "fx_change_pct", "currency": "USD", "op": ">=", "value": 3}],
  "action_kind": "set_margin",
  "action_value": "20",
  "dry_run": true
}
```

### 3. 재고 임박 가격 인상
```json
{
  "name": "재고 5개 이하 가격 인상",
  "triggers": [{"kind": "stock_qty", "op": "<=", "value": 5}],
  "action_kind": "multiply",
  "action_value": "1.10",
  "dry_run": true
}
```

### 4. 주말 할인
```json
{
  "name": "주말 특가 -5%",
  "triggers": [{"kind": "weekday", "in": ["sat", "sun"]}],
  "action_kind": "multiply",
  "action_value": "0.95",
  "action_floor_krw": 15000,
  "dry_run": true
}
```

### 5. 등록 30일 후 자동 할인
```json
{
  "name": "30일 후 신상품 할인",
  "triggers": [{"kind": "days_since_listing", "op": ">=", "value": 30}],
  "action_kind": "add",
  "action_value": "-5000",
  "action_floor_krw": 20000,
  "dry_run": true
}
```

---

## 시뮬레이션 → 적용 흐름

1. `/seller/pricing/rules` 에서 룰 생성 (`dry_run=true` 상태)
2. **시뮬레이션** 버튼 클릭 → 영향 SKU 미리보기 (가격 변동 없음)
3. 결과가 예상과 다르면 룰 수정 → 다시 시뮬레이션
4. 만족스러우면 Render 환경변수 `PRICING_DRY_RUN=0` 으로 변경
5. **지금 실행** 버튼 → 실제 가격 변경
6. `/seller/pricing/history` 에서 변동 이력 확인
7. 이상하면 **rollback** 버튼으로 즉시 복원

---

## Cron 자동 실행

Render Cron Job 설정:
- URL: `https://kohganepercentiii.com/cron/reprice`
- Method: `POST`
- Header: `X-Cron-Secret: <CRON_SECRET 값>`
- 스케줄: `0 18 * * *` (UTC 18:00 = KST 03:00)

---

## 룰이 생성되는데 목록에 안 보일 때

### 증상
- `/seller/pricing/rules`에서 룰 생성 성공 후 새로고침하면 목록이 비어 있음

### 원인
- 멀티워커 환경에서 인메모리 저장은 워커 간 공유되지 않음

### 현재 동작 (Phase 136.1)
- 기본 저장소는 Google Sheets
- Sheets 사용 불가 시 `PRICING_RULES_FALLBACK_PATH` JSONL 파일로 영구 저장
- JSONL 쓰기는 `tmp → replace` 원자적(atomic) 교체로 처리

### 점검 순서
1. `/auth/whoami`에서 로그인 상태 확인
2. `GOOGLE_SHEET_ID`/자격증명 설정 확인
3. fallback 파일 경로 쓰기 가능 여부 확인 (`data/pricing_rules.jsonl` 기본)
