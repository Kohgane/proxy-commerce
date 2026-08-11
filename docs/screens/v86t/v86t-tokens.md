# v86-T — 토큰 관리 화면 상태뱃지 공통화 + 에디토리얼

알림·카탈로그·마켓과 동일하게 토큰 관리 화면(`/seller/me/tokens`)의 상태 뱃지를 공통
`pc-badge`(v86-P 신설)로 통일 + 에디토리얼 헤더.

## 수리
- 상태 뱃지: 부트스트랩 `badge bg-success`(활성)/`bg-secondary`(삭제됨·스코프)/`bg-light`(스코프
  이력) + 인라인 스타일(유휴 만료) → `pc-badge`: 활성=청록(on)·유휴 만료=주황(off)·삭제됨/스코프
  태그=뮤트. (유휴 만료는 기존 `--warn` 인라인 → 공통 컴포넌트로 승격.)
- 헤더: `<h1 h3>` → 오버라인 키커(`console-kpi-label` '인증 토큰') + `h4` + 금 헤어라인.

## before/after
`docs/screens/v86t/v86t-tokens.png` — BEFORE(부트스트랩 컬러 뱃지·어두운 스코프 태그) vs
AFTER(pc-badge 청록 활성·주황 유휴만료·뮤트 스코프). 활성·유휴만료·삭제됨 3상태 토큰으로 렌더.

## 판정
- 가드 `tests/test_v86_t_tokens_grade.py`(4): 부트스트랩 badge 잔재 0·pc-badge 3변형·에디토리얼
  헤더·라우트 렌더.
- 회귀: token/design/ui_smoke/emoji/audit/v29/v38/v81 **278 passed**(발급 1회·마스킹·활성/이력
  분리 계약 보존).

## pc-badge 공통 컴포넌트 롤아웃 완료(클린 상태 화면)
v86-P(알림)·R(카탈로그)·S(마켓)·T(토큰) — 단순 상태 뱃지 화면 전반에 공통 `pc-badge` 적용 완료.
※ 주문(orders)은 9+ 상태의 다색 시스템, 마켓 색상 코딩 등 **정보량이 많은 색 체계**라 4변형
pc-badge로 축소하면 상태 구분이 손실 → 의도적으로 기존 체계 유지(다운그레이드 방지).

적용 스킬: **gogabridj-design**(공통 상태 뱃지·청록/주황/뮤트 토큰·금 헤어라인·이모지 0).
