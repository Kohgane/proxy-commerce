# AUTH.md — 인증 시스템 설정 가이드 (Phase 133)

## 개요

코가네 퍼센티는 카카오 / 구글 / 네이버 소셜 로그인 + 이메일 가입을 지원합니다.

---

## 환경변수

| 변수명 | 설명 | 필수 |
|---|---|---|
| `SECRET_KEY` | Flask 세션 암호화 키 | ✅ P0 |
| `KAKAO_REST_API_KEY` | 카카오 REST API 키 | P2 |
| `KAKAO_CLIENT_SECRET` | 카카오 클라이언트 시크릿 | P2 |
| `GOOGLE_OAUTH_CLIENT_ID` | 구글 OAuth 클라이언트 ID | P2 |
| `GOOGLE_OAUTH_CLIENT_SECRET` | 구글 OAuth 클라이언트 시크릿 | P2 |
| `NAVER_CLIENT_ID` | 네이버 로그인 Client ID | P2 |
| `NAVER_CLIENT_SECRET` | 네이버 로그인 Client Secret | P2 |
| `ADMIN_EMAILS` | 관리자 이메일 (쉼표 구분) | 권장 |
| `APP_BASE_URL` | 앱 베이스 URL (콜백 URI 생성용) | 권장 |

---

## 각 프로바이더 설정

### 카카오 로그인

1. [Kakao Developers](https://developers.kakao.com/) → 내 애플리케이션 → 앱 생성
2. 카카오 로그인 활성화
3. 리다이렉트 URI 등록:
   - `https://kohganepercentiii.com/auth/kakao/callback`
4. `REST API 키` → `KAKAO_REST_API_KEY`
5. `클라이언트 시크릿` (카카오 로그인 > 보안) → `KAKAO_CLIENT_SECRET`

### 구글 로그인

1. [Google Cloud Console](https://console.cloud.google.com/) → API & Services → Credentials
2. OAuth 2.0 클라이언트 ID 생성 (웹 애플리케이션)
3. 승인된 리디렉션 URI:
   - `https://kohganepercentiii.com/auth/google/callback`
4. `클라이언트 ID` → `GOOGLE_OAUTH_CLIENT_ID`
5. `클라이언트 보안 비밀` → `GOOGLE_OAUTH_CLIENT_SECRET`

> ⚠️ `GOOGLE_SERVICE_JSON_B64` (Sheets 접근용)과 **별개**입니다.

### 네이버 로그인

1. [Naver Developers](https://developers.naver.com/) → 내 애플리케이션 → 등록
2. 네이버 로그인 API 추가
3. 콜백 URL:
   - `https://kohganepercentiii.com/auth/naver/callback`
4. `Client ID` → `NAVER_CLIENT_ID`
5. `Client Secret` → `NAVER_CLIENT_SECRET`

> ⚠️ `NAVER_COMMERCE_CLIENT_ID/SECRET` (커머스 API용)과 **별개**입니다.

---

## 관리자 권한

`ADMIN_EMAILS` 환경변수에 쉼표로 구분된 이메일 등록:

```
ADMIN_EMAILS=owner@example.com,admin2@example.com
```

해당 이메일로 로그인/가입 시 자동으로 `role=admin` 부여.

---

## 세션 보안

- `SECRET_KEY` 필수 — 미설정 시 시작 경고 + 임시 키 자동 생성 (재시작 시 세션 만료)
- 세션 쿠키: `HttpOnly=True`, `SameSite=Lax`
- HTTPS 환경에서는 `SESSION_COOKIE_SECURE=1` 환경변수 설정 권장
- OAuth `state` 파라미터로 CSRF 방어
- 비밀번호: bcrypt 해시 (bcrypt 미설치 시 hashlib.scrypt 폴백)

---

## 라우트

| 경로 | 설명 |
|---|---|
| `GET /auth/login` | 로그인 페이지 |
| `GET /auth/signup` | 회원가입 페이지 |
| `GET /auth/<provider>/start` | OAuth 시작 (kakao/google/naver) |
| `GET /auth/<provider>/callback` | OAuth 콜백 |
| `POST /auth/logout` | 로그아웃 |
| `GET /auth/verify-email?token=` | 이메일 인증 |
| `POST /auth/forgot` | 비밀번호 재설정 메일 발송 |
| `GET /auth/reset?token=` | 재설정 페이지 |
| `POST /auth/reset` | 새 비밀번호 저장 |

---

## 후속 액션 (Render 배포 후)

1. Render → Environment Variables에 등록:
   - `SECRET_KEY` (openssl rand -hex 32)
   - `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`
   - `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`
   - `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
   - `ADMIN_EMAILS=형이메일@example.com`
   - `APP_BASE_URL=https://kohganepercentiii.com`
2. Manual Deploy
3. `/auth/login` → 소셜 버튼 3개 확인
4. 형 이메일로 카카오 로그인 → `/seller/dashboard` + Admin 배지 확인
