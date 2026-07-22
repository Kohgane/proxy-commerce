# v81 STEP4 — 라쿠텐 톱 오수집 차단 + 추천/이력 위젯 블록리스트

## 증상(오너 실기기)
`www.rakuten.co.jp/?l2-id=shop_header_logo`(톱페이지)에서 per-tile 수집버튼이 붙고 `data-kgp-skip` 135건 발생.
톱은 상품/목록 페이지가 아닌데 추천/이력 위젯(足あと·あなたにおすすめ·閲覧した商品からのおすすめ)이 타일로 오수집.

## 수리
### STEP A — 톱페이지 픽스처 + 하네스 계약(CI 게이트)
- `fixtures/realpages/rakuten-top.html` 추가(canonical=`https://www.rakuten.co.jp/`) — 오너 제출 스냅샷 구조(위젯 셀렉터/
  헤딩)를 충실히 재현한 합성 픽스처(실 스냅샷은 리포 미포함).
- 하네스 `tests/test_v81_rakuten_top.py` 계약: **(1) per-tile 수집버튼 0 · (2) 저장 후보 0 · (3) skip 총계 >0.**

### STEP B — 추천/이력 위젯 명시 블록리스트
- 신규 `_kgpInRecommendWidget(el)` — 컨테이너 셀렉터 `#riAshiato`(足あと), `[id^=tabpanel-recommend]`(추천 탭패널),
  섹션 헤딩 텍스트 매칭(`section`/`aside`/`role=region|tabpanel` 안 h1~h4/heading에 **閲覧した商品からのおすすめ·
  あなたにおすすめ·おすすめ商品·履歴から**… 포함 시 섹션 전체 제외).
- `_kgpGenericCards`에서 nav 체크 다음에 `if (_kgpInRecommendWidget(card)) { _kgpExcl.region++; _kgpMarkSkip(card,
  "recommend-widget"); continue; }` — **후보 제외만**(감지 자체는 유지: 제네릭 감지 로직 그대로, 이 섹션 타일만 스킵).

### STEP C — skip 사유 세분화
- `no-price-no-url` → `no-item-url`(상품 상세 링크 자체가 없음) / `no-price`(링크는 되나 가격만 없음)로 분리.
  keep-gate는 불변(가격·상품링크 둘 다 없을 때만 제외 — **회귀 0**).

manifest 1.5.119→**1.5.120**(재로딩 유도, 버전핀 전 갱신).

## 판정
- 하네스 `test_v81_rakuten_top.py`(3): 소스계약(블록리스트·사유분리) + 픽스처 톱 확인 + **실 kgpFindCards**(Playwright):
  `cards=0 · perTileBtns=0 · bar=false · recommend-widget≥6`(DOM `data-kgp-skip` 관측).
- 드리프트 하네스(v43_2·v63·v10 detection) 신규 `_kgpInRecommendWidget` dep 반영·그린.
- 전체 스위트 그린.

## 캡처
`docs/screens/v81/step4-rakuten-top.png` — 실 content_script 주입 결과 배너: **저장 후보 0 · per-tile 수집버튼 0 ·
벌크바 없음 · 제외 사유 recommend-widget 6 · non-product 2**(足あと·あなたにおすすめ·閲覧した商品 3위젯 6타일 + 카테고리 2).

## 금지 준수
어댑터 차단이 제네릭 감지를 죽이는 구조 아님 — **블록리스트는 후보 제외만, 감지 유지** · 추출 계약(하네스) 동반 ·
사유 세분화로 정직 자가보고(조용한 누락 0).

적용 스킬: (확장 감지·블록리스트 — 인라인. impeccable/humanizer CLI 미설치.)
