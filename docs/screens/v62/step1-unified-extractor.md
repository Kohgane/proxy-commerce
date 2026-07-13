# v62 STEP1 — 추출기 단일 모듈화 (경로별 품질 편차 제거)

## 근원
북마클릿 run.js가 **자체 약한 추출 로직**(M/G/GX/BS/PP/PR)을, 확장은 kgp-extractor.js를 써서 **이원화** →
"확장이 더 약함"·"경로별 편차"의 근원. run.js와 확장이 같은 extractor를 공유하도록 단일화.

## 수리
- `/seller/bookmarklet/run.js`(`_bookmarklet_run_js`)가 **`extensions/chrome-collector/kgp-extractor.js` 전체를 번들**
  (`_shared_extractor_js` 1회 로드) + 얇은 `window.__kgpRun(cb)` 래퍼(결과에 html·버전만 얹음).
- 확장 격리월드: manifest `content_scripts[iso].js = [kgp-extractor.js, content_script.js]` — content_script가
  `window.kgpExtractProduct()` 호출. → **양 경로가 동일 kgp-extractor.js 사용**(단일 소스, 중복 구현 0).
- 산출 스키마 통일: `title/price/currency/images/gallery_images/desc_text/desc_images/options/skus/rating/reviews
  /field_sources/warnings` — 양 경로 동일.
- kgp-extractor.js는 `chrome.*` 미참조(북마클릿 페이지 월드 안전).

## 판정
- 가드 test_v62_unified_extractor(4): run.js 공유 심볼 번들·확장 동일 로드·통일 스키마·run.js 200 서빙.
- test_v52 갱신(옛 PP/PR 재구현 제거 검증 + parsePriceStr 공유). run.js node --check PASS, run-v62.
- 오너: 동일 상품을 확장/북마클릿 각각 수집 → 필드 결과 동일 캡처(배포 후 실기기).

## v62 남은 STEP (후속)
STEP2 테무 goods_id 키드 매칭(간헐 종결) · STEP3 옵션/상세 완성도(v58/v60 반영 확인+아마존 twister) ·
STEP4 키워드 서버 생성 이관 · STEP5 v61 판정 회수(오너 실기기).
