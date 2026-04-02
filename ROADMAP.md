# Proxy Commerce 로드맵

## ✅ 완료된 Phase

| Phase | 내용 | PR | 완료일 |
|---|---|---|---|
| Phase 1-13 | 기본 시스템 구축 (봇, API, 환율, 배송, 주문, 재고, 감사, 캐시, 알림 등) | #1-#28 | 2026-03 |
| Phase 14 | 리뷰/프로모션/CRM | #29 | 2026-03-24 |
| Phase 15 | 마케팅 자동화 + 리포팅 고도화 + SEO 최적화 + 통합 웹훅 허브 | #30 | 2026-03-24 |
| Phase 16 | 경쟁사 분석 + 가격 인텔리전스 + 재고 예측 + 워크플로 자동화 | #31 | 2026-03-24 |
| Phase 17-1 | Amazon 상품 수집기 (US/JP) + 수집 파이프라인 기반 | #35 | 2026-04-01 |
| Phase 17-2 | 타오바오/1688 수집기 + 쿠팡/스마트스토어 업로더 | #36 | 2026-04-01 |
| Phase 18-1 | 상품 상세 페이지 에디터 | #37 | 2026-04-01 |
| Phase 19 | 주문 알림 + 실시간 환율 확장 + 마진 계산기 | #39 | 2026-04-01 |
| Phase 20 | Dashboard Web UI + CD 워크플로 수정 | #40 | 2026-04-01 |
| Phase 21 | 주문 알림 텔레그램 강화 + 봇 인라인 버튼 | #42 | 2026-04-02 |
| Phase 22 | 결제/정산 시스템 (토스페이먼츠, 수수료 계산) | #42 | 2026-04-02 |
| Phase 23 | 모니터링 대시보드 (Prometheus, Grafana) | #42 | 2026-04-02 |
| Phase 24 | OAuth + API Key 관리 (JWT, Google/Kakao) | #42 | 2026-04-02 |

## 🚧 진행 중 Phase

## Phase 21: 주문 알림 텔레그램 강화 ✅
- `src/order_alerts/` 완성
- 실시간 주문 상태 변경 알림 (주문접수 → 결제완료 → 배송중 → 배송완료)
- 텔레그램 봇 인라인 버튼 (주문 승인/취소/배송 시작)

## Phase 22: 결제/정산 시스템 ✅
- PG 연동 (토스페이먼츠/이니시스 등)
- 자동 정산 (판매가 - 원가 - 수수료 - 배송비)
- 수수료 계산 (쿠팡/스마트스토어 플랫폼별)

## Phase 23: 모니터링 대시보드 ✅
- Prometheus 메트릭 노출 (주문수, 에러율, API 응답시간)
- 헬스체크 엔드포인트 강화
- Grafana 대시보드 JSON 프로비저닝

## Phase 24: OAuth + API Key 관리 ✅
- JWT 인증 시스템
- 소셜 로그인 (Google/Kakao OAuth2)
- API Key 발급/관리/Rate Limiting

## Phase 25: 프론트엔드 관리자 패널
- Jinja2 기반 서버사이드 렌더링 (Bootstrap 5 CDN)
- 관리자 패널: `/admin/` 프리픽스
- 대시보드: 주문 현황 카드, 매출 요약 카드, 재고 경고 카드, 환율 카드
- 상품 목록: 수집된 상품 테이블, marketplace 필터, 번역 상태 필터, 업로드 상태
- 주문 목록: 상태별 필터, 주문 상세 모달/페이지
- 재고 현황: 재고 부족 상품 테이블, 재주문 필요 상품 하이라이트
- SSE 기반 실시간 알림 (`src/dashboard/websocket_handler.py`)
- 관련 코드: `src/dashboard/admin_views.py`, `src/dashboard/templates/`, `src/dashboard/static/`

## Phase 26: 성능 최적화 + 스케일링
- `CacheStrategy`: Write-through, Write-behind, Cache-aside 패턴
  - TTL 기반 만료 + 이벤트 기반 무효화
  - 인메모리 캐시 (dict 기반) + Redis 옵션
- `QueryOptimizer`: 벌크 조회 유틸리티, N+1 방지 패턴
- `AsyncTaskQueue`: 스레드 기반 작업 큐, 지수 백오프 재시도 (최대 3회)
- `ConnectionPoolManager`: DB/Redis 풀 크기 관리, 헬스체크
- 관련 코드: `src/performance/`

## Phase 27: 배송 추적 시스템
- `ShipmentTracker`: 운송장 등록, 상태 조회, 상태 변경 이벤트 발행
- 지원 택배사: CJ대한통운, 한진택배, 우체국 (mock API)
- `ShipmentStatus`: `picked_up`, `in_transit`, `out_for_delivery`, `delivered`, `exception`
- 배송 상태 변경 시 텔레그램 알림 연동
- API Blueprint: `/api/v1/shipping`
- 봇 커맨드: `/tracking <운송장번호>`
- 관련 코드: `src/shipping/tracker.py`, `src/shipping/carriers.py`, `src/api/shipping_api.py`

## Phase 28: 고객 서비스 (CS) 시스템
- `TicketManager`: 티켓 생성/조회/상태변경/할당
- 티켓 상태: `open`, `in_progress`, `waiting_customer`, `resolved`, `closed`
- `AutoResponder`: FAQ 키워드 매칭 → 자동 답변 제안
- `EscalationRule`: SLA 기반 (24시간 미응답 → 알림, 48시간 → 에스컬레이션)
- API Blueprint: `/api/v1/cs`
- 봇 커맨드: `/cs_list`, `/cs_reply <ticket_id> <message>`
- 관련 코드: `src/customer_service/`

## Phase 29: 데이터 분석 + 리포팅 고도화
- `SalesAnalytics`: 기간별 매출/이익 집계, 채널별 비교, 트렌드 분석
- `CustomerAnalytics`: RFM 분석 (Recency/Frequency/Monetary), 코호트 분석, 고객 LTV 추정
- `ProductAnalytics`: ABC 분류 (A=상위20% 매출), 마진율 분석, 재고 회전율
- `ReportExporter`: CSV 파일 생성, Google Sheets 연동 (mock)
- API Blueprint: `/api/v1/analytics`
- 봇 커맨드: `/analytics [sales|customers|products]`
- 관련 코드: `src/analytics/sales_analytics.py`, `src/analytics/customer_analytics.py`, `src/analytics/product_analytics.py`, `src/analytics/export.py`

## Phase 30: CI/CD 파이프라인 고도화 + 배포 자동화
- `dependency_audit.yml`: 주간 스케줄, `pip-audit` 실행, 결과 텔레그램 알림
- `release.yml`: `v*` 태그 push 시 체인지로그 자동 생성 → GitHub Release 생성
- `generate_changelog.py`: 이전 태그 이후 커밋 메시지 파싱 → Markdown 체인지로그
- `smoke_test.py`: 배포 후 주요 엔드포인트 응답 확인 (헬스체크, API 버전, 주요 페이지)
- 관련 코드: `.github/workflows/dependency_audit.yml`, `.github/workflows/release.yml`, `scripts/generate_changelog.py`, `scripts/smoke_test.py`

## 🔮 향후 고려 사항
- Phase 31: 글로벌 확장 (다국어 상품 페이지, 해외 결제)
- Phase 32: AI 기반 상품 추천 시스템
- Phase 33: 모바일 앱 API (React Native/Flutter)

## Phase 31: 재고 동기화 (Inventory Sync)
- `InventorySyncManager`: 다중 채널(쿠팡/네이버/내부) 재고 동기화
- `ChannelAdapter` ABC + `CoupangAdapter`, `NaverAdapter`, `InternalAdapter` 구현
- `ConflictResolver`: `conservative`(최솟값) / `last_write_wins` 전략
- `SafetyStockCalculator`: 안전 재고 계산, 재주문 포인트, 재주문 필요 여부 확인
- API Blueprint: `/api/inventory` (GET/POST `/sync`, GET `/status`)
- 봇 커맨드: `/sync_inventory`, `/stock_status [sku]`
- 관련 코드: `src/inventory_sync/`

## Phase 32: 번역 관리 (Translation)
- `TranslationManager`: 번역 요청 생성/상태조회/승인 (`pending`→`review`→`approved`)
- `GoogleTranslateProvider` / `ManualTranslationProvider` 구현
- `CommerceGlossary`: 커머스 용어집 적용 (Free Shipping → 무료배송 등)
- `QualityChecker`: 길이 비율, HTML 태그 보존, 금지어 검사
- API Blueprint: `/api/translation` (CRUD 요청, 승인, 상태 조회)
- 봇 커맨드: `/translate <product_id>`, `/translation_status`
- 관련 코드: `src/translation/`

## Phase 33: 자동 가격 엔진 (Pricing Engine)
- `AutoPricer`: 마진/경쟁자/수요 기반 가격 시뮬레이션 및 실행
- `MarginBasedRule`: 원가 / (1 - 마진율 - 채널수수료율)
- `CompetitorBasedRule`: 경쟁자 가격 × (1 + 조정률)
- `DemandBasedRule`: 기준가 × 수요지수
- `PriceHistory`: SKU별 가격 이력 저장/변동률 계산
- `PriceAlerts`: 임계값 초과 시 알림
- API Blueprint: `/api/pricing` (simulate, run, history)
- 봇 커맨드: `/reprice [sku]`, `/price_history <sku>`
- 관련 코드: `src/pricing_engine/`

## Phase 34: 공급자 관리 (Suppliers)
- `SupplierManager`: 공급자 CRUD (추가/조회/업데이트/비활성화)
- `SupplierScoring`: 품질(40%) + 납기(30%) + 가격(30%) 가중 점수, 등급(A/B/C/D)
- `PurchaseOrderManager`: 발주서 생성/상태변경 (`draft`→`sent`→`confirmed`→`shipped`→`received`)
- `SupplierCommunication`: 이메일 템플릿 기반 발주/확인/클레임 발송 (mock)
- API Blueprint: `/api/suppliers` (CRUD, 점수계산, 발주서 관리)
- 봇 커맨드: `/suppliers`, `/supplier_score <id>`, `/po_create <sup_id> <sku> <qty>`
- 관련 코드: `src/suppliers/`

## Phase 35: 알림 허브 고도화 (Notification Hub)
- `NotificationHub`: 이벤트 기반 다중 채널 알림 허브 (`notification_hub.py`)
- 지원 이벤트: `order_placed`, `order_shipped`, `stock_low`, `price_changed`, `cs_ticket`, `system_alert`
- `TelegramChannel`, `EmailChannel`, `SlackChannel` 구현 (`channels/`)
- `NotificationPreference`: 사용자별 채널/이벤트 설정 관리
- `NotificationTemplate`: 이벤트 기반 메시지 렌더링
- API Blueprint: `/api/notifications` (dispatch, preferences)
- 관련 코드: `src/notifications/notification_hub.py`, `src/notifications/channels/`, `src/notifications/preferences.py`
