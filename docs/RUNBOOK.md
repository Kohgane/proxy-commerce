# 운영 런북 (Operations Runbook)

## 일일 운영 체크리스트

### 매일 아침 (09:00 KST)

- [ ] `/health` 엔드포인트 응답 확인
- [ ] Telegram 봇 `/status` 커맨드로 전일 주문 현황 확인
- [ ] 재고 부족 알림 확인 (Telegram 메시지)
- [ ] 환율 변동 알림 확인 (±3% 초과 시 텔레그램 알림 발송)
- [ ] Google Sheets `orders` 워크시트에서 미처리 주문 확인

```bash
# CLI로 빠른 현황 확인
python -m src.cli health
python -m src.cli orders --status paid
python -m src.cli inventory --low-stock
python -m src.cli fx --rates
```

### 매주 월요일

- [ ] 주간 리포트 자동 발송 확인 (GitHub Actions `scheduled_export.yml`)
- [ ] 감사 로그 검토: `python -m src.cli audit --since 7d`
- [ ] 캐시 히트율 확인: `python -m src.cli cache --stats`
- [ ] 환율 이력 검토: Google Sheets `fx_history` 워크시트

---

## 장애 대응 절차

### 1. 서비스 다운 (Health Check 실패)

**증상**: `/health` → 502/503 응답

**대응**:
```bash
# 1. 컨테이너 상태 확인
docker ps
docker logs proxy-commerce-web --tail 100

# 2. 프로세스 재시작
docker-compose restart web

# 3. 로그 분석
docker logs proxy-commerce-web --since 5m | grep ERROR
```

**에스컬레이션**: 5분 내 복구 안 될 시 → Render 대시보드에서 수동 재배포

---

### 2. Shopify 웹훅 수신 실패

**증상**: Shopify → 401 응답, 주문 미수신

**점검**:
```bash
# HMAC 시크릿 확인
python -c "import os; print('OK' if os.getenv('SHOPIFY_CLIENT_SECRET') else 'MISSING')"

# 최근 감사 로그 확인
python -m src.cli audit --event webhook_rejected --since 1h
```

**해결**:
1. Shopify Admin → Settings → Notifications → Webhooks에서 시크릿 재확인
2. `.env`의 `SHOPIFY_CLIENT_SECRET` 업데이트
3. 설정 재로드: `POST /api/config/reload` (API Key 인증)

---

### 3. Google Sheets 연결 오류

**증상**: `gspread.exceptions.SpreadsheetNotFound` 또는 인증 오류

**점검**:
```bash
python -c "
import base64, os
data = os.getenv('GOOGLE_SERVICE_JSON_B64', '')
print('B64 길이:', len(data))
print('디코드 OK' if data else 'MISSING')
"
```

**해결**:
1. Google Cloud Console에서 서비스 계정 키 재발급
2. Base64 인코딩 후 `GOOGLE_SERVICE_JSON_B64` 업데이트:
   ```bash
   base64 -w 0 service-account.json
   ```
3. 공유 권한 확인: Sheets 파일에 서비스 계정 이메일 편집자 권한 부여

---

### 4. 환율 이상 (FX 오류)

**증상**: 환율이 갑자기 0 또는 비정상 값

**점검**:
```bash
python -m src.cli fx --rates
python -m src.cli fx --history --since 24h
```

**해결**:
1. `FX_USE_LIVE=0` → 수동 환율로 전환
2. `.env`에서 수동 값 설정: `FX_USDKRW=1380`, `FX_JPYKRW=9.2`, `FX_EURKRW=1500`
3. Frankfurter API 상태 확인: `curl https://api.frankfurter.app/latest?from=USD`
4. 복구 후 `FX_USE_LIVE=1` 재활성화

---

### 5. Rate Limit 오류 급증

**증상**: 다수의 429 응답

**점검**:
```bash
# 최근 rate limit 이벤트
python -m src.cli audit --event api_rate_limited --since 1h
```

**해결**:
1. 공격성 트래픽 확인 후 IP 차단 (Render/Cloudflare 설정)
2. 임시로 제한 완화: `RATE_LIMIT_WEBHOOK=120 per minute`
3. `RATE_LIMIT_ENABLED=0`으로 완전 비활성화 (비상시)

---

## 롤백 절차

### Render 자동 배포 롤백

```bash
# 1. Render 대시보드에서 이전 배포 버전 선택 → "Rollback to this deploy"
# 또는
# 2. GitHub에서 이전 커밋으로 revert PR 생성 후 머지
git revert <commit-hash>
git push origin main
```

### 환경변수 롤백

```bash
# 1. .env 파일에서 이전 값으로 복원
# 2. 설정 재로드 (서버 재시작 불필요 - 핫리로드)
curl -X POST https://your-app.onrender.com/api/config/reload \
  -H "X-API-Key: $DASHBOARD_API_KEY"
```

### 데이터 롤백

```bash
# Google Sheets 버전 이력에서 복원
# Sheets → 파일 → 버전 이력 → 이전 버전으로 복원
```

---

## 환경변수 변경 가이드

### 1. 운영 중 설정 변경 (핫리로드)

`CONFIG_HOT_RELOAD_ENABLED=1` 환경에서 `config.yml` 파일을 수정하면 자동 감지됩니다.

수동 강제 재로드:
```bash
curl -X POST https://your-app.onrender.com/api/config/reload \
  -H "X-API-Key: $DASHBOARD_API_KEY"
```

현재 설정 상태 확인:
```bash
curl https://your-app.onrender.com/api/config/status \
  -H "X-API-Key: $DASHBOARD_API_KEY"
```

설정 검증:
```bash
curl https://your-app.onrender.com/api/config/validate \
  -H "X-API-Key: $DASHBOARD_API_KEY"
```

### 2. 필수 환경변수 목록

```bash
GOOGLE_SERVICE_JSON_B64=<base64 서비스 계정 JSON>
GOOGLE_SHEET_ID=<Sheets 파일 ID>
SHOPIFY_SHOP=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxx
SHOPIFY_CLIENT_SECRET=shpss_xxxxx
TELEGRAM_BOT_TOKEN=123456:ABC-token
TELEGRAM_CHAT_ID=-100123456789
```

### 3. Render 환경변수 업데이트

Render 대시보드 → 서비스 → Environment → Edit Variables

**주의**: `GOOGLE_SERVICE_JSON_B64`는 줄바꿈 없이 단일 라인으로 입력

---

## 벤더 플러그인 추가 가이드

### 신규 벤더 플러그인 추가 (예: ACME 벤더)

1. `src/plugins/vendors/acme_plugin.py` 생성:

```python
from ..base import VendorPlugin

class AcmePlugin(VendorPlugin):
    vendor_key = "acme"
    display_name = "ACME Vendor"

    def check_stock(self, url: str) -> dict:
        ...

    def get_price(self, url: str) -> float:
        ...
```

2. `src/plugins/vendors/__init__.py`에 추가:
```python
from .acme_plugin import AcmePlugin
```

3. `config.example.yml`의 `plugins.vendors`에 추가:
```yaml
acme:
  enabled: true
```

4. `.env`에 추가:
```
ACME_API_KEY=your-key
```

5. SKU 접두어 매핑 추가 (`src/orders/router.py`):
```python
VENDOR_SKU_PREFIX = {
    'ACM': 'acme',
    ...
}
```

---

## 데이터 마이그레이션 실행 가이드

### 마이그레이션 상태 확인

```bash
python -m src.cli migration --status
```

### 마이그레이션 실행

```bash
# Dry-run (실제 변경 없음)
python -m src.cli migration --run --dry-run

# 실제 실행
python -m src.cli migration --run

# 특정 버전으로
python -m src.cli migration --run --target v002
```

### 롤백

```bash
python -m src.cli migration --rollback --target v001
```

### 백업 확인

```bash
# 마이그레이션 전 자동 백업 위치
python -m src.cli migration --list-backups
```

---

## 정기 작업 스케줄

| 작업 | 스케줄 | GitHub Actions 워크플로 |
|------|--------|------------------------|
| 일일 CSV 내보내기 | 매일 00:00 UTC | `scheduled_export.yml` |
| 주간 리포트 | 매주 월요일 00:00 UTC | `scheduled_export.yml` |
| 환율 업데이트 | 매 시간 | `FX_USE_LIVE=1` 자동 |
| 재고 동기화 | 실시간 (카탈로그 실행 시) | 수동 실행 |

---

## 모니터링 대시보드 접근

```
GET https://your-app.onrender.com/api/dashboard/summary
X-API-Key: $DASHBOARD_API_KEY
```

주요 알림 채널:
- **Telegram**: 주문 수신, 재고 부족, 환율 변동, 에러
- **Slack**: 주문 수신, 장애 알림 (SLACK_WEBHOOK_URL 설정 시)
- **Discord**: 에러/장애 알림 (DISCORD_WEBHOOK_URL 설정 시)
