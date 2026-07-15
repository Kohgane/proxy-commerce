# v71 STEP5 — 디폴트 마켓 스모크 표 회수 (v70 STEP4 잔여)

## 증상 (오너)
- 라쿠텐·야후재팬 등에서 수집 버튼 미표시(퍼센티는 뜨는 페이지에서 우리는 안 뜸).

## 근원 + 수리 (`content_script.js` `kgpDetectPageType`)
- v60 STEP5가 디폴트 소싱처를 `isDetail ? "single" : "list"`로 판정 → **애매 URL을 무조건 list 기본값**. 라쿠텐 상세(`item.rakuten.co.jp/shop/code/`)·야후 일부 상세 URL은 상세 RE에 안 걸려 **목록으로 오판** → 상세 FAB 미표시(목록 벌크바는 카드 0이라 아무것도 안 뜸).
- **수리**: 디폴트 소싱처도 **URL이 명확할 때만** URL 판정(`isDetail && !isList → single`, `isList && !isDetail → list`), **애매하면 DOM 신호로 낙하**(단일 h1·갤러리·JSON-LD Product → single → FAB / 리스트 그리드 → list → 벌크바 / 무신호 → unknown → FAB). 버튼은 항상 노출.

## 사이트별 스모크 표 (Playwright 실브라우저 실측 — `test_v71_market_smoke`)
| 사이트 | 대표 URL | 판정 | 목록 버튼 | 상세 버튼 | 단건 수집 |
|---|---|---|---|---|---|
| 라쿠텐 목록 | search.rakuten.co.jp/search/mall/desk/ | list | **벌크바 ✓**(카드 배지+호버) | — | 벌크 큐 |
| 라쿠텐 상세 | item.rakuten.co.jp/shop/abc123/ (상세 RE 불일치) | single(DOM 낙하) | — | **FAB ✓** | 단건 |
| 야후재팬 목록 | shopping.yahoo.co.jp/search?p=desk | list | **벌크바 ✓** | — | 벌크 큐 |
| 야후재팬 상세 | shopping.yahoo.co.jp/products/xyz-987 | single | — | **FAB ✓** | 단건 |

전 행 실측(라쿠텐 상세는 애매 URL→DOM(JSON-LD Product+단일 h1)→FAB로 회복 — 퍼센티 동급). 목록=중앙 벌크바+호버 배지, 상세=우측 단건 FAB, 둘 다 제네릭 휴리스틱 폴백 보장.

## 판정
- 가드 `tests/test_v71_market_smoke.py` (6): 소스계약(무조건 list 기본값 제거·DOM 낙하) + **Playwright 파라미터라이즈** 라쿠텐/야후 목록→벌크바·상세→FAB.
- 회귀 갱신: `test_v60_hover_default`(디폴트 소싱처 애매 URL→DOM 낙하로 정정, node 하네스에 라쿠텐 상세 케이스 추가).
- manifest 1.5.86. 전체 그린.
- **실기기(오너 몫)**: 라쿠텐(퍼센티 뜨는 페이지)·야후재팬 목록+상세 각 버튼 캡처 → `docs/screens/v71/`. (개발 프록시 라이브 마켓 차단 → 대행 불가, 구조 스모크로 대체.)

## 금지 준수
- 무음 미표시 0(애매 URL도 DOM 낙하로 버튼 보장) · 1회성 스캔 회귀 0(STEP4 재스캔) · 가짜 성공 0.

적용 스킬: (확장 페이지 판정 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
