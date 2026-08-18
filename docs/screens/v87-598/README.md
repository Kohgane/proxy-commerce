# #598 라쿠텐 상세 갤러리 1장 → n장 — 실픽스처 증빙

프리즈 해제: `fixtures/realpages/diag/kgp-snapshot-item-rakuten*.html`(TSUMUGI 상세, 285KB).

## 근원 (실크롬 실측)
라쿠텐은 **같은 상품 이미지 경로를 여러 CDN 미러 호스트**로 서빙한다:
- og:image = `shop.r10s.jp/receno/cabinet/bowl/tsumugi-tama/img/…`
- 갤러리 = `image.rakuten.co.jp/…/img/…`(24) · `tshop.r10s.jp/…/img/…`(11) — **path 동일**, host만 다름.

v80 STEP3 폴더 스코프의 `_rakutenFolder`가 폴더 키에 **호스트를 포함**해, og(한 호스트)의 폴더와 갤러리(다른 미러)의 폴더가 갈렸다 → (c) CDN 스윕이 폴더셋 밖으로 보고 갤러리를 **전량 제외** → **1장**.
추가로 컨테이너 셀렉터(`ImageMain`/`ImageThumb` 등)가 이 페이지의 **React 해시 클래스**(`image--38eoi`)를 못 잡아 (b) 스코프가 0 → (c) 스윕 의존.

## 수리 (v80 폴더 스코프 유지, 키 계산만 교정)
1. `_rakutenFolder`를 **경로(path)만**으로 판정(호스트 제거) → CDN 미러 호스트 변이에 무관하게 동일 상품을 묶음. 타상품 경로(`/receno/cabinet/lace/…`)는 여전히 상이 → **교차 오염 0 유지**.
2. `hiRes`가 라쿠텐 `?_ex=`만 지우고 `&s=0&r=1` 고아를 남겨 같은 이미지가 다른 URL로 중복되던 것 → 라쿠텐/r10s 이미지는 확장자 뒤 쿼리 통째 제거(원본 해상도 + 미러/쿼리 변이 dedupe).

## 실측 전후 (Playwright, 실 상세 픽스처)
| | 갤러리 이미지 | 폴더(상품) | 호스트무관 중복 | 비-라쿠텐 CDN |
|---|---|---|---|---|
| BEFORE | **1** | 1 | 0 | 0 |
| AFTER | **11**(캐러셀 전량) | **1**(현 상품만) | **0** | **0** |

- 11 = 캐러셀 `0000050172001~010`+`020`(상세 본문 `sale_desc`의 `…2000`·`blog*` 이미지는 갤러리 아님 → 제외, 교차 오염 0).
- 회귀 0: `_rakutenFolder`·`hiRes` 사용 기존 계약(v80 folder·v79 gallery·v76 rakuten adapter·v82 gate·v76 detail) 33 그린.
계약 `test_v87_598_rakuten_detail_gallery`(3, Playwright 실브라우저).
