# v62 STEP2 — 테무 Tier1 상품 매칭 (간헐 종결)

## 근원
인터셉터가 캡처를 **점수순**으로만 보관 → 추출이 `cap[0]`(최고점)을 채택. 다른 상품의 응답이 최고점이면
**이전/다른 상품 응답 오채택** → "같은 세션에서 성공↔실패 반복"(간헐).

## 수리
- `kgp-net.js` stash: 응답에 **goods_id 키 + ts** 부여 — `_goodsIdFromUrl`(-g-{n}·goods_id=·/goods/) +
  `_goodsIdFromObj`(응답 walk: goodsId/goods_id). `window.__kgpMatchCapture(goodsId)` = 내 goods_id 최신 응답
  (TTL 10분), 없으면 **null**. `window.__kgpPageGoodsId()` = 현재 URL goods_id.
- `kgp-extractor.js` `_globalStates`: goods_id 페이지(테무)면 **내 goods_id 매칭 캡처만 채택**. 미포착이면
  다른 상품 캡처 채택 금지(`__kgpTier1Mismatch=true`) → Tier2(DOM) 폴백.
- `kgp-main.js` diag: `pageGoodsId·matched·mismatch` 동봉. `content_script`: 미포착 시 토스트 원인
  "이 상품의 API 응답 미포착(goods_id N) — 페이지 새로고침 후 재시도" + tier1_diag에 page_goods_id·goods_matched 저장.

## 실증 (node)
캡처 3개(내 goods_id 최신·남의 상품 고점9·내 goods_id 오래됨) → `__kgpMatchCapture`가 **내 goods_id 최신만**
채택({mine:1}), 남의 고점·오래된 것 배제. 매칭 없으면 null(오채택 0). URL 패턴(-g-·goods_id=) 추출 실증.

## 판정 (배포 후 실기기 — 오너)
테무 A→B→C 연속 이동 수집 → 3건 각각 자기 이미지·가격 정합, 배지 상태(포착●/대기○) 녹화.
manifest 1.5.61→1.5.62. 가드 test_v62_temu_goods_match(3, node 실증).
