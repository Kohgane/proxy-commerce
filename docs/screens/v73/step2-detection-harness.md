# v73 STEP2 — UI 감지 계층 순수 모듈 하네스 (재발 방지)

## 목적
"추출은 되는데 **버튼이 사라지는/타일을 놓치는**" 부류의 회귀를 **기계가 잡게** 한다. 감지 로직을 DOM 주입·chrome과
분리한 **순수 모듈**로 빼고, 실 픽스처에 대해 계약을 CI 게이트로 검증한다.

## 구현
- **순수 모듈 `extensions/chrome-collector/kgp-detect.js`**: `KGPDetect.detectUI(document, href)` →
  `{pageType, tiles:[{asin,sponsored,region,href,anchor,hasAnchor,el}], main, ad, reco, asinMissing, anchors, countLabel}`.
  부수효과·chrome·주입 없음 → jsdom/Playwright에서 그대로 실행 가능. `pageType`(URL 규칙+DOM 점수)·`amazonTiles`
  (유효 ASIN·스폰서 태깅·region·anchor=img.s-image) 순수 함수.
- **content_script 위임(단일 소스)**: `kgpDetectPageType`가 `KGPDetect.pageType(document, location.href, {cardCount})`에
  위임(미로드 시 인라인 폴백). 매니페스트가 `kgp-detect.js`를 `content_script.js` **앞에** 로드(같은 isolated world).
- **drift-guard**: 감지 규칙(DETAIL/LIST URL 정규식·스폰서 셀렉터·타일 셀렉터·ASIN 패턴)을 모듈 ⇔ content_script
  **byte-identical**로 못박아 무단 분기 차단 → 한쪽만 바뀌면 CI 적색.

## 계약(오너 확정 아마존 검색 기준치 — CI 어서션)
| 항목 | 기대 | 결과 |
|---|---|---|
| pageType | 목록(list) | ✅ |
| tiles | 24 (`data-component-type="s-search-result"`) | ✅ |
| organic(main) | 16 | ✅ |
| ad(sponsored) | 8 (`puis-sponsored-label-text` 등) | ✅ |
| asin 결손 | 0 | ✅ |
| tile anchor | `img.s-image` 24/24 | ✅ |
| 벌크 카운트 | "메인 16 · 광고 8" | ✅ |

상세 3종(amazon-dp·temu·요시다-generic): **pageType='single'** ✅.

## 판정
- 가드 `tests/test_v73_detection_harness.py` (9): 매니페스트 로드 순서 · pageType 위임 소스 · drift-guard(규칙
  byte-identical) · 아마존 검색 계약(24/16/8/anchors/countLabel) · 상세 3종 single. 순수 모듈 = chrome 불필요·무레이스.
- 픽스처 `fixtures/realpages/amazon-search.html`(24/16유기/8광고·유효 ASIN·img.s-image; **오너 실스냅샷**
  `kgp-snapshot-www-amazon-com-s-k-ultraslim-phone-grip-*.html` **공급 시 교체** — 구조·계약 동일하게 맞춰 커밋됨).
- STEP1 가드(`test_v73_button_render`)도 실 번들(kgp-detect→content_script)로 재실행 → 위임 경로 end-to-end 검증.
- manifest 1.5.91→**1.5.92** + 버전핀. 다운로드 패키징에 kgp-detect.js 포함.
- 회귀: 전체 그린.
- **CI 게이트 로그**: python-guard(collect) + 로컬 전체 스위트 그린 = 감지 계약 통과.

## 금지 준수
추출기(kgp-extractor.js) 변경 0(동결) · 격리 제거 0 · 가짜 성공 0(실 픽스처·실 모듈 출력으로 검증).

적용 스킬: (감지 로직 순수 모듈 — UI 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
