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

외부 의존성 단계별 진단. Phase 126부터 4단계 분리 + `google_credentials` 단계 추가.

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
      "detail": "필수 환경변수 모두 존재"
    },
    {
      "name": "google_credentials",
      "status": "ok",
      "source": "secret_file:/etc/secrets/service-account.json",
      "detail": "service_account 로드 성공",
      "service_account": "svc@my-project.iam.gserviceaccount.com",
      "project_id": "my-project"
    },
    {
      "name": "google_sheets",
      "status": "ok",
      "detail": "연결 성공",
      "service_account": "svc@my-project.iam.gserviceaccount.com",
      "source": "secret_file:/etc/secrets/service-account.json"
    },
    {
      "name": "google_worksheets",
      "status": "ok",
      "detail": "필수 워크시트 모두 존재: ['catalog', 'orders', 'fx_rates', 'fx_history']"
    }
  ]
}
```

### 실패 응답 예시 — 자격증명 로드 실패
```json
{
  "status": "degraded",
  "checks": [
    {
      "name": "secrets_core",
      "status": "ok",
      "detail": "필수 환경변수 모두 존재"
    },
    {
      "name": "google_credentials",
      "status": "fail",
      "detail": "자격증명 소스를 찾을 수 없음...",
      "hint": "Render Dashboard → Environment → Secret Files 에서 service-account.json 등록 또는 GOOGLE_SERVICE_JSON_B64 환경변수 설정"
    },
    {
      "name": "google_sheets",
      "status": "skip",
      "detail": "google_credentials fail로 인해 스킵"
    },
    {
      "name": "google_worksheets",
      "status": "skip",
      "detail": "google_credentials fail로 인해 스킵"
    }
  ]
}
```

### 실패 응답 예시 — google_sheets 권한 없음
```json
{
  "status": "degraded",
  "checks": [
    {
      "name": "google_credentials",
      "status": "ok",
      "source": "GOOGLE_SERVICE_JSON_B64",
      "service_account": "svc@my-project.iam.gserviceaccount.com"
    },
    {
      "name": "google_sheets",
      "status": "fail",
      "detail": "permission denied — 시트 접근 권한 없음 (ID: 1AbC***...***xyz)",
      "hint": "Google Sheets 공유 메뉴에서 'svc@my-project.iam.gserviceaccount.com'을 편집자로 추가했는지 확인.",
      "sheet_id_masked": "1AbC***xyz"
    }
  ]
}
```

---

## Check 항목별 의미 (Phase 126)

| name | 의미 |
|---|---|
| `secrets_core` | `GOOGLE_SERVICE_JSON_B64`, `GOOGLE_SHEET_ID` 등 코어 환경변수 설정 여부 |
| `google_credentials` | 서비스 계정 자격증명 로드 (Secret File / b64 / raw JSON / 로컬 파일) |
| `google_sheets` | Google Sheets API 스프레드시트 열기 |
| `google_worksheets` | 필수 워크시트 (`catalog`, `orders`, `fx_rates`, `fx_history`) 존재 확인 |

### status 값
| status | 의미 |
|---|---|
| `ok` | 정상 |
| `fail` | 오류 발생 (detail + hint 참조) |
| `skip` | 이전 단계 실패로 건너뜀, 또는 설정 없음 |

### google_credentials.source 값
| source | 의미 |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | 환경변수로 지정한 파일 |
| `secret_file:/etc/secrets/service-account.json` | Render Secret File (권장) |
| `secret_file:/etc/secrets/google-service-account.json` | 대체 이름 Secret File |
| `GOOGLE_SERVICE_JSON_B64` | base64 환경변수 |
| `GOOGLE_SERVICE_JSON` | raw JSON 환경변수 |
| `local_file` | 개발용 로컬 파일 |

---

## 자격증명 등록 방법 (Render)

### 방법 1 — Secret File (권장)
1. Render Dashboard → 서비스 → **Environment** 탭
2. **Secret Files** 섹션 → **Add Secret File**
3. Filename: `service-account.json`
4. Contents: `service-account.json` 파일 내용 그대로 붙여넣기 (base64 X)
5. Save → 재배포

`google_credentials.source` = `"secret_file:/etc/secrets/service-account.json"` 이 되면 성공.

### 방법 2 — base64 환경변수
```bash
# Git Bash / Linux / Mac
base64 -w 0 service-account.json > sa_b64.txt
cat sa_b64.txt  # 한 줄 긴 문자열이어야 함

# 검증: 디코드 후 JSON 파싱 가능한지 확인
cat sa_b64.txt | base64 -d | python3 -m json.tool | head -5
```

Render → Environment Variables → `GOOGLE_SERVICE_JSON_B64` 에 `sa_b64.txt` 내용 붙여넣기.

> ⚠️ Windows의 base64 도구 사용 시 줄바꿈 옵션을 **LF (Unix)** 로 변경할 것.

### 방법 3 — raw JSON 환경변수
`GOOGLE_SERVICE_JSON` 환경변수에 JSON 전체를 그대로 붙여넣기.
특수문자(`"`, `\n` 등) 이스케이프에 주의.

---

## 실패 시 트러블슈팅 매트릭스

### secrets_core: fail

**증상**: `"detail": "누락된 시크릿: ['GOOGLE_SERVICE_JSON_B64']"`

**원인 & 해결**:
1. Render 대시보드 → 서비스 → Environment 탭에서 환경변수 확인
2. 누락된 환경변수 추가 후 Save → 재배포

---

### google_credentials: fail — 소스 없음

**증상**: `"detail": "자격증명 소스를 찾을 수 없음..."`

**원인 5가지**:
1. Secret File 미등록 + GOOGLE_SERVICE_JSON_B64 미설정
2. Render에서 환경변수 저장 후 재배포 안 함
3. 환경변수 이름 오타 (`GOOGLE_SERVIC_JSON_B64` 등)
4. Render 서비스가 올바른 환경(Production/Staging)인지 확인
5. 로컬 `service-account.json` 없음

**해결**: Secret File 등록 (위 "자격증명 등록 방법" 참조)

---

### google_credentials: fail — base64 decode 실패

**증상**: `"detail": "GOOGLE_SERVICE_JSON_B64 base64 디코드 실패: ..."`

**원인 & 해결**:
```bash
# 올바른 인코딩 방법 (줄바꿈 없이)
base64 -w 0 service-account.json
# Windows Git Bash에서는 LF 옵션 필요
```

---

### google_credentials: fail — JSON 파싱 실패

**증상**: `"detail": "...JSON 파싱 실패: Expecting value: line 1 column 1 (char 0)"`

**원인 5가지**:
1. base64 인코딩 시 CRLF 삽입됨 → 디코드 후 `\r` 끼어 파싱 실패
2. base64 결과에 줄바꿈이 포함됨 (76자 청크 옵션 ON)
3. Render에 raw JSON이 아닌 다른 값 붙여넣기
4. service-account.json 파일 자체가 손상됨
5. BOM 문자 앞에 붙어있음 (Windows Notepad 저장 시)

**해결**:
```bash
# 파일 검증
python3 -m json.tool service-account.json

# 재인코딩 (LF, 줄바꿈 없이)
base64 -w 0 service-account.json | tr -d '\n' > sa_b64.txt
```

---

### google_credentials: fail — 필수 필드 누락

**증상**: `"detail": "...JSON에 필수 필드 'private_key' 누락"`

**원인**: 서비스 계정 JSON이 아닌 다른 JSON을 업로드함

**해결**: Google Cloud Console → IAM → 서비스 계정 → 키 → JSON 형식으로 새 키 생성

---

### google_sheets: fail — GOOGLE_SHEET_ID placeholder

**증상**: `"detail": "GOOGLE_SHEET_ID가 placeholder 값처럼 보임: 'for-google-sh***'"`

**해결**:
1. Google Sheets URL 확인: `https://docs.google.com/spreadsheets/d/[실제ID]/edit`
2. `[실제ID]` 부분 (44자 내외 영문+숫자)을 복사
3. Render → Environment Variables → `GOOGLE_SHEET_ID` 업데이트

---

### google_sheets: fail — permission denied

**증상**: `"detail": "permission denied — 시트 접근 권한 없음 (ID: 1AbC***xyz)"`

**해결**:
1. `hint` 필드의 서비스계정 이메일 확인
2. Google Sheets 파일 열기 → **공유** 버튼
3. 서비스계정 이메일을 **편집자**로 추가 → **완료**
4. 5분 후 `/health/deep` 재확인

---

### google_sheets: fail — spreadsheet not found

**증상**: `"detail": "spreadsheet not found — 시트를 찾을 수 없음 (ID: 1AbC***xyz)"`

**해결**:
- 시트 URL의 `/d/` 와 `/edit` 사이 값이 `GOOGLE_SHEET_ID`와 일치하는지 확인
- URL 전체를 붙여넣으면 자동 ID 추출 시도함

---

### google_worksheets: fail — 누락된 워크시트

**증상**: `"detail": "누락된 워크시트: ['catalog', 'orders']"`

**해결**:
- `hint` 필드에 명시된 워크시트를 Google Sheets에 직접 생성
- 필수 워크시트: `catalog`, `orders`, `fx_rates`, `fx_history`
- 탭 이름 대소문자 정확히 일치해야 함

---

## 진단 명령

```bash
# 상세 진단 (JSON 포맷)
curl https://your-service.onrender.com/health/deep | python3 -m json.tool

# google_credentials.source 필드 확인
curl -s https://your-service.onrender.com/health/deep \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    cred=[c for c in d['checks'] if c['name']=='google_credentials']; \
    print(cred[0] if cred else 'not found')"
```

