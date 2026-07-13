# v64 STEP2 — 광고/실상품 분류 수리

## 근본 원인 (팩트)
- 증상: 아마존 66중 48 제외 — 실상품 다수가 광고로 오판, 전체선택 누락.
- 근본: `_kgpInBadRegion(el)`이 조상 클래스에 `sponsor|advert|ads|promo|deal` 토큰이 있으면 **영역째 제외**. 아마존 스폰서 상품은 `AdHolder`/`s-sponsored` 컨테이너 안에 있으므로 **실상품인데 카드째 사라짐**(v45가 태깅은 했지만 그 앞단 영역 제외가 먼저 잘라냄).

## 수리
### 1) 광고 영역 제외 → 명시 신호 태깅만
- `_kgpInBadRegion(el, opts)` — 구조적 비상품(`structRe`: footer·recommend·carousel·viewed·similar…)과 광고(`adRe`: sponsor·advert·ads·promo·deal)를 분리.
- `opts.allowAds=true`(아마존 어댑터)면 광고 토큰으로 **영역 제외하지 않음** → 스폰서 실상품 복구. 구조적 비상품은 여전히 제외.
- 스폰서 판별은 `_kgpAmazonSponsored`(광고 배지 텍스트·`data-component-type=sp-sponsored-result`·`aria-label*=Sponsored`)의 **명시 신호만** — 과잉 휴리스틱 없음.

### 2) AD 시각화 + 전체선택 광고 제외 + 토글
- 스폰서 카드 우상단 **AD 미니 배지**(먹 배경·금 테, gogabridj 토큰) → 오너가 분류 오판을 눈으로 검증.
- `_kgpSelectableUrls()` — 전체선택/전체수집 대상은 **기본 실상품만**(광고 제외). 벌크바 **`광고 포함`** 토글(`kgp_incl_ads`)로 전부 선택 가능.
- 벌크바 카운트: `상품 N개 · 광고 K · 제외 M · S개 선택`(광고와 구조적 제외를 분리 표기 — 정직).

## 판정
- 가드 `tests/test_v64_ad_filter.py` (4):
  - 소스계약(structRe/adRe·allowAds·AD 배지·selectable·incl-ads 토글).
  - **node**: 스폰서 컨테이너 카드 → 기본 제외 True / allowAds True → 통과(오제외 박멸) / 추천 레일은 여전히 제외.
  - **node**: 전체선택 대상 = 광고 제외(off) → 광고 포함(on) 전부.
  - manifest 1.5.65. 기존 e4/v43_2 계약도 새 분리표기로 갱신.
- 실기기(아마존 검색결과 상품/광고 카운트 실제와 부합(±2) + AD 배지) 캡처는 오너 환경 — 프록시 라이브 차단.

## 금지 준수
- 광고 오판 휴리스틱 **재도입 안 함**(오히려 제거) · 토큰 외 색 없음(먹/금) · 가짜성공 0.

적용 스킬: gogabridj-design(AD 배지 먹/금 토큰·이모지0). impeccable/humanizer CLI 미설치→의도 수동.
