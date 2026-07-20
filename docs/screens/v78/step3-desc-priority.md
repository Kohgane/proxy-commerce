# v78 STEP3 — 상세설명 우선순위 재배선 (desc_source)

## 근거(오너 실기기 진단, ext 1.5.102)
- 양쪽: `desc_text` = meta description(SEO 문구). 아마존 `detail_specs: 20` 잡고도 상세 필드는 "Buy …" 한 줄.

## 근본 원인
`_domDescription`이 어댑터 상세(feature-bullets 등)를 못 찾으면 **`_meta("description")`(SEO 'Buy …')로 폴백**하고,
오케스트레이션은 그 값을 최종 `desc_text`로 저장. 어댑터 상세와 meta가 한 함수에 섞여 우선순위 통제 불가.

## 수리 — 소스 사다리 재배선
- **`_adapterDetailText()`**(신설): 어댑터 상세 **DOM 전용**(meta 폴백 분리). 아마존 `#feature-bullets`+`#productDescription`+
  **`#aplus`(A+)** 본문, 테무 상세영역(`goods-desc`·`goodsDesc`·`productDesc`·`item-desc`), 제네릭 detail/description 컨테이너.
- **`_metaDescription()`**(분리): `og:description`/`description` — SEO 문구.
- **오케스트레이션 사다리**: ① 어댑터 상세(DOM) → ② ld+json/state description(Tier1) → ③ **meta는 최후 폴백**이며
  저장 시 `desc_source="meta"` 표기(품질 낮음 신호). 가격/이미지와 독립 수집(Tier1이 채워도 상세는 빌 수 있음).
- **detail_specs 병합**: `specs`(스펙 표)가 있으면 `desc_text`에 `· 키: 값`으로 병합(상세에서 스펙까지 한눈에).
- 출력에 **`desc_source`** 추가(adapter/tier1/ldjson/meta/specs).

## 계약(브리프)
> STEP 3 — desc_text 소스 사다리: 어댑터 상세 → ld+json → meta(최후·desc_source=meta 표기). detail_specs 병합.
> 계약: 아마존DP에서 desc_text에 "Buy " 접두 금지 + 불릿 포함.

## 판정
- 가드 `tests/test_v78_desc_priority.py`(4): source-contract(`_adapterDetailText`·`_metaDescription`·사다리·`desc_source`·
  스펙 병합·A+) + **Playwright**: 아마존DP(meta 'Buy …' 존재) → desc_text=어댑터 불릿('Buy ' 접두 금지)·`desc_source=adapter` /
  meta만 있는 페이지 → `desc_source=meta`(정직 표기).
- 실페이지 하네스에 `desc_text_excludes`·`desc_text_contains`·`desc_source` 계약 키 추가 + amazon-dp 픽스처에 SEO meta
  추가(어댑터가 meta를 이김 실증).
- **판정 캡처**: `step3-desc-priority.png`(BEFORE meta 'Buy …' 한 줄 → AFTER 어댑터 불릿·desc_source=adapter).
- manifest 1.5.106→**1.5.107**(재로딩) + 버전핀.

## 금지 준수
- 가짜성공 0(meta 폴백은 desc_source=meta로 정직 표기·감춤 0) · 추출기 변경 = 하네스 계약 동반.

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
