# v55 STEP1 (테무 Tier1 소생) + STEP2 (이미지·가격 게이트 서버 봉인)

## STEP1 — 테무 Tier1 소생 (MAIN 월드)
- **주입 검증**: manifest에 `kgp-net.js` = `world:MAIN` + `run_at:document_start` 확인(v51부터 정상). 수집 클릭 시
  content_script는 MAIN world(`__kgpReq`→kgp-main)로 `__kgpCaptured` 추출을 받아 병합(격리월드 window.fetch 래핑
  불가 문제를 MAIN 주입으로 이미 우회).
- **자동 진단(무음 금지)**: kgp-main이 응답에 `diag{netBound,captured,topScore,topUrl}` 동봉 → content_script가
  Tier1 기여 시 `Tier1 동작 ✓ 채택 {URL}` 로그, 아니면 **원인 1줄**:
  - 인터셉터 미주입(MAIN 로드 실패 → 재로딩) / 매치 0건(API 응답 못 잡음 → 새로고침) / 시그니처 미달(최고점 N/4).
  - 타임아웃(900ms) 폴백도 "MAIN world 미응답" 원인 로그.
- v54 시그니처 채점·최고점 자동 채택 유지 + 채택 URL을 `tier1_source` 전파 + chrome.storage 로컬 저장.
- field_sources 병합이 `tier1`을 격리월드 `dom`/`none` 위에 우선(라벨 정합).

## STEP2 — 이미지 스코프·가격 게이트 서버 봉인
- **`collect_sanitize.py` 단일 지점**: 모든 경로(확장·북마클릿·수동) 저장 직전 통과.
- **가격**: KRW<100 등 비상식 하한 미만 or 통화 미상 → **값 폐기('')** + `needs_check`(★ '9 KRW 저장' 근본 —
  기존엔 needs_check 표기만 하고 값 9를 남겨 배지 '누락'인데 9 저장되던 정합 오류). 정상가는 유지.
- **이미지**: 도메인(http)·비상품 URL(logo/icon/banner/sprite/data:/상대경로) 제외 + 순서보존 중복 제거(≤40).
  Tier2 DOM 폴백의 갤러리 스코프(추천·연관 차단)는 유지 + 서버 2차 방어.

## 로컬 실증
- sanity: `9 KRW`→''(needs_check), `500`/통화없음→'', `20605 KRW`/`12.99 USD` 유지. images: logo·data·상대·중복 제외.
- E2E(확장): price 9·images[a,logo,a] → DB **price=''**·price_status=needs_check·images 1장·배지 가격 present=False.

## 판정 (오너)
판매중 테무 수집 → Tier1 동작 로그 + 5탭 채움(미달 시 콘솔 표에서 어느 시그니처인지) / 재수집 시 9 금지·갤러리 오염 0.
확장 1.5.55 재로딩 + `curl /health` build 해시.

## 가드
test_v55_tier1_sanity(6): 주입 검증·진단 소스계약·sanity 폐기·이미지 필터·E2E 9폐기·manifest.
