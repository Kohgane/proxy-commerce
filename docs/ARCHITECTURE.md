# 시스템 아키텍처 (System Architecture)

## 전체 시스템 구성도

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Proxy Commerce Platform                            │
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────┐  │
│  │  Shopify     │    │ WooCommerce  │    │      Telegram Bot            │  │
│  │  Webhook     │    │  Webhook     │    │   (src/bot/)                 │  │
│  └──────┬───────┘    └──────┬───────┘    └──────────────┬───────────────┘  │
│         │                   │                           │                  │
│         └──────────┬────────┘                           │                  │
│                    ▼                                     ▼                  │
│         ┌──────────────────────┐           ┌────────────────────────────┐  │
│         │   Flask App          │           │   Bot Commands             │  │
│         │   (order_webhook.py) │           │   /status /revenue /stock  │  │
│         │                      │           └────────────────────────────┘  │
│         │  Middleware Stack:   │                                            │
│         │  - RateLimiter       │                                            │
│         │  - RequestLogger     │                                            │
│         │  - SecurityHeaders   │                                            │
│         └──────────┬───────────┘                                            │
│                    │                                                         │
│         ┌──────────▼───────────┐                                            │
│         │   Order Validator    │ ◄── 중복 주문 감지 + 스키마 검증             │
│         │   (src/validation/)  │                                            │
│         └──────────┬───────────┘                                            │
│                    │                                                         │
│         ┌──────────▼───────────┐                                            │
│         │   Order Router       │ ◄── SKU 접두어 → 벤더 매핑                 │
│         │   (src/orders/)      │                                            │
│         └──────┬───────┬───────┘                                            │
│                │       │                                                     │
│         ┌──────▼─┐  ┌──▼──────┐                                            │
│         │ Porter │  │MemoParis│  ← 소싱 벤더 (src/vendors/)                 │
│         └────────┘  └─────────┘                                            │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     알림 계층 (Notification Layer)                    │  │
│  │                                                                      │  │
│  │  ┌─────────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐    │  │
│  │  │  Telegram   │  │  Slack   │  │ Discord  │  │   Email       │    │  │
│  │  └─────────────┘  └──────────┘  └──────────┘  └───────────────┘    │  │
│  │         ▲                ▲            ▲                ▲            │  │
│  │         └────────────────┴────────────┴────────────────┘            │  │
│  │                    NotificationHub (src/notifications/)              │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     데이터 계층 (Data Layer)                          │  │
│  │                                                                      │  │
│  │  ┌────────────────┐    ┌────────────────┐    ┌────────────────────┐  │  │
│  │  │ Google Sheets  │    │   캐시 (TTL)    │    │   감사 로그         │  │  │
│  │  │ (카탈로그/주문) │    │  (src/cache/)  │    │  (src/audit/)      │  │  │
│  │  └────────────────┘    └────────────────┘    └────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 패키지별 역할 및 의존성

| 패키지 | 역할 | 주요 의존성 |
|--------|------|-------------|
| `src/order_webhook.py` | Flask 앱 진입점, 웹훅/헬스체크 라우팅 | `orders/`, `middleware/`, `validation/`, `audit/` |
| `src/orders/` | 주문 라우팅, 알림, 추적 | `catalog_lookup`, `utils/telegram` |
| `src/validation/` | 주문/상품 데이터 검증 | stdlib |
| `src/audit/` | 감사 로그 기록 | `utils/sheets` |
| `src/middleware/` | 레이트 리미팅, 요청 로깅, 보안 헤더 | `flask-limiter` |
| `src/resilience/` | 서킷 브레이커, 재시도, 헬스 모니터 | stdlib |
| `src/cache/` | 인메모리 TTL 캐시 | stdlib |
| `src/notifications/` | 고객 알림 + 멀티채널 허브 | `channels/` |
| `src/notifications/channels/` | Slack, Discord 웹훅 | `requests` |
| `src/bot/` | 텔레그램 봇 커맨드 | `utils/telegram` |
| `src/reorder/` | 자동 재발주 | `utils/sheets`, `utils/telegram` |
| `src/fx/` | 실시간 환율 | `requests`, `utils/sheets` |
| `src/inventory/` | 재고 동기화 | `vendors/`, `utils/sheets` |
| `src/analytics/` | BI + 자동 가격 조정 | `utils/sheets` |
| `src/dashboard/` | 운영 모니터링 | `utils/sheets` |
| `src/api/` | 관리자 대시보드 REST API | `auth_middleware`, `serializers` |
| `src/export/` | CSV/리포트 내보내기 | `utils/sheets` |
| `src/cli/` | 통합 운영 CLI | `src/*` 모든 패키지 |
| `src/channels/` | 판매 채널 (Percenty, Shopify, WooCommerce) | `vendors/` |
| `src/vendors/` | 소싱 벤더 클라이언트 | `requests` |
| `src/scrapers/` | 카탈로그 크롤러 | `requests`, `utils/sheets` |
| `src/shipping/` | 배송/세금 엔진 | stdlib |
| `src/plugins/` | 벤더 플러그인 아키텍처 | `vendors/` |
| `src/migration/` | 데이터 마이그레이션 | `utils/sheets` |
| `src/profiling/` | 성능 프로파일링 | stdlib |
| `src/config/` | 설정 핫리로드 + 검증 | `PyYAML`, `python-dotenv` |
| `src/auth/` | API 인증 | stdlib |
| `src/utils/` | 공통 유틸리티 (sheets, telegram, emailer) | `gspread`, `requests` |

## 데이터 플로우

### 주문 플로우

```
[Shopify Webhook]
       │  POST /webhook/shopify/order
       ▼
[SecurityMiddleware] → HMAC 검증 (X-Shopify-Hmac-Sha256)
       │
       ▼
[RateLimiter] → 분당 요청 수 제한
       │
       ▼
[OrderValidator] → 스키마 검증 + 중복 주문 감지
       │  실패 → 400 / 중복 → 200 (skipped)
       ▼
[OrderRouter] → SKU 접두어로 벤더 식별 → 구매 태스크 생성
       │
       ▼
[OrderStatusTracker] → Google Sheets orders 워크시트 기록
       │
       ▼
[OrderNotifier] → Telegram 알림 발송
       │
       ▼
[AuditLogger] → audit_log 워크시트 기록
       │
       ▼
[Response] → 200 OK {ok: true, tasks: {...}}
```

### 카탈로그 동기화 플로우

```
[Google Sheets: catalog]
       │  open_sheet()
       ▼
[catalog_sync.py] → row_to_product() 변환
       │
       ├──▶ [translate.py] → 언어 자동 번역 (DeepL/Papago)
       │
       ├──▶ [price.py] → FX 적용 + 마진 계산
       │         └── [fx/provider.py] → 실시간 환율
       │
       ├──▶ [image_uploader.py] → Cloudinary 이미지 업로드
       │
       ├──▶ [vendors/shopify_client.py] → Shopify 상품 upsert
       │
       └──▶ [vendors/woocommerce_client.py] → WooCommerce 상품 upsert
```

## 외부 서비스 연동 목록

| 서비스 | 연동 목적 | 관련 환경변수 |
|--------|-----------|---------------|
| **Google Sheets** | 카탈로그/주문/재고/감사로그 데이터 저장소 | `GOOGLE_SERVICE_JSON_B64`, `GOOGLE_SHEET_ID` |
| **Shopify** | 상품 업로드, 주문 수신, 다통화 | `SHOPIFY_SHOP`, `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_CLIENT_SECRET` |
| **WooCommerce** | 상품 업로드, 주문 수신 | `WOO_BASE_URL`, `WOO_CK`, `WOO_CS`, `WOO_WEBHOOK_SECRET` |
| **DeepL** | 상품명 번역 (KO ↔ EN) | `DEEPL_API_KEY`, `DEEPL_API_URL` |
| **Telegram** | 운영 알림, 봇 커맨드, 재발주 승인 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| **Slack** | 주문/오류 알림 | `SLACK_WEBHOOK_URL` |
| **Discord** | 오류 알림 | `DISCORD_WEBHOOK_URL` |
| **Cloudinary** | 상품 이미지 업로드/CDN | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` |
| **Frankfurter API** | 실시간 환율 (USD/JPY/EUR → KRW) | `FX_USE_LIVE`, `FX_SOURCE` |
| **SMTP** | 고객 이메일 알림 | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` |
| **Render** | 스테이징/프로덕션 자동 배포 | `RENDER_DEPLOY_HOOK_STAGING`, `RENDER_DEPLOY_HOOK_PRODUCTION` |

## 환경별 설정 차이 (Staging vs Production)

| 항목 | Staging | Production |
|------|---------|------------|
| `APP_ENV` | `staging` | `production` |
| `MODE` | `DRY_RUN` | `APPLY` |
| `GUNICORN_WORKERS` | 1 | 4 |
| `GUNICORN_LOG_LEVEL` | `debug` | `warning` |
| `AUTO_PRICING_MODE` | `DRY_RUN` | `APPLY` |
| `AUDIT_LOG_ENABLED` | `1` | `1` |
| `RATE_LIMIT_ENABLED` | `1` | `1` |
| `CUSTOMER_NOTIFY_ENABLED` | `0` | `1` |
| `CONFIG_HOT_RELOAD_ENABLED` | `0` | `0` |
| `CONFIG_STRICT_VALIDATION` | `0` | `1` |

## 보안 계층

1. **HMAC 검증**: Shopify 웹훅 서명 검증 (`X-Shopify-Hmac-Sha256`)
2. **Webhook Secret**: WooCommerce 웹훅 시크릿 검증
3. **API Key 인증**: 관리자 API (`X-API-Key` 헤더)
4. **Rate Limiting**: Flask-Limiter 기반 분당 요청 수 제한
5. **CORS**: 허용 오리진 환경변수 제어
6. **보안 헤더**: X-Content-Type-Options, X-Frame-Options 등
7. **콘텐츠 크기 제한**: 요청 본문 최대 1MB
