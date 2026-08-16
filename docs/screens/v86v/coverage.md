# v86-V — 커버리지 표 결함 일소 (라쿠텐 상세 오판정 + 아마존 갤러리 + echo + 알리)

## 오너 실기기 확정 (재조사 금지)
1.5.144 상세 3소스 채점: 가격 3소스 DOM 교차검증 그린(테무 12730 KRW / 알리 3820 KRW / 아마존 24.69 USD buybox).

## 작업 결과 (서열 순)

### 1. [크리티컬] 라쿠텐 상세 single 판정 ✅
- **증상**: `item.rakuten.co.jp/{샵}/{코드}/` 상세를 pageType=list로 오판정(스캔 105·상품 68·제네릭 91 —
  추천/사이드바 타일이 cardCount를 부풀림) → 단품 수집 거부 + **v86-H 억제**(pageType==='list'에서만 발동)로
  필드 전무. 소스 열 전체 차단.
- **수리(상세 판정 분기만)**: `content_script.js` `kgpDetectPageType`에서 수동 오버라이드 다음, KGPDetect
  위임 **전에** `_kgpIsRakutenItemHref(location.href)`(item.rakuten + 경로 세그먼트 2개↑)면 `single` 강제.
  → (a) FAB/팝업 단품 게이트 활성 (b) v86-H 억제 **미발동**(list 아님). 목록 `search.rakuten.co.jp`은 이
  판정 false라 **불영향(벌크 34타일 계약 유지)**.
- **인위회귀**: raw `KGPDetect.pageType(rakutenHref, {cardCount:60})` = **`list`(red, 게이트 무력화)** /
  게이트 `_kgpIsRakutenItemHref` = **single(green)** / 목록 href = false(불영향). node 실행 실증.
- **실브라우저(L2 계보)**: 확장 로드 + `item.rakuten.co.jp` 상세(추천 타일 40개) → `kgpDetectState.pageType
  === "single"` + `allowed === true`. **skip 0**.

### 2. 아마존 상세 갤러리 대표 1장 → n장 ✅
- **증상**: DOM 썸네일 마크업 16곳·이미지 ID 75종인데 갤러리 수집 1장.
- **근원**: `kgp-extractor.js` `needDom = !price || images.length===0`. 아마존 tier1(og:image·JSON-LD)이
  대표 1장 주면 `images.length===1`이라 `_domImages`(내부 `_amazonGallery`)가 **안 돌아** 1장 고정.
- **수리(신규 발명 0)**: 라쿠텐과 **동일 패턴**으로 아마존 host + `images.length<=1`이면 `_amazonGallery`(v70:
  #altImages 썸네일 스트립) 독립 수집·병합 + `hiRes`/`_amazonDynMax`(v82) 승격. 상세 A+(detail_images)는
  **범위 밖 백로그**.
- **실추출(playwright, 실 크로미움)**: og:image 1 + #altImages 5썸네일 → 수집 이미지 **≥5장**(1→n 실증).

### 3. echo mode 라벨 정합 — 어느 쪽이 참인가 (1줄) ✅
> **payload가 참**이다. 아마존 상세는 상태 JSON(tier1) 미캡처라도 buybox+DOM 어댑터가 가격·옵션·리뷰를
> 채운 **tier2 full 추출**인데, 클라(`kgpAcquireMeta`)가 tier1 미착지만 보고 `mode='simple'`로 과잉 강등해
> echo가 'simple인데 options·reviews 동봉'으로 모순이었다(서버 `_resolve_collect_mode`는 클라 simple을
> 그대로 신뢰 → '간이' 뱃지까지).
- **수리(클라만 — 서버 불가침)**: tier1 미착지라도 **가격+(옵션|리뷰|평점|SKU|상세≥20자)면 full 유지**,
  실제로 빈약할 때만 `simple`. `tier1_pending`으로 tier1 상태만 정직 표기. 'core'(북마클릿) 불변.

### 4. 알리 리뷰 본문 — 정직 표시 (사유 보고) ✅
> 알리 리뷰 **본문은 상품 tier1(캡처된 상태 JSON)에 없다** — 별도 피드백 XHR(feedback.aliexpress.com)로
> 지연 로드된다. tier1/kgp-net 스코프는 불가침이고 **새 요청 발명 금지**라 본문은 못 가져온다. 대신 rating
> 5.0·review_count는 상품 요약(tier1)에서 수신되므로 **드로어·목록에 평점·리뷰수를 정직 표시**하고 본문은
> 비운다(날조 0). = "평점만 수신" 정직 처리. (개별 본문 렌더 화면 없음 → 과대표기 없음.)

### 5. [U 흡수분]
- **(b) 알리 리스트 echo 미기록 봉인 ✅**: 수집 4경로(fab/hover/bulk/popup) **전부** `_kgpRecordEcho` 통과
  (v86-L 계보). 알리 리스트가 호버든 벌크든 echo 기록 — 계약으로 양경로 못박음.
- **(a) 라쿠텐 리스트 타일 가격 간이 포착 — 백로그(정직)**: 이 변경은 **프리즈된 목록 타일 스캐너**(벌크바
  34타일) 내부 `pr.price`를 건드린다. 브리프의 "라쿠텐 목록 경로 무수정"과 정면으로 겹쳐, rakuten 검색-리스트
  스냅샷으로 34타일 계약 불변을 검증하기 전엔 손대지 않는다(불검증 변경 회피). 오너가 프리즈를 풀면 별도 진행.

## 완료 보고 조건 (4항 + 해시)
1. **계약 그린(skip 0, KGP_REQUIRE_BROWSER=1)**: `tests/test_v86_v_coverage.py`(8) — 라쿠텐 single 실브라우저
   + 아마존 갤러리 실추출 + 소스계약. ✅
2. **인위회귀**: 호스트 게이트 무력화(raw KGPDetect) → 라쿠텐 상세 `list` red → 게이트 → `single` green. ✅
3. **버전 범프**: manifest 1.5.144 → **1.5.145** + 푸시.
4. **회귀 0**: 테무 5/5·알리 single·아마존 single + 리스트 3소스 suppressed 유지 — 탐지/타일/갤러리/echo 회귀 86 그린 + 전 스위트.

## 금지 구조 준수
- tier1 선택 로직·kgp-net.js 스코프 **무수정**. 서버 파일 **불가침**(echo mode도 클라만 수리).
- 라쿠텐 목록 경로(벌크바 34타일) **무수정** — 상세 판정 분기만(item.rakuten 룰).
- 상세이미지 펼침 자동화 **범위 밖(백로그)**.

## 최종 판정 = 오너 실기기
확장 1.5.145 재로딩 후: 라쿠텐 상세 [수집] 활성(필드 채워짐) / 아마존 상세 갤러리 n장 / echo mode≠simple(옵션·리뷰 동봉 시).
