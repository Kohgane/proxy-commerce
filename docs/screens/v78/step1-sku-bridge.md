# v78 STEP1 — sku→옵션 브리지

## 근거(오너 실기기 진단 로그, ext 1.5.102)
- 테무: `options: 0, skus: 8` — sku→옵션 변환 단절.

## 근본 원인
sku 스펙 매퍼 `_collectSkuSpecs`가 `_pickStrField(o, re)`로 축명/값 키를 찾는데, **키를 원문 그대로**
정규식(`speckey`/`specvalue`)에 매칭했다. 실기기 테무 sku는 **underscore 키**(`spec_key`/`spec_value`)를 써서
`speckey`/`specvalue` 패턴에 안 걸림 → 8개 sku가 있어도 축·값 미추출 → `axisMap` 공백 → **options=0**.

## 수리 — 키 정규화 + 단일 변환 함수
- **`_normKey(k)`**: 키에서 `_`·`-`·공백 제거 후 매칭(`_pickStrField`/`_pickUrlField`). `spec_key`→`speckey`,
  `spec_value`→`specvalue`, `spec_value_name`→`specvaluename` 인식 → 실기기 underscore sku 변환 복원.
- **`_skusToOptions(axisMap, skus)`**: sku→옵션 **단일 변환 함수**(하네스·확장 경로 통일). ① 이름 축(값 2+) 우선.
  ② 이름 축 0이어도 `skus[].spec` 있으면 **위치별 전치**로 축 복원(fragmented 축명 대비). 스펙 변형이 전혀 없으면
  옵션 0(정직 — 날조 금지).

## 계약(브리프)
> STEP 1 — sku→옵션 브리지: 단일 변환 함수로 통일. 계약: 진단 extracted에서 skus>0이면 options>0.

## 판정
- 가드 `tests/test_v78_sku_bridge.py`(4): manifest 핀 + source-contract(`_normKey`·`_skusToOptions`·단일 경로) +
  node(underscore `spec_key`/`spec_value` → 축 색상·값 베이지 인식) + **Playwright 실 추출**(테무 underscore sku
  8개 → 옵션 색상[4]·사이즈[2] · 값 오염 0 · 가격 40603 KRW).
- 실페이지 하네스 신규 픽스처 `temu-sku-underscore`(underscore sku, `skus>0 → options>0` 계약) — 실 kgp-extractor 검증.
- **판정 캡처**: `step1-sku-bridge.png`(BEFORE skus:8·options:0 → AFTER skus:8·options:2[색상·사이즈]).
- manifest 1.5.104→**1.5.105**(재로딩) + 버전핀.

## 정직 표기
- 실기기 진단 파일 미첨부 → underscore sku 구조를 합성 픽스처로 재현(오너 로그 skus:8·options:0 · 가격 40603 근거).
- 스펙 변형 없는 sku는 options 0 유지(가짜 옵션 생성 0).

## 금지 준수
- 가짜성공 0(스펙 없으면 옵션 0) · 옵션 값 URL/Object 오염 0 · 추출기 변경 = 하네스 계약 동반.

적용 스킬: (확장 추출기 순수 함수 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
