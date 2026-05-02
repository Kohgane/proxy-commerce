# 환경변수 레퍼런스 (ENV_VARS.md)

이 문서는 `proxy-commerce` Flask 앱을 실행할 때 필요한 모든 환경변수를 **PUBLIC / SECRET / OPTIONAL** 세 가지로 분류하여 설명합니다.

---

## 분류 기준

| 분류 | 설명 |
|------|------|
| **PUBLIC** | 공개 가능. `render.yaml`에 평문으로 정의해도 무방 |
| **SECRET** | Render 대시보드 > **Environment** 탭에서 직접 입력 (`sync: false`) |
| **OPTIONAL** | 미설정 시 기본값 사용 또는 해당 기능 비활성화 |

---

## 필수 환경변수 (PUBLIC)

| 변수명 | 예시값 | 설명 |
|--------|--------|------|
| `APP_ENV` | `production` | 실행 환경. `production` / `staging` / `ci` |
| `PORT` | `10000` | gunicorn 바인딩 포트. Render Free tier는 **10000** 고정 |
| `FX_DISABLE_NETWORK` | `1` | Phase 117 안정화 가드. `1`로 설정 시 FX API 외부 호출 차단, 캐시/mock 사용 |
| `GUNICORN_WORKERS` | `2` | gunicorn 워커 수. Render Free(512MB RAM) 기준 2 권장 |
| `GUNICORN_TIMEOUT` | `120` | 워커 타임아웃(초) |
| `GUNICORN_LOG_LEVEL` | `warning` | 로그 레벨. `debug` / `info` / `warning` / `error` |

---

## 시크릿 환경변수 (SECRET — Render UI에서 등록)

### Telegram 봇

| 변수명 | 설명 |
|--------|------|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 (`BotFather`에서 발급) |
| `TELEGRAM_CHAT_ID` | 알림을 받을 채팅/채널 ID |

### WooCommerce (메인 쇼핑몰)

| 변수명 | 설명 |
|--------|------|
| `WOO_BASE_URL` | WooCommerce 사이트 URL (예: `https://kohganepercentiii.com`) |
| `WOO_CK` | WooCommerce Consumer Key |
| `WOO_CS` | WooCommerce Consumer Secret |
| `WOO_WEBHOOK_SECRET` | WooCommerce 웹훅 시크릿 |

### Shopify (선택적 채널)

| 변수명 | 설명 |
|--------|------|
| `SHOPIFY_SHOP` | 숍 도메인 (예: `mystore.myshopify.com`) |
| `SHOPIFY_ACCESS_TOKEN` | Private App Access Token |
| `SHOPIFY_CLIENT_SECRET` | 웹훅 HMAC 검증용 시크릿 |

### Google Sheets (데이터 영속)

| 변수명 | 설명 |
|--------|------|
| `GOOGLE_SERVICE_JSON_B64` | Service Account JSON을 Base64 인코딩한 값 |
| `GOOGLE_SHEET_ID` | 주 스프레드시트 ID |

### Amazon SP-API (소싱)

| 변수명 | 설명 |
|--------|------|
| `AMAZON_SP_CLIENT_ID` | SP-API LWA Client ID |
| `AMAZON_SP_CLIENT_SECRET` | SP-API LWA Client Secret |
| `AMAZON_SP_REFRESH_TOKEN` | SP-API Refresh Token |
| `AMAZON_MARKETPLACE_ID` | 마켓플레이스 ID (예: `ATVPDKIKX0DER` for US) |

### 기타 시크릿

| 변수명 | 설명 |
|--------|------|
| `JWT_SECRET_KEY` | JWT 서명 키 (최소 32자 랜덤 문자열) |
| `FLASK_SECRET_KEY` | Flask 세션 암호화 키 |
| `RENDER_API_TOKEN` | Render 커스텀 도메인 스크립트용 (앱 런타임에는 불필요) |
| `CF_API_TOKEN` | Cloudflare 자동화 스크립트용 (앱 런타임에는 불필요) |

---

## 선택 환경변수 (OPTIONAL)

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `MODE` | `APPLY` | `DRY_RUN` 으로 설정 시 실제 주문 처리 없이 테스트 |
| `RUN_MIGRATIONS` | `0` | `1`로 설정 시 부팅 시 DB 마이그레이션 실행 |
| `RUN_SEED` | `0` | `1`로 설정 시 부팅 시 시드 데이터 삽입 (staging만 권장) |
| `LOG_LEVEL` | `INFO` | 앱 로그 레벨 |
| `CACHE_TTL` | `300` | 캐시 TTL(초) |
| `FX_CACHE_HOURS` | `1` | 환율 캐시 유효 시간(시간) |
| `NOTIFICATION_DELAY_THRESHOLD_HOURS` | `48` | 배송 지연 감지 임계값(시간) |
| `CORS_ORIGINS` | `*` | CORS 허용 오리진 |

---

## Render UI에서 시크릿 등록하는 방법

1. [Render 대시보드](https://dashboard.render.com) → 서비스 클릭
2. 좌측 메뉴 **Environment** 탭 클릭
3. **Add Environment Variable** 버튼 클릭
4. Key/Value 입력 후 **Save Changes**

> ⚠️ **주의**: `render.yaml`에 `sync: false`로 표시된 변수는 자동으로 동기화되지 않으므로 반드시 수동으로 등록해야 합니다.

---

## Google Service Account JSON → Base64 변환 방법

```bash
# 1. Google Cloud Console에서 Service Account JSON 다운로드
# 2. Base64 인코딩
base64 -i service-account.json | tr -d '\n'
# 3. 출력된 값을 GOOGLE_SERVICE_JSON_B64에 등록
```

---

## 환경변수 검증

배포 전 환경변수가 올바른지 확인:

```bash
python scripts/validate_env.py
```

생성 방법 (예시 `.env` 파일 기준):

```bash
python scripts/generate_env.py > .env.local
```
