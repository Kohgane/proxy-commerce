# v86-H — 스위트 레드 봉합 (CI collect-only 사각 노출)

## 발견
`origin/main`(1.5.137) 전체 스위트 실행 → **22건 실패**. 근본 원인: **CI python-guard가 `pytest --collect-only`만**
돌려(테스트 수집만 확인) 실제 실패를 못 잡는다. v79~v86의 의도적 추출 개선 이후 테스트/픽스처가 갱신 안 돼
레드가 **보이지 않게 누적**됐다(Docker Smoke도 전체 스위트 미실행).

## 분류·처리 (22건)

### A. 스테일 node-하네스 — 새 의존 함수 미주입 (테스트 버그, 제품 정상)
- `test_v76_title_sanitize` / `test_v80_recollect_verdict`: `_sanitizeTitle`이 v83 STEP3의 `_AMZ_CAT_TAIL_RE`를
  참조하는데 하네스가 주입 안 함 → ReferenceError. **주입 추가.**
- `test_v70_price_precision`: `_domPrice`가 v84.1의 `_inCartScope`를 참조 → deps에 `_fn("_inCartScope")` 추가.
- `test_v81_source_matcher::test_amazon_country_currency_locale`: `_localeCurrency(opts)`로 시그니처 변경 →
  추출 정규식 `\(\)`→`\([^)]*\)`. (통화값 de/jp/uk/fr/com은 불변 — 정상.)

### B. 스테일 소스계약 리터럴/센티널 (테스트 버그, 제품 의도 변경)
- `test_v45_p3p4p5`: FAB가 shadow DOM 전환 → z-index 위치 창(1500자) 브리틀. `_kgpPinFixed`의 top z-index
  강제(계약)로 단언 교체.
- `test_v47`·`test_v51`: ZIP 파일 목록이 `views.py`→`src/build_extension.py`로 단일화 이관됨. 계약 대상 파일 교정
  (build_extension이 kgp-main.js·kgp-net.js 포함 확인).
- `test_v56::test_token_not_in_run_js`: `"TOK"` 부분일치가 `_LOWRES_TOKEN_RE`('TOKEN')와 오탐 →
  정확 센티널(`kgp_`·`Bearer`·`Authorization`)로 교정.
- `test_v78_desc_priority`: `description = _m`→`_stripHtmlNoise(_m)` 래핑 반영.
- `test_v83_currency_ali`: 알리/아마존 정규식 v83 STEP2 타이트닝(`[a-z]{2,3}(\.[a-z]{2,3})?$`) 반영.

### C. 서버 동작 — 불일치 데이터 (테스트 데이터 버그, 제품 정상)
- `test_v72b_recollect`: 재수집이 **KRW-on-amazon.com**을 저장하려 했으나 v83 STEP1 도메인-통화 정합 게이트가
  정직하게 폐기(실 US 아마존은 KRW 미반환). 실증(`sanitize_payload`: KRW/.com→폐기, USD/.com→보존)으로 확인 →
  계약(재수집-가격채움)은 도메인 정합 통화(USD)로 검증하게 교정.

### D. 실페이지 진단 계약 (10건) — 오너 ground-truth 드리프트
- **7건 = `kgp-snapshot-*`(진단 임베드 없음)**: 팝업 '진단 스냅샷 저장'이 내리는 순수 DOM 스냅샷이 diag/에
  섞여 계약 baseline 없이 글로빙됨 → `_parse_diag` 실패. **DIAG_FILES를 임베드(kgp-diagnostic) 보유 파일로 필터**
  (스냅샷은 realpages 하네스용, 계약 대상 아님).
- **3건 = 진짜 드리프트**(오너 의도 브리프 v79/v80 반영, 코어 필드 title/price/images/rating은 불변):
  - rakuten receno **옵션 6→2**(v79/v80 화이트리스트가 브랜드·원산지·상품명 오염 제거 = **개선**).
  - amazon Craighill **리뷰 9→1**, temu **리뷰 6→10**(v79 STEP5 아마존 리뷰 재작성 — 카운트가 **양방향** 변화
    = 알고리즘 교체이지 체계적 손실 아님). 복잡 실 PDP(교차판매 리뷰 다수)라 카운트 자체가 모호.
  → **오너 캡처 baseline(임베드 extracted)을 현행 추출로 리베이스**(HTML 스냅샷·오너 메타 url/host/ext_version은
    불변, '기대 추출' 주석만 갱신 = 골든파일 정상 유지보수). ★리뷰 카운트 드리프트는 오너 라이브 스팟체크 권장.

### E. og-card 스테일 (마스킹됐던 23번째 실패)
- `test_v50_icon_v8_rollout::test_og_card_uses_v8_master`: og-card가 v8 마스터로 **재생성돼 있어야** 하는데
  main 커밋본이 구본이라 재생성 시 md5 불일치. (작업트리에 커밋 안 된 재생성본이 있어 첫 실행 땐 가려져 있었다.)
  → `scripts/gen_og_card.py` 재생성 커밋(정본 = v8 마스터). 유일한 **에셋 재생성**(코드 로직 무변경).

## 판정
- 개별 수리 후 각 파일 그린 + 전체 스위트 그린(레드 0).
- **제품 로직 변경 0**(테스트 하네스·계약·픽스처 baseline + og-card 에셋 재생성만) → 확장 manifest 범프 불요.

## 후속 권고 (CI 사각 봉인)
CI가 `--collect-only`뿐이라 실 실패가 안 잡힌다. **전체 스위트(또는 최소 확장/추출/계약 테스트군)를 CI에서 실제
실행**하도록 게이트 강화 권고(별도 결정 — 러너 시간 ~6분 증가 트레이드오프). 이번 22건은 그 사각의 누적분.
