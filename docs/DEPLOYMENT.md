# 배포 가이드 (Deployment Guide)

## 환경 분리 (Environment Separation)

이 프로젝트는 두 개의 분리된 배포 환경을 사용합니다.

| 환경 | 브랜치/트리거 | 모드 | Gunicorn Workers |
|------|--------------|------|-----------------|
| **staging** | `main` 머지 시 자동 | `DRY_RUN` | 1 |
| **production** | Git 태그 `v*` 푸시 | `APPLY` | 4 |

---

## Staging 배포

`main` 브랜치에 머지되면 GitHub Actions (`cd_staging.yml`)가 자동으로 실행됩니다.

```
main 브랜치 머지 → 테스트 실행 → Docker 이미지 빌드 → GHCR 푸시 → Render 배포 → 헬스체크
```

### 수동 트리거

Staging 배포를 수동으로 실행하려면:

```bash
gh workflow run cd_staging.yml
```

---

## Production 배포

Git 태그를 생성하고 푸시하면 자동 배포됩니다.

```bash
git tag v1.0.0
git push origin v1.0.0
```

배포 흐름:

```
태그 푸시 → 테스트 실행 → Docker 이미지 빌드 → GHCR 푸시 → Render 배포 → 헬스체크 → 실패 시 자동 롤백
```

### 버전 태그 규칙

- 형식: `vMAJOR.MINOR.PATCH` (예: `v1.2.3`)
- MAJOR: 하위 호환성이 없는 변경
- MINOR: 하위 호환 기능 추가
- PATCH: 버그 수정

---

## Render 설정 가이드

### 서비스 등록

`render.yaml`을 사용하거나 Render 대시보드에서 수동으로 서비스를 생성합니다.

1. [Render 대시보드](https://dashboard.render.com) 접속
2. **New** → **Web Service** 선택
3. GitHub 저장소 연결
4. 환경별 서비스 이름 설정:
   - Staging: `proxy-commerce-staging`
   - Production: `proxy-commerce-production`

### Deploy Hook 설정

각 서비스의 **Settings** → **Deploy Hook** URL을 복사하여 GitHub Secrets에 등록합니다.

| Secret 이름 | 용도 |
|------------|------|
| `RENDER_DEPLOY_HOOK_STAGING` | Staging 배포 트리거 |
| `RENDER_DEPLOY_HOOK_PRODUCTION` | Production 배포 트리거 |
| `RENDER_ROLLBACK_HOOK_PRODUCTION` | Production 롤백 트리거 |

### Render 환경 변수

`render.yaml`에 정의된 변수들은 `sync: false`로 설정되어 있어 Render 대시보드에서 수동으로 입력해야 합니다.

---

## 시크릿 관리

### GitHub Secrets 등록

GitHub 저장소 **Settings** → **Secrets and variables** → **Actions**에서 등록합니다.

#### Staging 환경 (environment: staging)

| Secret | 설명 |
|--------|------|
| `STAGING_GOOGLE_SERVICE_JSON_B64` | Google 서비스 계정 JSON (Base64) |
| `STAGING_GOOGLE_SHEET_ID` | Google Sheet ID |
| `STAGING_SHOPIFY_SHOP` | Shopify 스토어 도메인 |
| `STAGING_SHOPIFY_ACCESS_TOKEN` | Shopify Access Token (`shpat_`로 시작) |
| `STAGING_SHOPIFY_CLIENT_SECRET` | Shopify Client Secret (`shpss_`로 시작) |
| `STAGING_WOO_BASE_URL` | WooCommerce 스토어 URL |
| `STAGING_WOO_CK` | WooCommerce Consumer Key |
| `STAGING_WOO_CS` | WooCommerce Consumer Secret |
| `STAGING_TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `STAGING_TELEGRAM_CHAT_ID` | Telegram Chat ID |
| `STAGING_APP_URL` | Staging 앱 URL (헬스체크용) |

#### Production 환경 (environment: production)

| Secret | 설명 |
|--------|------|
| `PROD_GOOGLE_SERVICE_JSON_B64` | Google 서비스 계정 JSON (Base64) |
| `PROD_GOOGLE_SHEET_ID` | Google Sheet ID |
| `PROD_SHOPIFY_SHOP` | Shopify 스토어 도메인 |
| `PROD_SHOPIFY_ACCESS_TOKEN` | Shopify Access Token (`shpat_`로 시작) |
| `PROD_SHOPIFY_CLIENT_SECRET` | Shopify Client Secret (`shpss_`로 시작) |
| `PROD_WOO_BASE_URL` | WooCommerce 스토어 URL |
| `PROD_WOO_CK` | WooCommerce Consumer Key |
| `PROD_WOO_CS` | WooCommerce Consumer Secret |
| `PROD_TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `PROD_TELEGRAM_CHAT_ID` | Telegram Chat ID |
| `PRODUCTION_APP_URL` | Production 앱 URL (헬스체크용) |

### 환경 변수 검증

배포 전 환경 변수가 올바르게 설정되었는지 확인합니다.

```bash
# Staging 환경 검증
python scripts/validate_env.py --env staging

# Production 환경 검증
python scripts/validate_env.py --env production
```

### .env 파일 생성

환경 변수 템플릿에서 실제 `.env` 파일을 생성합니다.

```bash
# Staging용 .env 생성
python scripts/generate_env.py --env staging --output .env

# Production용 .env 생성
python scripts/generate_env.py --env production --output .env
```

---

## 롤백 절차

### 자동 롤백 (Production)

Production 배포 후 헬스체크가 실패하면 자동으로 롤백이 실행되고 Telegram으로 알림이 전송됩니다.

### 수동 롤백

#### Render 대시보드에서 롤백

1. Render 대시보드 → 해당 서비스 선택
2. **Deploys** 탭 → 이전 성공 배포 선택
3. **Rollback to this deploy** 클릭

#### Render API로 롤백

```bash
# RENDER_ROLLBACK_HOOK_PRODUCTION에 이전 배포 SHA를 사용
curl -fsSL -X POST "${RENDER_ROLLBACK_HOOK_PRODUCTION}"
```

#### Docker 이미지로 롤백

```bash
# GHCR에서 이전 버전 이미지 확인
docker pull ghcr.io/kohgane/proxy-commerce:v1.0.0

# 로컬에서 이전 버전 실행
docker run --env-file .env.production -p 8000:8000 \
  ghcr.io/kohgane/proxy-commerce:v1.0.0
```

---

## Healthcheck 엔드포인트

| 경로 | 설명 | 기대 응답 |
|------|------|----------|
| `GET /health` | 기본 생존 확인 | `200 OK` |
| `GET /health/ready` | 준비 상태 확인 (DB 연결 등) | `200 OK` |

### 수동 헬스체크 실행

```bash
# 기본 헬스체크
python scripts/post_deploy_check.py --url https://your-app.onrender.com --env staging

# 재시도 설정
python scripts/post_deploy_check.py \
  --url https://your-app.onrender.com \
  --env production \
  --retries 3 \
  --interval 10
```

---

## 모니터링 알림 설정

배포 결과는 Telegram으로 알림이 전송됩니다.

| 이벤트 | 메시지 |
|--------|--------|
| 배포 성공 | `✅ [env] 배포 완료 - vX.X.X, 모든 체크 정상` |
| 배포 실패 | `❌ [env] 배포 실패 - {오류 상세}` |
| 자동 롤백 | `🔄 [production] 롤백 실행 - vX.X.X 배포 실패로 인한 자동 롤백` |

### Telegram Bot 설정

1. [@BotFather](https://t.me/BotFather)에서 새 Bot 생성
2. Bot Token 복사 → GitHub Secrets에 등록
3. Bot과 대화 시작 후 Chat ID 확인:
   ```bash
   curl "https://api.telegram.org/bot{TOKEN}/getUpdates"
   ```
4. Chat ID → GitHub Secrets에 등록

### Docker Compose로 로컬 테스트

```bash
# Staging 환경 로컬 실행
docker compose -f docker-compose.staging.yml up

# Production 환경 로컬 실행
docker compose -f docker-compose.production.yml up
```
