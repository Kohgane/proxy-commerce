# v87-X2 · 한눈에 보기(수집 이력, collect_history) 에디토리얼 격상

STEP3 화면 순회 3/3. `collect_history.html` — 수집한 상품을 한자리에서 보는 목록.
gogabridj-design 토큰으로 헤더 격상 + JS 부트스트랩 색 잔재 제거(기능·정보구조 불변).

## 변경(BEFORE → AFTER)
- 헤더: 제네릭 `<h1 class="h3">수집 이력</h1>` → **오버라인 금 라벨**(`한눈에 보기`) + **세리프 헤더** `수집한 상품, 한눈에` + **금 헤어라인**.
- 엑셀 동기화 결과 JS: `badge bg-success`(신규)·`badge bg-primary`(갱신) → `pc-badge pc-badge-on`·`pc-badge pc-badge-muted`.
- 일괄/트렁케이트 안내: `alert alert-warning`·`alert alert-info` → `pc-status pc-status-warning/info`.

## 정직·불변
- 요약 KPI·필터·행(썸네일·상태·번역 뱃지·정리 후보 필터)은 v64/W1/W6·W7의 토큰 구현 유지.
- 행 상태 뱃지(성공=teal·실패=danger·보관=muted)는 v64 계약(`test_v64_history_ui`)과 정합.
- 기능 0 제거·개발표기·mock 0.

캡처: `x2-killist.png`(좌 BEFORE / 우 AFTER, 상태 다양성 mock 4건 실렌더).
