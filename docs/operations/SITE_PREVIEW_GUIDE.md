# 사이트 미리보기 가이드 (SITE_PREVIEW_GUIDE.md)

> `https://kohganepercenti.com` 에서 볼 수 있는 화면들과, 수정하고 싶을 때 어느 파일을 바꾸면 되는지 안내합니다.

---

## 접근 가능한 화면 목록

| URL | 화면 이름 | 설명 |
|-----|----------|------|
| `/health` | 헬스체크 | 서비스 상태 JSON |
| `/health/deep` | 상세 헬스체크 | DB/캐시/외부 의존성 상태 |
| `/admin/` | 관리자 대시보드 | 주문 현황, 매출 요약, 재고 경고, 환율 카드 |
| `/admin/products` | 상품 목록 | 수집된 상품 테이블, 마켓플레이스 필터 |
| `/admin/orders` | 주문 목록 | 상태별 필터, 주문 상세 모달 |
| `/admin/inventory` | 재고 현황 | 재고 부족 상품, 재주문 필요 하이라이트 |
| `/admin/analytics` | 분석 대시보드 | RFM 분류, 매출 추이, 채널별 분석 |
| `/api/docs` | API 문서 | OpenAPI 3.0 HTML 렌더링 |
| `/api/v1/dashboard/stats` | 대시보드 KPI | 주문수, 매출, 재고 수치 JSON |

---

## 화면별 수정 파일 매핑

### 대시보드 (메인 화면)

**화면**: `/admin/`  
**수정하고 싶은 것 → 파일**

| 수정 목표 | 수정할 파일 |
|----------|------------|
| KPI 카드 (주문수, 매출, 재고, 환율) 수치 | `src/dashboard/admin_views.py` → `dashboard()` 함수 |
| 카드 디자인 / 색상 / 레이아웃 | `src/dashboard/templates/dashboard.html` |
| 대시보드 CSS 스타일 | `src/dashboard/static/css/admin.css` |
| 실시간 알림 표시 방식 | `src/dashboard/websocket_handler.py` |
| 차트 데이터 | `src/dashboard/admin_views.py` → `/api/v1/dashboard/stats` |

---

### 상품 목록

**화면**: `/admin/products`  
**수정하고 싶은 것 → 파일**

| 수정 목표 | 수정할 파일 |
|----------|------------|
| 상품 테이블 컬럼/정렬 | `src/dashboard/templates/products.html` |
| 상품 데이터 쿼리 로직 | `src/dashboard/admin_views.py` → `products()` |
| 번역 상태 표시 | `src/translation/` + `src/dashboard/templates/products.html` |
| 마켓플레이스 필터 옵션 추가 | `src/dashboard/templates/products.html` (select 태그) |

---

### 주문 목록

**화면**: `/admin/orders`  
**수정하고 싶은 것 → 파일**

| 수정 목표 | 수정할 파일 |
|----------|------------|
| 주문 상태 필터 | `src/dashboard/templates/orders.html` |
| 주문 상세 모달 내용 | `src/dashboard/templates/orders.html` + `src/orders/order_router.py` |
| 주문 데이터 | `src/orders/order_router.py` |
| 자동구매 버튼 추가 | `src/dashboard/templates/orders.html` + `src/auto_purchase/` |

---

### 재고 현황

**화면**: `/admin/inventory`  
**수정하고 싶은 것 → 파일**

| 수정 목표 | 수정할 파일 |
|----------|------------|
| 재고 부족 임계값 변경 | `src/inventory/stock_checker.py` |
| 재고 테이블 컬럼 | `src/dashboard/templates/inventory.html` |
| 가상 재고 표시 | `src/virtual_inventory/` + 템플릿 |

---

### 배송 알림 관리

**화면**: `/api/v1/delivery-notifications/*`  
**수정하고 싶은 것 → 파일**

| 수정 목표 | 수정할 파일 |
|----------|------------|
| 알림 메시지 템플릿 (한국어) | `src/delivery_notifications/templates/ko.py` |
| 알림 메시지 템플릿 (영어) | `src/delivery_notifications/templates/en.py` |
| 지연 감지 임계값 (48h → 변경) | `src/delivery_notifications/delay_detector.py` |
| 알림 채널 추가 (카카오 등) | `src/delivery_notifications/dispatcher.py` |

---

### 반품/교환 관리

**화면**: `/api/v1/returns-automation/*`  
**수정하고 싶은 것 → 파일**

| 수정 목표 | 수정할 파일 |
|----------|------------|
| 자동 승인 기준 변경 | `src/returns_automation/auto_approval_engine.py` |
| 환불 계산 로직 | `src/returns_automation/refund_orchestrator.py` |
| 반품 분류 기준 | `src/returns_automation/return_classifier.py` |

---

### 정산/회계

**화면**: `/api/v1/finance/*`  
**수정하고 싶은 것 → 파일**

| 수정 목표 | 수정할 파일 |
|----------|------------|
| 채널 수수료율 변경 (쿠팡 11% 등) | `src/finance_accounting/channel_fee_calculator.py` |
| 이상거래 감지 임계값 | `src/finance_accounting/anomaly_detector.py` |
| 세무 리포트 형식 | `src/finance_accounting/tax_reporter.py` |
| 계정과목 목록 | `src/finance_accounting/ledger.py` |

---

### API 문서

**화면**: `/api/docs`  
**수정하고 싶은 것 → 파일**

| 수정 목표 | 수정할 파일 |
|----------|------------|
| API 스펙 내용 | `src/docs/openapi_schema.py` |
| 문서 HTML 스타일 | `src/docs/doc_renderer.py` |
| 새 엔드포인트 문서 추가 | `src/docs/openapi_schema.py` |

---

## 로컬에서 미리보기 실행

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경변수 설정 (mock 모드)
export FX_DISABLE_NETWORK=1
export APP_ENV=development
export PORT=8000

# 3. 앱 실행
python -m flask --app src.order_webhook run --port 8000 --debug

# 4. 브라우저에서 접속
open http://localhost:8000/admin/
open http://localhost:8000/api/docs
```

---

## Docker로 실행 (실제 배포 환경과 동일)

```bash
# 1. Docker 이미지 빌드
docker build -t proxy-commerce-local .

# 2. 컨테이너 실행
docker run -p 10000:10000 \
  -e PORT=10000 \
  -e APP_ENV=development \
  -e FX_DISABLE_NETWORK=1 \
  proxy-commerce-local

# 3. 브라우저에서 접속
open http://localhost:10000/admin/
```

---

## 화면 수정 후 반영 절차

```bash
# 1. 로컬에서 테스트
python -m pytest tests/ -q -x

# 2. Git commit & push
git add .
git commit -m "feat: 대시보드 KPI 카드 스타일 수정"
git push origin main

# 3. Render 자동 배포 대기 (보통 3~5분)
# 4. 배포 확인
curl https://kohganepercenti.com/health
python scripts/render_smoke.py https://kohganepercenti.com
```
