# CS 통합 인박스 (Phase 145)

- 모듈: `src/cs/unified_inbox.py`
- 화면: `/seller/cs/inbox`
- 환경변수:
  - `CS_UNIFIED_INBOX_ENABLED=1`
  - `CS_AI_DRAFT_PROVIDER=openai`

기능:
- 채널 통합 큐(마켓/이메일/카톡/챗봇 미해결)
- 우선순위 분류(환불/배송지연 우선)
- AI 초안 생성
- 24시간 SLA 경고 집계
