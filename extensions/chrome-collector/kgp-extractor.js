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
    // (0) ★Tier 1(v51/v54): kgp-net.js가 캡처·채점한 상품 API 응답 — 초기상태 전역이 없고 데이터가 API
    //     응답으로만 존재하는 사이트(테무)의 핵심. v54: 점수순 정렬(최고점=자가발견 채택). 채택 응답 URL을
    //     __kgpTier1Url 에 기록(sources=tier1:{URL패턴}). MAIN world에서만 채워짐(추가 요청 0).
    try {
      var cap = global.__kgpCaptured;
      // v62 STEP2: goods_id 페이지(테무 등)면 **내 goods_id 매칭 캡처만** 채택(이전 상품 응답 오채택 금지).
      var pgid = (typeof global.__kgpPageGoodsId === "function") ? global.__kgpPageGoodsId() : "";
      if (pgid) {
        var m = (typeof global.__kgpMatchCapture === "function") ? global.__kgpMatchCapture(pgid) : null;
        if (m && m.obj) {
          cands.push(m.obj);
          try { global.__kgpTier1Url = m.url || ""; global.__kgpTier1Score = m.score || 0; global.__kgpTier1Mismatch = false; } catch (e2) {}
        } else {
          // 내 goods_id 응답 미포착 → 다른 상품 캡처 채택 금지. Tier2(DOM) 폴백 신호.
          try { global.__kgpTier1Mismatch = true; global.__kgpTier1Url = ""; global.__kgpTier1Score = 0; } catch (e2) {}
        }
      } else if (cap && cap.length) {
        // goods_id 없는 사이트(비테무) → 기존 점수순 후보(오채택 위험 낮음).
        for (var c = 0; c < cap.length; c++) {
          var e = cap[c];
          var obj = (e && e.obj !== undefined) ? e.obj : e;   // v54 구조({obj,score,url}) / 구버전 호환
          if (obj && typeof obj === "object") cands.push(obj);
        }
        try { global.__kgpTier1Url = (cap[0] && cap[0].url) || ""; global.__kgpTier1Score = (cap[0] && cap[0].score) || 0; global.__kgpTier1Mismatch = false; } catch (e2) {}
      }
    } catch (e) {}
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
    // v57 STEP3: 테무 상세이미지 키 보강(decoration/bottom/richtext/longimage 등 접힘 상세도 detail로 라우팅).
    var DET_KEY = /(detail|desc|content|decoration|bottomimage|richtext|longimage|goodsdesc)/i;
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
  // v66 STEP2: 컨테이너 합성 텍스트 가격 — 테무 등은 통화·숫자를 여러 span으로 분절(₩|1|,|899)해
  //   노드 단위 매칭이 실패한다. content·data-price·aria-label 속성 + textContent를 **공백·개행 제거로
  //   조립**해 통화 패턴 매칭. 취소선 제외(_priceOriginal)는 컨테이너 단위 유지. 통화 미감지 시 빈 통화(추정 금지).
  function _composedPrice(el) {
    var cands = [
      el.getAttribute && el.getAttribute("content"),
      el.getAttribute && el.getAttribute("data-price"),
      el.getAttribute && el.getAttribute("aria-label"),
      (el.textContent || "").replace(/\s+/g, ""),   // span 분절 조립(공백·개행 제거)
    ];
    for (var i = 0; i < cands.length; i++) {
      var p = parsePriceStr(cands[i]);
      if (p && p.price) return p;
    }
    return null;
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
      var p = _composedPrice(el); if (!p) continue;
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
  // v51 Tier2: 갤러리 스코프 전용 제외(추천/연관/함께구매만 — 캐러셀/스와이퍼는 '갤러리 그 자체'라 제외 안 함).
  function _galleryExcluded(el) {
    var re = /(recommend|related|similar|also[-_ ]?bought|you[-_ ]?may|sponsored|advert|ranking|cross[-_ ]?sell|up[-_ ]?sell|footer|comment|qna|review[-_ ]?list)/i;
    var cur = el && el.parentElement, d = 0;
    while (cur && d < 10) {
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && re.test(tok)) return true;
      cur = cur.parentElement; d++;
    }
    return false;
  }
  // 이미지 요소의 최고해상도 후보(currentSrc·data-*·srcset 최대). naturalWidth 필터 미사용(URL·컨테이너로 판별).
  //   v57 STEP4: 롤오버/줌 data-* 변형(data-zoom-image·data-large·data-image-large·data-hires 등) 우선(고해상).
  function _bestImgSrc(im) {
    var src = im.getAttribute("data-zoom-image") || im.getAttribute("data-large") || im.getAttribute("data-large-image")
      || im.getAttribute("data-image-large") || im.getAttribute("data-hires") || im.getAttribute("data-old-hires")
      || im.getAttribute("data-zoom") || im.currentSrc || im.getAttribute("data-src")
      || im.getAttribute("data-original") || im.getAttribute("data-lazy") || im.getAttribute("data-image")
      || im.getAttribute("data-srcset") || im.src || "";
    try {
      // srcset(또는 data-srcset)에서 최대 해상도 후보 — data-*로 못 얻었을 때만 덮어씀.
      var ss = im.srcset || im.getAttribute("data-srcset") || "";
      if (ss && (!src || src === im.src)) {
        var best = "", bw = -1;
        ss.split(",").forEach(function (part) {
          var seg = part.trim().split(/\s+/); var u = seg[0];
          var w = seg[1] ? parseInt(seg[1], 10) || 0 : 0;
          if (u && w >= bw) { bw = w; best = u; }
        });
        if (best) src = best;
      }
    } catch (e) {}
    return src;
  }
  // v57 STEP4: 인라인 background-image:url(...) 스타일에서 이미지 URL 추출(div/ a 기반 갤러리 대응).
  function _bgImage(el) {
    try {
      var st = (el.getAttribute && el.getAttribute("style")) || "";
      var m = st.match(/background(?:-image)?\s*:\s*url\((['"]?)([^'")]+)\1\)/i);
      if (m && m[2]) return m[2].trim();
    } catch (e) {}
    return "";
  }
  function _domImages() {
    var out = [], seen = {}, det = [], detSeen = {};
    var og = _meta("og:image") || _meta("og:image:url"); if (isProductImg(og)) uniqPush(out, seen, hiRes(og));
    // 상품 갤러리 컨테이너(메인 캐러셀/스와이퍼/프리뷰)로 스코프 한정 — 페이지 전체 document.images 금지.
    var gSel = '[class*="gallery" i] img,[class*="product-image" i] img,[class*="main-image" i] img,#imgTagWrapperId img,'
      + '[class*="swiper" i] img,[class*="carousel" i] img,[class*="preview" i] img,[class*="mainImage" i] img,'
      + '[class*="bigImg" i] img,[class*="thumb" i] img,[data-testid*="gallery" i] img,[aria-roledescription="carousel"] img';
    var dSel = '#productDescription img,#feature-bullets img,[class*="detail" i] img,[class*="description" i] img,#aplus img';
    // 갤러리: naturalWidth 필터 없이 — 추천/연관 섹션만 제외(캐러셀은 갤러리라 허용).
    try {
      var gels = document.querySelectorAll(gSel);
      for (var gi = 0; gi < gels.length; gi++) {
        var im = gels[gi];
        if (_galleryExcluded(im)) continue;
        var src = _bestImgSrc(im);
        if (isProductImg(src)) uniqPush(out, seen, hiRes(src));
      }
    } catch (e) {}
    // v57 STEP4: 제네릭 갤러리 보강 — <picture><source srcset> + 인라인 background-image(div/a 갤러리).
    try {
      var gScope = '[class*="gallery" i],[class*="product-image" i],[class*="main-image" i],[class*="swiper" i],'
        + '[class*="carousel" i],[class*="preview" i],[class*="mainImage" i],[data-testid*="gallery" i]';
      var srcs = document.querySelectorAll(gScope + ' picture source,picture source');
      for (var si = 0; si < srcs.length; si++) {
        var so = srcs[si]; if (_galleryExcluded(so)) continue;
        var ssv = so.getAttribute("srcset") || so.getAttribute("data-srcset") || "";
        var u0 = ssv ? ssv.split(",")[0].trim().split(/\s+/)[0] : (so.getAttribute("src") || "");
        if (isProductImg(u0)) uniqPush(out, seen, hiRes(u0));
      }
      var bgs = document.querySelectorAll(gScope + ' [style*="background-image" i],[style*="background-image" i]');
      for (var bi = 0; bi < bgs.length && bi < 200; bi++) {
        var be = bgs[bi]; if (_galleryExcluded(be)) continue;
        var bu = _bgImage(be);
        if (isProductImg(bu)) uniqPush(out, seen, hiRes(bu));
      }
    } catch (e) {}
    // 상세 본문 이미지(별도 버킷) — 추천/리뷰/푸터 제외.
    try {
      var dels = document.querySelectorAll(dSel);
      for (var di = 0; di < dels.length; di++) {
        var dm = dels[di];
        if (_nonProdRegion(dm) || _galleryExcluded(dm)) continue;
        var dsrc = _bestImgSrc(dm);
        if (isProductImg(dsrc)) uniqPush(det, detSeen, hiRes(dsrc));
      }
    } catch (e) {}
    // 브리프(오너): 갤러리 컨테이너 스코프 실패 시 document.images 전체 폴백 금지 → 빈 배열(정직, Tier1이 채우거나 부분수집).
    return { images: out, detailImages: det };
  }
  // v57 STEP3: 상세영역에 '더보기'류 접힘 컨트롤이 있는지(펼치면 상세이미지가 더 나올 수 있음).
  var FOLD_RE = /(더\s*보기|펼치기|전체\s*보기|자세히\s*보기|see\s*more|view\s*more|read\s*more|show\s*more|expand)/i;
  function _foldButtons() {
    var out = [];
    try {
      var cands = document.querySelectorAll(
        '[class*="detail" i] button,[class*="detail" i] a,[class*="detail" i] [role="button"],' +
        '[class*="description" i] button,[class*="description" i] a,[class*="desc" i] [role="button"],' +
        'button,a[role="button"],[role="button"]');
      for (var i = 0; i < cands.length && out.length < 6; i++) {
        var el = cands[i];
        var t = (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim();
        if (t && t.length <= 20 && FOLD_RE.test(t)) out.push(el);
      }
    } catch (e) {}
    return out;
  }
  function _hasDetailFold() { return _foldButtons().length > 0; }
  var OPT_LABEL = /(색상|색깔|컬러|사이즈|크기|규격|수량|종류|옵션|타입|스타일|모델|용량|color|colour|size|variant|option|type|style|qty|quantity|model|capacity)/i;
  function _domOptions() {
    var out = [], seen = {};
    function _push(name, vals) {
      var uniq = [], s2 = {};
      vals.forEach(function (v) { v = (v || "").replace(/\s+/g, " ").trim(); if (v && v.length <= 40 && !s2[v]) { s2[v] = 1; uniq.push(v); } });
      if (uniq.length < 2) return;
      var key = name + "|" + uniq.join(",");
      if (seen[key]) return; seen[key] = 1;
      out.push({ name: name, values: uniq.slice(0, 50) });
    }
    try {
      var sels = document.querySelectorAll("select");
      for (var i = 0; i < sels.length; i++) {
        var sel = sels[i]; if (_nonProdRegion(sel)) continue;
        var vals = Array.prototype.slice.call(sel.options || []).map(function (o) { return (o.textContent || "").trim(); })
          .filter(function (t) { return t && !/^(선택|선택하세요|choose|select|please)/i.test(t); });
        var lbl = sel.getAttribute("aria-label") || (sel.labels && sel.labels[0] && sel.labels[0].textContent) || "";
        var m = String(lbl).match(OPT_LABEL); _push(m ? m[0] : "옵션", vals);
      }
    } catch (e) {}
    // v62 STEP3: 아마존 트위스터 — 축 이름 정확 매핑(색상/사이즈). 값은 v58 스와치 경로가 이미 잡지만
    //   이름이 '옵션'으로 뭉개짐 → 행 id(inline-twister-row-color_name) / .a-form-label('Color:')로 축명 복원.
    try {
      var _TW_ID = { color: "색상", size: "사이즈", style: "스타일", pattern: "패턴", flavor: "종류", model: "모델", material: "소재", edition: "에디션" };
      var trows = document.querySelectorAll('[id^="inline-twister-row-"],#twister [class*="twisterTextDiv" i]');
      for (var t2 = 0; t2 < trows.length; t2++) {
        var row = trows[t2];
        if (_nonProdRegion(row)) continue;
        // 축명: 행 id의 표준 축(color/size…)을 한글로 우선 매핑, 없으면 .a-form-label 텍스트.
        var rid = (row.id || "").replace("inline-twister-row-", "").split("_")[0].toLowerCase();
        var nm = _TW_ID[rid] || "";
        if (!nm) {
          var flbl = row.querySelector(".a-form-label,label");
          if (flbl) {
            var ft = String(flbl.innerText || flbl.textContent || "").replace(/[:：]\s*$/, "").replace(/\s+/g, " ").trim();
            var fm = ft.match(OPT_LABEL); if (fm) nm = fm[0];
          }
        }
        var tv = [], sw = row.querySelectorAll('.swatches li,[class*="swatch" i] li,ul.a-button-list li,[role="radio"],button[data-asin]');
        for (var s3 = 0; s3 < sw.length && tv.length < 60; s3++) {
          var el3 = sw[s3];
          var st = String((el3.getAttribute && (el3.getAttribute("title") || el3.getAttribute("aria-label"))) || el3.innerText || el3.textContent || "").replace(/\s+/g, " ").trim();
          if (st && st.length <= 40 && !/^(선택|choose|select|please|담기|구매|장바구니)/i.test(st)) tv.push(st);
        }
        _push(nm || "옵션", tv);
      }
    } catch (e) {}
    // v58 STEP2: 라디오·버튼 그룹(구매박스 인근 색상/사이즈 스와치) — select 없는 SPA(테무 등) 대응.
    //   role=radiogroup / [class*=sku i] / [class*=option i] / [class*=variant i] / [class*=spec i] 컨테이너에서
    //   버튼·라디오·라벨의 텍스트를 옵션 값으로. 추천/리뷰 영역 제외. 값 2+일 때만(확신 없으면 미수집=정직).
    try {
      var groups = document.querySelectorAll('[role="radiogroup"],[class*="sku" i],[class*="option" i],[class*="variant" i],[class*="spec" i],[class*="swatch" i]');
      for (var g = 0; g < groups.length; g++) {
        var grp = groups[g];
        if (_nonProdRegion(grp) || _galleryExcluded(grp)) continue;
        if (grp.closest && grp.closest('[id^="inline-twister-row-"]')) continue;   // v62: 트위스터는 위에서 축명 매핑(중복 방지)
        if (grp.querySelector("select")) continue;       // select은 위에서 처리(중복 방지)
        // 그룹 라벨: aria-label / [class*=label] / 첫 텍스트 노드 중 OPT_LABEL 매칭.
        var glbl = grp.getAttribute("aria-label") || "";
        if (!glbl) { var le = grp.querySelector('[class*="label" i],[class*="title" i],dt,.name'); if (le) glbl = (le.innerText || le.textContent || ""); }
        var gm = String(glbl).match(OPT_LABEL);
        // 값 후보: 버튼·라디오·옵션 라벨·스와치.
        var cands = grp.querySelectorAll('button,[role="radio"],label,[class*="value" i],[class*="item" i],a[data-value],[data-value]');
        var vv = [];
        for (var c = 0; c < cands.length && vv.length < 60; c++) {
          var el = cands[c];
          if (el.querySelector && el.querySelector("button,[role=radio],select")) continue;   // 중첩 컨테이너 스킵
          var t = (el.getAttribute && (el.getAttribute("aria-label") || el.getAttribute("data-value") || el.getAttribute("title"))) || el.innerText || el.textContent || "";
          t = String(t).replace(/\s+/g, " ").trim();
          if (t && t.length >= 1 && t.length <= 40 && !/^(선택|choose|select|please|담기|구매|장바구니|add to|buy)/i.test(t)) vv.push(t);
        }
        // 라벨 텍스트가 값에 섞이면 제외(라벨=그룹명).
        if (gm) vv = vv.filter(function (v) { return v.replace(/\s/g, "") !== gm[0].replace(/\s/g, ""); });
        _push(gm ? gm[0] : "옵션", vv);
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
    // v60 STEP2: 아마존 About this item(#feature-bullets) 불릿을 구조화 텍스트로 + productDescription 본문.
    try {
      var fb = document.querySelector("#feature-bullets");
      if (fb && !_nonProdRegion(fb)) {
        var bl = [];
        fb.querySelectorAll("li span.a-list-item, li").forEach(function (li) {
          var t = (li.innerText || li.textContent || "").replace(/\s+/g, " ").trim();
          if (t && t.length > 2 && !/^about this item$/i.test(t) && bl.indexOf("· " + t) < 0) bl.push("· " + t);
        });
        var pd = document.querySelector("#productDescription");
        var pdt = pd ? (pd.innerText || "").replace(/\n{3,}/g, "\n\n").trim() : "";
        var out = [bl.join("\n"), pdt].filter(Boolean).join("\n\n").trim();
        if (out.length > 20) return out.slice(0, 4000);
      }
    } catch (e) {}
    var sel = ['#productDescription', '[class*="description" i]', '[class*="detail" i]'];
    for (var i = 0; i < sel.length; i++) {
      try { var el = document.querySelector(sel[i]); if (el && !_nonProdRegion(el)) { var t = (el.innerText || "").trim(); if (t.length > 20) return t.slice(0, 4000); } } catch (e) {}
    }
    return _meta("og:description") || _meta("description") || "";
  }
  // v60 STEP1: 우리 확장이 주입한 DOM(kgp-*) 또는 사이드패널/챗/네비 등 페이지 크롬 안에 있는 요소인지.
  //   → 제목/키워드 추출에서 제외(아마존 'Chat history' 등 삽입 UI h1 오염 차단).
  function _isInjectedUI(el) {
    var re = /(^|\s|-)(kgp-|assistant|copilot|rufus|chat[-_ ]?history|chat[-_ ]?panel|side[-_ ]?panel|sidebar|drawer|overlay|extension|widget|toolbar|popover|modal)($|\s|-)/i;
    var cur = el, d = 0;
    while (cur && d < 12) {
      var id = cur.id || "";
      var cls = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || ""));
      if (/^kgp-/.test(id) || /(^|\s)kgp-/.test(cls) || (cur.getAttribute && cur.getAttribute("data-kgp-outline"))) return true;
      var tg = (cur.tagName || "").toLowerCase();
      if (tg === "nav" || tg === "aside" || tg === "header") return true;
      var role = cur.getAttribute && (cur.getAttribute("role") || "");
      if (/(complementary|navigation|dialog|banner)/i.test(role || "")) return true;
      if (re.test(id + " " + cls)) return true;
      cur = cur.parentElement; d++;
    }
    return false;
  }
  // v60 STEP1: 디폴트 소싱처 어댑터별 상품명 셀렉터(하드매핑) — 삽입 UI h1 오염을 원천 우회.
  function _adapterTitle() {
    var host = (location.hostname || "").toLowerCase();
    var MAP = [
      { re: /(^|\.)amazon\.[a-z.]+$/, sels: ["#productTitle", "#title #productTitle", "h1#title span"] },
      { re: /(^|\.)temu\.[a-z.]+$/, sels: ['[class*="goods-name" i]', '[class*="productTitle" i]', 'h1[class*="title" i]'] },
      { re: /(^|\.)(aliexpress|ae01)\.[a-z.]+$/, sels: ['h1[data-pl="product-title"]', '[class*="title--wrap" i] h1', "h1"] },
      { re: /(^|\.)(taobao|tmall)\.[a-z.]+$/, sels: ['[class*="mainTitle" i]', '[class*="ItemTitle" i]', "h1"] },
    ];
    for (var i = 0; i < MAP.length; i++) {
      if (!MAP[i].re.test(host)) continue;
      for (var s = 0; s < MAP[i].sels.length; s++) {
        try {
          var el = document.querySelector(MAP[i].sels[s]);
          if (el && !_isInjectedUI(el)) {
            var t = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
            if (t && t.length >= 2) return t.slice(0, 300);
          }
        } catch (e) {}
      }
      break;
    }
    return "";
  }
  // v60 STEP1: 본문 최상위 h1 — 우리 UI·삽입 패널 제외, 제일 긴(상품명일 가능성 높은) 것.
  function _cleanH1() {
    try {
      var h1s = document.querySelectorAll("h1");
      var best = "";
      for (var i = 0; i < h1s.length; i++) {
        var el = h1s[i];
        if (_isInjectedUI(el) || _nonProdRegion(el)) continue;
        var t = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
        if (t && t.length > best.length) best = t;
      }
      return best.slice(0, 300);
    } catch (e) { return ""; }
  }

  // v65 STEP1: 순수 사이트/브랜드명 판별(상품명 아님) — 제목이 'Temu'·'Amazon' 등으로 저장되는 것 차단.
  //   상품명이면 사이트명 뒤에 상품 정보가 붙거나(예 '무선 이어폰 | Temu') 길이가 길다. 바로 그 사이트명만/짧은 것만 배제.
  function _isBareSiteName(t) {
    var s = String(t || "").trim();
    if (!s) return true;
    if (s.length <= 2) return true;
    if (/^(temu|amazon|aliexpress|taobao|tmall|1688|rakuten|mercari|shopee|ebay|yahoo|paypaymall)!?(\.[a-z.]+)?\s*(shopping|쇼핑|ショッピング|재팬|japan)?[\s\-–|:·!]*$/i.test(s)) return true;
    return false;
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

    // v60 STEP1: 타이틀 우선순위 = 어댑터 지정 셀렉터 → ld+json/state name(Tier1) → 본문 h1(우리 UI·패널 제외)
    //   → og:title → document.title(최후). 삽입 UI h1('Chat history' 등) 오염 차단.
    var at = _adapterTitle();
    var h1t = _cleanH1();
    var ogt = _meta("og:title");
    // v65 STEP1: 순수 사이트/브랜드명("Temu" 등)은 상품명이 아니다 — 후보에서 배제(제목 'Temu' 재발 금지).
    var _cands = [{ v: at, s: "adapter" }, { v: j.title, s: "tier1" }, { v: h1t, s: "tier2" },
      { v: ogt, s: "tier3" }, { v: (document.title || ""), s: "tier3" }];
    var title = "", titleSrc = "none";
    for (var _ti = 0; _ti < _cands.length; _ti++) {
      var _c = String(_cands[_ti].v || "").replace(/\s+/g, " ").trim();
      if (_c && !_isBareSiteName(_c)) { title = _c; titleSrc = _cands[_ti].s; break; }
    }
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

    // v57 STEP3: 상세이미지는 **갤러리와 독립** 수집 — Tier1이 갤러리를 채웠어도 상세(더보기 접힘)는
    //   비어 있을 수 있다. 숨김 컨테이너(display:none 포함 — querySelectorAll은 포함)의 data-src까지 긁는다.
    var detailFold = _hasDetailFold();
    if (detailImages.length === 0) {
      try { var di2 = _domImages(); if (di2.detailImages && di2.detailImages.length) detailImages = di2.detailImages; } catch (e) {}
    }
    // v60 STEP2: 상세설명(desc_text)도 **가격/이미지와 독립** 수집 — Tier1이 가격·이미지를 채워 needDom이
    //   false여도 상세설명은 비어 있을 수 있다(아마존 About this item 미수집 근원). 있으면 채운다.
    if (!description) { try { description = _domDescription(); } catch (e) {} }
    if (!options.length) { try { options = _domOptions(); } catch (e) {} }
    if (!specs.length) { try { specs = _domSpecs(); } catch (e) {} }
    // 정직: 더보기 접힘이 남아 있고 상세이미지가 여전히 비었으면 '일부만' 경고(무음 실패 금지).
    if (detailFold && detailImages.length === 0) warnings.push("상세이미지 일부만(더보기 펼침 필요할 수 있어요)");

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

    // v51: 필드별 추출 Tier — Tier1(캡처 API/초기상태 JSON)·Tier2(렌더 DOM 갤러리·h1)·Tier3(og/meta)·none.
    //   서버 수집 로그에 '어느 Tier가 어느 필드를 줬는지' 표기. 값 없으면 none(가짜 소스 날조 금지).
    var fieldSources = {
      title: titleSrc,
      price: j.price ? "tier1" : (price ? "tier2" : "none"),
      images: (j.images && j.images.length) ? "tier1" : (gallery.length ? "tier2" : "none"),
      options: (j.options && j.options.length) ? "tier1" : (options.length ? "tier2" : "none"),
      description: j.description ? "tier1" : (description ? "tier2" : "none"),
      detail_images: (j.detailImages && j.detailImages.length) ? "tier1" : (detailImages.length ? "tier2" : "none"),
      reviews: ((j.reviews && j.reviews.length) || j.rating || j.reviewCount) ? "tier1" : "none"
    };

    var out = {
      url: location.href,
      title: String(title || "").slice(0, 300),
      price: price, currency: currency, price_status: price_status,
      image: gallery[0] || "",
      images: gallery, gallery_images: gallery, detail_images: detailImages,
      detail_fold: detailFold,          // v57 STEP3: 상세 '더보기' 접힘 잔존 여부(정직 표기용)
      thumbnail: gallery[0] || "",
      options: options, skus: skus,
      description: description, detail_specs: specs,
      desc_text: description, desc_images: detailImages,   // v60 STEP2: 상세 텍스트/이미지 명시 분리(브리프 명명)
      reviews: reviews, rating: rating, review_count: reviewCount,
      source: source, partial: partial, warnings: warnings,
      field_sources: fieldSources,
      // v54 STEP2: 자가발견 채택 응답 URL 패턴(sources=tier1:{URL}) — Tier1이 실제 기여했을 때만.
      tier1_source: (j.ok && fieldSources.price === "tier1") ? (global.__kgpTier1Url || "") : "",
      jsonld: _jsonLd(),
      collected_at: new Date().toISOString()
    };
    return out;
  }

  // v57 STEP3: 상세 '더보기' 접힘을 프로그램적으로 펼친다 — 클릭 → MutationObserver로 새 img 대기(최대 3s).
  //   상세이미지가 fold 뒤에 lazy-mount되는 테무 대응. 접힘 없으면 즉시 콜백(정상 페이지 지연 0).
  //   추가 네트워크 요청 없음(페이지 자체 로더가 이미지 채움). cb는 상세이미지 증가 여부와 무관하게 1회 호출.
  function kgpRevealDetailFolds(cb) {
    var done = false;
    function finish() { if (done) return; done = true; try { cb && cb(); } catch (e) {} }
    var btns;
    try { btns = _foldButtons(); } catch (e) { btns = []; }
    if (!btns || !btns.length) { finish(); return; }
    var scope = null;
    try { scope = document.querySelector('[class*="detail" i],[class*="description" i],[class*="goods-desc" i]') || document.body; } catch (e) { scope = document.body; }
    var before = 0;
    try { before = scope.querySelectorAll("img").length; } catch (e) {}
    var mo = null, timer = null;
    function stop() { try { if (mo) mo.disconnect(); } catch (e) {} if (timer) clearTimeout(timer); finish(); }
    try {
      mo = new MutationObserver(function () {
        var now = 0; try { now = scope.querySelectorAll("img").length; } catch (e) {}
        if (now > before) stop();               // 새 이미지 mount 확인 → 조기 종료
      });
      mo.observe(scope, { childList: true, subtree: true, attributes: true, attributeFilter: ["src", "data-src"] });
    } catch (e) {}
    // 접힘 버튼 클릭(최대 3개 — 여러 섹션 대응). 스크롤 유발 lazy도 커버.
    for (var i = 0; i < btns.length && i < 3; i++) {
      try { btns[i].scrollIntoView({ block: "center" }); } catch (e) {}
      try { btns[i].click(); } catch (e) {}
    }
    timer = setTimeout(stop, 3000);              // 최대 3초 후 강제 종료(무한 대기 금지)
  }

  // v65 STEP1: 렌더 완료 대기 — 정본 경로(렌더된 DOM 추출)의 게이트. 가격 패턴 텍스트 + 메인 이미지(≥200px)
  //   로드를 감지하면 준비 완료. 최대 maxMs(기본 8초) 초과 시 '부분'(있는 것만)으로 진행. 셀렉터 의존 최소.
  function _renderReady() {
    var priceOk = false, imgOk = false;
    try { var p = _domPrice(); priceOk = !!(p && p.price); } catch (e) {}
    try {
      var imgs = document.querySelectorAll("img");
      for (var i = 0; i < imgs.length; i++) {
        var im = imgs[i];
        if (((im.naturalWidth || im.width || 0) >= 200) && ((im.naturalHeight || im.height || 0) >= 200)) { imgOk = true; break; }
      }
    } catch (e) {}
    return { priceOk: priceOk, imgOk: imgOk, ready: priceOk && imgOk };
  }
  // 준비될 때까지 폴링(250ms). ready면 partial=false, maxMs 초과면 partial=true로 cb 호출(무한대기 금지).
  function kgpWaitRendered(cb, maxMs) {
    var intervalMs = 250;
    var maxTicks = Math.max(1, Math.ceil(((typeof maxMs === "number" ? maxMs : 8000)) / intervalMs));
    var ticks = 0, done = false;
    function finish(partial) { if (done) return; done = true; try { cb && cb({ partial: !!partial, ready: !partial }); } catch (e) {} }
    function tick() {
      if (done) return;
      var r;
      try { r = _renderReady(); } catch (e) { r = { ready: false }; }
      if (r.ready) { finish(false); return; }
      ticks++;
      if (ticks >= maxTicks) { finish(true); return; }   // 8초 초과 → 부분 표기
      setTimeout(tick, intervalMs);
    }
    tick();
  }

  global.kgpExtractProduct = kgpExtractProduct;
  global.kgpRevealDetailFolds = kgpRevealDetailFolds;
  global.kgpWaitRendered = kgpWaitRendered;
  global._kgpRenderReady = _renderReady;   // 테스트/진단용
  if (typeof module !== "undefined" && module.exports) module.exports = { kgpExtractProduct: kgpExtractProduct, kgpRevealDetailFolds: kgpRevealDetailFolds, kgpWaitRendered: kgpWaitRendered };
})(typeof window !== "undefined" ? window : this);
