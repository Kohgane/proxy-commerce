# v64 STEP7 — 수집 이력 UI 정돈 (지저분함 제거)

## 원칙
- gogabridj-design 기준 리스트 재정렬. **폰트·브랜드 토큰 변경 금지 — 배치·밀도·위계만.**

## 수리 (`collect_history_rows.html` / `collect_history.html`)
| 항목 | 전 | 후 |
|---|---|---|
| 제목 | 1줄 말줄임(text-truncate) | 유지 |
| 도메인 | 평문 muted 텍스트 | **은은한 칩**(한지 배경·line 보더 토큰) |
| 가격 | 좌정렬 | **우정렬**(text-end, 헤더도) — 스캔 편의 |
| 경로(source) | 부트스트랩 5색 배지(bg-primary 파랑·bg-warning 노랑·bg-info 청록·bg-secondary·bg-light) | **단일 중립 칩**(맵 라벨, 한지/먹 토큰) — 색 남용 제거 |
| 상태 | bg-success/bg-danger/bg-secondary(부트스트랩 채움) | **의미 토큰만**: 성공=청록·부분=주황·실패=적·보관=먹muted, **행당 1개** |
| 원가·판매가·환율 | (목록엔 원래 없음) | 드로어 가격 탭 유지(목록은 수집가만) |

- 컬럼 순서·개수 불변(벌크 상태 JS가 `tds[6]` 참조) — 셀 내부 스타일만 교체. bulk-status JS 배지도 토큰으로 동기화.

## 판정
- 가드 `tests/test_v64_history_ui.py` (7):
  - **행에서 부트스트랩 색 배지(bg-primary/warning/info/success/danger/secondary) 0**.
  - 가격 우정렬(셀·헤더)·도메인 토큰 칩·경로 단일 중립 칩·상태 토큰(teal/warn/danger)·제목 말줄임·**페이지 렌더 200**.
- 전/후 스크린샷 병치는 오너 환경(프록시가 Bootstrap CDN 차단 — 샌드박스 캡처 제약). `docs/screens/v64/step7-history-ui.md`.

## 금지 준수
- 토큰 외 색 없음(모두 var(--*) + 폴백) · 폰트·브랜드 토큰 불변 · 이모지 0(bi-* 아이콘) · 죽은 버튼 0(기능 보존, 스타일만).

적용 스킬: **gogabridj-design**(한지/먹/청록/주황 토큰·배지 통합·색 남용 제거·이모지0). impeccable/humanizer CLI 미설치→의도 수동.
