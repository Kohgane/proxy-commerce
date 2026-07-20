# v77 STEP3 — 보강 큐 연동 확인 (v65 STEP4 판정 회수)

## 배경(오너)
벌크바의 "상세 보강 시작 (0/7)"이 실작동하는지 — 7건 완주 후 이력 상태 전환 확인.

## 판정(회수) — 이미 구축(v64~v70)된 보강 큐를 7건 완주 계약으로 못박음
확장 코드 변경 없음(검증 테스트·캡처만) → **manifest bump 없음**(정직).

### 큐 상태 머신(background.js) — 7/7 완주
- `enrichStart`(targets) → `handleEnrichStart`이 큐 초기화·total 설정·응답 `{ok,total}`(0/7) → `_kgpEnrichLoop`.
- 루프: 1건씩 `_kgpEnrichOne`(소형 창/탭 렌더 → 상세 추출 → 서버 `/enrich` POST) → `done++` → `enrichProgress` 브로드캐스트.
- 큐 소진 → `running=false` → 종료 브로드캐스트. content_script가 `상세 보강 done/total`, `done>=total`이면 `· 완료`.
- **node 실측**(`_kgpEnrichOne` 스텁): 7 targets → `done=7·total=7·ok=7·running=false` + 완료 브로드캐스트(`lastDone=7·lastRunning=false`).

### 서버 `/enrich` — 7건 보강 + 상태 전환
- fill-only 병합(옵션·상세설명·리뷰·평점·리뷰수·상세이미지·갤러리 — 빈 필드만) + `extra["enriched"]=True` +
  상태 배지 재계산(부분→성공). 대표 썸네일 고해상 교체.
- **서버 실측**(7 부분 수집분): 7건 각각 `/enrich` → 전건 `ok:true` · `enriched=True` · 옵션·상세·리뷰 채워짐 ·
  `collect_status.filled` 증가(부분→성공 방향).

## 판정
- 가드 `tests/test_v77_enrich_queue.py`(4): manifest 불변(1.5.104) + source-contract(진행률 표기 `0/N`·`done/total`·`완료`·
  enrichProgress·큐 머신·`/enrich` POST) + **node 큐 7/7 완주** + **서버 7건 enriched·상태 전환**.
- **판정 캡처**: `step3-enrich-queue.png`(0/7 → 3/7 → 7/7 완료 진행바 + 이력 7건 enriched·등록 준비 상태 전환).

## 계약(브리프)
> STEP 3 — 벌크바 '상세 보강 시작 (0/7)' 실작동 · 7건 완주 후 이력 상태 전환(v65 STEP4 판정 회수).

## 금지 준수
- 확장 코드 변경 0(검증만) → bump 없음(정직) · 가짜성공 0(node 스텁 성공 경로·서버 실 병합) · 추출기 불변.
- ※ 라이브 아마존 7타일 전체 수집 → 소형 창 7회 보강 → 이력 상태 전환 실기기 녹화는 오너 몫(확장 1.5.104).

적용 스킬: (확장 큐·서버 보강 검증 — UI/CSS 렌더 변경 없음. impeccable/humanizer CLI 미설치.)
