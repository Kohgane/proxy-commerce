# v76 STEP5 — 상세이미지 일반화 (아마존 경로 → 테무·알리·라쿠텐)

## 배경(오너 하네 기준선)
- 상세이미지: 아마존만 6, 나머지 0. 아마존 `#aplus` 성공 경로를 기준으로 테무(보강 창)·알리·라쿠텐도 상세이미지 수집.

## 진단
상세이미지는 이미 **needDom과 무관하게 독립 수집**되는 별도 버킷이다(v57 STEP3/4·v71 STEP3에서 구축 —
`if (detailImages.length === 0) { di2 = _domImages(); ... }`). `_domImages`가 아마존은 전용 브랜치
(`#aplus·#productDescription·#feature-bullets`), 그 외는 제네릭 dSel(`[class*=detail]·[class*=description]·
decoration·richtext·goods-desc·longimage·productDesc·pdd`)로 상세이미지를 갤러리와 분리 수집한다.
→ 일반화 로직은 **이미 존재**하나, 오너 하네 '나머지 0'은 픽스처에 상세영역이 없었을 뿐 — 전 마켓 계약이 없었다.

## 이번 STEP(계약·인프라, 추출기 코드 불변)
- **하네스 상세이미지 계약 지원**: `test_v70_realpage_harness`에 `detail_images_min`/`detail_images_max`/
  `detail_images_exclude_substr` + **갤러리↔상세 상호배타**(같은 URL 양쪽 중복 금지) 검증 추가.
- **전 마켓 픽스처에 상세영역 부여 + di 계약**(실제 A+/설명/장식 구조 재현):
  - 아마존 `#aplus`(4장, 리뷰 `#reviews-medley-footer` 제외) — `detail_images_min:4`·`exclude:REVIEWIMG`
  - 테무 `decoration/richtext`(3장, 추천 `recommend-goods` 제외) — `detail_images_min:3`·`exclude:temu-rec1`
  - 알리 `description`(2장) — `detail_images_min:2`
  - 라쿠텐 `item-detail`(2장, STEP3) — `detail_images_min:2`
  - 요시다 상세영역 없음 → 0(정직, 계약 미부여)
- **검증 결과**(실 kgp-extractor): 전 마켓 상세이미지 수집 + 리뷰/추천 제외 + **갤러리↔상세 중복 0**.

## 판정
- 가드 `tests/test_v76_detail_images.py`(3 + 4파라미터): manifest 불변(1.5.101) + 하네스 상세 계약 지원 +
  독립 수집 소스 계약 + **Playwright 전 마켓 매트릭스**(아마존4·테무3·알리2·라쿠텐2 + 리뷰/추천 제외 + 상호배타 + `desc_images` 별칭 일치).
- 실페이지 하네스 4픽스처에 `detail_images_*` 계약 추가(7픽스처 그린).
- **판정 캡처**: `step5-detail-images.png`(전 마켓 di 매트릭스 — 갤러리/상세이미지/상세소재/제외/갤러리중복0).
- **manifest bump 없음**: 추출기 코드(kgp-extractor.js) 불변 — 픽스처·하네스 계약만 추가(정직).

## 정직 표기(한계)
- 실 스냅샷 미공급 → 합성 구조 픽스처(A+/decoration/description/item-detail)로 계약. 오너 실기기(테무 보강 후 상세이미지)
  검증은 오너 몫. 요시다는 상세영역 없어 di=0(계약 미부여).

## 금지 준수
- 가짜 성공 0(상세영역 없으면 0 유지) · 리뷰/추천 상세 혼입 제외 · 갤러리↔상세 상호배타 · 추출기 불변이라 bump 없음(정직).

적용 스킬: (확장 추출기 계약·하네스 인프라 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
