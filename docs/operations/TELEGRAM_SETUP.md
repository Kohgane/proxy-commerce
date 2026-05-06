# 텔레그램 봇 설정 가이드

## 1. 봇 생성

1. 텔레그램 앱에서 **@BotFather** 검색
2. `/newbot` 명령 입력
3. 봇 이름 입력 (예: `KoGane알림봇`)
4. 봇 사용자명 입력 (예: `kogane_notify_bot`) — `_bot`으로 끝나야 함
5. 발급된 **토큰** 복사 → Render `TELEGRAM_BOT_TOKEN`에 등록

## 2. Chat ID 확인

### 방법 A: 개인 채팅 (간단)
1. 봇과 1:1 채팅 시작 (봇 이름 검색 → Start)
2. 아무 메시지 전송
3. 브라우저에서 아래 URL 접속:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
4. `result[0].message.chat.id` 값 복사 → Render `TELEGRAM_CHAT_ID`에 등록

### 방법 B: 그룹 채팅
1. 그룹 채팅방 생성 또는 기존 그룹 사용
2. 봇을 그룹에 초대 (그룹 멤버 추가 → 봇 이름 검색)
3. 그룹에 아무 메시지 전송
4. `getUpdates` URL 접속 → `result[0].message.chat.id` 확인
   - 그룹 ID는 음수 (예: `-100123456789`)

## 3. Render 환경변수 등록

Render 대시보드 → 서비스 → Environment:
```
TELEGRAM_BOT_TOKEN = 1234567890:ABCdefghijklmnopqrstuvwxyz
TELEGRAM_CHAT_ID   = 123456789  (또는 그룹의 경우 -100123456789)
```

## 4. 연결 확인

1. `/admin/diagnostics` 접속 (admin 로그인 필요)
2. **섹션 3 — 메신저 채널 Health** → telegram 카드 확인
3. **테스트 버튼** 클릭 → 봇에서 메시지 도착 확인

## 자주 발생하는 오류

| 오류 | 원인 | 해결 |
|---|---|---|
| `getMe` 실패 (401) | 토큰이 잘못됨 | BotFather에서 토큰 재발급 |
| `getChat` 실패 (chat not found) | 봇이 채팅방에 없음 | 봇을 채팅에 초대하거나 1:1 채팅 시작 |
| `getChat` 실패 (Forbidden) | 봇이 강퇴됨 | 봇을 다시 초대 |
| 메시지 미수신 | chat_id 오류 | `getUpdates`로 정확한 chat_id 재확인 |
