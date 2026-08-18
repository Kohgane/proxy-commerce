# #597 라쿠텐 리스트 타일 가격 간이 포착 — 실픽스처 증빙

프리즈 해제: `fixtures/realpages/diag/kgp-snapshot-search-rakuten*.html`(실 검색 리스트, 612KB·136 item 앵커).

## 근원 (2갈래)
1. `_kgpPrice` 정규식이 `원`·`¥`만 잡고 **`円`(엔 한자) 접미 미처리** → `1,706円` 누락.
2. 가격이 **감지 카드 바깥 상위 타일 컨테이너**(`.searchresultitem`, 조상 d=2)에 있어 카드 스코프 텍스트로 못 잡음. (감지 카드는 `image-wrapper`, 円 0.)

## 수리 (감지 keep-set 불변 — 가격 필드만)
- `_kgpPrice`/`_KGP_CODE_MAP`/`_KGP_PRICE_RE`에 `円→JPY` 추가.
- **라쿠텐 item 타일 한정** tile-scoped 조상 가격 스코프: `item.rakuten.co.jp` 링크가 2개 초과(다른 타일 혼입)로 늘기 직전까지만 조상을 올라가 가격 포착 → 교차 오염 0. 없으면 빈값(날조 0).

## 실측 전후 (Playwright, 실 검색 픽스처)
| | 타일 감지 | 가격 채워짐 | 통화 | distinct 가격 |
|---|---|---|---|---|
| BEFORE | 35 | **0** | — | — |
| AFTER | **35(불변)** | **35** | JPY | **28**(교차 오염 0) |

- keep-set(감지·앵커) 불변 = 34타일 계약 회귀 0. 가격만 0→전수 채움.
- 회귀 0: 아마존/테무/rakuten-top/알리 타일 계약 불변(라쿠텐 host 게이트).
계약 `test_v87_597_rakuten_tile_price`(3, Playwright 실브라우저).
