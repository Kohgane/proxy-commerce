# Google OAuth "액세스 차단" 해결 가이드 (Phase 142)

## 증상

Google로 로그인 시 "액세스 차단됨: 이 앱의 요청을 완료할 수 없습니다" 오류.

## 원인별 체크리스트

### 1. Authorized redirect URI 미등록 (가장 흔한 원인)

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. APIs & Services → Credentials → OAuth 2.0 Client IDs 선택
3. **Authorized redirect URIs** 섹션에 다음 추가:
   ```
   https://kohganepercentiii.com/auth/google/callback
   ```
4. 저장 (적용에 5~10분 소요)

### 2. OAuth 동의 화면이 "Testing" 모드

1. APIs & Services → OAuth consent screen
2. Publishing status가 **Testing** 이면:
   - 옵션 A: **Test users** 항목에 본인 이메일 추가
   - 옵션 B: "PUBLISH APP" → In production으로 전환 (Google 검증 필요)
3. 저장

### 3. 클라이언트 ID/Secret 불일치

환경변수를 확인합니다:
```
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxx
```

- `GOOGLE_CLIENT_ID`가 Google Cloud Console의 OAuth 클라이언트 ID와 일치하는지 확인
- **다른 프로젝트**의 키가 사용되지 않는지 확인

### 4. API 활성화 여부

1. APIs & Services → Library
2. **Google+ API** 또는 **Google People API** 검색 후 Enable

## /admin/diagnostics 진단 카드 활용

로그인 후 `/admin/diagnostics` → 섹션 8 "인증 상태" 카드:

- Google CLIENT_ID 마지막 8자 표시
- 예상 redirect URI 확인
- 체크리스트 바로 보기

## 로컬 개발 환경

로컬 개발 시 `localhost` redirect URI도 추가해야 합니다:
```
http://localhost:5000/auth/google/callback
http://localhost:8000/auth/google/callback
```

## 환경변수 (Render)

Render 대시보드 → Environment Variables:
```
GOOGLE_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-<your-secret>
```
