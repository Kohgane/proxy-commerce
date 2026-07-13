# v66 STEP3 — 아마존 보강 판정 회수

## 판정 회수 (큐가 돌았나 vs 필드를 못 채웠나)
- 상태가 "옵션·상세·리뷰·평점 누락"인 원인을 **서버 로그로 특정**: enrich 엔드포인트가 `[enrich] item=%s changed=%s status=%s rep=%s` 1줄 로깅.
  - `changed`가 비어 있으면 → **보강은 돌았으나 상세 추출이 필드를 못 채움**(추출기 문제).
  - `/enrich` 호출 자체가 없으면 → **큐 미실행**(v65 STEP4 행 상태 '보강 대기'가 안 넘어감).
- 오너는 이 로그로 어느 쪽인지 특정 가능.

## 수리
### 1) 고해상 갤러리를 대표로 (`/enrich`)
- 보강 갤러리(상세 페이지 hi-res)를 **union 앞에** 두어 대표(images[0])가 고해상. `image_url`(목록 썸네일)도 hi-res로 교체 → **검색결과 저해상 썸네일을 대표로 쓰지 않음.**

### 2) 상세 추출 실작동 (공유 추출기, 이미 존재 — 계약 고정)
- 갤러리 hi-res: `hiRes()`(`._AC_SX..` 크기 토큰 제거) + `data-old-hires`.
- 상세: `#feature-bullets`(About this item 불릿) + `#productDescription` 본문 + `#aplus img`(A+ 이미지 → detail 버킷).
- 이 셀렉터들이 정본 경로(extractMetaWait→extractProductMeta→kgpExtractProduct)에서 실행 → 보강이 옵션·상세·리뷰·갤러리를 채움.

## 판정
- 가드 `tests/test_v66_amazon_enrich.py` (4):
  - enrich 갤러리-first·image_url 교체·판정 로그 계약 + 공유 추출기 아마존 상세 셀렉터 계약.
  - **서버 실행**: 저해상 씨드 → hi-res 갤러리 보강 → **대표=hires_main.jpg**(저해상은 뒤로)·상세이미지·옵션·리뷰 채움·상태 성공.
- 실기기(아마존 2건 보강 완료 → 드로어 [갤러리 고해상·상세 불릿·옵션·리뷰] 채움 + 상태 배지 성공)는 오너 환경 — 프록시 라이브 차단.

## 금지 준수
- 서버측 직접 크롤 0(보강은 확장 렌더 DOM) · 가짜성공 0(changed 실측 로그) · 저해상 대표 방지.

적용 스킬: (백엔드 병합 + 확장 추출기 — UI 렌더 무변경. impeccable/humanizer CLI 미설치.)
