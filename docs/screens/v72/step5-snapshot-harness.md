# v72 STEP5 — 스냅샷 하네스 정기 판정 (v70 STEP5 규약 지속)

## 목표
- 오너 제공 테무 스냅샷 + 아마존 픽스처로 **[price·currency·images·options·desc]** 5필드를 스냅샷 CI로 상시 판정.

## 구성
- **실 크로미움 하네스** `tests/test_v70_realpage_harness.py`(v70 STEP5): `fixtures/realpages/*.html`에 라이브 `kgp-extractor.js`를 물려 `kgpExtractProduct()`를 `*.expected.json`과 비교. 옵션 값 `[object`/`http` 오염 금지 계약 포함(v71 STEP2).
- **5필드 커버리지 계약** `tests/test_v72_snapshot_coverage.py`(신규): 대표 픽스처(`synthetic-amazon-dp`·`synthetic-temu-detail`)가 **price·currency·images·options·desc 5필드 계약을 모두** 담도록 강제(미래 변경이 필드를 조용히 빠뜨리지 못하게). + 테무/아마존 호스트·통화(KRW/USD) 반영 + CLAUDE.md 하네스 규약 상존 확인.
- 테무 픽스처에 `description_contains` 추가(5필드 완결).

## 대표 픽스처 판정 (실 크로미움)
| 픽스처 | price | currency | images | options | desc |
|---|---|---|---|---|---|
| synthetic-amazon-dp | 29.99 | USD | 5(관련상품·스프라이트 0) | 색상 4 | "무선 충전" |
| synthetic-temu-detail | 11235 | KRW(locale) | ≥3 | 색상 2·사이즈 2 | "방수" |

두 픽스처 모두 v70~v72 수리(가격 정밀·통화 로케일·sku 매퍼·갤러리 스코프)를 실 브라우저 DOM에서 회귀 검증.

## 판정
- 가드 `tests/test_v72_snapshot_coverage.py` (4) + `test_v70_realpage_harness`(하네스 실행) 그린.
- **CI 그린 로그**: 로컬 전체 **11308+ passed**(하네스 4건 실행·통과 포함). CD `pytest -q`(main)에서 하네스 그린. PR CI는 `--collect-only`라 수집만.
- 오너 제공 실페이지 스냅샷을 `fixtures/realpages/`에 커밋하면(확장 팝업 '진단 스냅샷 저장') 하네스 자동 포함.

## 금지 준수
- 픽스처 없는 추출 변경 0(CLAUDE.md 규약) · 합성 픽스처를 실페이지로 위장 0(정직 표기) · 가짜 성공 0.

적용 스킬: (하네스·픽스처 — 코드 변경 없음. impeccable/humanizer CLI 미설치.)
