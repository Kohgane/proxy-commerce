# v86-P — 알림 설정 화면 정직화 + 에디토리얼 격상

## 결함
`/seller/notifications`(셀러 노출, admin 게이트 없음)가 **개발 표기를 그대로 노출** — 절대원칙
("일반 유저에게 개발 표기 노출 금지") 위반:
- env-var 이름: `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`·`RESEND_API_KEY`·`RESEND_FROM_EMAIL`
  (셀러가 설정할 수 없는 오너 전역 설정).
- 개발 경로 `/health/deep`, 내부 플레이스홀더 `[상품명]`·`[서비스명]`·`[실패]`.
- 테스트 응답 메시지도 `TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정` 누출.

디자인도 제네릭(`<h4 fw-bold>` + 부트스트랩 `badge bg-success`/`bg-warning`).

## 수리
- **정직**: 개발 표기 전량 제거 → 평문 카피("새 주문, 오류, 재고 소진 등의 알림을 텔레그램으로…").
  테스트 응답도 "텔레그램 알림이 아직 연결되지 않았어요."로 교체.
- **디자인(gogabridj)**: 오버라인 키커(`console-kpi-label`) + 금 헤어라인(`pc-hairline`) 헤더 +
  상태 안내(`pc-status-info`).
- **공통 상태 뱃지 신규**: 부트스트랩 컬러 뱃지 → `.pc-badge`(app.css 단일 소스, **토큰 기반**:
  연결=청록 `var(--teal)` / 미연결=주황 `var(--orange)`, color-mix 은은한 배경, 하드코딩 hex 0).
  "상태 뱃지는 전 화면 공통 컴포넌트"(디자인 스킬) 원칙 — 이후 화면 재사용.
- 이모지 0(bi-* 아이콘), 새 창은 `rel="noopener"`.

## before/after
`docs/screens/v86p/v86p-notifications.png` — BEFORE(제네릭 h4·부트스트랩 뱃지·빨간 env-var 노출)
vs AFTER(오버라인+금 헤어라인·pc-badge 청록/주황·평문 카피). 텔레그램=연결됨/이메일=미연결로
두 뱃지 변형 동시 노출.

## 판정
- 가드 `tests/test_v86_p_notifications_grade.py`(6): 개발표기 0·에디토리얼 헤더·pc-badge(부트스트랩
  잔재 0·이모지 0)·pc-badge 토큰 기반·테스트 응답 누출 0·라우트 200 렌더 누출 0.
- 회귀: design/token/ui_smoke/emoji-sweep/audit **312 passed**.

적용 스킬: **gogabridj-design**(오버라인·금 헤어라인·청록/주황 토큰·공통 상태 뱃지·이모지 0).
impeccable/humanizer CLI 미설치 → 의도 수동 적용(개발 슬롭 제거·평문 톤).
