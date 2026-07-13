# v65 STEP1 — 렌더드-DOM 추출기 (사이트 불문 강건판)

## 전략 전환 (오너 승인)
- **테무 Tier1 인터셉트를 1차 경로에서 제외**(v54~63 무실적). 코드는 opportunistic 잔존 가능하나 판정·의존 금지.
- **모든 수집의 정본 경로 = 렌더된 DOM 추출.** 단건(상세 클릭)은 그 자리 렌더 DOM, 목록(호버·벌크)은 보강 큐가 백그라운드 탭으로 상세를 열어 **렌더 완료 후** DOM 추출. 테무·아마존·제네릭 동일 파이프라인.

## 수리
### 1) 렌더 완료 대기 게이트 (`kgp-extractor.js`)
- `_renderReady()` — 가격 패턴 텍스트(`_domPrice`) + 메인 이미지(≥200×200 로드) 감지. 둘 다 present면 준비 완료.
- `kgpWaitRendered(cb, maxMs=8000)` — 250ms 폴링, ready면 `partial:false`, **최대 8초 초과 시 `partial:true`**(있는 것만, 무한대기 금지). `global.kgpWaitRendered`로 노출(확장·북마클릿 공유).

### 2) 정본 경로 배선
- content_script 새 메시지 **`extractMetaWait`** — `kgpWaitRendered` → `kgpRevealDetailFolds`(접힘 상세 펼침) → `extractProductMeta`, 부분이면 `partial` 표기.
- 보강 큐(background)가 고정 `sleep(1200)` 대신 **`extractMetaWait`** 사용 → 렌더 완료 후 추출.

### 3) 제목 'Temu' 재발 차단 (`_isBareSiteName`)
- 순수 사이트/브랜드명(`Temu`·`Amazon.co.jp`·`Yahoo!ショッピング` 등)은 상품명이 아니므로 **제목 후보에서 배제**. 어댑터→tier1→tier2(h1)→og→document.title 순으로 **첫 유효(사이트명 아님)** 값 채택 → 제목이 "Temu"로 저장되는 것 원천 차단.

## 판정
- 가드 `tests/test_v65_rendered_dom.py` (4):
  - 소스계약(`kgpWaitRendered`·`_renderReady`·`_isBareSiteName`·`extractMetaWait`·보강 큐 사용).
  - **node**: 사이트명 가드(Temu/Amazon.co.jp/Yahoo!ショッピング=배제, 상품명=유효) + 렌더 준비(가격+이미지→ready·즉시 완료).
  - manifest 1.5.69. `test_v60_title_scope` 우선순위 계약 갱신.
- 실기기(테무 2건·아마존 2건 보강 완료 후 드로어 전 탭 — 제목 실상품명·가격 실가·갤러리 자기 상품) 캡처는 오너 환경 — 프록시 라이브 차단. **제목 "Temu"·가격 공란 재발 시 불합격**.

## 금지 준수
- Tier1 의존 판정 없음(정본=렌더 DOM) · 서버측 직접 크롤 0(보강은 확장 탭 컨텍스트) · 가짜 성공 0(미달=partial 표기).

적용 스킬: (확장 추출기 — 우리 토큰 무관 로직. impeccable/humanizer CLI 미설치.)
