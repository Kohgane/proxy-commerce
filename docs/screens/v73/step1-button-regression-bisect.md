# v73 STEP1 — 버튼 렌더 회귀 bisect·복원

## 증상(오너 리포트)
아마존 검색결과 **중앙 벌크바 소멸**, 상세 **우측 FAB 소멸**, **호버 버튼 일부만**. 카드 배지(좌상단 '수집')는 정상.

## bisect — 회귀 커밋 확정: `0d46c55` (v72 STEP4, all:initial 격리)
실제 content_script를 구조 충실 아마존 검색 DOM(24타일)에 주입해 **벌크바의 뷰포트 좌표**를 3개 커밋에서 측정:

| 커밋 | 벌크바 position | 벌크바 top | 실렌더(뷰포트 내) |
|---|---|---|---|
| `483a59f` (부모, all:initial 이전) | fixed | **12px** | ✅ 보임 |
| `0d46c55` (v72 STEP4 격리) | fixed | **2604px** | ❌ **소멸**(화면 밖) |
| `HEAD` (v73 수리) | fixed | **12px** | ✅ 복원 |

## 근본 원인 (감지·주입 로직 아님 — **위치 오프셋**)
v72 STEP4가 사이즈 격리로 `all:initial !important`를 cssText 최선두에 붙였다. `all:initial`은 `top/left/right/transform`을 **`auto`로** 리셋하는데 **`!important`가 걸려** 있었다. 그런데 벌크바·FAB·호버버튼의 그 오프셋들(`top:12px`·`left:50%`·`right:16px`·앵커 `top/left`)은 **비-`!important`**였다 → `auto !important`가 이겨 요소가 **정적 흐름 위치**(긴 목록 페이지 최하단, top≈2604px)로 떨어져 화면 밖 = '소멸'.
- **카드 배지가 생존한 이유**: 배지 오프셋(`top:6px !important`·`left:6px !important`)은 이미 `!important` → 격리를 이김. → "배지는 보이는데 바/FAB/호버만 소멸"과 정확히 일치.
- **FAB**: `right:16px`·`top:calc(50% - 24px)` 비-!important → 상세(긴 페이지) 최하단으로 → "상세 우측 버튼 소멸".
- **호버 버튼**: 앵커 오프셋 비-!important → 카드 내 정적 위치로 → 카드 레이아웃 따라 "일부만" 보임.

## 수리 (크기 격리 유지 — 격리 제거 아님)
- 벌크바·FAB cssText의 **모든 위치/레이아웃 오프셋에 `!important`** 부여(`top/left/right/gap/max-width/transform` 등).
- `_kgpAnchorCss`(호버 버튼 앵커) 오프셋 전부 `!important`.
- 동적 위치(드래그 `kgpMakeDraggable`·줌 클램프 `kgpClampFixed`)도 `_kgpPos()=setProperty(prop,val,'important')`로 설정 → 저장 위치 복원·드래그도 격리를 이김.
- `all:initial` 크기 격리는 **그대로 유지**(v72b STEP4 자식 격리 포함) — 알리 과대 방지 회귀 없음.

## 판정
- 가드 `tests/test_v73_button_render.py` (2, Playwright · 실 content_script 주입):
  - 검색: 벌크바 **실렌더**(barVisible=DOM+display+뷰포트+폭>0) + 24타일 배지·호버 버튼 + 카운트 "메인 16 · 광고 8".
  - 상세: 우측 FAB 실렌더(fixed·가시).
  - **barVisible**가 '존재하나 안 보임'(top=2604 소멸)을 잡는다 — 위치 회귀 재발 방지 machine.
- 픽스처 `fixtures/realpages/amazon-search.html`(24타일·16유기/8광고·유효 ASIN·img.s-image, 오너 실스냅샷 공급 시 교체).
- manifest 1.5.90→**1.5.91**(재로딩) + 버전핀 34곳.
- 회귀: 전체 그린.
- **판정 캡처**: docs/screens/v73/step1-amazon-search-bulkbar.png(벌크바 top-center 렌더 + 전 타일 호버/배지/AD), step1-amazon-detail-fab.png(우측 FAB).
- **실기기(오너 몫)**: 알리·아마존·테무·요시다 4사이트 3종 버튼(벌크바·FAB·호버) 캡처 — 확장 **1.5.91 재로딩** 후.

## 금지 준수
추출기 변경 0(동결) · 격리 제거 0(all:initial 유지) · 가짜 성공 0(barVisible 실렌더 검증).

적용 스킬: (확장 오버레이 위치 — 인라인 스타일 관행. impeccable/humanizer CLI 미설치.)
