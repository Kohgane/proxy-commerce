# v86-R — 상품 카탈로그 화면 에디토리얼 격상 (STEP 5)

대시보드·주문·알림(v86-P)과 동형 에디토리얼로 카탈로그를 격상 + 상태 뱃지를 공통
`pc-badge`(v86-P 신설)로 통일 + 원시 상태 코드 노출 제거.

## 수리
- **헤더**: 제네릭 `<h4 fw-bold>` → 오버라인 키커(`console-kpi-label` '내 상품') + 헤더 + 금
  헤어라인(`pc-hairline`). '총 N건'도 부트스트랩 badge → `pc-badge-muted`.
- **상태 뱃지**(catalog_rows): 부트스트랩 `badge bg-success/warning/danger/secondary/dark/light`
  전량 제거 → gogabridj `pc-badge` 변형: 활성=청록(on)·품절=주황(off)·오류=적(danger)·
  정지=뮤트(muted)·마켓 라벨=뮤트. app.css에 `.pc-badge-muted`(--text-muted 토큰) 추가.
- **원시 코드 노출 제거(정직)**: 상태 `price_anomaly`가 뱃지·필터에서 원시 코드로 노출되던 것 →
  '가격 이상' 한글 라벨. 상태 필터 드롭다운도 원시 코드(active/out_of_stock…) → 한글 라벨 맵.

## before/after
`docs/screens/v86r/v86r-catalog.png` — BEFORE(제네릭 h4·부트스트랩 컬러 뱃지·원시 `price_anomaly`)
vs AFTER(오버라인+금 헤어라인·pc-badge 청록/주황/적/뮤트·'가격 이상'). mock 6건으로 전 상태 노출.

## 판정
- 가드 `tests/test_v86_r_catalog_grade.py`(6): 에디토리얼 헤더·pc-badge(부트스트랩 잔재 0)·
  price_anomaly 한글·상태필터 한글맵·pc-badge-muted 토큰·v36 카드 계약 보존.
- 회귀: catalog/design/token/ui_smoke/v36/emoji/audit **361 passed**(무한스크롤 fmt=rows 파셜
  단일소스 유지).

적용 스킬: **gogabridj-design**(오버라인·금 헤어라인·청록/주황/적/뮤트 토큰·공통 상태 뱃지 재사용·
이모지 0). impeccable/humanizer CLI 미설치 → 의도 수동.
