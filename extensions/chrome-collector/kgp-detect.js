/**
 * kgp-detect.js — v73 STEP2: UI 감지 순수 모듈 (document 입력 → {pageType, tiles, anchors} 출력).
 *
 * DOM 주입·chrome·부수효과와 분리해 jsdom/Playwright 하네스에서 계약을 검증 가능하게 한다. content_script는
 * 이 모듈의 규칙에 위임(단일 소스). "추출은 되는데 버튼이 사라지는/타일을 놓치는" 부류의 회귀를 기계로 잡는다.
 *
 * 계약(아마존 검색): pageType='list' · tiles=24 · main(유기)=16 · ad(스폰서)=8 · asinMissing=0 ·
 *   각 tile anchor='img.s-image' · countLabel='메인 16 · 광고 8'. 상세: pageType='single'.
 */
(function (global) {
  "use strict";

  // ── URL 규칙(content_script와 단일 소스, drift-guard로 동기 못박음) ──
  const DETAIL_URL_RE = /(\/dp\/|\/gp\/product\/|\/vp\/products\/|item\.htm|aliexpress\.[^/]+\/item\/|[?&]goods_id=|[/-]g-\d{3,}|\/goods\/\d|\/product\/\d|\/products\/[\w-]+|\/itm\/)/i;
  const LIST_URL_RE = /(\/s\?|\/s\/|\/search|\/sch\b|[?&](q|keyword|query|search|k)=|\/category|\/categories|\/c\/|\/list\b|\/best\b|\/ranking|\/plp|\/browse|\/deals)/i;

  // 아마존 스폰서(광고) 판별 셀렉터 — 제외 아님, 태깅만(광고 상품도 수집 가능).
  const SPONSORED_SEL = '.s-sponsored-label-text, .puis-sponsored-label-text, [data-component-type="sp-sponsored-result"], [aria-label*="Sponsored"], [data-component-type="s-sponsored-label-info-icon"]';
  const TILE_SEL = '[data-component-type="s-search-result"], div[data-asin]:not([data-asin=""])';
  const ASIN_RE = /^[A-Z0-9]{10}$/;
  const RECO_RE = /(recommend|related|carousel|slider|viewed|recently|also-?viewed|also-?bought|similar|frequently|rcmd|sponsored-products|p13n|cross-?sell|up-?sell|you-?may)/i;
  const STRUCT_RE = /(footer|recommend|related|carousel|slider|viewed|recently|history|also-?viewed|also-?bought|similar|banner|rcmd)/;

  function _meta(n) {
    let cls = "";
    try { cls = (typeof n.className === "string" ? n.className : (n.getAttribute && n.getAttribute("class")) || ""); } catch (e) { cls = ""; }
    return ((n.id || "") + " " + cls + " " + ((n.getAttribute && (n.getAttribute("aria-label") || n.getAttribute("data-component-type"))) || "")).toLowerCase();
  }
  // 구조적 비상품(footer/header/nav)만 제외 — 추천/캐러셀은 제외 안 함(태깅만).
  function _inStructuralBad(el) {
    let n = el;
    for (let i = 0; n && i < 9; i++, n = n.parentElement) {
      const tag = (n.tagName || "").toLowerCase();
      if (tag === "footer" || tag === "header" || tag === "nav") return true;
    }
    return false;
  }
  function _isReco(el) {
    let n = el;
    for (let i = 0; n && i < 9; i++, n = n.parentElement) { if (RECO_RE.test(_meta(n))) return true; }
    return false;
  }

  // 페이지 타입: URL 하드매치 최우선, 애매하면 DOM 신호 점수화. (override/캐시는 content_script 래퍼 몫)
  function pageType(doc, href, opts) {
    opts = opts || {};
    const isDetail = DETAIL_URL_RE.test(href || "");
    const isList = LIST_URL_RE.test(href || "");
    if (isDetail && !isList) return "single";
    if (isList && !isDetail) return "list";
    let single = isDetail ? 3 : 0, list = isList ? 3 : 0;
    try { const h1 = doc.querySelectorAll("h1"); if (h1.length === 1 && (h1[0].textContent || "").trim().length > 6) single += 1; } catch (e) {}
    try { if (doc.querySelector('[class*="gallery" i],[class*="swiper" i],[class*="carousel" i],[aria-roledescription="carousel"]')) single += 1; } catch (e) {}
    try {
      doc.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
        const t = s.textContent || "";
        if (/"@type"\s*:\s*"Product"/i.test(t)) single += 2;
        if (/"@type"\s*:\s*"ItemList"/i.test(t)) list += 2;
      });
    } catch (e) {}
    const n = opts.cardCount || 0;
    if (n >= 6) list += 3; else if (n >= 3) list += 1;
    if (single === 0 && list === 0) return "unknown";
    if (list > single) return "list";
    if (single > list) return "single";
    return "unknown";
  }

  // 아마존 타일 감지 — 유효 ASIN + 스폰서 태깅 + region(main/reco) + anchor(img.s-image). 제외 사유 카운트.
  function amazonTiles(doc, origin) {
    const tiles = [], seen = {};
    const excl = { region: 0, parse: 0, dup: 0 };
    const mainSlot = (doc.querySelector && doc.querySelector('.s-main-slot, [data-component-type="s-search-results"]')) || null;
    const set = new Set();
    doc.querySelectorAll(TILE_SEL).forEach((e) => set.add(e));
    const all = Array.from(set);
    all.forEach((el) => {
      try {
        if (_inStructuralBad(el)) { excl.region++; return; }
        const asin = (el.getAttribute("data-asin") || "").trim();
        if (!ASIN_RE.test(asin)) { excl.parse++; return; }
        const parentAsin = el.parentElement && el.parentElement.closest('[data-asin]:not([data-asin=""])');
        if (parentAsin && parentAsin !== el && (parentAsin.getAttribute("data-asin") || "").trim() === asin) { excl.dup++; return; }
        const sponsored = !!el.querySelector(SPONSORED_SEL);
        const region = (mainSlot ? mainSlot.contains(el) : !_isReco(el)) ? "main" : "reco";
        const a = el.querySelector('a.a-link-normal[href*="/dp/"], h2 a, a.a-link-normal.s-no-outline, a[href*="/dp/"]');
        let href = a && a.href ? a.href.split("?")[0].split("#")[0] : "";
        if (!href || href.indexOf("http") !== 0) href = (origin || "") + "/dp/" + asin;
        if (seen[href]) { excl.dup++; return; }
        seen[href] = 1;
        const anchorImg = el.querySelector("img.s-image");
        tiles.push({ el: el, asin: asin, sponsored: sponsored, region: region, href: href,
          anchor: anchorImg ? "img.s-image" : null, hasAnchor: !!anchorImg });
      } catch (e) { /* noop */ }
    });
    return { tiles: tiles, scanned: all.length, excl: excl };
  }

  // 종합: 페이지 타입 + 타일 + 카운트 + 앵커. (아마존 외 사이트는 tiles=[] — 제네릭 감지는 content_script 몫)
  function detectUI(doc, href) {
    let origin = "";
    try { origin = new URL(href).origin; } catch (e) { origin = ""; }
    const at = amazonTiles(doc, origin);
    const tiles = at.tiles;
    const ad = tiles.filter((t) => t.sponsored).length;
    const reco = tiles.filter((t) => t.region === "reco").length;
    const main = tiles.filter((t) => t.region !== "reco" && !t.sponsored).length;
    const asinMissing = at.excl.parse;   // 유효 ASIN 결손(비상품/광고 위젯 등) 카운트
    const recoTxt = reco ? " · 추천 " + reco : "";
    const adTxt = ad ? " · 광고 " + ad : "";
    return {
      pageType: pageType(doc, href, { cardCount: tiles.length }),
      tiles: tiles, tileCount: tiles.length,
      main: main, ad: ad, reco: reco, asinMissing: asinMissing,
      anchors: tiles.map((t) => t.anchor),
      countLabel: "메인 " + main + recoTxt + adTxt,   // content_script 카운트 표기와 동일 포맷
    };
  }

  // v82 STEP3: 페이지타입 게이트 — 단일 추출·"이 상품 수집하기"는 pageType==='single'에서만 허용.
  //   지난 팝업 문구 버그(톱/검색에서 단일 추출 가동)의 근치. 단일 소스(팝업·content_script·하네스 공용).
  function singleExtractAllowed(pt) { return pt === "single"; }
  // 게이트 차단 시 팝업 문구 분기(single이면 null — 게이트 통과).
  function singleGateMessage(pt) {
    if (pt === "single") return null;
    if (pt === "list") return "목록 페이지예요. 타일의 [수집] 버튼이나 벌크바를 쓰세요";
    return "상품 페이지가 아니에요. 상품/목록 페이지에서 수집할 수 있어요";
  }

  global.KGPDetect = {
    DETAIL_URL_RE: DETAIL_URL_RE, LIST_URL_RE: LIST_URL_RE,
    SPONSORED_SEL: SPONSORED_SEL, TILE_SEL: TILE_SEL, ASIN_RE: ASIN_RE,
    pageType: pageType, amazonTiles: amazonTiles, detectUI: detectUI,
    singleExtractAllowed: singleExtractAllowed, singleGateMessage: singleGateMessage,
  };
})(typeof self !== "undefined" ? self : this);
