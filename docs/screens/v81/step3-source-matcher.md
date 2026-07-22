# v81 STEP3 — 소싱처 매처 단일화 + 아마존 국가도메인 와일드카드

## 증상(오너 실기기 재현)
`www.rakuten.co.jp/?l2-id=shop_header_logo` 에서 **팝업 = "여긴 지정 소싱처가 아니에요"**, 동일 페이지 스냅샷 =
`kgp-collect-fab` 주입됨 + `data-kgp-skip` 135건. → 소싱처 판정 로직이 **팝업/콘텐츠스크립트 두 벌로 이원화**되어 불일치.

## 근본 원인
- `popup.js`가 **6개짜리 자체 목록**(`DEFAULT_SOURCE_TESTS`: taobao/tmall/1688/temu/amazon/aliexpress)만 들고 있어,
  `content_script.js`의 **13개 레지스트리**에 있는 rakuten·iherb·dhgate·qoo10·mercari·yahoo·yoshida를 **몰랐다**.
  → 라쿠텐에서 콘텐츠스크립트는 FAB 주입 / 팝업은 미지정 표시(모순).

## 수리
1. **단일 진실원천 `kgp-sources.js`** 신설 — 레지스트리(13 소싱처) + 매처(`matchHost`/`matchUrl`/`allowed`). IIFE로
   `global.KGPSources` 노출(kgp-detect.js와 동일 패턴).
   - **서브도메인 와일드카드**: `(^|\.)rakuten\.(co\.jp|com)$` 하나로 www/item/search/books.rakuten 전부 커버.
   - **쿼리·트래킹 무시**: 매칭은 **hostname만**(URL 파싱이 `?l2-id=…` 등 자연 제거).
   - **아마존 국가도메인 흡수**: `(^|\.)amazon\.[a-z][a-z.]*$` 가 com/de/co.jp/co.uk/fr/it/es… 전부 매칭.
2. **양쪽 위임**:
   - `content_script.js`: `KGP_DEFAULT_SOURCES`를 `KGPSources.SOURCES`에서 파생(.test 어댑터, fast-path 호환),
     `kgpHostAllowed()`가 `KGPSources.allowed()`에 위임(KGPSources 미로드 폴백 유지).
   - `popup.js`: 자체 목록/매처 제거 → `KGPSources.matchHost()` 사용.
   - `manifest.json` content_scripts에 `kgp-sources.js`를 `content_script.js`보다 먼저 로드, `popup.html`도 로드.
3. **메시지 3분리**(브리프 3):
   - 호스트 미등록 → "여긴 지정 소싱처가 아니에요. '소싱처 관리'에서 추가할 수 있어요."
   - 소싱처 + 상품/목록 페이지 → "지정 소싱처 (○○) — 수집 버튼이 표시돼요"
   - **소싱처지만 톱/홈** → "○○입니다 (소싱처 ✓). 상품·목록 페이지에서 수집 버튼이 나와요." (라쿠텐 톱이 여기)
   - 페이지 타입 판정은 `KGPDetect.DETAIL_URL_RE`/`LIST_URL_RE`(URL 규칙) 재사용(팝업은 DOM 없음 → URL만).
4. **아마존 국가 통화**(원 STEP3): `kgp-extractor._localeCurrency`가 이미 de→EUR·co.jp→JPY·co.uk→GBP·fr/it/es→EUR·
   그 외 amazon.*→USD 처리 — 이번에 **계약 하네스로 못박음**(회귀 방지).
5. manifest 1.5.118→**1.5.119**(재로딩 유도, 버전핀 전 갱신).

## 판정(브리프 4: 매처 단위테스트 CI 게이트)
가드 `tests/test_v81_source_matcher.py`(6, node 실행):
- `test_matcher_registry_contract`: rakuten 서브도메인 4종·amazon 국가도메인 6종·taobao → 정확 id, 미등록 2종 → null.
- `test_matcher_ignores_query_and_defaults_toggle`: `?l2-id&scid` 무시, defaults off→null, custom 도메인 매칭.
- `test_amazon_country_currency_locale`: de→EUR·jp→JPY·uk→GBP·fr→EUR·com→USD.
- `test_popup_delegates_to_kgpsources`: 팝업 자체목록 제거·KGPSources 위임·메시지 3분리·popup.html 스크립트 로드.
- `test_content_script_derives_registry_from_kgpsources`: KGPSources.SOURCES 파생·13 소싱처 전원.
- `test_manifest_loads_sources_before_content_script`: 로드 순서·버전핀.

확장 회귀 스위트(FAB·감지 하네스·타일·통화 로케일 등) 39 그린 · 전체 스위트 그린.

## 캡처
`docs/screens/v81/step3-source-matcher.png` — 실제 kgp-sources.js+kgp-detect.js 로직으로 4케이스 배지:
라쿠텐 톱=hint(소싱처✓·상품/목록에서) / 아마존 독일 dp=on(수집 버튼 표시) / 라쿠텐 상품=on / 미등록=off(미지정).

## 금지 준수
블록리스트 아님(감지 자체는 유지) · 단일 소스로 drift 봉인 · 국가도메인은 규칙 흡수(하드코딩 나열 아님) ·
메시지는 사실만(호스트 등록 O/X vs 페이지타입 분리).

적용 스킬: (확장 소싱처 매처·팝업 배지 — 인라인 스타일(gogabridj 토큰 색값 준수·이모지 0). impeccable/humanizer CLI 미설치.)
