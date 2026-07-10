# v51 STEP1 — 테무 어댑터 3계층 (클라이언트)

## 전제 (오너 확정, 재조사 안 함)
테무 KR 상품 페이지: `window.rawData`/초기상태 전역 없음(전역 30개 전수 — PRERENDER_CONFIG·InitialI18nStore
뿐), og:title/image 없음. 상품 데이터는 **부팅 후 API 응답(JSON)으로만** 존재. → 서버·인라인 스크립트
파싱 구조적 불가. `state_json.py`의 rawData 탐색은 **테무 URL에서 폐기**.

## Tier 1 — 상품 API 응답 캡처 (확장 전용, 최우선)
- **`kgp-net.js`** (manifest `world:MAIN`, `run_at:document_start`): 페이지가 API를 부르기 **전에** 주입 →
  `window.fetch`·`XMLHttpRequest` 래핑. 상품형 JSON 응답(sku/goods/gallery/salePrice 힌트)만 `window.__kgpCaptured`에
  최근 8개 보관. **우리가 테무 API를 부르는 게 아니라 페이지가 이미 받은 응답을 읽을 뿐 — 추가 요청 0, 차단 리스크 0.**
- 수집 시 `kgp-extractor`가 `__kgpCaptured`를 최우선 상태로 walker에 투입 → sku 가격(센트/원 확인·sanity KRW<100
  거부)·갤러리 전체(순서 보존)·옵션 sku 스펙·상세 이미지·평점·리뷰 매핑. (MAIN world라 `__kgpCaptured` 접근 가능.)

## Tier 2 — 렌더 DOM 갤러리 스코프 (확장 폴백 + 북마클릿 기본)
- 이미지: **페이지 전체 `document.images` 폴백 금지.** 상품 갤러리 컨테이너(gallery/carousel/swiper/preview/
  main-image…)로 스코프 한정, `_bestImgSrc`(currentSrc·data-src·srcset 최고해상). **naturalWidth 필터 제거**
  (lazy 갤러리 0을 버리고 로딩된 추천 이미지를 통과시키던 오수집 원인) → URL·컨테이너 위치로 판별. 추천/연관/함께
  구매(`_galleryExcluded`) 명시 제외(단, 캐러셀/스와이퍼는 '갤러리 그 자체'라 허용).
- 가격: 갤러리 인근 가격 노드(통화기호+숫자), 취소선(정가) 제외 판매가. 타이틀: h1 우선 → og → document.title.

## Tier 3 — 기존 og/meta 제네릭 (타 사이트용 유지)

## 필드별 출처 + 정직 표기
- 추출기가 `field_sources:{price:"tier1",images:"tier2",title:"tier3",...}` → 서버 저장 → 드로어 수집 로그에
  `Tier1(API/상태)·Tier2(DOM)·Tier3(og)` 표기. 못 얻은 필드 → "부분 수집" 배지.
- 북마클릿은 테무에서 Tier1 불가(페이지월드 API 캡처는 확장 document_start 전용) → 테무 접속 시 **"테무는 확장 권장"
  안내 토스트 1회**.

## 로컬 실증 (node)
- kgp-net: 상품 응답(goods/skuList) 캡처 1건, 비상품(PRERENDER_CONFIG/InitialI18nStore) 배제.
- Tier1 추출: `__kgpCaptured` Temu형 JSON → **price=20605 KRW**·갤러리 3·상세 1·옵션 블랙/화이트·rating 4.7·
  review_count 328·partial=false·field_sources 전부 tier1.
- state_json: 테무 URL → `{}`(폐기), 비-테무 URL → 정상 파싱.

## 판정 (오너 실기기)
테무 실URL(판매중) 확장 수집 → 드로어 5탭: 실판매가 일치·갤러리=해당 상품만·옵션 sku·상세·리뷰 + sources 로그 캡처.
북마클릿 동일 URL → 부분 수집 배지 + "확장 권장" 안내 캡처. (확장 1.5.52 재로딩.)

## 가드
test_v51_temu_adapter(6): manifest Tier1 주입 / net 캡처(상품만) / Tier1 추출(node) / Tier2 스코프 소스계약 /
state_json 테무 폐기 / 소스 라벨·북마클릿 토스트·다운로드 kgp-net 포함. 다운로드 ZIP·manifest 1.5.51→1.5.52.
