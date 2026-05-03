# 헬스체크 운영 가이드 (Health Check Operations)

## 엔드포인트 목록

| 엔드포인트 | 설명 | 인증 필요 |
|---|---|---|
| `GET /health` | 기본 헬스체크 (앱 버전, 상태) | 없음 |
| `GET /health/ready` | 준비 상태 확인 (시크릿 설정 여부) | 없음 |
| `GET /health/deep` | 심층 진단 (외부 서비스 연결 포함) | 없음 |

---

## GET /health

기본 상태 확인. 앱이 살아있으면 항상 200.

```json
{
  "status": "ok",
  "service": "proxy-commerce",
  "version": "1.0.0"
}
```

---

## GET /health/ready

코어 시크릿 설정 여부 확인. soft-fail — 항상 HTTP 200 반환.

```json
{
  "status": "ready",
  "degraded": false,
  "checks": {
    "secrets_core": true
  }
}
```

**degraded:true 케이스**
```json
{
  "status": "ready",
  "degraded": true,
  "checks": {
    "secrets_core": false
  }
}
```

---

## GET /health/deep

외부 의존성 상세 진단. Phase 124부터 각 check에 `detail`과 `hint` 필드 포함.

### 성공 응답 예시
```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime_seconds": 17.2,
  "timestamp": "2026-05-03T09:34:55.706+00:00",
  "checks": [
    {
      "name": "secrets_core",
      "status": "ok",
      "detail": "모든 코어 시크릿 정상"
    },
    {
      "name": "google_sheets",
      "status": "ok",
      "detail": "연결 성공",
      "service_account": "proxy-commerce@xxx.iam.gserviceaccount.com"
    }
  ]
}
```

### 실패 응답 예시 (google_sheets fail)
```json
{
  "status": "degraded",
  "checks": [
    {
      "name": "google_sheets",
      "status": "fail",
      "detail": "permission denied — 시트 접근 권한 없음",
      "hint": "시트의 공유 메뉴에서 서비스계정 이메일 (proxy-commerce@xxx.iam.gserviceaccount.com) 을 편집자로 추가",
      "service_account": "proxy-commerce@xxx.iam.gserviceaccount.com"
    }
  ]
}
```

---

## Check 항목별 의미

| name | 의미 |
|---|---|
| `secrets_core` | `GOOGLE_SERVICE_JSON_B64`, `GOOGLE_SHEET_ID` 등 코어 환경변수 설정 여부 |
| `google_sheets` | Google Sheets API 연결 및 워크시트 접근 가능 여부 |

### status 값
| status | 의미 |
|---|---|
| `ok` | 정상 |
| `fail` | 오류 발생 (detail + hint 참조) |
| `skip` | 해당 설정이 없어 체크를 건너뜀 |

---

## 실패 시 트러블슈팅 매트릭스

### secrets_core: fail

**증상**: `"detail": "누락된 시크릿: ['GOOGLE_SERVICE_JSON_B64']"`

**해결**:
1. Render 대시보드 → 서비스 → Environment 탭
2. 누락된 환경변수 추가
3. Deploy 재시작

---

### google_sheets: fail — base64 decode 실패

**증상**: `"detail": "base64 decode 실패: ..."`

**해결**:
```bash
# 올바른 인코딩 방법 (줄바꿈 없이)
base64 -w 0 service-account.json | tr -d '\n'
# 출력된 문자열을 Render의 GOOGLE_SERVICE_JSON_B64에 설정
```

---

### google_sheets: fail — JSON 파싱 실패

**증상**: `"detail": "JSON 파싱 실패: ..."`

**해결**:
- service-account.json 파일이 올바른 JSON인지 확인
- `python3 -c "import json; json.load(open('service-account.json'))"` 로 검증

---

### google_sheets: fail — permission denied

**증상**: `"detail": "permission denied — 시트 접근 권한 없음"`

**해결**:
1. `hint` 필드의 서비스계정 이메일 확인
2. Google Sheets 파일 열기 → 공유 버튼
3. 서비스계정 이메일을 **편집자**로 추가

---

### google_sheets: fail — spreadsheet not found

**증상**: `"detail": "spreadsheet not found — 시트를 찾을 수 없음"`

**해결**:
- Render의 `GOOGLE_SHEET_ID` 환경변수 확인
- 시트 URL: `https://docs.google.com/spreadsheets/d/[SHEET_ID]/edit`
- `[SHEET_ID]` 부분이 `GOOGLE_SHEET_ID` 값과 일치해야 함

---

### google_sheets: fail — 누락된 워크시트

**증상**: `"detail": "누락된 워크시트: ['catalog', 'orders']"`

**해결**:
- hint 필드에 명시된 워크시트를 Google Sheets에 직접 생성
- 필수 워크시트: `catalog`, `orders`, `fx_rates`, `fx_history`
