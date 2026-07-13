# v66 STEP1 — 감지 분모를 메인 그리드로 한정

## 원칙
- 카드 감지·카운트 대상을 **메인 검색결과 그리드**로 스코프. 추천 캐러셀·frequently-viewed·배너 타일은 **분모에서 제외**하고 별도 카운트("추천영역 n 제외"). **분모 뻥튀기 금지.**

## 수리 (`_kgpAmazonCards`)
- 스코프 = `document.querySelector('.s-main-slot, [data-component-type="s-search-results"]')`. 카드 셀렉터를 이 스코프 안에서만(`scope.querySelectorAll`).
- 메인 그리드 **밖** 유효 ASIN 카드(추천 영역)는 `_kgpExcl.reco++`로 별도 집계(분모에 미포함).
- `_kgpExcl`에 `reco` 추가. 팝업 감지 진단 패널: **`메인 그리드: 상품 N / 스캔 N · 추천영역 제외 M`**. 벌크바 카운트: `메인 N개 중 상품 M … · 추천 제외 K`.

## 메인 그리드 100% 인식 (버튼 안 붙는 카드 0)
- 메인 슬롯 내 미감지 카드 원인은 디버그 패널 사유 분해(파싱실패/URL실패/중복)로 근거. 유효 ASIN 상품은 v42/v45 셀렉터 확장으로 이미 인식 → 메인 슬롯 스코프로 추천영역 오염 제거 → 메인 인식률 상향.

## 판정
- 가드 `tests/test_v66_main_grid_scope.py` (3):
  - 소스계약(`reco`·`.s-main-slot`·`scope.querySelectorAll`·팝업/툴바 추천 제외 표기).
  - **node로 실제 `_kgpAmazonCards` 실행**: 메인 슬롯 3 상품 + 밖 2 유효 ASIN → **감지 3·스캔 3(뻥튀기 없음)·reco 2** 실증.
  - manifest 1.5.72. e4/v25 계약(메인 표기)·exclusion-audit 리터럴 갱신.
- 실기기(아마존 검색결과 스크롤 전체 버튼 없는 메인 카드 0 + 패널 "메인 n/n · 추천 제외 m")는 오너 환경 — 프록시 라이브 차단.

## 금지 준수
- 분모 뻥튀기(추천영역 포함 카운트) 제거 · Tier1 의존 0 · 가짜성공 0.

적용 스킬: (확장 감지 스코프 — 우리 토큰 유지. impeccable/humanizer CLI 미설치.)
