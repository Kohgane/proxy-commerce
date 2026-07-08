/* kgp-extractor.js — 공유 상품 추출기(확장·북마클릿 동일 코드).
 *
 * 소스 우선순위(오너): ①초기 상태 JSON(JSON-LD + 페이지 전역 상태) 파싱 → ②DOM 셀렉터 폴백 →
 *   ③둘 다 실패 시 partial=true('부분 수집' 정직 표기, 가짜 성공 금지).
 * 가격: 표시용(통화기호 포함) 문자열 우선 파싱, 정수/센트 애매하면 sanity 게이트로 넘김.
 *   sanity: 통화 미상 또는 비상식 하한(KRW<100 등) → price_status='needs_check' + 경고(warnings).
 *   재고 수·리뷰 수 숫자는 가격 후보에서 원천 배제.
 * 이미지: 갤러리 URL 배열(원본 해상도 우선) — 순서 보존 + 중복 제거, 1번=썸네일.
 * 옵션: 스펙(색상·사이즈…) + sku별 가격(있으면). 상세: 상세 이미지 배열 + 속성 텍스트 표(데이터만).
 * 리뷰: 평점·리뷰 수 + 초기 JSON에 이미 실린 텍스트 리뷰 상위 N건(추가 API 호출 없음). 없으면 없음.
 *
 * 전역 하나만 노출: window.kgpExtractProduct(). 확장은 manifest로, 북마클릿은 서버가 인라인해 공유.
 */
(function (global) {
  "use strict";
  if (global.kgpExtractProduct) return;   // 중복 로드 방지(확장+북마클릿 동시 상황)

  var REVIEW_MAX = 10;

  // ── 공통 유틸 ──────────────────────────────────────────────
  function _sym(s) {
    var M = { "$": "USD", "＄": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "￥": "JPY", "₩": "KRW", "￦": "KRW" };
    return M[s] || "";
  }
  var CODE = { USD: "USD", EUR: "EUR", GBP: "GBP", JPY: "JPY", KRW: "KRW", CNY: "CNY",
               "원": "KRW", "엔": "JPY", "위안": "CNY", "元": "CNY" };
  var PRICE_RE = /([\$＄€£¥￥₩￦])\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(USD|EUR|GBP|JPY|KRW|CNY|원|엔|위안|元)/i;
  function parsePriceStr(raw) {
    var m = String(raw == null ? "" : raw).match(PRICE_RE);
    if (!m) return null;
    var sym = m[1] || "", num = (m[2] || m[3] || "").replace(/,/g, ""), code = m[4] || "";
    if (!num) return null;
    var cur = code ? (CODE[code] || CODE[code.toUpperCase()] || code.toUpperCase()) : (_sym(sym) || "");
    return { price: num, currency: cur };
  }
  function uniqPush(arr, seen, v) {
    v = (v == null ? "" : String(v)).trim();
    if (v && !seen[v]) { seen[v] = 1; arr.push(v); }
  }

  // 원본 해상도화(썸네일 크기 토큰 제거 — 아마존 _AC_SX../Temu ...?imageView 등)
  function hiRes(u) {
    if (!u) return u;
    try {
      // 아마존 크기 토큰(image._AC_SX466_.jpg → image.jpg)은 통째로 제거(더블닷 방지).
      u = u.replace(/\._(AC_)?S[XYLS]\d+_/gi, "").replace(/\._(SX|SY|SS|SL|UX|UY|CR)\d+(,\d+)*_/gi, "");
      u = u.replace(/(\?|&)(imageView2?|thumb|w|width|h|height|size|quality)=[^&]*/gi, "");
      u = u.replace(/[?&]$/, "").replace(/\.{2,}(jpg|jpeg|png|webp|gif)/i, ".$1");
    } catch (e) {}
    return u;
  }

  // 비-상품 이미지(로고/아이콘/배너/픽셀…) 판정
  var NONPROD_IMG = /(logo|sprite|icon|favicon|avatar|placeholder|loading|blank|pixel|spinner|banner|badge|button|arrow|chevron|caret|rating|star_|flags?|emoji|watermark|qr[-_]?code|coupon|nav_|1x1|transparent\.|spacer)/i;
  function isProductImg(s) { return s && s.indexOf("data:") !== 0 && !NONPROD_IMG.test(s); }

  // 가격이 아닌 숫자(재고·쿠폰·수량·평점·판매수) 문맥 배제
  var NONPRICE = /(재고|남음|남았|개\s*남|수량|qty|quantity|stock|left|in\s*cart|장바구니|쿠폰|coupon|적립|포인트|point|리뷰|review|평점|rating|판매|sold|명이|배송비|shipping\s*fee|무료배송|free\s*shipping|할인율|% ?off|퍼센트)/i;

  // ── ① 초기 상태 JSON ──────────────────────────────────────
  // 스키마를 하드코딩하지 않는다(사이트별 구조 상이·추측 금지). JSON-LD Product + 페이지 전역 상태
  // 객체를 **키 이름 휴리스틱**으로 깊이 탐색해 가격/이미지/스펙/리뷰를 모은다.
  function _jsonLd() {
    var out = [];
    try {
      var s = document.querySelectorAll('script[type="application/ld+json"]');
      for (var i = 0; i < s.length; i++) {
        try { var j = JSON.parse(s[i].innerText || s[i].textContent || ""); if (j) out.push(j); } catch (e) {}
      }
    } catch (e) {}
    return out;
  }
  var STATE_KEYS = ["__NEXT_DATA__", "__NUXT__", "__INITIAL_STATE__", "__INIT_DATA__", "__STORE__",
                    "rawData", "__PRELOADED_STATE__", "__APOLLO_STATE__", "__data", "pageData", "window._d"];

  // 문자열에서 index 위치의 { 또는 [ 부터 문자열-인지 균형 매칭으로 JSON 조각을 잘라낸다.
  function _sliceBalanced(s, from) {
    var open = s.charAt(from), close = open === "{" ? "}" : "]";
    if (open !== "{" && open !== "[") return null;
    var depth = 0, inStr = false, esc = false, q = "";
    for (var i = from; i < s.length; i++) {
      var c = s.charAt(i);
      if (inStr) {
        if (esc) esc = false; else if (c === "\\") esc = true; else if (c === q) inStr = false;
      } else {
        if (c === '"' || c === "'") { inStr = true; q = c; }
        else if (c === "{" || c === "[") depth++;
        else if (c === "}" || c === "]") { depth--; if (depth === 0) return s.slice(from, i + 1); }
      }
    }
    return null;
  }

  // ★핵심(v46 STEP3): 확장 content script는 **격리 월드**라 페이지의 live window.rawData를 못 읽는다.
  //   → 인라인 <script> **텍스트**에서 'window.rawData = {...}' 류 초기 상태 할당을 파싱(DOM 텍스트라
  //   격리월드에서도 접근 가능). 북마클릿(페이지월드)도 동일 코드로 동작.
  function _scriptStates() {
    var out = [];
    try {
      var ss = document.querySelectorAll("script:not([src])");
      for (var i = 0; i < ss.length && i < 60; i++) {
        var t = ss[i].textContent || "";
        if (t.length < 20 || t.length > 6000000) continue;
        for (var k = 0; k < STATE_KEYS.length; k++) {
          var key = STATE_KEYS[k];
          var pos = 0, guard = 0;
          while (guard++ < 5) {
            var idx = t.indexOf(key, pos);
            if (idx < 0) break;
            pos = idx + key.length;
            var eq = t.indexOf("=", idx);
            if (eq < 0 || eq - idx > key.length + 8) continue;   // '=' 가 키 바로 뒤여야(할당)
            var seg = t.slice(eq, eq + 300);
            var mb = /[{\[]/.exec(seg);
            if (!mb) continue;
            var raw = _sliceBalanced(t, eq + mb.index);
            if (raw) { try { var o = JSON.parse(raw); if (o && typeof o === "object") out.push(o); } catch (e) {} }
          }
        }
      }
    } catch (e) {}
    return out;
  }

  function _globalStates() {
    // 흔한 초기 상태 전역/스크립트(next/nuxt/redux/사이트 커스텀). 값이 객체면 후보로.
    var cands = [];
    // (1) live 전역 — 북마클릿(페이지월드)에서만 유효. 확장(격리월드)에선 대개 undefined.
    for (var i = 0; i < STATE_KEYS.length; i++) {
      try { var v = global[STATE_KEYS[i]]; if (v && typeof v === "object") cands.push(v); } catch (e) {}
    }
    // (2) <script id=__NEXT_DATA__ type=application/json> 등 인라인 JSON(DOM 텍스트).
    try {
      var ss = document.querySelectorAll('script[type="application/json"]');
      for (var k = 0; k < ss.length && k < 12; k++) {
        try { var o = JSON.parse(ss[k].textContent || ""); if (o && typeof o === "object") cands.push(o); } catch (e) {}
      }
    } catch (e) {}
    // (3) ★인라인 <script> 텍스트의 상태 할당(window.rawData=... 등) — 격리월드 대응 핵심.
    var st = _scriptStates();
    for (var j = 0; j < st.length; j++) cands.push(st[j]);
    return cands;
  }
  function _walk(root, visit, maxNodes) {
    var stack = [root], n = 0;
    var seen = typeof WeakSet !== "undefined" ? new WeakSet() : null;
    while (stack.length && n < (maxNodes || 20000)) {
      var cur = stack.pop(); n++;
      if (!cur || typeof cur !== "object") continue;
      if (seen) { if (seen.has(cur)) continue; seen.add(cur); }
      visit(cur);
      for (var key in cur) {
        try { var val = cur[key]; if (val && typeof val === "object") stack.push(val); } catch (e) {}
      }
    }
  }
  function _fromJson() {
    var res = { title: "", price: "", currency: "", images: [], detailImages: [], specs: [],
                options: [], skus: [], reviews: [], rating: "", reviewCount: "", description: "", ok: false };
    var imgSeen = {}, detSeen = {};
    // JSON-LD Product 우선(표준·신뢰)
    var lds = _jsonLd();
    for (var i = 0; i < lds.length; i++) {
      var arr = Array.isArray(lds[i]) ? lds[i] : (lds[i]["@graph"] || [lds[i]]);
      for (var a = 0; a < arr.length; a++) {
        var p = arr[a]; if (!p || typeof p !== "object") continue;
        var t = p["@type"]; if (t && String(t).toLowerCase().indexOf("product") < 0) continue;
        if (p.name && !res.title) res.title = String(p.name).slice(0, 300);
        if (p.description && !res.description) res.description = String(p.description);
        var imgs = p.image || (p.offers && p.offers.image);
        if (imgs) [].concat(imgs).forEach(function (u) { if (isProductImg(u)) uniqPush(res.images, imgSeen, hiRes(u)); });
        var off = p.offers ? [].concat(p.offers) : [];
        for (var o = 0; o < off.length; o++) {
          var of = off[o]; if (!of) continue;
          if (of.price && !res.price) {
            res.price = String(of.price).replace(/,/g, "");
            res.currency = String(of.priceCurrency || "").toUpperCase();
          }
        }
        var agg = p.aggregateRating;
        if (agg) { res.rating = String(agg.ratingValue || ""); res.reviewCount = String(agg.reviewCount || agg.ratingCount || ""); }
        var rv = p.review ? [].concat(p.review) : [];
        for (var r = 0; r < rv.length && res.reviews.length < REVIEW_MAX; r++) {
          var one = rv[r]; if (!one) continue;
          res.reviews.push({
            author: (one.author && (one.author.name || one.author)) || "",
            rating: (one.reviewRating && one.reviewRating.ratingValue) || "",
            text: String(one.reviewBody || one.description || "").slice(0, 500)
          });
        }
        res.ok = res.ok || !!(res.price || res.images.length);
      }
    }
    // 전역/스크립트 상태 딥워크(스키마 무관·키 이름 휴리스틱) — JSON-LD로 못 채운 것 보강.
    var IMG_KEY = /(image|img|pic|photo|thumb|gallery|carousel|album)/i;
    var DET_KEY = /(detail|desc|content)/i;
    var SKU_KEY = /(sku|variant|goodsspec|specsku|skulist|productlist)/i;
    var SPEC_KEY = /(spec|attr|prop|option|variation)/i;
    var PRICE_KEY = /(price|amount|sale|deal|salePrice|normalPrice)/i;
    var PRICE_BAD = /(count|qty|num|origin|list|regular|market|before|min|max|unit|discount|off|save)/i;
    var RATE_KEY = /(avgrating|averagerating|ratingvalue|goodsscore|starscore|score|rating)$/i;
    var CNT_KEY = /(reviewcount|reviewnum|commentcount|reviewtotal|totalreview|ratingcount)/i;

    function pushImgs(arr, dest, seen) {
      for (var i = 0; i < arr.length && dest.length < 40; i++) {
        var u = arr[i];
        if (typeof u === "object" && u) u = u.url || u.src || u.imageUrl || u.thumbUrl || u.image || "";
        if (typeof u === "string" && /^https?:\/\//.test(u) && isProductImg(u)) uniqPush(dest, seen, hiRes(u));
      }
    }
    // 숫자 가격의 센트/소단위 환산: 통화가 소단위(USD/EUR/GBP…) + 정수 + 큰 값이면 ÷100.
    function priceFromNum(n, cur) {
      var v = Number(n);
      if (!(v > 0)) return "";
      var CENTS = { USD: 1, EUR: 1, GBP: 1, CNY: 1, AUD: 1, CAD: 1 };  // 소단위 있는 통화
      if (cur && CENTS[cur] && v === Math.floor(v) && v >= 1000) return String(v / 100);
      return String(v);
    }
    function skuPrice(o) {
      for (var k in o) {
        try {
          if (PRICE_KEY.test(k) && !PRICE_BAD.test(k)) {
            var pv = o[k];
            if (typeof pv === "string") { var pp = parsePriceStr(pv); if (pp) return pp; }
            else if (typeof pv === "number") {
              var cur = String(o.currency || o.currencyCode || o.priceCurrency || res.currency || "").toUpperCase();
              var val = priceFromNum(pv, cur); if (val) return { price: val, currency: cur };
            }
          }
        } catch (e) {}
      }
      return null;
    }
    var _skuPriceSet = false;
    var states = _globalStates();   // live 전역 + 인라인 <script> 텍스트 상태(격리월드 대응)
    for (var s = 0; s < states.length; s++) {
      _walk(states[s], function (node) {
        for (var key in node) {
          try {
            var kv = String(key).toLowerCase(), v = node[key];
            // (1) 이미지 배열(배열 키가 이미지류)
            if (Array.isArray(v) && IMG_KEY.test(kv)) {
              pushImgs(v, DET_KEY.test(kv) ? res.detailImages : res.images, DET_KEY.test(kv) ? detSeen : imgSeen);
            }
            // (2) 단일 이미지 url
            else if (typeof v === "string" && /^https?:\/\//.test(v) && IMG_KEY.test(kv) && isProductImg(v)) {
              uniqPush(DET_KEY.test(kv) ? res.detailImages : res.images, DET_KEY.test(kv) ? detSeen : imgSeen, hiRes(v));
            }
            // (3) SKU 배열 → 옵션·sku별 가격, 메인 가격(첫 유효 sku)
            else if (Array.isArray(v) && SKU_KEY.test(kv) && v.length && typeof v[0] === "object") {
              for (var i = 0; i < v.length && i < 200; i++) {
                var so = v[i]; if (!so || typeof so !== "object") continue;
                var sp = skuPrice(so);
                var specVals = [];
                for (var sk in so) { if (SPEC_KEY.test(sk)) { var sv = so[sk]; if (Array.isArray(sv)) specVals = specVals.concat(sv.map(String)); else if (typeof sv === "string") specVals.push(sv); } }
                res.skus.push({ spec: specVals, price: sp ? sp.price : "", currency: sp ? sp.currency : "" });
                if (sp && !_skuPriceSet) { res.price = sp.price; res.currency = sp.currency; _skuPriceSet = true; }
              }
            }
            // (4) 평점·리뷰수
            else if (RATE_KEY.test(kv) && !res.rating && (typeof v === "string" || typeof v === "number")) {
              var rn = parseFloat(v); if (rn > 0 && rn <= 5) res.rating = String(v);
            }
            else if (CNT_KEY.test(kv) && !res.reviewCount && (typeof v === "string" || typeof v === "number")) {
              res.reviewCount = String(v);
            }
            // (5) 제목·설명
            else if (!res.title && /(^title$|goodsname|productname|itemname|^name$)/i.test(kv) && typeof v === "string" && v.length > 2) {
              res.title = v.slice(0, 300);
            }
            else if (!res.description && /(description|detailtext|goodsdesc|productdesc)/i.test(kv) && typeof v === "string" && v.length > 20) {
              res.description = v.slice(0, 4000);
            }
          } catch (e) {}
        }
        // (6) 가격: sku에서 못 얻었으면 표시 문자열(통화기호 포함) 우선.
        if (!res.price) {
          for (var k2 in node) {
            try {
              if (PRICE_KEY.test(k2) && !PRICE_BAD.test(k2)) {
                var pv2 = node[k2];
                if (typeof pv2 === "string") { var pp2 = parsePriceStr(pv2); if (pp2 && pp2.currency) { res.price = pp2.price; res.currency = pp2.currency; break; } }
              }
            } catch (e) {}
          }
        }
        // (7) 리뷰 텍스트(초기 JSON에 실린 것만) — 길이 완화.
        if (res.reviews.length < REVIEW_MAX) {
          try {
            var body = node.reviewBody || node.comment || node.content || node.text;
            var hasRating = node.rating != null || node.star != null || node.score != null;
            if (typeof body === "string" && body.length >= 2 && (hasRating || node.reviewId || node.commentId || node.reviewer)) {
              res.reviews.push({ author: node.author || node.userName || node.nickname || node.reviewer || "",
                                 rating: node.rating || node.star || node.score || "",
                                 text: String(body).slice(0, 500) });
            }
          } catch (e) {}
        }
      }, 30000);
    }
    // 옵션: sku 스펙 값을 축 이름 없이 합쳐 후보로(중복 제거). 이름은 알 수 없으면 '옵션'.
    if (res.skus.length) {
      var ovals = [], oseen = {};
      res.skus.forEach(function (sk) { (sk.spec || []).forEach(function (val) { if (val && !oseen[val]) { oseen[val] = 1; ovals.push(val); } }); });
      if (ovals.length >= 2) res.options.push({ name: "옵션", values: ovals.slice(0, 100) });
    }
    res.ok = !!(res.price || res.images.length || res.title);
    return res;
  }

  // ── ② DOM 폴백 ────────────────────────────────────────────
  function _meta(prop) {
    var el = document.querySelector('meta[property="' + prop + '"],meta[name="' + prop + '"]');
    return el ? (el.getAttribute("content") || "") : "";
  }
  function _nonProdRegion(el) {
    var re = /(recommend|related|similar|also[-_ ]?bought|sponsored|advert|ranking|carousel|cross[-_ ]?sell|up[-_ ]?sell|footer|navbar|breadcrumb|review|comment|qna|feedback|seller|merchant|store[-_ ]?info|vendor|brand[-_ ]?header)/i;
    var cur = el && el.parentElement, d = 0;
    while (cur && d < 8) {
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && re.test(tok)) return true;
      cur = cur.parentElement; d++;
    }
    return false;
  }
  function _priceOriginal(el) {
    var re = /(original|was[-_ ]?price|strike|line[-_]?through|regular|list[-_]?price|old[-_]?price|compare[-_]?at|정가|원가|할인전)/i;
    var cur = el, d = 0;
    while (cur && d < 4) {
      var tag = (cur.tagName || "").toLowerCase();
      if (tag === "del" || tag === "s" || tag === "strike") return true;
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && re.test(tok)) return true;
      try { if ((getComputedStyle(cur).textDecorationLine || "").indexOf("line-through") >= 0) return true; } catch (e) {}
      cur = cur.parentElement; d++;
    }
    return false;
  }
  function _nonPriceCtx(el) {
    var cur = el, d = 0;
    while (cur && d < 4) {
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && NONPRICE.test(tok)) return true;
      cur = cur.parentElement; d++;
    }
    return NONPRICE.test((el.textContent || "").slice(0, 40));
  }
  function _nodePath(el) {
    var parts = [], cur = el, n = 0;
    while (cur && n < 4) {
      var t = (cur.tagName || "").toLowerCase();
      var c = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || ""));
      parts.unshift(t + (c ? "." + String(c).trim().split(/\s+/).slice(0, 2).join(".") : ""));
      cur = cur.parentElement; n++;
    }
    return parts.join(" > ");
  }
  function _domPrice() {
    var nodes = [];
    try {
      nodes = Array.prototype.slice.call(document.querySelectorAll('[class*="price" i],[class*="Price"],[itemprop="price"],[data-price],[class*="amount" i],[aria-label*="price" i]'));
    } catch (e) { nodes = []; }
    var cands = [];
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (_nonProdRegion(el) || _priceOriginal(el) || _nonPriceCtx(el)) continue;
      var raw = el.getAttribute("content") || el.getAttribute("data-price") || (el.textContent || "").trim();
      var p = parsePriceStr(raw); if (!p) continue;
      var fs = 0; try { fs = parseFloat(getComputedStyle(el).fontSize) || 0; } catch (e) {}
      cands.push({ price: p.price, currency: p.currency, val: parseFloat(p.price) || 0, fs: fs, path: _nodePath(el) });
    }
    cands.sort(function (a, b) { return (b.fs - a.fs) || (b.val - a.val); });
    try {
      console.log("[고가수집기] (DOM)가격 후보(" + cands.length + "):",
        cands.slice(0, 6).map(function (c) { return c.price + " " + c.currency + " @" + c.fs + "px [" + c.path + "]"; }));
    } catch (e) {}
    return cands[0] || null;
  }
  function _domImages() {
    var out = [], seen = {}, det = [], detSeen = {};
    var og = _meta("og:image") || _meta("og:image:url"); if (isProductImg(og)) uniqPush(out, seen, hiRes(og));
    var gSel = '[class*="gallery" i] img,[class*="product-image" i] img,[class*="main-image" i] img,#imgTagWrapperId img,[class*="swiper" i] img,[class*="carousel" i] img';
    var dSel = '#productDescription img,#feature-bullets img,[class*="detail" i] img,[class*="description" i] img,#aplus img';
    function grab(sel, arr, sset, bucket) {
      try {
        var els = document.querySelectorAll(sel);
        for (var i = 0; i < els.length; i++) {
          var im = els[i];
          if (_nonProdRegion(im)) continue;
          var src = im.currentSrc || im.getAttribute("data-old-hires") || im.getAttribute("data-src") || im.getAttribute("data-original") || im.src || "";
          if (im.srcset) { var last = im.srcset.split(",").pop(); if (last) src = last.trim().split(/\s+/)[0] || src; }
          if ((im.naturalWidth || 250) < 200 && !bucket) continue;   // 갤러리는 큰 것만
          if (isProductImg(src)) uniqPush(arr, sset, hiRes(src));
        }
      } catch (e) {}
    }
    grab(gSel, out, seen, false);
    grab(dSel, det, detSeen, true);
    // 갤러리 못 찾으면 페이지의 큰 상품 이미지로 폴백
    if (out.length <= 1) {
      try {
        var all = document.images || [];
        for (var i = 0; i < all.length; i++) {
          var im = all[i]; if (_nonProdRegion(im)) continue;
          if ((im.naturalWidth || 0) >= 300 && (im.naturalHeight || 0) >= 300 && isProductImg(im.currentSrc || im.src)) uniqPush(out, seen, hiRes(im.currentSrc || im.src));
        }
      } catch (e) {}
    }
    return { images: out, detailImages: det };
  }
  var OPT_LABEL = /(색상|색깔|컬러|사이즈|크기|규격|수량|종류|옵션|타입|스타일|모델|용량|color|colour|size|variant|option|type|style|qty|quantity|model|capacity)/i;
  function _domOptions() {
    var out = [], seen = {};
    try {
      var sels = document.querySelectorAll("select");
      for (var i = 0; i < sels.length; i++) {
        var sel = sels[i]; if (_nonProdRegion(sel)) continue;
        var vals = Array.prototype.slice.call(sel.options || []).map(function (o) { return (o.textContent || "").trim(); })
          .filter(function (t) { return t && !/^(선택|선택하세요|choose|select|please)/i.test(t); });
        var uniq = []; var s2 = {}; vals.forEach(function (v) { if (!s2[v]) { s2[v] = 1; uniq.push(v); } });
        if (uniq.length >= 2) {
          var lbl = sel.getAttribute("aria-label") || (sel.labels && sel.labels[0] && sel.labels[0].textContent) || "";
          var m = String(lbl).match(OPT_LABEL); out.push({ name: m ? m[0] : "옵션", values: uniq.slice(0, 50) });
        }
      }
    } catch (e) {}
    return out;
  }
  function _domSpecs() {
    // 속성 표(스펙): table tr / dl / [class*=spec|attribute|param] li
    var specs = [], seen = {};
    try {
      var rows = document.querySelectorAll('table tr,[class*="spec" i] li,[class*="attribute" i] li,[class*="param" i] li,dl');
      for (var i = 0; i < rows.length && specs.length < 60; i++) {
        var row = rows[i]; if (_nonProdRegion(row)) continue;
        var cells = row.querySelectorAll("th,td,dt,dd");
        if (cells.length >= 2) {
          var k = (cells[0].textContent || "").trim().slice(0, 60), v = (cells[1].textContent || "").trim().slice(0, 200);
          if (k && v && !seen[k]) { seen[k] = 1; specs.push({ k: k, v: v }); }
        } else {
          var txt = (row.textContent || "").trim();
          var mm = txt.match(/^([^:：]{1,40})[:：]\s*(.+)$/);
          if (mm && !seen[mm[1]]) { seen[mm[1]] = 1; specs.push({ k: mm[1].trim(), v: mm[2].trim().slice(0, 200) }); }
        }
      }
    } catch (e) {}
    return specs;
  }
  function _domDescription() {
    var sel = ['#feature-bullets', '#productDescription', '[class*="description" i]', '[class*="detail" i]'];
    for (var i = 0; i < sel.length; i++) {
      try { var el = document.querySelector(sel[i]); if (el) { var t = (el.innerText || "").trim(); if (t.length > 20) return t.slice(0, 4000); } } catch (e) {}
    }
    return _meta("og:description") || _meta("description") || "";
  }

  // ── 가격 sanity 게이트 ─────────────────────────────────────
  function _priceSanity(price, currency) {
    var warnings = [], status = "";
    var v = parseFloat(String(price || "").replace(/,/g, ""));
    if (!(v > 0)) return { price: "", currency: currency || "", status: "needs_check", warnings: ["가격을 확실히 읽지 못했어요"] };
    if (!currency) { status = "needs_check"; warnings.push("통화를 확인하지 못했어요"); }
    // 비상식 하한: 통화별 최소 상식가. 재고/리뷰 숫자 오인(예: 9 KRW) 저장 거부.
    var MIN = { KRW: 100, JPY: 10, CNY: 1, USD: 0.5, EUR: 0.5, GBP: 0.5 };
    if (currency && MIN[currency] != null && v < MIN[currency]) {
      status = "needs_check"; warnings.push("가격이 비상식적으로 낮아요(" + currency + " " + v + ") — 재고/쿠폰 숫자 오인 가능");
    }
    return { price: String(price), currency: currency || "", status: status, warnings: warnings };
  }

  // ── 오케스트레이션 ────────────────────────────────────────
  function kgpExtractProduct() {
    var warnings = [], source = "json";
    var j = {};
    try { j = _fromJson(); } catch (e) { j = { ok: false, images: [], detailImages: [], options: [], skus: [], specs: [], reviews: [] }; }

    var title = j.title || _meta("og:title") || (document.title || "");
    var price = j.price || "", currency = j.currency || "";
    var images = (j.images || []).slice(), detailImages = (j.detailImages || []).slice();
    var options = (j.options || []).slice(), skus = (j.skus || []).slice(), specs = (j.specs || []).slice();
    var reviews = (j.reviews || []).slice(), rating = j.rating || "", reviewCount = j.reviewCount || "";
    var description = j.description || "";

    var needDom = !price || images.length === 0;
    if (needDom) {
      source = j.ok ? "json+dom" : "dom";
      try {
        if (!price) { var dp = _domPrice(); if (dp) { price = dp.price; currency = dp.currency; } }
        if (images.length === 0) { var di = _domImages(); images = di.images; if (!detailImages.length) detailImages = di.detailImages; }
        if (!options.length) options = _domOptions();
        if (!specs.length) specs = _domSpecs();
        if (!description) description = _domDescription();
      } catch (e) { warnings.push("DOM 폴백 중 일부 실패"); }
    }

    // ③ 둘 다 실패 → 부분 수집(가짜 성공 금지)
    var partial = !price && images.length === 0;
    if (partial) { source = "partial"; warnings.push("초기 JSON·DOM 모두에서 핵심 정보를 못 읽어 부분 수집입니다"); }

    // 가격 sanity
    var sane = _priceSanity(price, currency);
    var price_status = sane.status;
    price = sane.status === "needs_check" && !sane.price ? "" : sane.price;
    currency = sane.currency;
    warnings = warnings.concat(sane.warnings);

    // 이미지 원본해상도 + 순서 보존 + 중복 제거(이미 uniqPush로 됨). 1번=썸네일.
    var seen = {}, gallery = [];
    images.forEach(function (u) { uniqPush(gallery, seen, u); });

    try {
      console.log("[고가수집기] 추출 소스=" + source, "| 가격=" + price + " " + currency + " (" + (price_status || "ok") + ")",
        "| 갤러리=" + gallery.length + " 상세이미지=" + detailImages.length + " 옵션=" + options.length + " 스펙=" + specs.length + " 리뷰=" + reviews.length,
        warnings.length ? "| 경고:" + warnings.join(" / ") : "");
    } catch (e) {}

    var out = {
      url: location.href,
      title: String(title || "").slice(0, 300),
      price: price, currency: currency, price_status: price_status,
      image: gallery[0] || "",
      images: gallery, gallery_images: gallery, detail_images: detailImages,
      thumbnail: gallery[0] || "",
      options: options, skus: skus,
      description: description, detail_specs: specs,
      reviews: reviews, rating: rating, review_count: reviewCount,
      source: source, partial: partial, warnings: warnings,
      jsonld: _jsonLd(),
      collected_at: new Date().toISOString()
    };
    return out;
  }

  global.kgpExtractProduct = kgpExtractProduct;
  if (typeof module !== "undefined" && module.exports) module.exports = { kgpExtractProduct: kgpExtractProduct };
})(typeof window !== "undefined" ? window : this);
