# 운영 진단 대시보드 가이드

## 접속

`/admin/diagnostics` — **admin 역할 필수**

로그인 후 `ADMIN_EMAILS` 환경변수에 본인 이메일이 등록되어 있으면 자동으로 admin 역할 부여됩니다.

---

## 각 섹션 설명

### 섹션 1: 환경변수 매트릭스

모든 API 키의 등록 상태를 카테고리별로 표시합니다.

- ✅ **활성** — 환경변수가 설정됨
- ❌ **누락** — 환경변수 미설정 (옆의 발급 링크 클릭)

핵심 환경변수 체크리스트:
- `GOOGLE_SHEET_ID` + `GOOGLE_SERVICE_JSON_B64` — 데이터 저장소
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — 알림
- `RESEND_API_KEY` — 이메일 알림
- 마켓별 API 키 (쿠팡/스마트스토어/11번가/WC)

### 섹션 2: OAuth 콜백 URL

각 OAuth 프로바이더에 등록해야 할 정확한 콜백 URL을 표시합니다.
**복사** 버튼으로 URL을 클립보드에 복사한 뒤 각 개발자 콘솔에 붙여넣으세요.

#### Google Cloud Console
1. https://console.cloud.google.com → 프로젝트 선택
2. API 및 서비스 → 사용자 인증 정보
3. OAuth 2.0 클라이언트 ID 클릭
4. 승인된 리디렉션 URI에 콜백 URL 추가

#### 카카오 디벨로퍼스
1. https://developers.kakao.com → 내 애플리케이션
2. 앱 설정 → 플랫폼 → Web 플랫폼 등록
3. 제품 설정 → 카카오 로그인 → 활성화
4. Redirect URI 등록

#### 네이버 디벨로퍼스
1. https://developers.naver.com → Application → 내 애플리케이션
2. 사용 API: 네이버 아이디로 로그인
3. 서비스 URL + Callback URL 등록

### 섹션 3: 메신저 채널 Health

각 채널의 연결 상태를 실시간으로 확인합니다.

- **텔레그램**: 테스트 버튼으로 실제 메시지 발송 확인 가능
  - 오류 시 힌트 메시지 표시 (봇 초대 여부, chat_id 오류 등)
- **Resend**: API 키 등록 여부 확인

### 섹션 4: 마켓 어댑터 Health

4개 마켓(쿠팡/스마트스토어/11번가/WooCommerce)의 API 연결 상태를 표시합니다.

- `missing` — API 키 미설정
- `dry_run` — ADAPTER_DRY_RUN=1 (실제 연결 안 함)
- `ok` — 연결 성공
- `fail` — 연결 실패 (상세 메시지 확인)

### 섹션 5: 가격 엔진 상태

자동 가격 조정 엔진의 현재 상태를 요약합니다.

- **DRY_RUN 모드** — 파란색이면 시뮬레이션만 (안전), 초록색이면 실제 적용
- **활성 룰 개수** — 0이면 가격 변경 없음
- **마지막 실행** — 가장 최근 cron 실행 시각

### 섹션 6: 최근 24시간 알림 로그

채널별 발송 성공/실패 통계와 자주 발생하는 오류를 표시합니다.

---

## 운영 체크리스트

배포 후 확인 순서:

1. `/admin/diagnostics` 접속
2. 섹션 2: OAuth 콜백 URL 각 콘솔에 등록됐는지 확인
3. 섹션 3: 텔레그램 테스트 → 메시지 수신 확인
4. 섹션 4: 마켓 어댑터 최소 1개 이상 `ok` 상태 확인
5. 섹션 5: PRICING_DRY_RUN=1 상태 → 시뮬레이션 며칠 관찰
6. 이상 없으면 PRICING_DRY_RUN=0 으로 전환
