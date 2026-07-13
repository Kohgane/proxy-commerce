# v64 STEP5 — 테무 판정 회수 (v62·63 미결)

## 감사 (코드 상태 — main 반영 확인)
v62·v63의 테무 관련 코드는 전부 배포·가드됨. 라이브 캡처만 미회수(개발 환경 프록시가 테무 차단으로 대행 불가).

| 항목 | 코드 | 가드 |
|---|---|---|
| generic-first 감지(어댑터 실패가 제네릭 미차단) | v63 STEP1 `kgpFindCards` 제네릭 선행 + `_kgpMergeCards` | `test_v63_generic_first_detect`·`test_v63_detection_contract` |
| 테무 SPA 앵커 폴백(이미지 `<a>` 미포함) | v63 STEP1 `_kgpGenericCards` 카드 컨테이너 앵커 | `test_v63_detection_contract`(node 스냅샷 테무식 카드 감지) |
| goods_id 정확 매칭(이전 상품 오채택 금지) | v62 STEP2 Tier1 캡처 goods_id 키드 맵 | `test_v62_temu_goods_match` |
| 감지 디버그 패널(왜 안 떠?) | v63 STEP1 팝업 `감지 진단` | `test_v63_generic_first_detect` |
| 손실 매트릭스 | v63 STEP2 `/seller/collect/field-loss` | `test_v63_field_loss_matrix` |

## 정직 — 라이브 미회수 (오너 검증 몫)
이 개발 환경은 프록시가 라이브 테무/아마존을 차단하므로 아래 3연속 캡처를 대신 낼 수 없다(가짜 캡처 날조 금지). **이번 PR에서 테무 캡처 미첨부 = STEP5 라이브 판정 불합격으로 정직 표기.**

오너 회수 절차(확장 **1.5.68** 재로딩 후):
1. 테무 검색결과 → 중앙 벌크바 + 호버 [수집] 표시 확인(v63 generic-first 라이브).
2. 상세 A→B→C 연속 수집 → 각 자기 이미지·가격, goods_id 매칭 배지(포착됨●/대기○).
3. `GET /seller/collect/field-loss`로 손실 매트릭스 전/후.

## 결론
- 코드 갭 0(v62·63 테무 경로 전부 머지·가드). STEP5는 **라이브 판정 회수** 성격 — 오너 환경에서만 캡처 가능.
- v64 STEP1(벌크 상세 보강)이 테무 벌크의 옵션·상세 누락도 2단 보강으로 메움(백그라운드 탭).

적용 스킬: (감사·문서 — 코드 변경 없음. impeccable/humanizer CLI 미설치.)
