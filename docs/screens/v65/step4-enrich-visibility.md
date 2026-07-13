# v65 STEP4 — 보강 큐 가시성

## 감사 — v64 STEP1 큐 UI 배포 확인
- 팝업 큐 UI(`enrichPanel`/`enrichCount` n/총 · `enrichPause` 일시정지 · `enrichStop` 중단)가 **실제 배포됨**(v64 STEP1, #473 머지, manifest 1.5.68+ → 현재 1.5.71).
- 배경 큐가 진행률 방송(`_kgpBroadcastEnrich` → `enrichProgress`) + 일시정지/중단 메시지 처리. 벌크바 상태에도 실시간 표시.
- → 미배포 아님. 이 STEP은 큐 UI 감사 통과 + **이력 행 상태 추가**.

## 수리 — 수집 이력 행 보강 상태
- 뷰(`views.py`)가 `enrich_status`를 **실제 저장값 기준**으로 파생:
  - `ex.enriched == true` → **done**(보강 완료).
  - 아니고 `source ∈ {bulk, bulk_collect}` + `collect_status != 성공` → **pending**(보강 대기/중).
  - 단건(상세 페이지 클릭 수집)은 이미 풀데이터 → `''`(배지 없음, 보강 불필요).
- 행 템플릿(`collect_history_rows.html`) 상태 셀에:
  - **대기**: 스피너 + `보강 중…`(한지/muted 토큰, "상세를 백그라운드에서 보강 중" 툴팁).
  - **완료**: `보강 완료`(청록 토큰, bi-stars).
- 실시간 진행(n/총)·실패 재시도는 **팝업 큐 UI**(수집 사이트 탭)에서, 이력 행은 **영속 상태**(대기→완료)를 정직하게 표기(가짜 진행 0).

## 판정
- 가드 `tests/test_v65_enrich_visibility.py` (5): 큐 UI 배포 감사 + `enrich_status` 파생 계약 + 행 배지(대기 스피너·완료·토큰 색) + 렌더 200.
- 실기기(벌크 5건 → 팝업 큐 진행 + 이력 상태 전환 녹화)는 오너 환경 — 프록시 라이브 차단.

## 금지 준수
- 실제 저장값(enriched) 기준 — 가짜 진행/성공 0. 토큰 외 색 0(청록/한지). Tier1 의존 0.

적용 스킬: **gogabridj-design**(상태 배지 토큰·스피너·이모지0 bi-*). impeccable/humanizer CLI 미설치→의도 수동.
