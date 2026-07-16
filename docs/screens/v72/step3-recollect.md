# v72(b) STEP3 — 목록 벌크바 [다시 수집] 재추출

## 목적
구버전 확장으로 수집한 항목('-' 가격·Chat history 잔재·구스코프 이미지)을 **최신 추출기로 세탁**하는 통로.
목록 벌크바에서 선택 상품을 다시 수집하면 **기존 레코드를 갱신**(신규 행 생성 0)한다.

## 구현 (표시·저장 계층만 — 추출기 동결)
- **content_script**: 벌크바에 `[다시 수집]`(data-act=recollect) 버튼 추가(금 아웃라인). 클릭 → 선택분을
  `kgpCollect(sel, { force: true })`. `kgpRunBulk(items, opts)`가 `opts.force`면 각 item에 `force=true` 부착.
  선택 없으면 안내('먼저 배지를 눌러 선택'), 조용한 무동작 금지.
- **서버(기존 경로 재사용)**: `/api/v1/collect/extension`은 이미 `force`(=overwrite)를 처리 — 중복(product_key)
  감지 시 **신규 행을 만들지 않고** 기존 항목의 가격·이미지·제목·옵션·상세를 갱신하고 `{ok, updated:true, item_id}`
  회신. background `handleCollectBulk`가 `updated`(중복 아님)를 성공으로 집계 + `item_id`를 **enrichTargets**에
  담아 보강 큐(enrichStart) 재투입 → 2단 상세 보강도 다시 돈다.
- 추출 로직(kgp-extractor.js)·서버 파싱 **무변경**(하네스 합격 동결). force는 저장 덮어쓰기 배선만.

## 판정
- 가드 `tests/test_v72b_recollect.py` (6):
  - source-contract: 벌크바 버튼·핸들러·`kgpRunBulk(items, opts)` force 부착.
  - server-contract: force 시 `_hist_update`(append 아님)·`updated:True`.
  - **behavioral**: '-'(빈) 가격 항목 → force 재수집 → **같은 item_id·가격 12000 채워짐·행 수 불변**(신규 0)·`recollected` 마킹.
  - force 응답 item_id(보강 큐 재투입 조건).
  - **node**: `kgpRunBulk({force:true})`가 items 각각에 `force:true` 부착(일반 배치엔 미부착=회귀 방지).
- manifest 1.5.88→**1.5.89**(재로딩 유도) + 버전핀 34곳 갱신.
- 회귀: 전체 그린.
- **실기기(오너 몫)**: 아마존 '-' 2건 선택 → [다시 수집] → 가격 채움 캡처(확장 1.5.89 재로딩 후).

## 금지 준수
추출기 로직 변경 0(동결) · 신규 행 생성 0(force=덮어쓰기) · 가짜 성공 0(서버 update 성공만 집계).

적용 스킬: (확장 벌크바 버튼·서버 저장 배선 — 확장 인라인 스타일 관행 유지. impeccable/humanizer CLI 미설치.)
