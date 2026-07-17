# v75 STEP3 — 스냅샷 제출 경로 정식화 (진단 파일)

## 목적
오너/유저가 **파일 하나만 전달**하면 하네스가 그대로 재현하도록, 확장에서 **스냅샷 + 추출 결과 로그**를 하나의
진단 파일로 묶어 다운로드.

## 구현
- **content_script `kgpDiagBundle` 메시지**: 현재 페이지의 스냅샷 HTML + `kgpExtractProduct()` **추출 결과** +
  감지 로그(pageType·generic/adapter·bar/fab·제외 카운트) + 확장 버전을 함께 반환.
- **팝업 버튼 `[이 페이지 수집이 이상해요]`**(스냅샷 저장 버튼 옆, 청록): 번들을 받아 **단일 진단 파일**로 다운로드.
  파일 = **스냅샷 HTML(그대로 `fixtures/realpages/` 픽스처)** + 말미에 `<script type="application/json"
  id="kgp-diagnostic">{extracted, detection, url, ext_version}</script>` **임베드**. → 파일 하나로 (a)추출기 실행
  (HTML) + (b)실제 추출 결과 대조(임베드)가 모두 가능.
- 파일명 `kgp-diagnostic-<host-slug>.html`. 저장 후 팝업에 요약(제목/가격/이미지 ○/× 개수) 표기(정직).

## 판정
- 가드 `tests/test_v75_diag_bundle.py`(3): source-contract(kgpDiagBundle 핸들러·추출/감지/버전 포함·팝업 버튼·임베드
  JSON·파일명·다운로드) + **Playwright 재현 실증**(실 kgp-extractor로 번들 생성 → 임베드에서 추출 결과 복원 →
  price=6620·스냅샷 HTML에 runParams 보존 = 한 파일로 재현).
- **판정 캡처**: `step3-diag-file.png`(진단 파일 1건 구조 — 스냅샷 2096자 + 추출 제목·가격 6620 KRW·갤러리 10·옵션 2·source json).
- manifest 1.5.96→**1.5.97**(재로딩) + 버전핀.
- **실기기(오너 몫)**: 실제 사이트에서 [이 페이지 수집이 이상해요] → 진단 파일 1건 생성 캡처(확장 1.5.97 재로딩 후).

## 금지 준수
가짜 성공 0(실 추출 결과·실 스냅샷만 번들) · 추출기 변경 0(번들링만).

적용 스킬: (확장 팝업 버튼·번들 다운로드 — 인라인 스타일 관행. impeccable/humanizer CLI 미설치.)
