# 변경 이력 (CHANGELOG)

모든 주요 변경 사항은 이 파일에 기록됩니다.
[Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

---

## [13.0.0] — 2026-03-24

### 추가 (Added)

**13-1: E2E 통합 테스트 (`tests/e2e/`)**
- `tests/e2e/test_order_flow.py` — Shopify/WooCommerce 주문 전체 플로우 E2E 테스트
- `tests/e2e/test_catalog_flow.py` — 카탈로그 동기화 전체 플로우 E2E 테스트
- `tests/e2e/test_notification_flow.py` — 알림 전체 플로우 E2E 테스트
- `tests/e2e/test_reorder_flow.py` — 재발주 전체 플로우 E2E 테스트
- `tests/e2e/conftest.py` — E2E 테스트 공용 fixture

**13-2: 설정 핫리로드 시스템 (`src/config/`)**
- `src/config/manager.py` — `ConfigManager` 싱글톤: env + YAML 로딩, 핫리로드, `on_change` 콜백
- `src/config/validator.py` — `ConfigValidator`: 필수값/타입/범위/의존성 검증
- `src/config/schema.py` — 전체 환경변수 스키마 정의 (`get_all_config_schema()`)
- `src/config/watcher.py` — `FileWatcher`: config.yml 변경 감지 데몬 스레드

**13-3: 운영 문서 최종화 (`docs/`)**
- `docs/ARCHITECTURE.md` — 전체 시스템 아키텍처 + 데이터 플로우 + 외부 서비스 목록
- `docs/API_REFERENCE.md` — 웹훅/Admin/Health/Config API 레퍼런스
- `docs/RUNBOOK.md` — 일일 운영 체크리스트 + 장애 대응 절차 + 운영 가이드
- `docs/CHANGELOG.md` — 본 파일

**13-4: 설정 관련 API 엔드포인트 (`src/api/config_routes.py`)**
- `GET /api/config/status` — 현재 설정 상태 (민감 데이터 마스킹)
- `POST /api/config/reload` — 설정 강제 재로드
- `GET /api/config/validate` — 설정 검증 결과

**13-5: 환경 설정 업데이트**
- `.env.example` — `CONFIG_HOT_RELOAD_ENABLED`, `CONFIG_CHECK_INTERVAL`, `CONFIG_STRICT_VALIDATION` 추가
- `config.example.yml` — `config:` 섹션 추가

**13-6: 단위 테스트**
- `tests/test_config_manager.py` — ConfigManager 테스트
- `tests/test_config_validator.py` — ConfigValidator 테스트
- `tests/test_config_watcher.py` — FileWatcher 테스트
- `tests/test_config_schema.py` — 스키마 테스트

---

## [12.0.0] — 2026-03

### 추가 (Added)

**12-1: 벤더 플러그인 아키텍처 (`src/plugins/`)**
- `VendorPlugin` ABC 베이스 클래스
- `PluginRegistry` — 자동 등록 + 로드
- Porter, Memo Paris 기본 플러그인

**12-2: 데이터 마이그레이션 (`src/migration/`)**
- `SchemaManager` — 스키마 버전 관리
- `Migrator` — 마이그레이션 실행/롤백
- `BackupManager` — 자동 백업

**12-3: 성능 프로파일링 (`src/profiling/`)**
- `ExecutionTimer` — 함수/API 실행 시간 측정
- `APIMetrics` — 엔드포인트별 성능 지표
- `ResourceMonitor` — CPU/메모리 모니터링

### 수정 (Fixed)

- CI/CD: `cd_staging.yml`, `cd_production.yml`에서 빈 시크릿(Render hook) 체크 조건 추가
- `curl: (3) URL rejected: Malformed input` 오류 수정

---

## [11.0.0] — 2026-03

### 추가 (Added)

**11-1: 관리자 대시보드 REST API (`src/api/`)**
- `GET /api/dashboard/summary` — 운영 현황 요약
- `GET /api/dashboard/orders` — 주문 목록
- `GET /api/dashboard/revenue` — 매출 데이터
- `GET /api/dashboard/inventory` — 재고 현황
- `GET /api/dashboard/fx` — 환율 현황
- `X-API-Key` 인증 미들웨어

**11-2: 데이터 내보내기 (`src/export/`)**
- CSV 내보내기 (주문/재고/매출/감사)
- 종합 리포트 생성
- GitHub Actions `scheduled_export.yml` — 일일/주간 정기 내보내기

**11-3: 통합 운영 CLI (`src/cli/`)**
- `sync`, `orders`, `inventory`, `fx`, `export`, `report`, `health`, `audit`, `cache` 커맨드

---

## [10.0.0] — 2026-03

### 추가 (Added)

**10-1: 미들웨어 계층 (`src/middleware/`)**
- `RateLimiter` — Flask-Limiter 기반 API 레이트 리미팅
- `RequestLogger` — JSON 구조화 요청 로깅
- `SecurityMiddleware` — 보안 헤더 + CORS

**10-2: 복원력 시스템 (`src/resilience/`)**
- `CircuitBreaker` — 서킷 브레이커 패턴
- `RetryHandler` — 지수 백오프 재시도
- `HealthMonitor` — 종합 헬스 모니터

**10-3: 데이터 검증 (`src/validation/`)**
- `OrderValidator` — 주문 페이로드 검증 + 중복 감지
- `ProductValidator` — 상품 데이터 검증
- `validate_schema()` — 범용 스키마 검증

**10-4: 인메모리 캐시 (`src/cache/`)**
- `MemoryCache` — TTL 기반 LRU 캐시
- `@cache_response` 데코레이터

**10-5: 감사 로그 (`src/audit/`)**
- `AuditLogger` — 이벤트 타입별 감사 기록
- `EventType` Enum — 15+ 이벤트 타입

---

## [9.0.0] — 2026-02

### 추가 (Added)

**9-1: 텔레그램 봇 (`src/bot/`)**
- `/status`, `/revenue`, `/stock`, `/fx`, `/help` 커맨드

**9-2: 고객 알림 (`src/notifications/`)**
- `CustomerNotifier` — 주문확인/배송시작/완료 이메일+텔레그램 자동 알림
- `NotificationHub` — 통합 알림 허브 (Telegram + Slack + Discord + Email)

**9-3: 자동 재발주 (`src/reorder/`)**
- `AutoReorder` — 재고 부족 감지 → 발주 큐 생성 → 텔레그램 승인 요청
- `ReorderQueue` — 발주 큐 관리

**9-4: 멀티채널 알림 허브**
- `SlackNotifier` — Slack 웹훅 연동
- `DiscordNotifier` — Discord 웹훅 연동

### 수정 (Fixed)

- `requirements-dev.txt` 생성 (pytest, pytest-cov, flake8)
- CI에서 dev 의존성 설치 문제 수정

---

## [8.0.0] — 2026-02

### 추가 (Added)

- 통합 테스트 강화 + flake8 CI 파이프라인
- 서킷 브레이커/재시도 패턴 기초 구현
- 프로덕션 안정화 패치

---

## [7.0.0] — 2026-01

### 추가 (Added)

**비즈니스 인텔리전스 + 운영 자동화 (`src/analytics/`)**
- `AutoPricing` — 마진 기반 자동 가격 조정
- `NewProductDetector` — 신규 상품 탐지
- `BusinessReport` — 주간/월간 리포트
- `ReorderAnalyzer` — 재고 소진 예측

---

## [6.0.0] — 2026-01

### 추가 (Added)

**6-1: 다국가 배송/세금 엔진 (`src/shipping/`)**
- 13개국 배송비 계산
- 관부가세 계산기
- 통관 서류 생성

**6-2: Shopify Markets 다통화 + 국제 라우팅**
- `ShopifyMarketsClient` — 다통화 가격 설정
- `InternationalRouter` — 국가별 라우팅

---

## [5.0.0] — 2025-12

### 추가 (Added)

- Docker + Gunicorn 프로덕션 배포 환경 구성
- Staging/Production 환경 분리
- CI/CD 자동 배포 파이프라인 (GitHub Actions)

---

## [4.0.0] — 2025-12

### 추가 (Added)

**4-1: 모니터링 대시보드 (`src/dashboard/`)**
- 주문/재고/환율 현황 모니터링
- 정기 리포트 자동 발송

**4-2: 재고 자동 동기화 (`src/inventory/`)**
- Porter/Memo Paris 재고 자동 확인
- 재고 부족 알림

**4-3: 실시간 환율 자동 연동 (`src/fx/`)**
- Frankfurter API 기반 실시간 환율
- 환율 변동 알림

---

## [3.0.0] — 2025-11

### 추가 (Added)

**주문 자동 라우팅 엔진 (`src/orders/`)**
- SKU 접두어 기반 벤더 식별
- 배대지(Zenmarket) 연동
- 주문 상태 추적

---

## [2.0.0] — 2025-11

### 추가 (Added)

**판매 채널 통합 (`src/channels/`)**
- 퍼센티 CSV 내보내기
- Shopify: HMAC 검증, GraphQL, 상품 upsert
- WooCommerce: 프로덕션 강화, 배치 업로드

---

## [1.0.0] — 2025-10

### 추가 (Added)

**코어 기능**
- 다중통화 지원 (JPY, EUR → KRW) + 랜딩 코스트 계산
- DeepL 다국어 번역 + 캐싱
- 소싱 벤더 모듈 (Porter, Memo Paris)
- 크롤러/스크래퍼 (Listly CSV → Sheets)
