# 14일 빠른실행 오퍼레이션 플랜

> **최우선 KPI**: D14 안에 실주문 1건 완료  
> **원칙**: 자동화는 MVP 범위만 · 법/정책 리스크는 보수적 차단 우선

---

## 실행 원칙 요약

| 원칙 | 내용 |
|------|------|
| 속도 | 최단 경로로 판매 가능 상태 달성 |
| 범위 | 수집 → 검수 → 업로드 → 모니터링 MVP |
| 안전 | 타오바오 화이트리스트 필수, 브랜드 정책 준수 |
| 환경 | `WC_*` = kohganemultishop.org (메인), `WOO_*` = kohganewps.org (레거시) |

---

## Day-by-Day 상세 계획

### Day 1 — 킥오프 & 환경 정비

- [ ] `.env` 분리: dev / staging / prod
- [ ] `WC_*` (kohganemultishop.org) 키 확인 및 `.env.example` 업데이트
- [ ] PortOne 결제 웹훅 test key/secret 정리
- [ ] 텔레그램 봇 or 슬랙 webhook URL 준비
- [ ] 성공지표 확정:
  - 상품 30개 등록
  - 테스트 결제 성공
  - CS 시나리오 4종 초안 완성

---

### Day 2 — 결제 & WooCommerce 연결 검증

- [ ] PortOne 웹훅 검증: `결제완료` / `결제실패` / `취소`
- [ ] WooCommerce REST API 연결 테스트 (상품 create / update / draft)
- [ ] `WC_URL`, `WC_KEY`, `WC_SECRET` 환경변수로 API 호출 성공 확인
- [ ] 배송/환불 기본 정책 페이지 초안 작성 (법적 문구 포함)

---

### Day 3 — Product Schema 고정

- [ ] `schemas/product.py` (Pydantic) 작성
  - 필수 필드: `source`, `source_product_id`, `source_url`, `brand`, `title`, `description`, `currency`, `cost_price`, `sell_price`, `images[]`, `thumbnail`, `options[]`, `stock_status`
- [ ] validator 작성 (가격 / 이미지 / 옵션)
- [ ] 샘플 fixture 10개 통과 확인
- [ ] 공통 파이프라인 뼈대: `fetch → parse → normalize → validate → draft_publish`

---

### Day 4 — ALO Collector MVP

- [ ] `collectors/alo.py` 구현
  - 추출 필드: 제목 / 가격 / 이미지 / 옵션 / 원문 URL
- [ ] 키워드 자동 생성 (카테고리 + 브랜드 + 핵심 속성)
- [ ] raw + normalized JSON 저장
- [ ] 최소 20개 상품 수집 성공 확인

---

### Day 5 — lululemon Collector MVP

- [ ] `collectors/lululemon.py` 구현
- [ ] 이미지/썸네일 정리 규칙: 대표 이미지 1 + 상세 N
- [ ] 이미지 URL 유효성 체크 포함
- [ ] 스키마 검증 통과율 95% 이상 확인

---

### Day 6 — Pricing Engine MVP

- [ ] `pricing/engine.py` 구현
  - `calculate_sell_price(cost, exchange_rate, shipping_fee, fee_rate, margin_pct)`
  - `calculate_margin_rate(cost, sell_price, ...)`
- [ ] 정책 프리셋 3종 (`config/pricing.yaml`):
  - **입문형**: 마진 20%
  - **표준형**: 마진 28%
  - **공격형**: 마진 35%
- [ ] 최소마진 하한선 미달 시 publish 차단 로직
- [ ] 단위테스트 작성

---

### Day 7 — WooCommerce Draft Publisher

- [ ] `publishers/woocommerce.py` 구현 (`WC_*` primary)
- [ ] 중복방지 키: `source + source_product_id`
- [ ] draft publish CLI: `python -m app.publish --source alo --dry-run`
- [ ] 업로드 결과 로그 저장 (`logs/upload_history.jsonl`)
- [ ] "수동 검수 승인 후 publish" 플로우 확인

---

### Day 8 — Taobao Seller Whitelist Gate

- [ ] `compliance/seller_whitelist.py` 구현
  - whitelist 저장소 (JSON / SQLite)
  - 신뢰점수 threshold 설정 가능
- [ ] 판매자 미등록 시 자동 reject + 차단 사유 로깅
- [ ] 초기 신뢰 판매자 20개 이상 등록
- [ ] reject report export 기능

---

### Day 9 — Stock/Price Watcher + 알림

- [ ] `monitoring/watcher.py` 구현
  - 스케줄러 1시간 간격 실행
  - 품절 전환 / 가격변동 감지
- [ ] 텔레그램 or 슬랙 알림 연결
- [ ] 노이즈 억제: 동일 알림 24시간 중복 제한
- [ ] 알림 메시지 포맷 통일

---

### Day 10 — CS 자동 응답 템플릿

- [ ] 템플릿 4종 작성:
  - 반품 안내
  - 교환 처리 안내
  - 환불 처리 안내
  - 배송 지연 안내
- [ ] 고객명 / 주문번호 치환 변수 지원 (`{{customer_name}}`, `{{order_id}}`)
- [ ] 주문 상태별 템플릿 매핑
- [ ] 한국어 기본 + 영문 fallback

---

### Day 11 — 수동수집 엔드포인트 MVP

- [ ] URL 입력 → 이미지/제목/가격 추출 API 엔드포인트
  - `POST /api/collect/manual` `{ "url": "..." }`
- [ ] 추출 실패 시 재시도 / 에러 로그 남김
- [ ] 지원 소스: ALO, lululemon, 타오바오(화이트리스트 통과 후)

---

### Day 12 — 신상품 자동 캐치 스케줄러

- [ ] `scheduler/new_product_checker.py` 구현
  - 브랜드별 뉴드롭 체크 (daily)
  - 신규 발견 시 draft 자동 생성
- [ ] 브랜드별 체크 URL/셀렉터 config 분리

---

### Day 13 — E2E 리허설

- [ ] 전체 플로우 1회 실행:
  ```
  수집 → 가격 계산 → WooCommerce draft 업로드
  → 텔레그램 알림 → CS 템플릿 확인
  ```
- [ ] 장애 시나리오 테스트:
  - 품절 상품 업로드 시도 → reject 확인
  - 가격변동 → 알림 발송 확인
  - 결제 실패 → 웹훅 처리 확인
- [ ] 이탈 포인트 수정

---

### Day 14 — 판매 오픈 🚀

- [ ] 소량 SKU (10~30개) 실판매 오픈 (WooCommerce published)
- [ ] 실주문 1건 완료 → **D14 KPI 달성**
- [ ] D+1 개선 목록 정리:
  - 병목 지점
  - 전환률
  - CS 응답 속도

---

## 체크포인트 요약

| Day | 마일스톤 |
|-----|---------|
| D2  | 결제 + WC API 연결 완료 |
| D5  | 수집기 2종 MVP 완료 |
| D7  | 드래프트 업로드 자동화 완료 |
| D9  | 모니터링 + 알림 작동 |
| D13 | E2E 리허설 통과 |
| D14 | 🎯 실주문 1건 완료 |
