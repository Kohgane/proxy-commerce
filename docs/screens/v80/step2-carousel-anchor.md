# v80 STEP2 — 알리 캐러셀 안정 앵커

## 증상(오너 실기기 1.5.114)
알리 카드 호버 시 이미지 자동 슬라이드 → img 기준 앵커가 매 전환마다 재배치 → 버튼 증발·클릭 불가.

## 근본 원인
버튼 앵커 = `imgEl.parentElement`(= **swiper-slide**). 캐러셀이 슬라이드를 교체(자동 슬라이드)하면 우리 버튼도
슬라이드와 함께 제거됨 → 재부착(플리커)·클릭 불가. `closest('[class*=swiper]')`도 **가장 가까운** 매치(=슬라이드,
`swiper-slide`도 'swiper' 포함)를 잡아 여전히 불안정.

## 수리
1. **최외곽 캐러셀 조상에 앵커**: `imgEl.parentElement`부터 `c.el`까지 올라가며 `carousel|swiper|slider|slick|
   gallery|magnifier` 매치를 **계속 갱신** → 최종 = **최외곽 캐러셀 컨테이너(안정, 슬라이드 상위, 교체 안 됨)**.
   캐러셀 없으면 `imgEl.parentElement`(정밀 유지 — 일반 사이트 회귀 0).
2. **z-index 상향**: 버튼 `2147483639`→**`2147483644`**(알리 호버 오버레이/미리보기 팝업 `2147483643` 위 → 가려짐 방지).
3. **재부착 트리거 스코프**(기존 v74 STEP3 유지): 재부착은 **우리 오버레이 제거 시만** 발동 — 캐러셀 이미지 교체
   변이는 트리거 아님. 안정 앵커 덕분에 슬라이드 교체가 우리 버튼을 제거하지 않아 재부착 자체가 안 일어남.

## 계약(브리프)
> STEP 2 — 안정 컨테이너 앵커·캐러셀 img 교체는 재부착 제외·z-index 오버레이 위. 판정: 호버 중 이미지 넘어가도 버튼 고정·클릭.

## 판정
- 가드 `tests/test_v80_carousel_anchor.py`(3): source-contract(최외곽 캐러셀 앵커·z-index·재부착 스코프) +
  **Playwright**(알리식 swiper 카드): 버튼이 **swiper 컨테이너**에 앵커(슬라이드 아님)·**슬라이드 innerHTML 교체
  후에도 버튼 생존**·여전히 컨테이너 자식·중복 0·`z ≥ 2147483644`(오버레이 위).
- 기존 앵커/알리 하네스(`test_v65_button_anchor`·`test_v74_ali_button_survival`·`test_v72b_ali_button_isolation`)
  갱신·그린(일반 카드는 imgEl.parentElement 정밀 앵커 유지 — 회귀 0).
- **판정 캡처**: `step2-carousel-anchor.png`(BEFORE 슬라이드 앵커 증발 → AFTER 컨테이너 앵커 생존).
- 전체 **11469 passed / 22 skipped**. manifest 1.5.115→**1.5.116**.
- 오너 최종 판정: 확장 재로딩 후 알리 목록에서 호버 중 이미지 넘어가도 버튼 고정·클릭 녹화.

## 금지 준수
- 추출기 무변경(오버레이 앵커/위치만) · 일반 사이트 정밀 앵커 회귀 0 · 단일 버튼(멱등) 유지.

적용 스킬: (확장 오버레이 앵커/z-index — 인라인 스타일 관행. impeccable/humanizer CLI 미설치.)
