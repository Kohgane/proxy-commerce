# v79 STEP6 — desc_text 재배선 확인 (SEO/필러 거부)

## 증상(오너 실기기 1.5.108)
v78 STEP3(어댑터>ldjson>meta 사다리) 반영에도 **테무 'Temu에서…'·아마존 'Buy …'**가 여전히 desc_text에 저장.

## 배포 감사
v78 STEP3 사다리(`_adapterDetailText` + `description = _ad; descSource = "adapter";`)는 **번들에 실존**(머지 확인).
요시다가 정상 상세를 내므로 사다리 자체는 동작. → 남은 갭은 코드 부재가 아니라 **사다리의 Tier1(state
description)·meta 후보가 마켓 SEO/필러여도 거부 없이 채택**되던 것.

## 근본 원인
- **테무**: 어댑터 상세 텍스트가 비면(테무 상세는 이미지형) 사다리가 **Tier1 `j.description`**(state에 baked된
  'Temu에서 이 …을 확인하세요' 필러)로 폴백 → descSource=tier1로 필러 저장.
- **아마존**: 어댑터(feature-bullets) 미매치 시 **meta 'Buy … online'**로 폴백 → descSource=meta로 SEO 저장.

## 수리
- **`_isFillerDesc(s)`**(신설, 서버 `_FILLER_DESC_RE` 미러) — `^Buy `, `{사이트}에서 이 …을 확인하세요`,
  `제품/상품도 좋아할 수 있습니다`, `쇼핑하여 절약을 시작`, `Shop … and save`, `^Temu…` 패턴 판정.
- **사다리 Tier1·meta 게이트**: `j.description`/`_metaDescription()` 후보가 `_isFillerDesc`면 **거부** →
  빈 상세(+ 편집 AI 초안, v42 1-6, 정직). **어댑터 상세(실 DOM)는 신뢰**(필터 안 함). **specs 병합은 유지**
  (필러 거부돼도 스펙표는 desc에 반영 — descSource=specs).
- 오탐 0: '조립 방법을 확인하세요' 같은 실제 상세는 필러 아님(패턴은 '{사이트}에서 이 …을 확인하세요' 전체 형태만).

## 계약(브리프)
> STEP 6 — 픽스처에서 desc_text 접두 'Temu에서'/'Buy ' 금지.

## 판정
- 가드 `tests/test_v79_desc_filler.py`(5): 배포 감사(사다리 번들 실존) + `_isFillerDesc` 단위(필러 6케이스,
  오탐 0) + **Playwright**:
  - 테무(state·meta 'Temu에서…' 필러 + 스펙표) → desc_text 접두 'Temu에서' 0, 스펙 병합('소재: 원목') 유지.
  - 아마존(meta 'Buy …' + feature-bullets) → desc_text 접두 'Buy ' 0, 어댑터 불릿 포함, desc_source=adapter.
- 기존 `test_v78_desc_priority`·`test_v60_desc_translate_draft`·실페이지 하네스 그린(회귀 0).
- **판정 캡처**: `step6-desc-filler.png`(사다리 + 필러 게이트).
- 전체 **11463 passed / 22 skipped**. manifest 1.5.113→**1.5.114**.

## 금지 준수
- 추출기 변경 = 하네스 계약 동반 · 필러 저장 0(정직 — 빈 상세 + AI 초안) · 스펙 병합 소실 0.

적용 스킬: (확장 추출기 순수 함수 — UI 없음. impeccable/humanizer CLI 미설치.)
