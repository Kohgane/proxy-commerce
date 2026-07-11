# v56 STEP4 — 테무 Tier1 최종 판정 (v55 결과 회수)

## 감사 (배포 마커·확장 버전)
| 항목 | 상태 |
|---|---|
| v55 MAIN 월드 인터셉터(kgp-net.js) | manifest `world:MAIN`+`run_at:document_start` 존재(main 병합됨) |
| kgp-net.js 파일 | 존재(Docker `COPY extensions/`) |
| 확장 버전 | 1.5.56 |
| Tier1 진단 로그 | v55: content_script가 Tier1 동작/원인 콘솔 1줄(무음 금지) |
| 라이브 배포 | `curl /health` build 해시로 확인(오너 — 프록시가 도메인 차단) |

## 신규: 판정 durable + 드로어 표기 (콘솔 안 봐도 확인)
- content_script가 `merged.tier1_diag = {used, netBound, captured, topScore, source, cause}`를 payload에 동봉.
- 서버 extension_api가 `tier1_diag`·`tier1_source`를 extra_json에 저장.
- **드로어 수집 로그에 Tier1 판정 표기**: 동작 시 "⚡ Tier1 동작 — 채택 {URL} · 최고점 N/4", 미동작 시
  "Tier1 미동작 → DOM 폴백. 원인: {미주입/매치0/시그니처미달}". → **이 캡처 하나가 합격선**을 드로어에서 직접 확인.

## tier1 미채택 시 (진단 표 없이 '불가' 결론 금지)
- 원인이 `tier1_diag.cause`에 저장 → 어느 지점(미주입/매치0/시그니처미달)인지 지목. 팝업 '자가진단 모드'(v54)
  콘솔 표로 후보 응답 채점 확인 → 그 지점만 수리. "테무 구조상 불가" 결론은 진단 표 첨부 없이는 금지.

## 로컬 실증
- tier1_diag payload→extra_json 저장(used·topScore·source). 미동작 케이스 원인 저장('매치 0건').
- 감사: manifest MAIN document_start·kgp-net.js 존재·1.5.56.

## 판정 (오너)
확장 1.5.56 재로딩 → 판매중 테무 상품 수집 → **드로어에 'Tier1 동작 — 채택 URL' + 가격 실판매가 + 해당 상품
갤러리** 캡처(합격선). 미동작이면 드로어 원인 + 자가진단 표 첨부.

## 가드
test_v56_temu_verdict(4): 인터셉터 감사·diag 동봉/저장·드로어 판정 표기·E2E 저장(동작/미동작 원인).
