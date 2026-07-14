# v70 STEP4 — 디폴트 소싱처 전수 버튼 보장 (오너 최우선)

## 증상 (오너)
- 수집 버튼이 테무·아마존 외 디폴트 소싱처에서 전멸(요시다 등 과거 작동 사이트 회귀 의심).

## 회귀 원인 특정 (감사 선행)
- **버튼 보장 폴백은 정상**: v63 `_kgpMergeCards`(제네릭-먼저 + 어댑터 보강)로 어댑터 셀렉터 실패가 제네릭 감지를 막지 않음. v67 all-tile 개편은 `_kgpInBadRegion(structuralOnly)`로 커버리지를 **넓혔지(추천 타일도 부착)** 좁히지 않음 → 제네릭 폴백 회귀 아님.
- **진짜 결함 = 레지스트리 드리프트**: `kgpIsDefaultSourcing()`이 별도 정규식 `KGP_DEFAULT_SRC_RE` 단독 판정인데, 이 정규식이 레지스트리 `KGP_DEFAULT_SOURCES`(13사이트)보다 **4개 누락**(yoshida·iherb·dhgate·qoo10). 누락 사이트는 결정적 페이지 판정(상세=single·목록=list)을 못 받고 DOM 점수제로 빠져 `unknown` 가능 → 목록 벌크바 미표시(단건 FAB은 host 게이트로 표시).

## 수리
1. **레지스트리 단일 소스** (`content_script.js`):
   - `kgpIsDefaultSourcing()` = 정규식 fast-path **OR `KGP_DEFAULT_SOURCES` 순회 백스톱** → 레지스트리 전 사이트가 결정적 판정. 정규식에도 누락 4도메인 보강(drift 0).
2. **레지스트리 명문화** (`src/collectors/sourcing_registry.py`): `DEFAULT_SOURCING_SITES`(13) + `registry_ids()`/`registry_rows()`. 가드가 확장 id와 **1:1 일치** 강제(드리프트 재발 봉인).
3. **콘솔 가이드** `/seller/guide/sources`(`guide_sources.html`, 사이드바 링크): 사이트별 [목록/호버/상세] 버튼 보장 표 + 미지원 사이트 직접 추가 정직 안내(가짜 지원 표기 0).

## 사이트별 스모크 표 (node 하네스 실측 — `test_v70_default_sites_parity`)
전 레지스트리 사이트: **host 허용 ✓ + 상세URL→single·목록URL→list 결정적 판정 ✓**. (목록 버튼=중앙 벌크바+호버 배지 / 상세 버튼=단건 FAB, 둘 다 제네릭 휴리스틱 폴백 보장.)

| 소싱처 | 대표 host | host 허용 | 목록 판정 | 상세 판정 | 단건/벌크 경로 |
|---|---|---|---|---|---|
| 타오바오 | item.taobao.com | ✓ | list | single | 제네릭 |
| 티몰 | detail.tmall.com | ✓ | list | single | 제네릭 |
| 1688 | detail.1688.com | ✓ | list | single | 제네릭 |
| 테무 | www.temu.com | ✓ | list | single | 제네릭(+보강창) |
| 아마존 | www.amazon.com | ✓ | list | single | 정밀 어댑터+제네릭 |
| 아마존JP | www.amazon.co.jp | ✓ | list | single | 정밀 어댑터+제네릭 |
| 알리익스프레스 | www.aliexpress.com | ✓ | list | single | 제네릭 |
| 아이허브 | www.iherb.com | ✓ | list | single | 제네릭(회귀 수리) |
| DHgate | www.dhgate.com | ✓ | list | single | 제네릭(회귀 수리) |
| 큐텐 | www.qoo10.jp | ✓ | list | single | 제네릭(회귀 수리) |
| 메루카리 | www.mercari.com | ✓ | list | single | 제네릭 |
| 라쿠텐 | item.rakuten.co.jp | ✓ | list | single | 제네릭 |
| 야후쇼핑(재팬) | shopping.yahoo.co.jp | ✓ | list | single | 제네릭 |
| 요시다카반 | www.yoshidakaban.com | ✓ | list | single | 제네릭(회귀 수리) |

비레지스트리(shop.random-store.com) → host 미허용(정직 게이트, 하드 차단 아님 — 확장 소싱처 관리에서 추가 가능).

## 판정
- 가드 `tests/test_v70_default_sites_parity.py` (5): 서버↔확장 id 파리티 · 레지스트리 백스톱 소스계약 · 제네릭 폴백 비-게이트(v63) · 가이드 라우트 200(전 사이트 렌더) · **node 전 사이트 host 허용+결정적 판정**.
- manifest 1.5.79. 회귀 `test_v60_hover_default`·`test_v55_nav_button`·`test_v53_button_context` 그린.
- **실기기(오너 몫)**: 레지스트리 5곳(테무·아마존 포함) 목록+상세 버튼 캡처 각 1장 → `docs/screens/v70/`. (개발 프록시가 라이브 마켓 차단 → 대행 불가.)

## 금지 준수
- 어댑터 실패가 제네릭 차단(회귀) 0 · 무음 미표시 0(미지원은 가이드에 정직 표기) · 가짜 지원 표기 0.

적용 스킬: **gogabridj-design**(가이드 표=한지/먹/청록 토큰·bi-* 아이콘·이모지0·다리 모티프). impeccable/humanizer CLI 미설치→의도 수동.
