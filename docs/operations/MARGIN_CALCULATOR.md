# 마진 계산기 운영 가이드

> Phase 125 — 셀러 대시보드 마진 계산기 실연동

---

## 개요

셀러가 해외 상품을 매입해 국내 마켓에 판매할 때 발생하는 **모든 비용을 Decimal 정밀도로 계산**하고,
목표 마진율에 맞는 **권장 판매가를 자동 역산**하는 모듈입니다.

핵심 파일:
- `src/seller_console/margin_calculator.py` — 계산 엔진
- `src/seller_console/views.py` — Flask 라우트 (`/seller/pricing/*`, `/api/v1/pricing/calculate`)
- `src/seller_console/templates/pricing_console.html` — 마진 계산기 UI

---

## 입력 항목 의미

| 항목 | 클래스 필드 | 기본값 | 설명 |
|---|---|---|---|
| 매입가 | `CostInput.buy_price` | — | 상품 원가 (해당 통화 단위) |
| 매입 통화 | `CostInput.buy_currency` | USD | KRW/USD/JPY/EUR/CNY |
| 수량 | `CostInput.qty` | 1 | 한 번에 매입하는 수량 |
| 배대지 수수료 | `CostInput.forwarder_fee` | 0 | 배송 대행지 수수료 (KRW) |
| 국제 배송비 | `CostInput.international_shipping` | 0 | 해외→국내 배송비 (KRW) |
| 국내 배송비 | `CostInput.domestic_shipping` | 0 | 국내 배송비 (KRW) |
| 관세율 | `CostInput.customs_rate` | 0.20 | 소수 형식 (0.20 = 20%) |
| 면세 임계 | `CostInput.customs_threshold_krw` | 150,000 | 이 금액 이하이면 관세 면제 |
| 환율 수동 지정 | `CostInput.fx_override` | None | None=실시간 환율 |

| 항목 | 클래스 필드 | 기본값 | 설명 |
|---|---|---|---|
| 마켓 | `MarketInput.marketplace` | — | coupang / smartstore / 11st / kohganemultishop / shopify |
| 마켓 수수료율 | `MarketInput.commission_rate` | (자동) | % 단위, MARKET_PRICE_POLICY에서 자동 로드 |
| PG 수수료율 | `MarketInput.pg_fee_rate` | 0 | % 단위, 자체몰/Shopify 적용 |
| 목표 마진율 | `MarketInput.target_margin_pct` | 22 | % 단위 |

---

## 계산 공식

### 1. 환산
```
cost_in_krw = buy_price × qty × fx_rate(buy_currency)
```

### 2. 관부가세
```
if cost_in_krw > customs_threshold_krw:
    customs_in_krw = cost_in_krw × customs_rate
else:
    customs_in_krw = 0
```

### 3. 총 랜딩 코스트 (Total Landed Cost)
```
total_landed_cost = cost_in_krw
                  + customs_in_krw
                  + forwarder_fee
                  + international_shipping
                  + domestic_shipping
                  + extra_fees
```

### 4. 수수료율 합계
```
total_fee_rate = (commission_rate + pg_fee_rate) / 100
```

### 5. 권장 판매가 역산 (목표 마진 만족)
```
sell_price = total_landed_cost / ((1 - total_fee_rate) × (1 - target_margin_pct/100))
```
결과는 10원 단위 올림.

### 6. 실 마진 계산
```
net_revenue    = sell_price × (1 - total_fee_rate)
margin_krw     = net_revenue - total_landed_cost
margin_pct     = margin_krw / sell_price × 100
```

### 7. 손익분기점
```
breakeven = total_landed_cost / (1 - total_fee_rate)
```

---

## 마켓별 수수료 표

`src/channels/percenty.py`의 `MARKET_PRICE_POLICY`에서 자동 로드됩니다.

| 마켓 | 수수료율 | 비고 |
|---|---|---|
| 쿠팡 | 10.8% | 패션잡화 기준 |
| 스마트스토어 | 5.0% | 네이버 기본 |
| 11번가 | 12.0% | — |
| 코가네멀티샵 | 3.0% | 자체몰 (PG 수수료 별도) |
| Shopify | 2.0% | Shopify Payments 기본 |

---

## 시나리오 예시 3종

### 시나리오 A — 미국 명품 가방 (USD 100, 쿠팡)
- 매입가: USD 100 @ 1,370 = ₩137,000
- 국제 배송: ₩15,000
- 관세(20%): ₩137,000 × 0.20 = ₩27,400 (면세 임계 초과)
- 랜딩 코스트: ₩179,400
- 목표 마진 22%, 쿠팡 수수료 10.8%:
  - 권장 판매가 ≈ ₩257,000
  - 실 마진 ≈ ₩55,700 (21.7%)

### 시나리오 B — 일본 화장품 (JPY 3,000, 스마트스토어, 면세)
- 매입가: JPY 3,000 @ 9.12 = ₩27,360
- 국내 배송: ₩3,000
- 관세: 면세(₩27,360 < ₩150,000)
- 랜딩 코스트: ₩30,360
- 목표 마진 22%, 스마트스토어 수수료 5%:
  - 권장 판매가 ≈ ₩41,000
  - 실 마진 ≈ ₩8,850 (21.6%)

### 시나리오 C — 중국 의류 (CNY 200, 11번가)
- 매입가: CNY 200 @ 188 = ₩37,600
- 배대지: ₩5,000, 국제 배송: ₩8,000
- 관세(20%): ₩37,600 × 0.20 = ₩7,520 (임계 초과)
- 랜딩 코스트: ₩58,120
- 목표 마진 22%, 11번가 수수료 12%:
  - 권장 판매가 ≈ ₩94,000
  - 실 마진 ≈ ₩20,760 (22.1%)

---

## API 엔드포인트

### POST /seller/pricing/calc
단일 마켓 마진 계산.

```json
{
  "buy_price": 100,
  "currency": "USD",
  "marketplace": "coupang",
  "customs_rate": 20,
  "domestic_shipping": 3000,
  "target_margin_pct": 22
}
```

### POST /seller/pricing/compare
여러 마켓 동시 비교.

```json
{
  "buy_price": 100,
  "currency": "USD",
  "customs_rate": 20,
  "marketplaces": ["coupang", "smartstore", "11st", "kohganemultishop"]
}
```

### POST /api/v1/pricing/calculate
공개 API (인증 stub, Phase 129에서 토큰 검증 추가 예정).

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `FX_USDKRW` | 1370 | USD/KRW 환율 폴백 |
| `FX_JPYKRW` | 9.12 | JPY/KRW 환율 폴백 |
| `FX_EURKRW` | 1485 | EUR/KRW 환율 폴백 |
| `FX_CNYKRW` | 188 | CNY/KRW 환율 폴백 |
| `FX_DISABLE_NETWORK` | 0 | 1로 설정 시 네트워크 환율 차단 (CI 환경) |

---

## 관련 파일

- `src/fx/provider.py` — 실시간 환율 프로바이더
- `src/channels/percenty.py` — `MARKET_PRICE_POLICY` (수수료율 원본)
- `src/seller_console/data_aggregator.py` — 대시보드 위젯용 환율 집계
