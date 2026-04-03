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
| Phase 25 | 프론트엔드 관리자 패널 (Jinja2 + Bootstrap 5) | #43 | 2026-04-02 |
| Phase 26 | 성능 최적화 + 스케일링 (캐시 전략, 비동기 큐) | #43 | 2026-04-02 |
| Phase 27 | 배송 추적 시스템 (택배사 연동, 상태 알림) | #43 | 2026-04-02 |
| Phase 28 | 고객 서비스 (CS) 시스템 (티켓, 자동 응답, SLA) | #43 | 2026-04-02 |
| Phase 29 | 데이터 분석 + 리포팅 고도화 (RFM, ABC 분류) | #43 | 2026-04-02 |
| Phase 30 | CI/CD 파이프라인 고도화 (의존성 감사, 자동 릴리스) | #43 | 2026-04-02 |
| Phase 31 | 멀티 채널 재고 동기화 (쿠팡/네이버/자체몰) | #44 | 2026-04-02 |
| Phase 32 | 다국어 상품 번역 파이프라인 (EN/JA/ZH→KO) | #44 | 2026-04-02 |
| Phase 33 | 자동 가격 조정 엔진 (마진/경쟁가/수요 기반) | #44 | 2026-04-02 |
| Phase 34 | 공급업체 관리 시스템 (CRUD, 스코어링, 발주서) | #44 | 2026-04-02 |
| Phase 35 | 알림 허브 통합 (텔레그램+이메일+Slack 다채널) | #44 | 2026-04-02 |
| Phase 36 | E2E 테스트 + 통합 테스트 | #44 | 2026-04-02 |
| Phase 37 | 반품/교환 관리 (환불 계산, 검수 A~D, 교환 처리) | #45 | 2026-04-02 |
| Phase 38 | 쿠폰/프로모션 코드 시스템 | #45 | 2026-04-02 |
| Phase 39 | 카테고리/태그 관리 (계층 트리, 자동 태깅) | #45 | 2026-04-02 |
| Phase 40 | 배치 작업 스케줄러 (cron 파싱, 작업 이력) | #45 | 2026-04-02 |
| Phase 41 | 감사 로그 고도화 (who/what/when, 데코레이터) | #45 | 2026-04-02 |
| Phase 42 | 데이터 마이그레이션/시드 도구 | #45 | 2026-04-02 |

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

## Phase 37: 반품/교환 관리 (Returns/Exchange)
- `ReturnManager`: 반품 CRUD + 상태 전환 (`requested`→`approved`→`received`→`inspected`→`refunded`/`exchanged`)
- `RefundCalculator`: 환불 금액 계산 (배송비 공제, 검수 등급 비율, 쿠폰 처리)
- `InspectionService`: 검수 등급 A(100%)/B(90%)/C(70%)/D(0%)
- `ExchangeHandler`: 동일 상품 재배송, 옵션 변경 교환
- API Blueprint: `/api/v1/returns`
- 봇 커맨드: `/returns`, `/return_approve <id>`, `/return_inspect <id> <grade>`
- 관련 코드: `src/returns/`

## Phase 38: 쿠폰/프로모션 코드 시스템 (Coupon/Promotion)
- `CouponManager`: CRUD + 유효성 검증; 타입: percentage/fixed_amount/free_shipping
- `CodeGenerator`: 랜덤 8~16자 코드, 접두사 지원 (SUMMER-XXXX), 일괄 생성
- `RedemptionService`: 쿠폰 사용, 중복 방지, 이력 추적
- `CouponRule` (ABC): `MinOrderAmountRule`, `ProductCategoryRule`, `DateRangeRule`, `FirstPurchaseRule`
- API Blueprint: `/api/v1/coupons`
- 봇 커맨드: `/coupons`, `/coupon_create`, `/coupon_validate <code>`
- 관련 코드: `src/coupons/`

## Phase 39: 카테고리/태그 관리 (Category/Tag)
- `CategoryManager`: 무한 깊이 계층 트리 CRUD, 이동, 자식 포함 삭제
- `TagManager`: CRUD, 키워드 기반 자동 태깅, 태그 검색
- `CategoryMapping`: 플랫폼 카테고리 ID 매핑 (쿠팡↔네이버↔내부), 미매핑 탐색
- `BreadcrumbGenerator`: 경로 문자열 생성 "전자제품 > 컴퓨터 > 노트북"
- API Blueprint: `/api/v1/categories`
- 봇 커맨드: `/categories`, `/add_tag <product_id> <tag>`
- 관련 코드: `src/categories/`

## Phase 40: 작업 스케줄러 (Job Scheduler)
- `JobScheduler`: 인터벌 스케줄링 (every_minutes, every_hours, daily_at), 간단한 cron 파서, 실행/일시정지/재개/삭제
- `JobRegistry`: 이름→callable 매핑, @register_job 데코레이터
- `JobHistory`: 실행 이력 (시작/종료/상태/결과/오류), 최근 N개
- `RetryPolicy`: 최대 재시도, 지수 백오프
- API Blueprint: `/api/v1/scheduler`
- 봇 커맨드: `/jobs`, `/job_run <name>`, `/job_history <name>`
- 관련 코드: `src/scheduler/`

## Phase 41: 감사 로그 확장 (Audit Log)
- `AuditStore`: 인메모리 + JSON Lines 파일 백업, 최대 레코드 설정
- `AuditQuery`: 기간/사용자/이벤트 타입/리소스 필터, 페이지네이션, 전문 검색
- `@audit_log` 데코레이터: 함수 실행 전/후 자동 기록
- API Blueprint: `/api/v1/audit`
- 봇 커맨드: `/audit_log`, `/audit_search <keyword>`
- 관련 코드: `src/audit/` (audit_store.py, audit_query.py, decorators.py 추가)

## Phase 42: 데이터 마이그레이션 + 시드 도구 (Migration/Seed)
- `SeedGenerator`: 개발/테스트용 시드 데이터 (상품 50개, 주문 30개, 고객 20개), 한국어 샘플 데이터
- `DataValidator`: 무결성 검사 (필수 필드, 참조 무결성, 타입 검증)
- `ExportImport`: JSON/CSV 내보내기/가져오기, 대량 가져오기
- CLI: `scripts/migrate.py` (up/down/status), `scripts/seed.py` (seed/reset)
- 관련 코드: `src/migration/` (seed.py, validators.py, export_import.py 추가)

## Phase 43: 위시리스트 / 관심상품 관리
- `WishlistManager`: 위시리스트 CRUD, 아이템 추가/삭제/이동 (폴더 그룹), 메모/우선순위(1~5)
  - 사용자당 최대 위시리스트: 10, 위시리스트당 최대 아이템: 100
- `PriceWatch`: 목표 가격 설정, 현재 가격 비교, 알림 생성, 가격 이력 추적 (최근 30일)
- `WishlistShare`: 공유 토큰 생성, 읽기 전용 조회, 만료 처리
- `WishlistRecommender`: 카테고리/태그 분석 → 유사 상품 추천
- API Blueprint: `src/api/wishlist_api.py` (`/api/v1/wishlist`)
- 봇 커맨드: `/wishlist`, `/wish_add <product_id>`, `/wish_watch <product_id> <target_price>`
- 관련 코드: `src/wishlist/`

## Phase 44: 상품 번들/세트 관리
- `BundleManager`: 번들 CRUD (fixed/pick_n/mix_match 타입), 상태 (draft/active/inactive)
- `BundlePricing`: sum_discount/fixed_price/cheapest_free 전략
- `BundleAvailability`: 구성 상품 전체 재고 확인, 부분 가용 시 대안 제안
- `BundleSuggestion`: 구매 이력 기반 함께 구매 빈도 분석 → 번들 제안
- API Blueprint: `src/api/bundles_api.py` (`/api/v1/bundles`)
- 봇 커맨드: `/bundles`, `/bundle_create`, `/bundle_price <bundle_id>`
- 관련 코드: `src/bundles/`

## Phase 45: 멀티 통화 확장 + 결제 게이트웨이 추상화
- `CurrencyManager`: 지원 통화 등록/조회, 기본 통화 설정 (KRW)
- `CurrencyConverter`: 환율 기반 변환, 캐시 (TTL 1시간), 통화별 라운딩 규칙
- `CurrencyDisplay`: 통화별 포맷팅 (₩12,300 / $12.30 / ¥1,230)
- `SettlementCalculator`: 통화별 정산 (환전 수수료%, 최소 수수료)
- `PaymentGateway` ABC + `TossPaymentsGateway`, `StripeGateway`, `PayPalGateway` mock
- `GatewayManager`: 통화/국가 기반 PG 선택, 결제 라우팅
- API Blueprint: `src/api/multicurrency_api.py` (`/api/v1/currency`), `src/api/payment_api.py` (`/api/v1/payments`)
- 봇 커맨드: `/convert <amount> <from> <to>`, `/payment_status <payment_id>`
- 관련 코드: `src/multicurrency/`, `src/payment_gateway/`

## Phase 46: 이미지 관리 파이프라인
- `ImageManager`: 이미지 CRUD + 메타데이터 (크기, 포맷, URL, alt 텍스트)
- `ImageOptimizer`: 리사이즈 스펙 (thumbnail/medium/large), 변환 시뮬레이션 (mock)
- `WatermarkService`: 텍스트 워터마크 (위치/크기/투명도), 적용 시뮬레이션 (mock)
- `CDNUploader` ABC + `CloudinaryUploader`, `S3Uploader` mock 구현
- `ProductGallery`: 상품별 이미지 순서 관리, 대표 이미지 설정, 최대 10장
- API Blueprint: `src/api/images_api.py` (`/api/v1/images`)
- 봇 커맨드: `/images <product_id>`, `/image_upload <product_id> <url>`
- 관련 코드: `src/images/`

## Phase 47: 사용자 프로필 + 주소록 관리
- `UserManager`: 사용자 프로필 CRUD, 등급 (bronze→silver→gold→vip, 누적 구매 기준)
  - 등급별 혜택: 할인율, 무료배송 기준, 포인트 적립률
- `AddressBook`: 배송지 CRUD (최대 5개), 기본 배송지 설정, 필수 필드 유효성 검증
- `UserPreferences`: 언어 (ko/en/ja/zh), 통화, 알림 채널 (telegram/email/sms)
- `ActivityLog`: 활동 기록 (로그인/상품조회/주문/검색), 최근 N건 조회
- API Blueprint: `src/api/users_api.py` (`/api/v1/users`)
- 봇 커맨드: `/profile`, `/address_add`, `/my_activity`
- 관련 코드: `src/users/`

## Phase 48: 검색 엔진 + 필터링
- `SearchEngine`: 키워드 기반 인메모리 역인덱스, 한/영/중/일 지원, 스코어링 (제목 3x, 태그 2x, 설명 1x)
- `SearchFilter`: 가격 범위/카테고리/마켓플레이스/평점/재고 필터 (AND 로직)
- `SearchSorter`: price_asc/price_desc/newest/popularity/rating 정렬
- `Autocomplete`: 접두사 매칭, 인기 검색어 상위 10개, 최근 검색어
- `SearchAnalytics`: 검색어 빈도 집계, 결과 없는 검색어 추적, 클릭률 추적
- API Blueprint: `src/api/search_api.py` (`/api/v1/search`)
- 봇 커맨드: `/search <keyword>`, `/popular_searches`
- 관련 코드: `src/search/`

## Phase 49: 멀티테넌시
- `TenantManager`: 테넌트 CRUD, 플랜 관리, 상태 (active/inactive)
- `TenantConfig`: 테넌트별 설정 (마진율, 통화 전략, 배송 정책, 알림 설정)
- `TenantIsolation`: tenant_id 기반 데이터 격리 유틸리티
- `SubscriptionPlan`: free/basic/pro/enterprise 플랜, 기능/사용량 제한
- `UsageTracker`: 테넌트별 API 호출/주문/상품 사용량 추적
- API Blueprint: `src/api/tenancy_api.py` (`/api/v1/tenants`)
- 봇 커맨드: `/tenants`
- 관련 코드: `src/tenancy/`

## Phase 50: A/B 테스트 프레임워크
- `ExperimentManager`: 실험 CRUD (draft→running→stopped), 변형 목록 관리
- `VariantAssigner`: SHA-256 해시 기반 일관된 변형 할당
- `MetricsTracker`: 실험/변형별 이벤트 (impression/conversion/click/revenue) 추적
- `StatisticalAnalyzer`: Z-검정 통계적 유의성 분석, 표준정규분포 CDF 근사
- `ExperimentReport`: 실험 결과 보고서 (메트릭 + 유의성 검정)
- API Blueprint: `src/api/ab_testing_api.py` (`/api/v1/experiments`)
- 봇 커맨드: `/experiments`
- 관련 코드: `src/ab_testing/`

## Phase 51: 웹훅 관리
- `WebhookRegistry`: 웹훅 URL/이벤트/시크릿 CRUD, 활성/비활성 관리
- `WebhookSigner`: HMAC-SHA256 서명 및 검증
- `DeliveryLog`: 전달 기록 (상태코드, 응답, 성공여부, 재시도 횟수)
- `WebhookDispatcher`: HTTP POST 발송, 서명 추가, 실패 시 재시도 예약
- `RetryScheduler`: 지수 백오프 재시도 큐 (최대 5회, 60~1500초)
- API Blueprint: `src/api/webhook_manager_api.py` (`/api/v1/webhooks`)
- 관련 코드: `src/webhook_manager/`

## Phase 52: API 문서 자동 생성
- `EndpointScanner`: Flask URL map 스캔, 엔드포인트/메서드/블루프린트 추출
- `SchemaBuilder`: OpenAPI 3.0 파라미터/응답/요청 스키마 빌더
- `APIDocGenerator`: OpenAPI 3.0 스펙 자동 생성
- `DocRenderer`: OpenAPI 스펙을 HTML 테이블로 렌더링
- API Blueprint: `src/api/docs_api.py` (`/api/docs`, `/api/docs/openapi.json`)
- 관련 코드: `src/docs/`

## Phase 53: 구조화된 로깅/추적
- `StructuredLogger`: JSON 형식 구조화된 로그 (timestamp/level/message/service/trace_id)
- `TraceContext`: 스레드 로컬 trace_id/span_id 관리
- `RequestTracer`: 함수 데코레이터 기반 요청 추적 (시작/종료/소요시간)
- `LogAggregator`: 로그 수집/조회 (level/service/trace_id 필터, 최대 1000건)
- `CorrelationMiddleware`: Flask before/after 훅으로 X-Trace-ID 자동 주입
- API Blueprint: `src/api/traces_api.py` (`/api/v1/traces`)
- 관련 코드: `src/logging_tracing/`

## Phase 54: 성능 벤치마크
- `LoadProfile`: 부하 프로파일 (동시사용자/실행시간/램프업/대상URL/메서드)
- `ResponseAnalyzer`: 응답시간 통계 (p50/p95/p99/mean/min/max/count)
- `BenchmarkReport`: 벤치마크 결과 보고서 (통계+오류율+요약텍스트)
- `RegressionDetector`: 이전 결과 대비 성능 회귀 감지 (기본 임계값 20%)
- `BenchmarkRunner`: ThreadPoolExecutor 기반 병렬 부하 테스트 실행
- API Blueprint: `src/api/benchmark_api.py` (`/api/v1/benchmark`)
- CLI: `scripts/benchmark.py`
- 관련 코드: `src/benchmark/`
