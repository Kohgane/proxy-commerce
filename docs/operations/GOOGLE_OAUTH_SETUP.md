# Google OAuth "액세스 차단" 해결 가이드 (Phase 176)

## 증상

Google로 로그인 시 "액세스 차단됨: 이 앱의 요청을 완료할 수 없습니다" 또는 `redirect_uri_mismatch` 오류.

## 원인별 체크리스트

### 1. Authorized redirect URI 미등록 (가장 흔한 원인)

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. APIs & Services → Credentials → OAuth 2.0 Client IDs 선택
3. **Authorized redirect URIs** 섹션에 다음 추가 (글자 단위로 정확히):
   ```
   https://kohganepercentiii.com/auth/google/callback
   ```
4. 저장 (적용에 5~10분 소요)

> **팁**: `/admin/diagnostics` 섹션 2의 📋 버튼으로 현재 앱이 보내는 `redirect_uri`와 실제 런타임 `client_id`를 그대로 복사/대조하면 오타와 클라이언트 혼동을 함께 줄일 수 있습니다.

### 2. OAuth 동의 화면이 "Testing" 모드

1. APIs & Services → OAuth consent screen
2. Publishing status가 **Testing** 이면:
   - 옵션 A: **Test users** 항목에 본인 이메일 추가
   - 옵션 B: "PUBLISH APP" → In production으로 전환 (Google 검증 필요)
3. 저장

> **중요**: 브랜딩 인증(앱 검증)은 **로그인 자체와 무관**합니다. 기본 스코프(`openid email profile`)만 사용하는 경우 미인증 상태여도 로그인 가능합니다. "확인되지 않은 앱" 경고가 떠도 [고급] → [계속]으로 진행할 수 있습니다. 브랜딩 인증이 필요한 경우는 민감 스코프 추가·100명 초과·일부 고급 기능에 한합니다.

### 3. 클라이언트 ID/Secret 불일치

환경변수를 확인합니다 (표준 이름 우선, 레거시 이름 폴백 지원):

**표준 (권장):**
```
GOOGLE_OAUTH_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-xxxxxx
```

**레거시 별칭 (하위호환, 표준이 비어있으면 자동 사용):**
```
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxx
```

> ⚠️ `GOOGLE_SERVICE_JSON_B64` 또는 `GOOGLE_SERVICE_ACCOUNT_JSON` (Sheets·Drive 접근용)과 **별개**입니다. 두 키를 혼동하지 마세요.

- `GOOGLE_OAUTH_CLIENT_ID`가 Google Cloud Console의 OAuth 클라이언트 ID와 일치하는지 확인
- **다른 프로젝트**의 키가 사용되지 않는지 확인
- `/admin/diagnostics`와 로그인 화면 운영자 박스에 보이는 `client_id`가 실제 런타임 값입니다
- `GOOGLE_OAUTH_CLIENT_ID`와 `GOOGLE_CLIENT_ID`가 **둘 다 설정되어 값이 다르면**, 앱은 표준 env(`GOOGLE_OAUTH_CLIENT_ID`)를 사용하고 경고를 표시합니다. 하나만 남기세요.
- `GOOGLE_OAUTH_CLIENT_SECRET`와 `GOOGLE_CLIENT_SECRET`도 둘 다 다르면 경고를 표시합니다. secret 원문은 화면에 노출되지 않고 "설정됨 (끝 1234)" 형태의 힌트만 보입니다.

### 4. redirect_uri 불일치 — 발생 패턴

| 상황 | 원인 | 해결 |
|---|---|---|
| `www.` 유무 차이 | 콘솔 `www.kohgane...` vs 앱 `kohgane...` | 콘솔에 두 버전 모두 등록 |
| 끝 슬래시 | 콘솔 `.../callback/` vs 앱 `.../callback` | 슬래시 없는 버전으로 통일 |
| http vs https | 프록시 설정 누락 | `APP_BASE_URL=https://...` 명시 |
| Render 기본 도메인 | 커스텀 도메인만 콘솔 등록 | Render 도메인도 추가 등록 |

### 5. API 활성화 여부

1. APIs & Services → Library
2. **Google+ API** 또는 **Google People API** 검색 후 Enable

## /admin/diagnostics 진단 카드 활용

로그인 후 `/admin/diagnostics` → 섹션 2 "OAuth 진단":

- 프로바이더별 실제 redirect_uri 전체 문자열 + 📋 복사 버튼
- 프로바이더별 실제 runtime client_id 전체 문자열 + 📋 복사 버튼
- 어떤 env(표준/레거시)가 실제로 읽혔는지 표시
- `client_secret`는 설정 여부 + 마지막 4자리 힌트만 표시 (원문 비노출)
- Google 표준/레거시 env가 동시에 다르게 설정되면 경고 배너 표시
- URI 출처(OAUTH_REDIRECT_BASE_URL / APP_BASE_URL / 요청 컨텍스트) 표시
- 로그인 화면 하단 "🔧 OAuth 콜백 URI / Client ID 확인" 접이식 섹션에서도 확인 가능

## 로컬 개발 환경

로컬 개발 시 `localhost` redirect URI도 추가해야 합니다:
```
http://localhost:5000/auth/google/callback
http://localhost:8000/auth/google/callback
```

## 환경변수 (Render 배포)

Render 대시보드 → Environment Variables:
```
GOOGLE_OAUTH_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-<your-secret>
APP_BASE_URL=https://kohganepercentiii.com
```

`APP_BASE_URL`은 GitHub CI 환경에는 없어도 됩니다 — 코드가 요청 컨텍스트에서 host를 자동 유도합니다.

## 운영자 액션 체크리스트 (머지 후)

1. `/admin/diagnostics` 접속 → 섹션 2에서 Google의 **redirect_uri + client_id**를 Google Cloud Console과 직접 대조
2. Render Environment의 `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`를 그 클라이언트 값으로 맞춤
3. `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`가 따로 남아 값이 다르면 제거
4. secret이 노출된 적이 있으면 콘솔에서 rotate 후 새 값으로 교체
5. 저장 → 재배포 → **5~10분 대기** 후 시크릿 창에서 구글 로그인 재시도
6. 네이버: 개발 중 상태이면 [멤버 관리]에 네이버 로그인 ID 등록 (이메일 X)
