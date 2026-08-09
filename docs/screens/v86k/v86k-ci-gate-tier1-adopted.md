# v86-K — CI 실스위트 게이트(오너 승인) + tier1_diag adopted 계측

## 1. CI 사각 봉인 (collect-only → 실스위트 필수 체크)
근본: 종전 CI python-guard가 `pytest --collect-only`뿐이라 실 실패를 못 잡았다(v86-H2에서 23 레드 은닉).
- **KGP_REQUIRE_BROWSER=1**(conftest 훅): 브라우저/노드/jsdom/Pillow **인프라 부재로 인한 skip을 실패로 전환**
  (조용한 skip 금지 = false-green의 구조적 원인 봉인). 의도적 로직 skip은 그대로 둔다(정직).
- **full-suite 잡(인메모리 레인)**: chromium+node+jsdom+Pillow 전부 설치, KGP_REQUIRE_BROWSER=1로 전 스위트 실행.
- **pg-suite 잡(격리 레인)**: Postgres 서비스+DATABASE_URL로 Supabase 이관/DB계량 계약만 별도 실행.
  ※전역 DATABASE_URL은 앱을 PG 모드로 바꿔 인메모리 가정 테스트 58건을 깬다(실측 확인) → 레인 분리 필수.
- 두 잡의 합집합이 전 계약 커버 → **CI 전체 조용한 skip 0(인프라)**.

### 첫 전체 실행 3수치 (로컬 실측, KGP_REQUIRE_BROWSER=1)
- **인메모리 레인**: **11881 passed · 0 failed · 2 skipped** · 6:56.
  - 잔여 skip 2 = `test_v86_shadow_visibility` yoshida(오프라인 스냅샷 카드 미감지 = **계약 대상 없음**,
    로직 skip·인프라 아님). 계약 본문 수정 금지로 보존·보고(공허한 그린 방지).
  - 인프라 skip 0(브라우저/노드/jsdom/Pillow 전부 실행).
- **PG 레인**: **31 passed · 0 skipped**(supabase stage1~3·backup·migrate·token_bulk_delete·db_metering).
- CI 러너 시간: 인메모리 ~7분 + PG ~2분(오너 승인 ~6분 트레이드오프 범위).

## 2. tier1_diag adopted 블록 (읽기 전용 계측)
오너 실기기(테무 1.5.140): top=추천 캐러셀 goods_detail_like(goods_id 605155487520667, goods_matched=false)가
최고점인데도 **채택 안 됨** = 방어 실작동. 종전 진단은 top만 실어 '무엇이 채택됐나'를 못 봤다.
- `__kgpAdoptedCandidate`(kgp-net.js): extractor가 세팅한 전역(__kgpTier1Url/Mismatch/Score) **역판독만**
  (분기 추가 0, 선택 로직 무변경). 반환: adopted·url·score·goods_id·goods_matched·price/images/sku/reviews 불리언
  + **adopt_cause enum**(빈 문자열 금지): adopted:id_match / adopted:top_score / rejected:id_mismatch /
  rejected:no_capture / rejected:score / rejected:not_injected.
- kgp-main.js가 diag.adopted 브릿지, content_script _kgpTier1Diag가 진단에 노출.
- **top≠adopted면 그 자체가 방어(id 불일치 기각) 작동 증거**로 판독. (오너 케이스: top score>0인데 adopted=false·
  adopt_cause=rejected:id_mismatch)

## 판정
- 가드: `test_v86_k_tier1_adopted`(3, node 하네스로 채택/방어기각/미주입 실증) + `test_v86_k_require_browser`
  (2, 게이트 무는지 서브프로세스 실증: 플래그 ON 인프라 skip→비통과, 로직 skip 유지).
- 인위회귀: CI에서 계약 1건 인위 red → full-suite 잡 실패(머지 차단) → 원복 green(별도 커밋 이력으로 증명).
- 버전: 계측 변경(kgp-net/main/content_script) → manifest 1.5.140→**1.5.141** 범프.
- v86-H·I 회귀 없음(억제 계약·테무 payload 계약 그린 유지).

금지 준수: 추출기·tier1 선택 로직·kgp-net.js 스코프 무변경(adopted는 역판독 관찰). 서버 파일 불가침.
