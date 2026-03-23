# 운영 매뉴얼 — Proxy Commerce

> 이 문서는 Proxy Commerce 플랫폼의 운영팀을 위한 절차서입니다.

---

## 목차

1. [배포 절차](#배포-절차)
2. [장애 대응 매뉴얼](#장애-대응-매뉴얼)
3. [모니터링 체크리스트](#모니터링-체크리스트)
4. [시크릿 로테이션 가이드](#시크릿-로테이션-가이드)
5. [일일/주간 운영 체크리스트](#일일주간-운영-체크리스트)

---

## 배포 절차

### Staging 배포

Staging 배포는 `main` 브랜치 push 시 **자동**으로 실행됩니다.

수동 배포가 필요한 경우:
```bash
# 1. Staging 환경변수 확인
python scripts/validate_env.py --env staging

# 2. Docker 이미지 빌드
docker build -t proxy-commerce:staging .

# 3. Staging Compose 실행
docker-compose -f docker-compose.staging.yml up -d

# 4. 헬스체크 확인 (Staging 포트: 8001)
curl http://staging-server:8001/health/deep

# 5. 스모크 테스트
python scripts/post_deploy_check.py --url http://staging-server:8001
```

**Staging 검증 항목:**
- [ ] `/health` 200 OK
- [ ] `/health/ready` 200 OK (core secrets 설정 확인)
- [ ] `/health/deep` 200 OK (Sheets 연결 확인)
- [ ] 테스트 주문 수동 라우팅 확인
- [ ] Telegram 알림 수신 확인

### Production 배포

Production 배포는 `v*` 태그 push + **수동 승인** 후 실행됩니다.

```bash
# 1. 변경사항 최종 확인
git log --oneline main..HEAD

# 2. 태그 생성 및 push
git tag v8.0.0 -m "Phase 8: 프로덕션 안정화"
git push origin v8.0.0

# 3. GitHub Actions > cd_production.yml 에서 Approve 클릭

# 4. 배포 후 검증 (약 3~5분 소요)
python scripts/post_deploy_check.py --url https://production-server.com

# 5. 배포 완료 Telegram 알림 확인
```

**Production 배포 체크리스트:**
- [ ] Staging 테스트 모두 통과
- [ ] flake8 린트 통과
- [ ] pytest 전체 통과 (944+)
- [ ] 환경변수 시크릿 최신화 확인
- [ ] 데이터베이스/Sheets 백업 확인
- [ ] 롤백 계획 준비

### 롤백 절차

```bash
# 이전 버전으로 롤백 (git tag 방식)
git tag v8.0.0-rollback v7.x.x  # 안전한 이전 태그
git push origin v8.0.0-rollback

# Docker 이미지 롤백
docker-compose -f docker-compose.production.yml down
docker run -p 8000:8000 --env-file .env.production proxy-commerce:<previous-tag>

# 긴급 롤백 (Render)
render deploys rollback --service proxy-commerce-production
```

---

## 장애 대응 매뉴얼

### 장애 1: 웹훅 서버 응답 없음

**증상:** `/health` 엔드포인트 타임아웃 또는 500 에러

**원인 파악:**
```bash
# 컨테이너 상태 확인
docker ps -a | grep proxy-commerce
docker logs proxy-commerce --tail=100

# 프로세스 확인
ps aux | grep gunicorn

# 포트 확인
ss -tlnp | grep 8000
```

**대응 절차:**
1. `docker restart proxy-commerce` (즉시 재시작)
2. 로그에서 오류 확인 후 원인 조치
3. 환경변수 누락 시 `.env` 파일 확인 후 재시작
4. 재시작 후 30초 내 `/health` 응답 확인

---

### 장애 2: Google Sheets 연결 실패

**증상:** `/health/deep`에서 `google_sheets: false`, `WorksheetNotFound` 오류

**원인 파악:**
```bash
# 시크릿 검증
python scripts/validate_env.py

# Sheets 연결 테스트
python -c "
from src.utils.sheets import open_sheet
import os
ws = open_sheet(os.environ['GOOGLE_SHEET_ID'], 'catalog')
print('Connected:', ws.title)
"
```

**대응 절차:**
1. `GOOGLE_SERVICE_JSON_B64` 값 확인 (base64 디코딩 후 JSON 유효성 검사)
2. 서비스 계정에 Sheets 편집 권한 있는지 확인
3. `WorksheetNotFound` 오류: 해당 워크시트가 없으면 수동 생성
   - 필요 워크시트: `catalog`, `orders`, `fx_rates`, `fx_history`
4. Google API 할당량 초과 시 1시간 후 재시도

---

### 장애 3: Shopify 웹훅 HMAC 검증 실패

**증상:** `/webhook/shopify/order` 에 401 응답

**원인 파악:**
```bash
# 시크릿 확인
echo $SHOPIFY_CLIENT_SECRET | wc -c  # 값이 있는지 확인

# HMAC 검증 테스트 (로그 확인)
docker logs proxy-commerce --tail=20 | grep -i hmac
```

**대응 절차:**
1. `SHOPIFY_CLIENT_SECRET`이 현재 앱의 Client Secret과 일치하는지 확인
2. Shopify Admin > Apps > API credentials에서 Client Secret 재확인
3. 시크릿 로테이션이 필요한 경우 [시크릿 로테이션 가이드](#시크릿-로테이션-가이드) 참조

---

### 장애 4: Telegram 알림 미수신

**증상:** 주문 라우팅은 성공하지만 Telegram 알림 없음

**원인 파악:**
```bash
# 토큰/채팅ID 확인
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}&text=test"
```

**대응 절차:**
1. Bot Token이 유효한지 확인 (`getMe` API 응답 확인)
2. Chat ID가 올바른지 확인 (그룹은 `-100`으로 시작)
3. 봇이 채널/그룹에 추가되어 있는지 확인
4. `TELEGRAM_ENABLED=1` 환경변수 설정 확인

---

### 장애 5: 환율 업데이트 실패

**증상:** `fx_update` GitHub Actions 워크플로 실패

**원인 파악:**
```bash
# 환율 API 직접 테스트
curl "https://api.frankfurter.app/latest?from=USD&to=KRW"

# 현재 환율 캐시 상태
python -m src.fx.cli --action current
```

**대응 절차:**
1. frankfurter.app API 장애 시 `FX_PROVIDER=exchangerate-api`로 전환 후 `EXCHANGERATE_API_KEY` 설정
2. 수동으로 환율 강제 갱신: `python -m src.fx.cli --action update --force`
3. 1시간 이상 업데이트 불가 시 수동 환율(`FX_USDKRW` 등) 환경변수로 폴백

---

### 장애 6: 재고 동기화 실패

**증상:** `inventory_sync` 워크플로 실패 또는 재고 데이터 불일치

**원인 파악:**
```bash
# 재고 동기화 DRY_RUN 테스트
python -m src.inventory.cli --action full-sync --dry-run

# 특정 SKU 확인
python -m src.inventory.cli --action check --sku PTR-TNK-001
```

**대응 절차:**
1. 벤더 사이트 접근 가능 여부 확인 (yoshidakaban.com, memoparis.com)
2. `STOCK_CHECK_DELAY` 값 증가 (기본 2초 → 5초)로 재시도:
   ```bash
   # .env 또는 GitHub Secrets에서 환경변수 수정
   STOCK_CHECK_DELAY=5
   docker restart proxy-commerce
   ```
3. 특정 SKU만 오류 시 해당 `src_url` 유효성 확인
4. Shopify/WooCommerce API 오류 시 인증 토큰 재확인

---

### 장애 7: Rate Limiter 429 오류

**증상:** 웹훅 엔드포인트에서 429 Too Many Requests 응답

**원인 파악:**
```bash
# Rate Limiter 설정 확인
echo $RATE_LIMIT_WEBHOOK  # 기본: "60 per minute"
echo $RATE_LIMIT_ENABLED  # 기본: "1"
```

**대응 절차:**
1. 정당한 트래픽이면 `RATE_LIMIT_WEBHOOK` 값 상향 (예: `120 per minute`)
2. 비정상 트래픽 공격 의심 시 Cloudflare 등 WAF에서 IP 차단
3. 테스트/개발 환경에서는 `RATE_LIMIT_ENABLED=0`으로 비활성화

---

## 모니터링 체크리스트

### 실시간 모니터링

```bash
# 헬스체크 모니터링 스크립트
watch -n 30 'curl -s http://localhost:8000/health | python3 -m json.tool'

# 로그 실시간 확인
docker logs -f proxy-commerce 2>&1 | grep -E "ERROR|WARNING|order_id"
```

### 매일 확인 항목

- [ ] `/health/deep` 모든 체크 통과
- [ ] GitHub Actions 최근 워크플로 성공 여부
- [ ] Google Sheets `orders` 시트 새 주문 기록 확인
- [ ] Telegram 일일 요약 수신 확인
- [ ] 미처리 주문(`pending` 상태) 없는지 확인:
  ```bash
  python -m src.dashboard.cli --action status --filter pending
  ```

### 주간 확인 항목

- [ ] 환율 변동 이상 없는지 확인 (±5% 이상이면 점검)
- [ ] 재고 부족 상품 목록 확인
- [ ] 마진율 이상 저하 상품 확인 (15% 미만)
- [ ] Google Sheets 용량 확인 (5MB 초과 시 정리)
- [ ] Rate Limiter 로그에서 비정상 패턴 확인

---

## 시크릿 로테이션 가이드

### 로테이션 빈도 권장 사항

| 시크릿 | 권장 로테이션 주기 | 우선순위 |
|--------|------------------|---------|
| `SHOPIFY_ACCESS_TOKEN` | 90일 | 높음 |
| `SHOPIFY_CLIENT_SECRET` | 앱 재생성 시 | 높음 |
| `WOO_CK` / `WOO_CS` | 90일 | 높음 |
| `DEEPL_API_KEY` | 180일 | 중간 |
| `TELEGRAM_BOT_TOKEN` | 필요 시 | 낮음 |
| `GOOGLE_SERVICE_JSON_B64` | 365일 | 중간 |

### Shopify 토큰 로테이션

```bash
# 1. Shopify Admin에서 새 Access Token 생성
# 2. GitHub Secrets 업데이트 (GitHub CLI 사용)
gh secret set SHOPIFY_ACCESS_TOKEN --body "shpat_new_token" --repo Kohgane/proxy-commerce

# 3. 서버 재시작
docker restart proxy-commerce

# 4. 헬스체크 확인
curl http://localhost:8000/health/deep
```

### Google 서비스 계정 키 로테이션

```bash
# 1. Google Cloud Console에서 새 키 생성
# 2. 새 키를 base64로 인코딩
base64 -i new-service-account.json | tr -d '\n' > new_key_b64.txt

# 3. GitHub Secrets 업데이트
gh secret set GOOGLE_SERVICE_JSON_B64 < new_key_b64.txt --repo Kohgane/proxy-commerce

# 4. 구 키 즉시 폐기 (Google Cloud Console)
# 5. 서버 재시작 + 검증
docker restart proxy-commerce && curl http://localhost:8000/health/deep
```

### WooCommerce API 키 로테이션

```bash
# 1. WooCommerce Admin > Settings > Advanced > REST API에서 새 키 생성
# 2. GitHub Secrets 업데이트
gh secret set WOO_CK --body "ck_new_key" --repo Kohgane/proxy-commerce
gh secret set WOO_CS --body "cs_new_secret" --repo Kohgane/proxy-commerce

# 3. 재시작 + 검증
```

---

## 일일/주간 운영 체크리스트

### 일일 체크리스트 (10분)

```
□ 오전 점검 (09:00)
  □ GitHub Actions 야간 워크플로 결과 확인 (daily_summary, fx_update)
  □ Telegram 일일 요약 메시지 수신 확인
  □ /health/deep 엔드포인트 정상 응답 확인
  □ 미처리 주문 확인: python -m src.dashboard.cli --action status --filter pending

□ 오후 점검 (18:00)
  □ 당일 신규 주문 라우팅 처리 여부 확인
  □ 재고 동기화 결과 확인 (inventory_sync 워크플로)
  □ 가격 이상 변동 알림 확인 (환율 변동 시 auto_pricing_check 결과)
```

### 주간 체크리스트 (30분, 매주 월요일)

```
□ 주간 리포트 확인 (weekly_report 워크플로 결과)
  □ 지난 주 매출/마진 분석
  □ 베스트셀러 상품 확인
  □ 마진 위험 SKU 점검 (15% 미만)
  □ 국가별 매출 분포 확인

□ 재고 점검
  □ 재고 부족 상품 목록: python -m src.inventory.cli --action report
  □ 재주문 필요 상품 확인: python -m src.analytics.cli --action reorder-check
  □ 신상품 감지 결과 검토: python -m src.analytics.cli --action detect-new-products

□ 인프라 점검
  □ Docker 컨테이너 메모리 사용량 확인
  □ Google Sheets 데이터 용량 확인
  □ 시크릿 만료일 확인 (3개월 이내 만료 시 로테이션)

□ 보안 점검
  □ Rate Limiter 로그에서 비정상 접근 패턴 확인
  □ Shopify 웹훅 실패 로그 확인
  □ 의심스러운 주문 패턴 확인 (봇 주문 등)
```

### 긴급 연락 및 에스컬레이션

| 상황 | 담당 | 연락 방법 |
|------|------|----------|
| 서버 다운 | 운영팀 | Telegram 즉시 알림 |
| 결제 오류 | 개발팀 | GitHub Issues 등록 |
| 데이터 유실 | 개발팀+운영팀 | 직접 연락 |
| 보안 사고 | 모든 팀 | 즉시 시크릿 로테이션 |
