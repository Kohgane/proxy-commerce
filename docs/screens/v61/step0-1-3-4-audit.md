# v61 STEP0-1-3-4 + STEP5/6 감사

## STEP0 — [P0 보안] 자격증명 마스킹 (src/utils/secret_mask.py)
- `mask_value` = 접두어 + **** + 뒤 4자(ck_****d4a7). `mask_url`/`mask_text` = 쿼리 시크릿·Authorization Basic/Bearer·리터럴 마스킹.
- 오탐 방지: 일반 단어 'key'는 마스킹 안 함(쿼리/헤더 문맥만).
- 전 어댑터 공통 유틸 — WC(STEP1)·11번가(STEP4)에 적용, 확장 예정.

## STEP1 — 코가네멀티샵(WC) 406 수리 (src/vendors/woocommerce_client.py)
- 인증: 쿼리스트링 consumer_key/secret → **HTTP Basic Auth 헤더**(`auth=(ck,cs)`, HTTPS 표준).
- User-Agent: 봇 UA → **일반 브라우저형**(Bluehost ModSecurity 회피). Accept: application/json.
- **빈 sku= 파라미터 제거**(`_clean_params`) + `_find_by_sku('')`는 조회 안 함(전체목록 첫 상품 오매칭 방지).
- 4xx 실패 시 응답 본문 요약을 **마스킹 후** 진단 로그(자격증명 평문 0).

## STEP3 — 스마트스토어 약관 준수 게이트 복원
- `smartstore_approved()`(env SMARTSTORE_APPROVED) — 커머스솔루션 승인 전 **업로드 시도 자체 차단**
  (`_prevalidate_market`가 smartstore_pending_review로 즉시 반환, 토큰 발급·실패 노출 0).
- UI: 등록 모달에서 스마트스토어 타일 **비활성 + '심사중 — 커머스솔루션 승인 후 오픈' 배지**. 승인 시 플래그로 오픈.

## STEP4 — 11번가 진단 노출
- `등록 실패: 등록 실패` 동어반복 제거 → **응답 코드+메시지 원문(마스킹)** `[997] 등록된 API 정보 없음` 형태.
  코드·메시지 둘 다 없으면 원문 앞부분(마스킹)으로 진단(뭉뚱그림 금지).

## STEP5 — 테무 감사 (인터셉터 주입 설정 확인 — 실작동 판정은 오너 실기기)
manifest 감사: `content_scripts[0] = kgp-net.js · world=MAIN · run_at=document_start` — **인터셉터는 정상 주입 설정**.
`content_scripts[2] = kgp-main.js(world=MAIN)`도 확인. 진단 표(v54/55/56)는 확장 콘솔에 출력되게 배선됨.
→ **설정은 정상**. 실배포 판정(진단 표 출력·sources=tier1)은 오너 실기기(테무 판매중 상품 + 확장 1.5.61 재로딩) 필요.
이 환경 프록시는 라이브 테무 차단이라 제가 콘솔 표를 직접 못 뽑습니다(정직). 진단 표가 안 나오면 확장 미주입 확정 →
그때 수리가 전부라는 브리프 지침대로, 오너 콘솔 캡처를 주시면 다음 수리를 특정하겠습니다.

## STEP6 — v60 반영 확인 (감사 완료)
main(d378d45)에 v60 STEP1(#456)·STEP2-4(#457)·STEP5(#458) **전부 머지 확인**. 아마존 제목 오염 차단·상세 구조화·옵션
포함됨 → 판정은 오너 아마존 재수집(제목="andobil…" 재발 0).

## 오너 검증 (배포 후 실기기)
① WC 등록 성공 ② diagnostics Shopify 녹색(STEP2 후속) ③ 스마트스토어 심사중 배지 ④ 테무 진단표+5탭 ⑤ 아마존 3필드.
