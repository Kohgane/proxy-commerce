# 안정화 체크리스트 (STABILIZATION_CHECKLIST.md)

> 사이트를 보면서 수정을 반복할 수 있도록 각 Phase별 known limitation과 실서비스 전환 절차를 정리합니다.  
> **최종 업데이트**: 2026-05-02 (Phase 120)

---

## Phase별 Known Limitation

### 🔴 P0 — 즉시 해결 필요 (실서비스 전환 전 필수)

| Phase | 모듈 | Known Limitation | 해결 방법 |
|-------|------|------------------|----------|
| 1–13 | `src/fx/` | `FX_DISABLE_NETWORK=1` 로 mock 환율 사용 중 | FX API 키 발급 후 `FX_DISABLE_NETWORK` 제거 또는 `0`으로 설정 |
| 98 | `src/woocommerce_publisher/` | `WOO_BASE_URL` 미설정 시 게시 불가 | Render에서 WooCommerce 환경변수 등록 |
| 96/101 | `src/auto_purchase/` | `MODE=DRY_RUN` 시 실제 구매 없음 | `MODE=APPLY` 로 변경 (신중하게) |
| 119 | `src/finance_accounting/` | DB 없이 in-memory 원장 사용 (재시작 시 초기화) | SQLite 또는 PostgreSQL 연결 설정 |

---

### 🟡 P1 — 조기 해결 권장 (1개월 내)

| Phase | 모듈 | Known Limitation | 해결 방법 |
|-------|------|------------------|----------|
| 117 | `src/delivery_notifications/` | 이메일 전송 mock (실제 발송 없음) | SMTP 환경변수 설정 (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`) |
| 118 | `src/returns_automation/` | PG 환불은 mock (실제 환불 없음) | `TOSS_SECRET_KEY` 설정 후 환불 엔드포인트 실 연동 |
| 27 | `src/shipping/` | 택배 조회 API 키 없으면 mock 데이터 반환 | 스마트택배 API 키 발급 |
| 22 | `src/payment/` | 토스페이먼츠 테스트 키 사용 중 | 실 키로 교체 (`TOSS_CLIENT_KEY`, `TOSS_SECRET_KEY`) |
| 95 | `src/mobile_api/` | API 문서(`/api/docs`) 인증 없음 | `DOCS_AUTH_ENABLED=1` 설정 |

---

### 🟢 P2 — 점진적 개선 (3개월 내)

| Phase | 모듈 | Known Limitation | 해결 방법 |
|-------|------|------------------|----------|
| 23 | `monitoring/` | Grafana/Prometheus 설정 파일만 있고 실제 서버 없음 | Render + Grafana Cloud 무료 플랜 연동 |
| 49 | `src/multitenancy/` | 단일 테넌트로만 테스트됨 | 멀티테넌트 E2E 테스트 추가 |
| 80 | `src/data_sync/` | 외부 DB 없이 Sheets 기반 동기화 | PostgreSQL 도입 시 마이그레이션 |
| 115 | `src/sourcing_discovery/` | 트렌드 수집 외부 API mock | 실 API 키 연결 |

---

## 실서비스 전환 키/계정 목록

### 즉시 필요 (P0)

| 계정/키 | 발급 위치 | 환경변수 | 예상 비용 |
|---------|----------|----------|----------|
| Telegram Bot | [@BotFather](https://t.me/BotFather) | `TELEGRAM_BOT_TOKEN` | 무료 |
| WooCommerce API Key | 사이트 관리자 → REST API | `WOO_CK`, `WOO_CS` | 무료 |
| Cloudflare 도메인 | [dash.cloudflare.com](https://dash.cloudflare.com) | `CF_API_TOKEN` | $9.77/년 |
| Render 배포 | [dashboard.render.com](https://dashboard.render.com) | `RENDER_API_TOKEN` | 이미 결제 완료 |

### 조기 필요 (P1)

| 계정/키 | 발급 위치 | 환경변수 | 예상 비용 |
|---------|----------|----------|----------|
| 토스페이먼츠 실키 | [developers.tosspayments.com](https://developers.tosspayments.com) | `TOSS_CLIENT_KEY`, `TOSS_SECRET_KEY` | 수수료 1.5–3.3% |
| 스마트택배 API | [tracker.delivery](https://tracker.delivery) | `TRACKER_API_KEY` | 무료 플랜 있음 |
| SMTP (이메일 발송) | Gmail/Naver/SendGrid | `SMTP_HOST` 등 | 무료~$15/월 |
| Amazon SP-API | [sellercentral.amazon.com](https://sellercentral.amazon.com) | `AMAZON_SP_*` | 무료 (판매 계정 필요) |

### 나중에 필요 (P2)

| 계정/키 | 발급 위치 | 환경변수 | 예상 비용 |
|---------|----------|----------|----------|
| 쿠팡 파트너스 API | [partners.coupang.com](https://partners.coupang.com) | `COUPANG_ACCESS_KEY` | 무료 |
| 네이버 커머스 API | [developers.naver.com](https://developers.naver.com) | `NAVER_CLIENT_ID` | 무료 |
| Google Sheets Service Account | [console.cloud.google.com](https://console.cloud.google.com) | `GOOGLE_SERVICE_JSON_B64` | 무료 |
| Shopify Private App | Shopify 관리자 | `SHOPIFY_ACCESS_TOKEN` | 월 $29~ |

---

## 우선순위 안정화 작업 큐

### P0 — 즉시 처리 (이번 주)

- [ ] `FX_DISABLE_NETWORK=0` 으로 전환 후 환율 API 정상 동작 확인
- [ ] WooCommerce 환경변수 Render에 등록 (`WOO_BASE_URL`, `WOO_CK`, `WOO_CS`)
- [ ] `kohganepercentiii.com` 도메인 구매 (Cloudflare Registrar)
- [ ] Render 커스텀 도메인 추가 (`python scripts/render_domain_attach.py`)
- [ ] Cloudflare DNS 설정 (`python scripts/cloudflare_setup.py`)
- [ ] 헬스체크 확인: `curl https://kohganepercentiii.com/health`

### P1 — 이번 달

- [ ] 토스페이먼츠 실 키로 교체 후 결제 테스트
- [ ] 이메일 발송 SMTP 연결
- [ ] 배송 추적 API 키 발급 + 연결
- [ ] Phase 117/118/119 통합 E2E 테스트 (실 주문 시뮬레이션)
- [ ] Render 메트릭 모니터링 설정 (UptimeRobot 등)

### P2 — 다음 분기

- [ ] PostgreSQL 도입 (in-memory 정산 → DB 영속)
- [ ] Grafana Cloud 무료 플랜 연동
- [ ] 쿠팡/네이버 채널 실 연동
- [ ] 모바일 앱 API 인증 강화
- [ ] Phase 122: E2E 통합 테스트 전 사이클

---

## Issue 자동 생성 스크립트 (선택)

다음 명령으로 P0 작업 항목들을 GitHub Issue로 자동 생성할 수 있습니다:

```bash
# GitHub CLI 필요
gh issue create --title "[P0] FX_DISABLE_NETWORK 해제 후 환율 API 검증" \
  --label "priority:p0,stability" \
  --body "FX_DISABLE_NETWORK=0으로 전환 후 환율 API 정상 동작 확인\n\n참고: docs/operations/STABILIZATION_CHECKLIST.md"

gh issue create --title "[P0] WooCommerce 환경변수 Render 등록" \
  --label "priority:p0,stability" \
  --body "WOO_BASE_URL, WOO_CK, WOO_CS를 Render 대시보드에 등록\n\n참고: docs/deployment/ENV_VARS.md"
```
