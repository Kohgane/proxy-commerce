# fixtures/realpages/diag/ — 진단 파일 = 회귀 테스트 (v78 STEP5)

## 무엇인가
확장 팝업 **'이 페이지 수집이 이상해요'**(kgpDiagBundle) 버튼이 내려주는 진단 파일 그대로다.
파일 하나 = **스냅샷 HTML** + 임베드 JSON:

```html
<!doctype html> … 페이지 렌더 DOM 전체 …
<script type="application/json" id="kgp-diagnostic">
{ "url": "...", "host": "...", "ext_version": "1.5.x",
  "extracted": { …kgpExtractProduct() 결과 스냅샷… },
  "detection": { …감지 로그… } }
</script>
```

## 왜 (STEP5 — 공식 계약층)
하네스 어서션 스키마를 **진단 `extracted` 포맷과 동일**하게 통일했다. 그래서 오너가 이 파일 하나를
이 폴더에 넣으면 `tests/test_v78_diag_contract.py`가 자동으로 회귀 테스트로 삼는다:

1. 파일의 임베드 JSON에서 **기록된 `extracted`(계약 스냅샷)** 를 읽고,
2. 같은 HTML을 **재-추출**한 뒤,
3. **계약 필드**(진단 extracted 스키마 그대로: `price·currency·price_status·field_sources·desc_source·
   options·skus·images·detail_images·reviews·rating·review_count·title`)가 **일치**하는지 대조.

즉 "이 HTML은 이 결과로 계속 추출돼야 한다"를 오너 파일 자체가 못박는다. 추출기를 바꿔 이 결과가
달라지면 이 게이트가 빨개진다(회귀 방지).

## 드롭인 방법 (오너)
1. 문제 페이지에서 팝업 → '이 페이지 수집이 이상해요' → `kgp-diagnostic-<slug>.html` 다운로드.
2. 그 파일을 이 폴더(`fixtures/realpages/diag/`)에 커밋.
3. CI/`pytest tests/test_v78_diag_contract.py`가 그 파일을 회귀 계약으로 자동 실행.

※ 결과가 **틀린** 페이지라면(버그 재현), 먼저 추출기를 고쳐 올바른 스냅샷을 만든 뒤 그 파일을 넣는다
(틀린 스냅샷을 계약으로 박제하지 말 것 — 정직).

## 현재 파일
- `amazon-dp-sample.html` — 합성 진단 파일(현재 추출기로 생성, 실기기 캡처 아님·정직 표기).
  buybox 현재가 29.99 / field_sources.price=buybox / desc_source=adapter / 옵션 색상×4 / rating 없음(더미 0).
