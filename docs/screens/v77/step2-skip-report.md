# v77 STEP2 — 미부착 타일 자가보고 (data-kgp-skip)

## 배경(오너)
캡처의 그 미부착 타일(World's Slimmest, $4.99)이 "왜 이 타일만 버튼이 없지?"를 판독 불가. 자격 필터 탈락 사유가 안 보임.

## 수리 — data-kgp-skip 자가보고
- **`_kgpMarkSkip(el, reason)`**: 자격 필터에서 탈락한 타일에 `data-kgp-skip="사유"` 속성 부여 + 사유별 카운트
  집계(`_kgpSkipStats`). 채택된 타일은 `_kgpClearSkip`로 표식 제거(재스캔 정합).
- **사유 매핑**:
  - 아마존 어댑터: `non-product`(구조적 비상품 영역)·`no-asin`(유효 ASIN 없음)·`dup`(중복)·`parse-fail`(제목·이미지 없음).
  - 제네릭: `no-url`(URL 추출 실패)·`dup`·`non-product`·`nav`(내비/카테고리)·`parse-fail`·`no-price-no-url`.
- **디버그 패널**: 진단 번들(`kgpDiagBundle`)·감지 응답에 `excl`(사유별 카운트) + `skipStats`(타일 스킵 사유별)
  집계 노출 → "이 페이지 왜 이래?"를 사유 분해로 판독.
- **표식 정합**: 스캔된 전 타일은 **버튼(`data-kgp="done"`, STEP1) 또는 스킵 사유(`data-kgp-skip`)** 중 하나 —
  **무표식 타일 0**. 특정 미부착 타일은 속성 하나로 이유 확인.

## 판정
- 가드 `tests/test_v77_skip_report.py`(3): source-contract(`_kgpMarkSkip`/`_kgpClearSkip`/`_kgpSkipReset`·어댑터·제네릭
  사유·진단 skipStats) + **Playwright 실 주입**(아마존 검색 25타일: 버튼 24 + 스킵 1(no-asin) + **무표식 0** +
  비상품 위젯 `data-kgp-skip="no-asin"`).
- 픽스처 `amazon-search.html`에 비상품 위젯(ASIN 없음·이미지 없음) 1개 추가 → 스킵 자가보고 실증(상품 24 불변).
- 영향 테스트: 노드 하네스(v63/v65/v66)에 스킵 스텁 추가 · 감지 계약(v73_detection) asinMissing 1(비상품 위젯).
- **판정 캡처**: `step2-skip-report.png`(24 타일 버튼 + 1 비상품 위젯 `data-kgp-skip="no-asin"` · 무표식 0 · 실측표).
- manifest 1.5.103→**1.5.104**(재로딩) + 버전핀. 추출기 불변.

## 계약(브리프)
> STEP 2 — 미부착 타일 자가보고: 탈락 타일에 `data-kgp-skip="사유"` + 사유별 카운트. 타일 전부 [버튼 1개 or skip 사유 1개] — 무표식 0.

## 금지 준수
- 추출기 변경 0 · 가짜성공 0(스킵은 실제 탈락 타일에만·정직 사유) · 무표식 타일 0.
- ※ 오너 캡처의 실제 미부착 타일($4.99)은 라이브에서 확장 1.5.104 재로딩 후 그 타일의 `data-kgp-skip` 값으로 원인 확인
  (버튼이 있어야 할 상품이 스킵되면 그 사유가 곧 버그 지목).

적용 스킬: (확장 감지 로직·자가보고 속성 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
