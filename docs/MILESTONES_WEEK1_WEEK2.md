# 마일스톤: Week1 & Week2

> **목표**: D14 실주문 1건 완료  
> 마일스톤 날짜는 실제 시작일 기준으로 아래 플레이스홀더를 수정하세요.

---

## Milestone 1 — `Week1 - MVP 판매준비`

| 항목 | 내용 |
|------|------|
| **목표** | 수집 → 가격 → 드래프트 업로드 → 모니터링 최소 동작 |
| **시작일** | `YYYY-MM-DD` (실제 날짜로 교체) |
| **마감일** | `YYYY-MM-DD` (+7일) |
| **성공 기준** | 상품 30개 WooCommerce draft 등록 완료 + 알림 1건 정상 수신 |

### 포함 이슈 (P0 — 9개)

| # | 이슈 제목 | 컴포넌트 |
|---|-----------|----------|
| 1 | `[P0] Product Schema 표준화 (Pydantic)` | `component:schema` |
| 2 | `[P0] Collector Pipeline 공통화` | `component:collector` |
| 3 | `[P0] ALO Collector MVP` | `component:collector` |
| 4 | `[P0] lululemon Collector MVP` | `component:collector` |
| 5 | `[P0] Pricing Engine (마진 자동세팅)` | `component:pricing` |
| 6 | `[P0] WooCommerce Draft Publisher` | `component:publisher` |
| 7 | `[P0] Taobao Seller Whitelist Gate` | `component:taobao-gate` |
| 8 | `[P0] Stock/Price Watcher + Alert` | `component:monitoring` |
| 9 | `[P0] CS 자동 응답 템플릿 (기초 4종)` | `component:cs` |

### gh CLI로 마일스톤 생성

```bash
gh api repos/Kohgane/proxy-commerce/milestones \
  --method POST \
  --field title="Week1 - MVP 판매준비" \
  --field description="수집→가격→드래프트업로드→모니터링 최소 동작. 상품 30개 WC draft 등록 완료." \
  --field due_on="YYYY-MM-DDT23:59:59Z"
```

---

## Milestone 2 — `Week2 - 판매오픈 & 안정화`

| 항목 | 내용 |
|------|------|
| **목표** | 실결제 1건 + CS 자동화 + 신상품 자동 캐치 |
| **시작일** | `YYYY-MM-DD` (+8일) |
| **마감일** | `YYYY-MM-DD` (+14일) |
| **성공 기준** | 🎯 실주문 1건 완료 (D14 KPI) |

### 포함 이슈 (P1)

| # | 이슈 제목 | 컴포넌트 |
|---|-----------|----------|
| 10 | `[P1] 수동수집 URL→이미지 추출 API` | `component:collector` |
| 11 | `[P1] 신상품 자동 캐치 스케줄러` | `component:scheduler` |
| 12 | `[P1] 운영 상태 대시보드 (품절/문제/노출)` | `component:monitoring` |
| 13 | `[P1] E2E 리허설 & 판매오픈` | `component:infra` |
| 14 | `[P1] 배송/환불 정책 페이지 공개` | `component:cs` |

### gh CLI로 마일스톤 생성

```bash
gh api repos/Kohgane/proxy-commerce/milestones \
  --method POST \
  --field title="Week2 - 판매오픈 & 안정화" \
  --field description="실결제 1건 완료(D14 KPI). CS 자동화 + 신상품 캐치 + E2E 리허설." \
  --field due_on="YYYY-MM-DDT23:59:59Z"
```

---

## 전체 실행 순서 (오늘 당장)

```
1. 라벨 생성  →  docs/ISSUE_LABEL_TAXONOMY.md 의 gh 명령어 실행
2. 마일스톤 생성  →  이 문서의 gh 명령어 실행 (날짜 수정 후)
3. P0 이슈 9개 등록  →  docs/WEEK1_TICKET_SET.md 본문 복붙
4. 이슈에 라벨 + 마일스톤 할당
5. Week1 작업 착수 (Product Schema → Pipeline → 수집기 순)
```

---

## 이슈-마일스톤 매핑 요약

```
Week1 - MVP 판매준비
├── #1  Product Schema 표준화
├── #2  Collector Pipeline 공통화
├── #3  ALO Collector MVP
├── #4  lululemon Collector MVP
├── #5  Pricing Engine
├── #6  WooCommerce Draft Publisher
├── #7  Taobao Seller Whitelist Gate
├── #8  Stock/Price Watcher + Alert
└── #9  CS 자동 응답 템플릿

Week2 - 판매오픈 & 안정화
├── #10 수동수집 API
├── #11 신상품 자동 캐치
├── #12 운영 대시보드
├── #13 E2E 리허설 & 판매오픈
└── #14 배송/환불 정책 페이지
```
