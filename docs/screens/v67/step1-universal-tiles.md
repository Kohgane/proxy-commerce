# v67 STEP1 — 전 타일 버튼 (퍼센티 패리티)

## 정정 (오너)
- v66의 메인 그리드 한정은 **카운트 표시에만** 적용. 수집 버튼은 **상품 타일 전부에**(메인 그리드 + 추천 캐러셀 + frequently-viewed + 배너). 광고 타일도 AD 배지와 함께 버튼 제공.

## 수리
### 1) 전 타일 감지 (버튼 부착)
- `_kgpAmazonCards`: 스코프를 `.s-main-slot`에서 **document 전역**으로 되돌림 — 추천/캐러셀 타일도 감지·버튼 부착. 구조적 비상품(footer/nav)만 제외(`_kgpInBadRegion(el, {allowAds:true, structuralOnly:true})`).
- `_kgpGenericCards`: 추천/캐러셀 제외(`_kgpInBadRegion(card)`) → `structuralOnly`로 완화(footer/nav만 제외) — 캐러셀 상품 타일도 버튼.
- 각 카드에 **`region` 태그**(main/reco): 아마존은 `.s-main-slot.contains`, 제네릭은 `_kgpIsRecoRegion`(recommend/carousel/viewed/similar/frequently…).

### 2) 카운트 = [메인 n / 추천 m / 광고 k]
- 벌크바: `메인 N · 추천 M · 광고 K · S개 선택`. 팝업: `감지: 상품 N개 (추천 m · 광고 k 포함)`.
- **전체선택/전체수집 기본 = 메인 비스폰서만**. `추천 포함`(kgp_incl_reco)·`광고 포함`(kgp_incl_ads) 토글로 확장. 개별 타일 수집은 버튼으로 항상 가능.

### 3) 제외 사유 분해 (실데이터 회수 메커니즘)
- v65 STEP2 `_kgpExcl{parse,url,dup,region}` + reco 태그로 팝업 진단 패널이 사유별 실측 노출. 추천/광고는 '제외' 아님(태그) — 진짜 제외(파싱/URL/중복/구조)만 표기. 오너가 상위 원인을 실데이터로 캡처 가능.

## 판정
- 가드 `tests/test_v67_universal_tiles.py` (3) + 갱신된 `test_v66_main_grid_scope`:
  - 소스계약(`_kgpIsRecoRegion`·`structuralOnly`·`_kgpInclReco`·incl-reco 토글·region selectable·region 카운트).
  - **node**: 전체선택 기본 메인만(m1,m2) → 추천 포함(+r1) → 광고 포함(+a1) / 아마존 메인3+추천2 **전부 감지**(count 5)·region 태그 정확.
  - manifest 1.5.74.
- 실기기(아마존 검색 캐러셀 포함 전 타일 버튼 부착 스크롤 녹화 + 사유 분해 표)는 오너 환경 — 프록시 라이브 차단.

## 금지 준수
- 추천영역 버튼 누락 회귀 **제거**(전 타일 부착) · 분모 뻥튀기 방지(카운트는 메인/추천/광고 분리) · 서버측 직접 크롤 0 · 가짜성공 0.

적용 스킬: (확장 감지·툴바 — 우리 토큰 유지. impeccable/humanizer CLI 미설치.)
