# v87-X2 · 상품 수집 화면(manual_collect) 에디토리얼 격상

STEP3 화면 순회 1/3. gogabridj-design 토큰으로 격상(정보구조·기능 불변, 스타일만).

## 변경(BEFORE → AFTER)
- 헤더: 제네릭 `<h1 class="h4">상품 수집 → 등록</h1>` → **오버라인 금 라벨**(`console-kpi-label`) + **세리프 헤더** `해외 상품, 한 번에 담기` + **금 헤어라인**(`pc-hairline`) — P~T 계보 동일 패턴.
- 상태 안내: `alert alert-info`(부트스트랩 파랑) → `pc-status pc-status-warning`(은은한 앰버, 토큰).
- 강조색: `text-primary`(부트스트랩 파랑 #0d6efd) → `text-teal`(청록, 브랜드) — "수집" 인라인 강조·인페이지 안내·스피너.
- JS 일괄 결과: `alert alert-info` → `pc-status pc-status-info`.
- 파비콘 안내 카드: `alert alert-light` → 중립 `border rounded bg-white`(부트스트랩 alert 시맨틱 제거).
- 인라인 하드코딩 hex `#e5e7eb` → `var(--line,#e6decb)`(썸네일 보더 2곳).

## 정직·불변
- 기능 0 제거(원클릭 소싱처·URL·일괄수집·인페이지 안내 전부 유지). 개발표기·mock 0.
- 강조 1색/화면: CTA=주황(처음이신가요), 링크·상태=청록, 포인트=금.

캡처: `x2-collect.png`(좌 BEFORE / 우 AFTER, 실행 결과 렌더).
