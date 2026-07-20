# v78 STEP5 — 진단 extracted를 공식 계약층으로

## 브리프
> STEP 5 — 진단 extracted를 공식 계약층으로: 하네스 어서션을 진단 extracted 포맷과 동일 스키마로 통일
> (오너 제출 파일이 곧 회귀 테스트).

## 무엇을 했나
확장 팝업 **'이 페이지 수집이 이상해요'**(kgpDiagBundle)가 내려주는 진단 파일(`kgp-diagnostic-*.html`)은
**스냅샷 HTML + 임베드 JSON**(`<script id="kgp-diagnostic">{url, extracted, detection, …}</script>`)이다.
`extracted`는 캡처 시점 `kgpExtractProduct()` 결과 스냅샷.

STEP5는 하네스 어서션 스키마를 **그 진단 `extracted` 포맷과 동일**하게 통일했다. 오너가 파일 하나를
`fixtures/realpages/diag/`에 넣으면 `tests/test_v78_diag_contract.py`가 자동으로 회귀 테스트로 삼는다:

1. 파일의 임베드 JSON에서 **기록된 `extracted`(계약 스냅샷)** 를 읽고,
2. 임베드(우리 메타)를 제거한 **스냅샷 HTML만 재-서빙**해 `kgpExtractProduct()`를 재실행,
3. **계약 필드**(진단 extracted 스키마 그대로: `price·currency·price_status·field_sources·desc_source·
   options·skus·images·detail_images·reviews·rating·review_count·title`)가 **일치**하는지 대조.

즉 "이 HTML은 이 결과로 계속 추출돼야 한다"를 **오너 파일 자체가 못박는다**. 추출기를 바꿔 이 결과가
달라지면 이 게이트가 빨개진다(회귀 방지). `_contract_view()` 투영 키 = 진단 extracted 실 필드명(스키마 통일).

## 왜 임베드 제거인가
추출기의 `_fromJson()`가 `application/json` 스크립트를 워크하므로, 임베드 JSON을 그대로 두면 그 blob을
페이지 데이터로 오인한다(재-추출 오염). 임베드는 우리 메타일 뿐 캡처된 페이지 콘텐츠가 아니므로 재-서빙
전에 제거 → 남는 건 오너가 캡처한 순수 스냅샷 HTML. (샘플 픽스처도 클린 스냅샷의 fixpoint로 생성.)

## 판정
- 가드 `tests/test_v78_diag_contract.py`(4): 진단 임베드 파서 + **계약뷰 키가 진단 extracted 필드명과 동일**
  실증 + `diag/README.md` drop-in 규약 + **Playwright**: `amazon-dp-sample.html` 재-추출 == 기록 extracted(계약뷰).
- 샘플 `fixtures/realpages/diag/amazon-dp-sample.html`: price 29.99 · `field_sources.price=buybox` ·
  `desc_source=adapter` · 옵션 색상×4 · rating 없음(더미 0) · review_count 3.
- **판정 캡처**: `step5-diag-contract.png`(오너 파일 → 임베드 제거·재추출 → 계약뷰 대조 → 회귀 게이트).
- 전체 **11438 passed / 22 skipped**.

## 정직 / 금지 준수
- 샘플은 **합성 진단 파일**(현재 추출기로 생성, 실기기 캡처 아님) 명시. 틀린 스냅샷을 계약으로 박제 금지
  (버그 재현 파일은 먼저 추출기를 고쳐 올바른 스냅샷을 만든 뒤 넣는다 — README 명문화).
- **확장 런타임 무변경**(하네스·픽스처만) → manifest **버전 유지 1.5.108**(no-op 리로드 배제).

적용 스킬: (테스트 하네스·픽스처 — 확장/UI 런타임 변경 없음. impeccable/humanizer CLI 미설치.)
