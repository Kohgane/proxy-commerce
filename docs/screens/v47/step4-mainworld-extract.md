# v47 STEP4 — 상세·이미지 전수 수집 재판정 (MAIN world 주입, 근본)

## 진단 — v46 STEP3가 실기기서 여전히 실패한 지점
v46은 확장 격리월드에서 **인라인 `<script>` 텍스트**를 파싱해 초기 상태 JSON을 읽었다. 그런데:
- **파싱 도달?** yes — 인라인 스크립트에 상태가 실린 사이트는 읽힌다(로컬 Chromium 검증됨).
- **깨지는 지점 = 초기 상태가 인라인 HTML에 없을 때.** Temu 등은 상품 상세/갤러리/리뷰를 **XHR로
  렌더 후에** `window.rawData`·스토어에 채운다. 이 값은 **인라인 `<script>` 텍스트에도 없다**(런타임에만
  존재). 격리월드는 그 live 전역을 못 읽으므로 → 가격/이미지 못 얻음 → **'부분 수집'**.
- 즉 v46은 '인라인에 실린 사이트'는 고쳤지만 'XHR로 채우는 사이트'는 구조적으로 못 읽었다(격리월드 한계).

## 근본 수리 — MAIN world 주입
manifest `content_scripts`에 `"world": "MAIN"` 항목 추가(kgp-extractor.js + **kgp-main.js**). MAIN world는
**페이지 월드**라 live 전역(window.rawData/__NEXT_DATA__ 등)이 그대로 보인다.
- `kgp-main.js`: 격리월드가 `postMessage({__kgpReq})` 하면 그 시점 live DOM/전역에서 `kgpExtractProduct()`
  실행 → **결과(작은 plain object)만** `postMessage({__kgpRes, meta})`로 넘김(순환참조/대용량 상태는 안 넘김).
- `content_script.js`: `kgpExtractMerged()` — 격리월드 추출 + MAIN world 추출을 **병합**(빈 필드 채우기,
  이미지·옵션·리뷰·상세는 더 완전한 쪽 채택, 가격+이미지 확보되면 partial 해제, field_sources json 우선).
  MAIN world 미응답(비지원 크롬/타임아웃 700ms)이면 격리월드 추출만(정직 폴백).
- **추가 API(XHR/fetch) 호출 0** — 오너 금지사항 준수. 이미 페이지가 받아둔 초기 상태만 읽는다.

## 수집 필드 (전수)
- 가격: sanity 게이트(KRW<100 등 거부 → needs_check).
- 갤러리 이미지: 순서 보존·중복 제거, 1번=썸네일(hiRes 원본 해상도).
- 옵션: sku 스펙 + sku별 가격.
- 상세: 상세 이미지 + 속성 표 + 본문 텍스트.
- 평점·리뷰 수 + 초기 JSON 텍스트 리뷰(추가 호출 없음).
- STEP2 상태 컬럼과 연동 — 병합 후 필드 present가 목록/드로어/토스트에 정직 표기.

## 검증
- manifest MAIN world 항목(kgp-extractor+kgp-main). kgp-main 브릿지(__kgpReq→kgpExtractProduct→__kgpRes).
- content_script kgpExtractMerged/kgpMergeMeta + handleFabClick 사용. **node로 실제 kgpMergeMeta 실행**:
  격리 부분(가격·이미지 없음) + MAIN 완전(20605 KRW·이미지 3·리뷰·평점) → 병합 완전, partial=false.
- 다운로드 ZIP include에 kgp-main.js 포함(빠지면 근본 무효). manifest 1.5.47→1.5.48.
- 가드 test_v47_mainworld_extract(6). 전체 회귀 그린.

## 최종 판정(오너 실기기)
확장 1.5.48 재로딩 후 Temu 상품 페이지에서 수집 → 가격·**갤러리 전 장**·옵션·상세·리뷰가 채워지고
목록 상태가 **성공 7/7**(또는 실제 빠진 필드만 부분)로 뜨는지 캡처. 콘솔에 `MAIN world 병합 — 이미지 N→M` 로그.
