# v86-S — 고아 [Mock] 템플릿 제거 + 마켓 현황 상태뱃지 격상

## 1) 고아 [Mock] 템플릿 제거 (정직 데이터)
`src/seller_console/templates/market_status.html`은 **어느 라우트도 렌더하지 않는 고아 템플릿**
(`/seller/market-status`는 `/seller/markets`로 리다이렉트 → `markets.html` 렌더). 내부에
하드코딩 `[Mock] Alo Yoga …` 가짜 상품 표·가짜 상태 뱃지를 담고 있었다. 오너 절대원칙(가짜
데이터 금지) + 코드 위생 → **파일 삭제** + `market_status.py`의 스테일 주석 갱신.
(검증: render_template·include·동적 렌더·테스트 참조 0 — 런타임 무영향.)

## 2) 라이브 markets.html 상태뱃지 격상
`/seller/markets`(라이브 마켓 현황)의 상품 상태 뱃지를 부트스트랩 `badge bg-*` → 공통
`pc-badge`(v86-P/R 컴포넌트):
- 활성=청록(on)·품절=주황(off)·오류=적(danger)·**가격 이상**=주황(off)·정지=뮤트·마켓 라벨=뮤트·
  준비 중=주황·'실 데이터'=청록.
- 원시/비일관 라벨 정리: `가격이상`(bg-info) → **`가격 이상`**(뱃지·상태 필터 옵션 동시).
- 헤더에 금 헤어라인(`pc-hairline`) 추가(오버라인은 기존).

## before/after
`docs/screens/v86s/v86s-markets.png` — BEFORE(부트스트랩 컬러 뱃지) vs AFTER(pc-badge 청록/주황/
적/뮤트·'가격 이상'). live 소스 5상태 아이템으로 렌더.

## 판정
- 가드 `tests/test_v86_s_markets_grade.py`(5): 고아 템플릿·가짜데이터 잔재 0·코드 참조 0 /
  markets pc-badge(부트스트랩 잔재 0)·'가격 이상'·헤어라인 / `/market-status`→`/markets` 리다이렉트 보존.
- 회귀: market/i18n/design/ui_smoke/v24/emoji/audit **1082 passed**.

적용 스킬: **gogabridj-design**(공통 상태 뱃지 재사용·청록/주황/적/뮤트 토큰·금 헤어라인·이모지 0).
정직 데이터(가짜 [Mock] 잔재 제거). impeccable/humanizer CLI 미설치 → 의도 수동.
