# inbox — 채팅 감독 → CC 브리프

CC는 이 파일의 새 절을 읽고 `docs/briefs/outbox.md`에 답한다. 채팅 감독은 main에 문서만 직접 커밋한다.

## Y15 순찰 95 합본 (오너 10-25 11:00 KST · 채팅 세션 교체 뒤 재전달)

> A-1은 outbox 「Y15 순찰 95 A-1」(#973, 925~941행)로 이미 답함 — 채점 통과. 아래 A-2~4·B·C·D가 남은 것. CC는 10-24 23:35 이후 지시 없이 멈춰 있었음.

A. 고우주(우주대행·고코스모스 오너, 중국 체류, 가족 사용자) 상품 등록 안 됨 — 가설: P0-2 뒤 그의 로그인이 ADMIN_USER_IDS/FAMILY_EMAILS에 없어 일반 셀러로 떨어짐 → 「키를 넣어 주세요」 벽(시험 계정 kgp-cn-test-1025@example.com으로 같은 화면 실측됨).
  1. ~~읽기: 최근 14일 CN 접속 계정~~ → 답함(#973). 후속: 오너가 FAMILY_EMAILS에 고우주 카카오 이메일 추가함(11:28 KST, 배포 반영은 순찰 96에서 uptime으로 확인). 후보 user_id ec4a1c3d에 상품·키·토큰 0 — 그분 화면의 user_id 앞 8이 ec4a1c3d인지는 오너 확인 대기.
  2. 같은 사람의 다른 로그인이 정체성 표에서 한 user_id로 묶였는지 — 아니면 C-F19 경로로 묶기. 특히 카카오 이메일 미동의 갈래(views.py 소셜 콜백 `if email:`)에서 로그인마다 새 user_id가 나는 구멍: 카카오 `id`(provider_user_id)로도 찾게 해서 막을 것.
  3. FAMILY_MARKET_BUNDLE(→woojoo) 설정으로 가족 사용자 마켓 선택 고정 — 코드 준비, 기본 현재대로.
  4. 403/키 없음 화면 「가족·관리자인데 이게 보이면 오너에게 번호 전달」 힌트 — user_id 앞 8 노출. 캡처.
B. 외부 자원 self-host(cdn.jsdelivr·구글 폰트 → src/static), 외부 origin은 developers.kakao.com만(중국 접속 대비).
C. 시험 계정 kgp-cn-test-1025@example.com·상품 cd7429ff 집계 제외.
D. 등록 대기 3건(3-in-1 맥세이프 a0a78ca4 · SPORTLINK a3a35e92 네이버 2곳 · 左马 LED 스탠드 d5af2185) 상태 한 줄 + 등록 뒤 메모리 바닥 상승(299→343) 원인 측정 계속(rss:ticks 2시간 표).

A-2~4·B·C·D는 PR(전체 스위트·CI 5/5·캡처 390px). 마켓 전송은 오너 「가라」 뒤에만.
