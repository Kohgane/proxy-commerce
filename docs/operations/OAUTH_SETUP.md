# OAuth 설정 및 트러블슈팅

## Google

### 새 OAuth 클라이언트 생성
1. Google Cloud Console → API 및 서비스 → 사용자 인증 정보
2. **OAuth 2.0 클라이언트 ID** 생성 → 유형은 웹 애플리케이션
3. JavaScript 원본: `https://kohganepercentiii.com`
4. Redirect URI: `https://kohganepercentiii.com/auth/google/callback`

### 게시 모드 vs 테스트 모드
- **테스트 모드**: 테스트 사용자 추가 필수
- **프로덕션**: 도메인 검증, 개인정보처리방침, 이용약관 필요
- 설정 변경 후 Google 캐시 반영에 5~10분 이상 걸릴 수 있음

### 도메인 검증
- Google Search Console에서 `kohganepercentiii.com` 검증
- 승인된 도메인은 실제 서비스 도메인만 남기기

### 필수 URL 등록
- 개인정보처리방침: `https://kohganepercentiii.com/privacy`
- 이용약관: `https://kohganepercentiii.com/terms`

## Kakao

1. Kakao Developers → 내 애플리케이션 → 제품 설정 → 카카오 로그인 활성화
2. 앱 설정 → 플랫폼 → Web 플랫폼에 `https://kohganepercentiii.com` 등록
3. Redirect URI: `https://kohganepercentiii.com/auth/kakao/callback`
4. 동의 항목에서 이메일/닉네임 필수 동의 확인

## Naver

1. 네이버 디벨로퍼스 → 내 애플리케이션 → 네이버 로그인 API 설정
2. Callback URL: `https://kohganepercentiii.com/auth/naver/callback`
3. 멤버 관리는 **네이버 로그인 ID** 기준입니다. 이메일이 아니라 `diwlslzpdltus_88` 같은 ID를 등록해야 합니다.
4. 앱 상태가 `개발 중` 이면 등록된 멤버만 로그인 가능
5. 멤버 제한 해제를 위해 정식 서비스 검수 요청 필요

## 운영 팁
- `/admin/diagnostics` 에서 콜백 URL 복사 및 체크리스트 확인
- OAuth 정상화 전에는 `/auth/magic-link` 또는 `/auth/bootstrap` 사용
