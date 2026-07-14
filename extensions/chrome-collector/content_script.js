/**
 * content_script.js — 페이지 컨텍스트에서 메타 추출 + 인페이지 '수집' 버튼 (Phase 202+)
 * 고가수집기
 *
 * 1) 백그라운드/팝업에서 "extractMeta" 메시지 요청 시 메타 응답.
 * 2) v10: '지정 소싱처' 도메인에서만 수집 UI(FAB/리스팅 바)를 주입한다(그 외 사이트엔 아무것도 안 그림).
 *    소싱처는 기본셋 + 사용자 지정(chrome.storage.local의 kgp_sources)로 관리, 런타임 즉시 반영.
 * 3) 리스팅은 사이트 어댑터(아마존 등) + 엄격 휴리스틱으로 '실제 제품 카드만' 감지(추천/푸터/썸네일 제외).
 */

// v39-E2 #1: PDP 가격 노드에서 '현재가(판매가)'를 읽는다(취소선·추천/리뷰 영역 제외).
//   서버 스코프 추출(_extract_scoped_price)과 동일 취지의 인페이지 판.
const _KGP_ORIG_PRICE_RE = /(original|was[-_ ]?price|strike|line[-_]?through|regular|list[-_]?price|old[-_]?price|compare[-_]?at|정가|원가|할인전)/i;
const _KGP_NONPROD_RE = /(recommend|related|similar|also[-_ ]?(bought|viewed)|sponsored|advert|ranking|recently[-_ ]?viewed|carousel|cross[-_ ]?sell|up[-_ ]?sell|footer|review|comment)/i;
function _kgpPriceIsOriginal(el) {
  let cur = el, depth = 0;
  while (cur && depth < 4) {
    const tag = (cur.tagName || "").toLowerCase();
    if (tag === "del" || tag === "s" || tag === "strike") return true;
    const tok = ((cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || ""));
    if (tok && _KGP_ORIG_PRICE_RE.test(tok)) return true;
    try { if ((getComputedStyle(cur).textDecorationLine || "").indexOf("line-through") >= 0) return true; } catch (e) { /* noop */ }
    cur = cur.parentElement; depth++;
  }
  return false;
}
function _kgpInNonProd(el) {
  let cur = el && el.parentElement, depth = 0;
  while (cur && depth < 6) {
    const tok = ((cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || ""));
    if (tok && _KGP_NONPROD_RE.test(tok)) return true;
    cur = cur.parentElement; depth++;
  }
  return false;
}
// v42 1-1: 통화 감지에 한국어/일본어/중국어 접미어(원·엔·위안·元) 포함 — Temu KR은 '₩' 또는 '61,144원'.
const _KGP_SYM_MAP = { "$": "USD", "＄": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "￥": "JPY", "₩": "KRW", "￦": "KRW" };
const _KGP_CODE_MAP = {
  "USD": "USD", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY", "KRW": "KRW", "CNY": "CNY",
  "원": "KRW", "엔": "JPY", "위안": "CNY", "元": "CNY",
};
const _KGP_PRICE_RE = /([\$＄€£¥￥₩￦])\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(USD|EUR|GBP|JPY|KRW|CNY|원|엔|위안|元)/i;
function _kgpParsePrice(raw) {
  const m = (raw || "").match(_KGP_PRICE_RE);
  if (!m) return null;
  const sym = m[1] || "", num = (m[2] || m[3] || "").replace(/,/g, ""), code = m[4] || "";
  if (!num) return null;
  const cur = code ? (_KGP_CODE_MAP[code] || _KGP_CODE_MAP[code.toUpperCase()] || code.toUpperCase())
                   : (_KGP_SYM_MAP[sym] || "");
  return { price: num, currency: cur };
}
// 가격이 아닌 숫자(재고 '9개 남음'·쿠폰·수량·배송·평점·판매수)를 걸러 Temu '9 KRW' 오추출을 막는다.
const _KGP_NONPRICE_RE = /(재고|남음|남았|개\s*남|수량|qty|quantity|stock|left|in\s*cart|장바구니|쿠폰|coupon|적립|포인트|point|리뷰|review|평점|rating|판매|sold|명이|배송비|shipping\s*fee|무료배송|free\s*shipping|할인율|% ?off|퍼센트)/i;
function _kgpNonPriceCtx(el) {
  // 노드 자신·근접 조상(4단계) 텍스트/클래스에 재고·쿠폰·수량 신호가 있으면 가격 후보에서 제외.
  let cur = el, depth = 0;
  while (cur && depth < 4) {
    const tok = ((cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || ""));
    if (tok && _KGP_NONPRICE_RE.test(tok)) return true;
    cur = cur.parentElement; depth++;
  }
  // 노드 자신 텍스트가 '9개 남음'처럼 재고/수량 문구면 제외(가격 숫자와 혼동 방지).
  const own = (el.textContent || "").slice(0, 40);
  if (_KGP_NONPRICE_RE.test(own)) return true;
  return false;
}
function _kgpNodePath(el) {
  var parts = [], cur = el, n = 0;
  while (cur && n < 4) {
    var t = (cur.tagName || "").toLowerCase();
    var c = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || ""));
    parts.unshift(t + (c ? "." + String(c).trim().split(/\s+/).slice(0, 2).join(".") : ""));
    cur = cur.parentElement; n++;
  }
  return parts.join(" > ");
}
function _kgpScopedPrice() {
  // P0(오너): Temu 실가 20,605원인데 9 KRW 저장 = 재고 '9개 남음'/쿠폰 숫자를 가격으로 오인.
  //   수리: ①재고·쿠폰·수량·평점 문맥 제외 ②원가(취소선)·추천/리뷰 제외 ③**메인 가격은 화면에서
  //   가장 큰 글씨** → 후보를 폰트 크기로 스코어(동률이면 큰 값). 후보·채택 노드경로를 콘솔 로그.
  let nodes = [];
  try {
    nodes = Array.from(document.querySelectorAll('[class*="price" i],[class*="Price"],[itemprop="price"],[data-price],[class*="amount" i],[aria-label*="price" i]'));
  } catch (e) { nodes = []; }
  const cands = [];
  for (const el of nodes) {
    if (_kgpInNonProd(el) || _kgpPriceIsOriginal(el) || _kgpNonPriceCtx(el)) continue;
    const raw = el.getAttribute("content") || el.getAttribute("data-price") || (el.textContent || "").trim();
    const p = _kgpParsePrice(raw);
    if (!p) continue;
    let fs = 0;
    try { fs = parseFloat(getComputedStyle(el).fontSize) || 0; } catch (e) { fs = 0; }
    cands.push({ price: p.price, currency: p.currency, val: parseFloat(p.price) || 0, fs: fs, path: _kgpNodePath(el) });
  }
  // 메인 가격 = 가장 큰 글씨(시각적 프로미넌스). 폰트 정보 없으면 큰 값으로.
  cands.sort((a, b) => (b.fs - a.fs) || (b.val - a.val));
  const best = cands[0] || null;
  try {
    console.log("[고가수집기] 가격 후보(" + cands.length + "):",
      cands.slice(0, 8).map(c => c.price + " " + c.currency + " @" + c.fs + "px [" + c.path + "]"));
    if (best) console.log("[고가수집기] 채택 가격:", best.price, best.currency, "| node:", best.path);
  } catch (e) {}
  return best ? { price: best.price, currency: best.currency } : { price: "", currency: "" };
}

// v45(5): 클릭 시점 옵션(색상/사이즈/수량/변형) 추출 — payload.options로 전송(서버가 편집 프리필).
//   보수적: <select> + 라벨 붙은 스와치 그룹(값 2개 이상)만. 추천/리뷰 영역·과다 그룹 제외.
const _KGP_OPT_LABEL = /(색상|색깔|컬러|사이즈|크기|규격|수량|종류|옵션|타입|스타일|모델|용량|color|colour|size|variant|option|type|style|qty|quantity|model|capacity)/i;
function _kgpOptName(around) {
  const m = (around || "").match(_KGP_OPT_LABEL);
  return m ? m[0] : "옵션";
}
function _kgpCollectOptions() {
  const out = [], seen = new Set();
  try {
    // 1) <select> 드롭다운
    document.querySelectorAll("select").forEach((sel) => {
      if (_kgpInNonProd(sel)) return;
      const opts = Array.from(sel.options || []).map((o) => (o.textContent || "").trim())
        .filter((t) => t && !/^(선택|선택하세요|choose|select|please)/i.test(t));
      const uniq = Array.from(new Set(opts));
      if (uniq.length >= 2) {
        const lbl = sel.getAttribute("aria-label") || (sel.labels && sel.labels[0] && sel.labels[0].textContent) || "";
        out.push({ name: _kgpOptName(lbl), values: uniq.slice(0, 50) });
      }
    });
    // 2) 스와치/변형 그룹
    document.querySelectorAll('[class*="sku" i],[class*="variant" i],[class*="option" i],[class*="attr" i],[role="radiogroup"],[class*="spec" i]').forEach((grp) => {
      if (_kgpInNonProd(grp)) return;
      const vals = [];
      grp.querySelectorAll('button,[role="radio"],li,span[aria-label],img[alt],[class*="item" i]').forEach((el) => {
        let t = (el.getAttribute("aria-label") || el.getAttribute("title") || el.getAttribute("alt") || el.textContent || "").replace(/\s+/g, " ").trim();
        if (t && t.length >= 1 && t.length <= 40 && !_KGP_OPT_LABEL.test(t) && vals.indexOf(t) < 0) vals.push(t);
      });
      if (vals.length >= 2 && vals.length <= 60) {
        const lblEl = grp.querySelector('[class*="label" i],[class*="title" i],dt,legend');
        const around = ((lblEl && lblEl.textContent) || "") + " " + ((grp.previousElementSibling && grp.previousElementSibling.textContent) || "") + " " + (grp.getAttribute("aria-label") || "");
        const name = _kgpOptName(around);
        const key = name + "|" + vals.slice(0, 4).join(",");
        if (!seen.has(key)) { seen.add(key); out.push({ name: name, values: vals.slice(0, 50) }); }
      }
    });
  } catch (e) { /* noop */ }
  return out.slice(0, 8);
}

// v44: 사이트별 PDP 추출 — 서버 사후 크롤(봇 차단 영구실패) 대신 클릭 시점 렌더 DOM에서 직접 읽기.
//   아마존: #imgTagWrapperId(고해상)·#altImages 썸네일→원본 · #feature-bullets·#productDescription·#aplus.
//   Temu: 메인 캐러셀 컨테이너 · 상세 영역. 갤러리/상세 2버킷.
function _kgpAmazonHiRes(u) {
  if (!u) return u;
  // 아마존 이미지 URL의 크기/포맷 수식자(._AC_SX466_ · ._SS40_ 등) 제거 → 원본 고해상.
  return u.replace(/\._[A-Za-z0-9,_-]+_\.(jpg|jpeg|png|gif|webp)/i, ".$1");
}
function _kgpSitePdp() {
  const host = (location.hostname || "").toLowerCase();
  const out = { gallery: [], detail: [], description: "" };
  const _add = (arr, u) => { u = (u || "").trim(); if (u && u.indexOf("data:") !== 0 && arr.indexOf(u) < 0) arr.push(u); };
  try {
    if (/(^|\.)amazon\.[a-z.]+$/.test(host)) {
      const main = document.querySelector("#imgTagWrapperId img, #landingImage, #imgBlkFront, #main-image");
      if (main) {
        _add(out.gallery, main.getAttribute("data-old-hires") || "");
        const dyn = main.getAttribute("data-a-dynamic-image");
        if (dyn) { try { Object.keys(JSON.parse(dyn)).forEach(u => _add(out.gallery, u)); } catch (e) { /* noop */ } }
        _add(out.gallery, _kgpAmazonHiRes(main.currentSrc || main.src || ""));
      }
      document.querySelectorAll("#altImages img, #imageBlockThumbs img, li.imageThumbnail img").forEach(im => {
        _add(out.gallery, _kgpAmazonHiRes(im.currentSrc || im.src || ""));
      });
      document.querySelectorAll("#aplus img, #aplus_feature_div img, #productDescription img").forEach(im => {
        _add(out.detail, _kgpAmazonHiRes(im.getAttribute("data-src") || im.currentSrc || im.src || ""));
      });
      const bullets = [];
      document.querySelectorAll("#feature-bullets li span.a-list-item, #feature-bullets li").forEach(li => {
        const t = (li.innerText || li.textContent || "").trim();
        if (t && t.length > 2 && bullets.indexOf(t) < 0) bullets.push("· " + t);
      });
      const pd = document.querySelector("#productDescription");
      const pdText = pd ? (pd.innerText || "").trim() : "";
      out.description = [bullets.join("\n"), pdText].filter(Boolean).join("\n\n").slice(0, 4000);
    } else if (/(^|\.)temu\.[a-z.]+$/.test(host)) {
      const gal = document.querySelector('[class*="gallery" i],[class*="Gallery" i],[class*="mainImage" i],[class*="swiper" i]');
      if (gal) gal.querySelectorAll("img").forEach(im => _add(out.gallery, im.currentSrc || im.src || im.getAttribute("data-src") || ""));
      const det = document.querySelector('[class*="detail" i],[class*="Description" i],[class*="goods-desc" i]');
      if (det) {
        det.querySelectorAll("img").forEach(im => _add(out.detail, im.currentSrc || im.src || im.getAttribute("data-src") || ""));
        // v44: Temu 상세 영역 텍스트 + 스펙표(속성표) — 본문 innerText가 스펙표 셀도 포함.
        const specRows = [];
        det.querySelectorAll("table tr, dl > dt, dl > dd, [class*='spec' i] li, [class*='attribute' i] li, [class*='param' i] li").forEach(el => {
          const t = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
          if (t && t.length >= 2 && specRows.indexOf(t) < 0) specRows.push(t);
        });
        const bodyText = (det.innerText || "").trim();
        out.description = [bodyText, specRows.length ? ("· " + specRows.slice(0, 40).join("\n· ")) : ""]
          .filter(Boolean).join("\n\n").slice(0, 4000);
      }
    }
  } catch (e) { /* noop */ }
  return out;
}

function extractProductMeta() {
  // 공유 추출기(kgp-extractor.js) 우선 — 확장·북마클릿 동일 코드(JSON우선·DOM폴백·부분수집·가격 sanity).
  //   manifest가 이 스크립트보다 먼저 로드. 만약 미로드면 아래 레거시 DOM 폴백으로 정직 동작.
  if (typeof window.kgpExtractProduct === "function") {
    try { return window.kgpExtractProduct(); } catch (e) { try { console.error("[고가수집기] 공유 추출기 오류, 레거시 폴백:", e); } catch (_) {} }
  }
  const getMeta = (prop) => {
    const el = document.querySelector(
      `meta[property="${prop}"], meta[name="${prop}"]`
    );
    return el ? el.getAttribute("content") || "" : "";
  };

  // JSON-LD 추출
  const jsonldScripts = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => {
      try {
        return JSON.parse(s.innerText || s.textContent || "");
      } catch {
        return null;
      }
    })
    .filter(Boolean);

  // 이미지: og:image 우선 + 페이지의 모든 상품 이미지(로고/배너/아이콘/작은 이미지 제외)
  const ogImage = getMeta("og:image") || getMeta("og:image:url") || "";
  // v11 P0: 무관 이미지(플래그·태그·픽셀·문서아이콘·화살표 등) 제외 — 서버 블랙리스트와 동일.
  const _isProductImg = (s) =>
    s && s.indexOf("data:") !== 0 &&
    !/(logo|sprite|icon|favicon|avatar|placeholder|loading|blank|pixel|spinner|banner|badge|button|arrow|chevron|caret|rating|star_|flags?|emoji|openingemail|supplier-public-tag|public-tag|\.slim\.|tracking|beacon|watermark|qr[-_]?code|coupon|nav_|\/pdf|pdf[-_]|\.pdf|\.doc|doc[-_]icon|\/doc\/|1x1|transparent\.|spacer)/i.test(s);
  const images = [];
  const _seenImg = new Set();
  const _pushImg = (s) => { if (_isProductImg(s) && !_seenImg.has(s)) { _seenImg.add(s); images.push(s); } };
  // v16 P0: 추천/연관/함께 본/스폰서/푸터 등 '다른 상품' 영역의 이미지는 제외(PDD 스코프, 혼입 방지).
  const _kgpNonProductRe = /(recommend|related|similar|also[-_ ]?(bought|viewed|like)|you[-_ ]?may|frequently[-_ ]?bought|sponsored|advert|promotion|ranking|best[-_ ]?seller|recently[-_ ]?viewed|carousel|slider|cross[-_ ]?sell|up[-_ ]?sell|comparison|footer|navbar|breadcrumb|other[-_ ]?products|popular|trending|review|comment|reply|qna|feedback|testimonial)/i;
  const _kgpInNonProductRegion = (el) => {
    let cur = el && el.parentElement, depth = 0;
    while (cur && depth < 8) {
      const tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && _kgpNonProductRe.test(tok)) return true;
      cur = cur.parentElement; depth++;
    }
    return false;
  };
  // v43-3: 판매자/브랜드 로고는 상품 이미지 아님 — src뿐 아니라 alt/class/조상영역으로도 배제('ALL IN HOME' 등).
  const _kgpSellerLogoRe = /(logo|brand|seller|merchant|store[-_ ]?(logo|name)|shop[-_ ]?(logo|name)|mall[-_ ]?name|판매자|브랜드관)/i;
  const _kgpIsSellerLogo = (im) => {
    try {
      const cls = (im.className && im.className.baseVal !== undefined ? im.className.baseVal : (im.className || ""));
      if (_kgpSellerLogoRe.test((im.getAttribute("alt") || "") + " " + cls + " " + (im.id || ""))) return true;
      let cur = im.parentElement, depth = 0;
      while (cur && depth < 5) {   // 판매자 정보 영역 안이면 로고로 간주
        const tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
        if (/(seller|merchant|store[-_ ]?info|shop[-_ ]?info|vendor|brand[-_ ]?header)/i.test(tok)) return true;
        cur = cur.parentElement; depth++;
      }
    } catch (e) { /* noop */ }
    return false;
  };
  // v43-3: PDP 갤러리(대표) ↔ 상세 본문 이미지 2버킷 스코프.
  const _KGP_GALLERY_SEL = '[class*="gallery" i],[class*="product-image" i],[class*="productImage" i],[class*="main-image" i],[class*="mainImage" i],[id*="imgTagWrapper" i],#imageBlock,[data-testid*="gallery" i]';
  const _KGP_DETAIL_SEL = '#productDescription,#feature-bullets,[class*="product-detail" i],[class*="description" i],[id*="description" i]';
  const _kgpInside = (im, sel) => { try { return !!(im.closest && im.closest(sel)); } catch (e) { return false; } };
  const gallery = [], detail = [];
  if (ogImage) { _pushImg(ogImage); gallery.push(ogImage); }
  // v44: 사이트별 PDP 추출을 최우선(아마존 고해상·A+·불릿 / Temu 캐러셀·상세) — 갤러리 대표는 여기서.
  const _site = _kgpSitePdp();
  _site.gallery.forEach((u) => { if (_isProductImg(u)) { _pushImg(u); if (gallery.indexOf(u) < 0) gallery.push(u); } });
  _site.detail.forEach((u) => { if (_isProductImg(u)) { _pushImg(u); if (detail.indexOf(u) < 0) detail.push(u); } });
  try {
    document.querySelectorAll("img").forEach((im) => {
      let src = im.currentSrc || im.src || im.getAttribute("data-src") || im.getAttribute("data-original") || "";
      if (!src && im.getAttribute("srcset")) {
        const parts = im.getAttribute("srcset").split(",");
        src = (parts[parts.length - 1] || "").trim().split(" ")[0];
      }
      const w = im.naturalWidth || im.width || 0;
      const h = im.naturalHeight || im.height || 0;
      if (!src || w < 250 || h < 250) return;
      if (_kgpInNonProductRegion(im) || _kgpIsSellerLogo(im) || !_isProductImg(src)) return;  // 추천·판매자로고·무관 제외
      _pushImg(src);
      if (_kgpInside(im, _KGP_DETAIL_SEL)) { if (detail.indexOf(src) < 0) detail.push(src); }
      else if (_kgpInside(im, _KGP_GALLERY_SEL)) { if (gallery.indexOf(src) < 0) gallery.push(src); }
    });
  } catch (e) { /* noop */ }

  // v42 1-1: 클릭 시점 렌더된 DOM의 '현재가'를 최우선으로 읽는다.
  //   SPA(Temu 등)의 og:price는 스테일하거나 USD 오값이 흔함 → 화면에 렌더된 판매가가 진실.
  //   순서: ①스코프 DOM 현재가(취소선·추천/리뷰 제외) → ②og:price 메타 → ③본문 텍스트 휴리스틱.
  //   통화 못 얻으면 빈 값(기본값 USD 금지) → 서버가 '가격 확인 필요' 정직 처리.
  let heuristicPrice = "";
  let heuristicCurrency = "";
  const _scoped = _kgpScopedPrice();
  if (_scoped.price) {
    heuristicPrice = _scoped.price;
    heuristicCurrency = _scoped.currency || "";
  }
  if (!heuristicPrice) {
    const metaAmt = getMeta("product:price:amount");
    if (metaAmt) {
      heuristicPrice = String(metaAmt).replace(/[^\d.,]/g, "").replace(/,/g, "");
      heuristicCurrency = (getMeta("product:price:currency") || "").toUpperCase();
    }
  }
  if (!heuristicPrice) {
    // 본문 텍스트 폴백 — 원/₩/¥/$/€ (Temu KR '61,144원' 포함).
    const bodyText = document.body ? document.body.innerText.slice(0, 4000) : "";
    const _bp = _kgpParsePrice(bodyText);
    if (_bp) { heuristicPrice = _bp.price; heuristicCurrency = _bp.currency || ""; }
  }

  // 봇 차단(403) 사이트도 수집되도록 페이지 HTML을 함께 전송 → 서버가 파싱(가격/이미지/옵션 보강).
  // 대용량 방지를 위해 상한(600KB)으로 자른다.
  let pageHtml = "";
  try {
    pageHtml = (document.documentElement ? document.documentElement.outerHTML : "").slice(0, 600000);
  } catch (e) {
    pageHtml = "";
  }

  // v16 P0: 사이트 공통 마케팅 필러(상품 설명 아님)는 보내지 않는다 — 서버 필러 가드와 동일 취지.
  const _kgpFiller = /(절약을\s*시작|쇼핑하여\s*절약|에서\s*쇼핑하여|최저가로\s*쇼핑|지금\s*쇼핑하세요|여기를\s*눌러|링크를\s*확인하세요|smarter\s+shopping|start\s+saving|save\s+big|free\s+shipping\s+on\s+(all\s+)?orders)/i;
  // 실제 상품 설명 우선: 설명 섹션 요소 텍스트 → 없으면 필러 아닌 og:description.
  function _kgpRealDescription() {
    // v44: 사이트별 상세(아마존 불릿+상세, Temu 본문)를 최우선 — 필러 아니면 그대로.
    if (_site && _site.description && _site.description.length >= 20 && !_kgpFiller.test(_site.description)) {
      return _site.description.slice(0, 4000);
    }
    const sel = ["#productDescription", "#feature-bullets", "#description",
      ".product-description", "[class*='product-detail']", "[class*='description']",
      "[id*='description']"];
    for (const s of sel) {
      try {
        const el = document.querySelector(s);
        const txt = el && (el.innerText || el.textContent || "").trim();
        if (txt && txt.length >= 30 && !_kgpFiller.test(txt)) return txt.slice(0, 4000);
      } catch (e) { /* noop */ }
    }
    const og = getMeta("og:description") || getMeta("description") || "";
    return _kgpFiller.test(og) ? "" : og;
  }

  return {
    url: location.href,
    title: getMeta("og:title") || document.title || "",
    image: (gallery[0] || images[0] || ogImage),   // v43-3: 대표=갤러리 첫 장(로고 배제)
    images: images,
    gallery_images: gallery,               // v43-3: 갤러리(대표) / 상세 2버킷 — 서버가 스코프 반영
    detail_images: detail,
    options: _kgpCollectOptions(),         // v45(5): 클릭 시점 옵션(색상/사이즈/수량) — 서버 편집 프리필
    price: heuristicPrice,                 // v42 1-1: 렌더 DOM 현재가 우선(위에서 scoped→meta→본문 순 해결)
    currency: heuristicCurrency,           // 기본값 USD 금지 — 못 얻으면 빈 값 → 서버 '가격 확인 필요'
    description: _kgpRealDescription(),
    brand: getMeta("og:brand") || "",
    jsonld: jsonldScripts,
    html: pageHtml,
    ext_version: (function () { try { return chrome.runtime.getManifest().version; } catch (e) { return ""; } })(),  // P0 진단·하위호환
    collected_at: new Date().toISOString()
  };
}

// 백그라운드 서비스 워커 메시지 리스너
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "extractMeta") {
    sendResponse(extractProductMeta());
    return true;
  }
  // v65 STEP1: 렌더 완료 대기 후 추출(정본 경로) — 보강 큐가 백그라운드 탭에서 사용.
  //   가격+메인이미지 로드 감지(최대 8초) → 접힘 상세 펼침 → 렌더된 DOM 추출. 부분이면 partial 표기.
  if (msg.action === "extractMetaWait") {
    const _wait = (typeof window.kgpWaitRendered === "function") ? window.kgpWaitRendered : (cb) => cb({ partial: false });
    _wait((res) => {
      const _finish = () => {
        let meta = {};
        try { meta = extractProductMeta() || {}; } catch (e) { meta = {}; }
        meta.partial = !!(res && res.partial);
        sendResponse(meta);
      };
      // 상세 접힘(더보기) 펼쳐 상세 이미지·불릿까지 렌더 후 추출.
      try { if (typeof window.kgpRevealDetailFolds === "function") window.kgpRevealDetailFolds(_finish); else _finish(); }
      catch (e) { _finish(); }
    }, 8000);
    return true;   // 비동기 응답
  }
  // v42 E-5: 벌크 수집 진행률 실시간 갱신(background가 1건마다 전송).
  if (msg.action === "bulkProgress") {
    kgpSetStatus(`수집 중… (${msg.done}/${msg.total})`);
    return false;
  }
  // v63 STEP1: 감지 디버그 패널 — 팝업이 조회. 지금 이 페이지의 실측 상태를 반환('왜 안 떠?'를 캡처 한 장으로).
  if (msg.action === "kgpDetectState") {
    let pt = "unknown", allowed = false, cards = 0, btn = "none";
    try { allowed = kgpHostAllowed() || kgpEntrySession(); } catch (e) {}
    try { pt = kgpPageType(); } catch (e) {}
    try { kgpFindCards(); cards = _kgpLastDetect.merged; } catch (e) {}
    try {
      if (document.getElementById(KGP_TOOLBAR_ID)) btn = "bulkbar";
      else if (document.getElementById(KGP_REOPEN_ID)) btn = "reopen";
      else if (document.getElementById(KGP_BTN_ID)) btn = "fab";
    } catch (e) {}
    sendResponse({
      ok: true, host: (location.hostname || ""), allowed: allowed, pageType: pt,
      cards: cards, generic: _kgpLastDetect.generic, adapter: _kgpLastDetect.adapter,
      adapterMatched: _kgpLastDetect.adapterMatched, scanned: _kgpScannedCount || 0, button: btn,
      excl: _kgpExcl,   // v65 STEP2: 제외 사유 분해(광고/파싱/URL/중복/영역)
    });
    return true;
  }
  return false;
});

// v16 P0: MV3 — 확장이 업데이트/재로딩되면 기존 탭의 content script는 chrome.runtime이 끊겨
// (extension context invalidated) sendMessage가 "Cannot read properties of undefined (reading 'sendMessage')"
// 를 던진다. 컨텍스트 유효성(chrome.runtime.id)을 먼저 확인하고, 끊겼으면 raw 에러 대신 새로고침 안내로 정직 처리.
function kgpExtAlive() {
  try { return !!(chrome && chrome.runtime && chrome.runtime.id); } catch (e) { return false; }
}
function kgpSendMessage(msg, cb) {
  if (!kgpExtAlive()) {
    cb && cb({ ok: false, error: "확장이 업데이트되었어요. 페이지를 새로고침(F5)한 뒤 다시 시도하세요.", _invalidated: true });
    return;
  }
  try {
    chrome.runtime.sendMessage(msg, (resp) => {
      const err = (chrome.runtime && chrome.runtime.lastError) ? chrome.runtime.lastError.message : "";
      if (err) { cb && cb({ ok: false, error: err }); return; }
      cb && cb(resp);
    });
  } catch (e) {
    cb && cb({ ok: false, error: (e && e.message) || "확장 연결 실패", _invalidated: true });
  }
}

// ---------------------------------------------------------------------------
// 인페이지 '수집' 버튼 (Phase 202)
// ---------------------------------------------------------------------------

const KGP_BTN_ID = "kgp-collect-fab";

/** 상품 페이지로 보이는지 휴리스틱 판단. */
function looksLikeProductPage() {
  const getMeta = (p) =>
    document.querySelector(`meta[property="${p}"], meta[name="${p}"]`)?.getAttribute("content") || "";
  if (getMeta("og:type").toLowerCase() === "product") return true;
  if (getMeta("product:price:amount")) return true;
  if (getMeta("og:image") && getMeta("og:title")) return true;
  // JSON-LD Product
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const data = JSON.parse(s.innerText || s.textContent || "");
      const arr = Array.isArray(data) ? data : [data];
      if (arr.some(x => x && String(x["@type"] || "").toLowerCase().includes("product"))) return true;
    } catch { /* noop */ }
  }
  return false;
}

// 알럿 중복 방지(오너): 수집 요청마다 corr-id를 부여하고, 그 corr-id의 완료 알럿은 '건당 1회'만.
//   (콜백 이중 발화·경로 중복 등 어떤 원인이든 같은 건은 한 번만 토스트/축하한다.)
let _kgpCorrSeq = 0;
const _kgpCorrDone = new Set();
function kgpNewCorr() { return "c" + Date.now() + "-" + (++_kgpCorrSeq); }
function kgpAlertOnce(corr, fn) {
  if (!corr) { fn(); return; }
  if (_kgpCorrDone.has(corr)) return;   // 같은 요청은 이미 알럿함 → 중복 억제
  _kgpCorrDone.add(corr);
  if (_kgpCorrDone.size > 300) {        // 메모리 상한(오래된 corr 정리)
    const it = _kgpCorrDone.values();
    for (let i = 0; i < 100; i++) { const v = it.next(); if (v.done) break; _kgpCorrDone.delete(v.value); }
  }
  fn();
}

function kgpToast(message, ok) {
  let t = document.getElementById("kgp-collect-toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "kgp-collect-toast";
    t.style.cssText = [
      "position:fixed", "right:20px", "bottom:84px", "z-index:2147483647",
      "max-width:280px", "padding:10px 14px", "border-radius:10px",
      "font:13px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "color:#fff", "box-shadow:0 4px 16px rgba(0,0,0,.25)", "white-space:pre-wrap"
    ].join(";");
    document.body.appendChild(t);
  }
  t.style.background = ok ? "#16a34a" : "#dc2626";
  t.textContent = message;
  t.style.opacity = "1";
  clearTimeout(t._hideTimer);
  t._hideTimer = setTimeout(() => { t.style.opacity = "0"; }, 4000);
}

// 결과 토스트(단일 메시지 + 액션 버튼). 신규/중복을 '하나씩' 명확히 — 완료·중복 동시 출력 금지.
let _kgpServerUrl = "";
try { kgpSendMessage({ action: "getSettings" }, (s) => { if (s && s.serverUrl) _kgpServerUrl = s.serverUrl; }); } catch (e) {}
function _kgpEsc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function kgpOpenHistory() {
  const base = _kgpServerUrl || "https://kohganepercentiii.com";
  window.open(base + "/seller/collect/history", "_blank", "noopener");
}
function kgpResultToast(message, ok, actions) {
  // actions: [{label, fn}] — 토스트 안 작은 버튼(이력 열기 / 다시 수집)
  let t = document.getElementById("kgp-collect-toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "kgp-collect-toast";
    t.style.cssText = [
      "position:fixed", "right:20px", "bottom:84px", "z-index:2147483647",
      "max-width:300px", "padding:11px 14px", "border-radius:10px",
      "font:13px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "color:#fff", "box-shadow:0 4px 16px rgba(0,0,0,.25)"
    ].join(";");
    document.body.appendChild(t);
  }
  t.style.background = ok ? "#16a34a" : "#dc2626";
  t.innerHTML = '<div style="white-space:pre-wrap">' + _kgpEsc(message) + "</div>";
  (actions || []).forEach((a, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = a.label;
    btn.style.cssText = "margin:8px 6px 0 0;padding:5px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.6);background:rgba(255,255,255,.14);color:#fff;font:600 12px/1 inherit;cursor:pointer";
    btn.addEventListener("click", (e) => { e.stopPropagation(); try { a.fn(); } catch (err) {} });
    t.appendChild(btn);
  });
  t.style.opacity = "1";
  clearTimeout(t._hideTimer);
  // 액션 버튼이 있으면 오래 유지(클릭 기회), 없으면 4초.
  t._hideTimer = setTimeout(() => { t.style.opacity = "0"; }, (actions && actions.length) ? 9000 : 4000);
}

function setFabState(btn, state) {
  if (state === "loading") {
    btn.dataset.busy = "1";
    btn.style.opacity = "0.7";
    btn.querySelector(".kgp-fab-label").textContent = "수집 중...";
  } else {
    btn.dataset.busy = "";
    btn.style.opacity = "1";
    btn.querySelector(".kgp-fab-label").textContent = "고가수집기";
  }
}

// 고가브릿지 게이트웨이(B) 마크 — 공식 브랜드 자산과 동일(금 아치 + 청록 다리 + 주황 키스톤).
// v21/v22/v38: 옛 마크·이모지 폐기 — 확정 브릿지 마크 단독(어두운 원형 배지 위 스트로크 아치).
// v39 신규 브릿지 마크 — 흰 배경 + 검정 라운드 보더 + 금 게이트 링(아치) + 주황 키스톤 + 청록 데크 2줄 + 금 타이.
// 파비콘/확장/PWA 아이콘과 동일 디자인(단일 소스). 소형 표시에 맞춰 스트로크 굵게.
const KGP_BRIDGE_SVG =
  '<svg width="22" height="22" viewBox="0 0 512 512" aria-hidden="true" style="display:block">' +
  '<rect x="23" y="23" width="466" height="466" rx="112" fill="#ffffff" stroke="#111111" stroke-width="26"/>' +
  '<circle cx="256" cy="205" r="92" fill="none" stroke="#c9a24b" stroke-width="40"/>' +
  '<line x1="67" y1="338" x2="445" y2="338" stroke="#119a8e" stroke-width="40" stroke-linecap="round"/>' +
  '<line x1="67" y1="381" x2="445" y2="381" stroke="#119a8e" stroke-width="40" stroke-linecap="round"/>' +
  '<line x1="130" y1="338" x2="130" y2="381" stroke="#c9a24b" stroke-width="16"/>' +
  '<line x1="256" y1="338" x2="256" y2="381" stroke="#c9a24b" stroke-width="16"/>' +
  '<line x1="382" y1="338" x2="382" y2="381" stroke="#c9a24b" stroke-width="16"/>' +
  '<circle cx="256" cy="113" r="44" fill="#f5821f"/>' +
  '</svg>';

// ---------------------------------------------------------------------------
// v7 공통 유틸 — 위치 기억(localStorage)·드래그·등장모션·수집 누적/축하(따라하기 재미).
//   prefers-reduced-motion 존중. 일부 사이트에서 localStorage가 막힐 수 있어 전부 try/catch.
// ---------------------------------------------------------------------------
const KGP_RM = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
function kgpLSget(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } }
function kgpLSset(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* noop */ } }

function kgpEnsureStyles() {
  if (KGP_RM || document.getElementById("kgp-style")) return;
  const st = document.createElement("style");
  st.id = "kgp-style";
  st.textContent =
    "@keyframes kgpPulse{0%,100%{box-shadow:0 4px 14px rgba(0,0,0,.4),0 0 0 0 rgba(17,154,142,.55)}50%{box-shadow:0 4px 14px rgba(0,0,0,.4),0 0 0 8px rgba(17,154,142,0)}}" +
    "@keyframes kgpStampIn{0%{transform:scale(.4) rotate(-16deg);opacity:0}60%{transform:scale(1.14) rotate(-7deg);opacity:1}100%{transform:scale(1) rotate(-7deg);opacity:1}}";
  (document.head || document.documentElement).appendChild(st);
}

// 드래그로 위치 이동 + 마지막 위치를 localStorage에 기억. opts.handle/opts.ignore 지원.
// 드래그 직후 click을 억제하도록 el._kgpDragged 플래그를 잠깐 세운다.
function kgpMakeDraggable(el, storeKey, opts) {
  opts = opts || {};
  const saved = kgpLSget(storeKey, "");
  if (saved) {
    try {
      const p = JSON.parse(saved);
      if (p && typeof p.left === "number") {
        el.style.left = Math.max(4, Math.min(window.innerWidth - 40, p.left)) + "px";
        el.style.top = Math.max(4, Math.min(window.innerHeight - 40, p.top)) + "px";
        el.style.right = "auto"; el.style.bottom = "auto"; el.style.transform = "none";
      }
    } catch (e) { /* noop */ }
  }
  const handle = opts.handle || el;
  handle.style.cursor = "grab";
  let down = false, moved = false, sx = 0, sy = 0, ox = 0, oy = 0;
  handle.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    if (opts.ignore && e.target.closest && e.target.closest(opts.ignore)) return;
    down = true; moved = false; sx = e.clientX; sy = e.clientY;
    const r = el.getBoundingClientRect(); ox = r.left; oy = r.top;
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!down) return;
    const dx = e.clientX - sx, dy = e.clientY - sy;
    if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
    if (moved) {
      const nl = Math.max(4, Math.min(window.innerWidth - el.offsetWidth - 4, ox + dx));
      const nt = Math.max(4, Math.min(window.innerHeight - el.offsetHeight - 4, oy + dy));
      el.style.left = nl + "px"; el.style.top = nt + "px";
      el.style.right = "auto"; el.style.bottom = "auto"; el.style.transform = "none";
    }
  });
  window.addEventListener("mouseup", () => {
    if (down && moved) {
      const r = el.getBoundingClientRect();
      kgpLSset(storeKey, JSON.stringify({ left: Math.round(r.left), top: Math.round(r.top) }));
      el._kgpDragged = true;
      setTimeout(() => { el._kgpDragged = false; }, 60);
    }
    down = false;
  });
  kgpRegisterFixed(el);   // v15: 줌/리사이즈 시 화면 안으로 재보정
}

// v15 P0: 페이지 줌(Ctrl+휠)·창 리사이즈 시 고정 오버레이가 화면 밖으로 나가거나
// 가장자리에서 겹치지 않도록 뷰포트 안으로 다시 끌어들인다. (left/top으로 배치된 요소만 보정 —
// right/bottom 앵커는 본래 뷰포트 상대라 안전.) 카운트업/배지 등 일회성 요소는 등록하지 않는다.
const KGP_FIXED_ELS = [];
function kgpRegisterFixed(el) { if (el && KGP_FIXED_ELS.indexOf(el) < 0) KGP_FIXED_ELS.push(el); }
function kgpClampFixed(el) {
  if (!el || !el.isConnected) return;
  if (!el.style.left || el.style.left === "auto") return;
  const w = el.offsetWidth, h = el.offsetHeight;
  const l = parseFloat(el.style.left) || 0, t = parseFloat(el.style.top) || 0;
  el.style.left = Math.max(4, Math.min(Math.max(4, window.innerWidth - w - 4), l)) + "px";
  el.style.top = Math.max(4, Math.min(Math.max(4, window.innerHeight - h - 4), t)) + "px";
}
let _kgpResizeT = null;
function kgpOnViewportChange() {
  if (_kgpResizeT) return;
  _kgpResizeT = setTimeout(() => {
    _kgpResizeT = null;
    for (let i = KGP_FIXED_ELS.length - 1; i >= 0; i--) {
      if (!KGP_FIXED_ELS[i].isConnected) { KGP_FIXED_ELS.splice(i, 1); continue; }
      kgpClampFixed(KGP_FIXED_ELS[i]);
    }
  }, 120);
}
if (!window.__kgpViewportBound) {
  window.addEventListener("resize", kgpOnViewportChange);
  window.__kgpViewportBound = true;
}

// v64 STEP4: 벌크바 스크롤 추적 sticky 하드닝. 바는 position:fixed(뷰포트 상단 고정)라 원래 스크롤을
//   따라오지만, 일부 사이트는 <html>/<body> 조상에 transform/filter를 걸어 position:fixed의 기준을
//   바꿔 바가 콘텐츠와 함께 스크롤돼 버린다(고전적 'fixed inside transform' 버그). 스크롤 시 바의 실제
//   top이 의도한 값에서 밀렸으면 translateY로 보정해 항상 뷰포트 상단에 고정한다. 사용자가 드래그해
//   위치를 저장했으면(kgp_bar_pos) 존중(자동 재핀 안 함). z-index는 최상위(2147483647)라 사이트 헤더 위.
const _KGP_BAR_TOP = 12;
let _kgpBarPinT = null;
function _kgpKeepBarPinned() {
  const bar = document.getElementById(KGP_TOOLBAR_ID);
  if (!bar || !bar.isConnected) return;
  if (kgpLSget("kgp_bar_pos", "")) return;          // 사용자가 옮긴 위치는 존중
  bar.style.transform = "translateX(-50%)";          // 기준 복원 후 실제 top 측정
  let top;
  try { top = bar.getBoundingClientRect().top; } catch (e) { return; }
  const drift = top - _KGP_BAR_TOP;                   // 변형 조상 때문에 밀린 양(정상 사이트=≈0)
  if (Math.abs(drift) > 1) bar.style.transform = "translateX(-50%) translateY(" + (-drift) + "px)";
}
function _kgpBarScroll() {
  if (_kgpBarPinT) return;                            // 스크롤 스로틀(리플로우 최소화)
  _kgpBarPinT = setTimeout(() => { _kgpBarPinT = null; _kgpKeepBarPinned(); }, 120);
}
if (!window.__kgpBarScrollBound) {
  window.addEventListener("scroll", _kgpBarScroll, { passive: true });
  window.__kgpBarScrollBound = true;
}

// v45 P4·P5: 지속 오버레이(FAB·벌크바·구석 배지)를 <body>가 아니라 **documentElement(<html>) 직속**에
//   붙인다. 이유: ①SPA가 <body> 전체를 갈아끼워도 오버레이가 살아남음(P5 깜빡임 방지) ②<body>에 걸린
//   transform/filter가 position:fixed 기준을 바꿔 '좌상단 처박힘'을 유발하는 것을 회피(P4 상단중앙 고정).
//   (transient 토스트/도장은 짧게 살다 사라져 <body>여도 무방.)
function _kgpMount(el) {
  (document.documentElement || document.body).appendChild(el);
}

// 수집 누적 카운트 + 마일스톤 축하(실제 성공 시에만 호출).
function kgpBumpCount(n) {
  let c = parseInt(kgpLSget("kgp_collect_count", "0"), 10) || 0;
  c += (n || 0); kgpLSset("kgp_collect_count", String(c));
  return c;
}
const KGP_WIT = [
  "오늘도 한 건 +1", "담았습니다. 다음 상품 가시죠", "착! 도장 쾅",
  "수집 완료, 다음 상품으로", "마진은 셀러님 몫",
];
function kgpCelebrate(added, silent) {
  // silent=true면 축하 애니메이션(스탬프)만 — 토스트는 호출부가 '하나' 띄운다(완료/중복 동시출력 금지).
  added = Math.max(1, added || 1);
  const total = kgpBumpCount(added);
  const prev = total - added;
  const milestones = [10, 50, 100, 300, 500, 1000];
  let milestone = 0;
  for (const m of milestones) { if (prev < m && total >= m) milestone = m; }
  if (KGP_RM) {
    if (!silent) kgpToast(`수집 완료 · 누적 ${total}건` + (milestone ? `\n${milestone}건 달성!` : ""), true);
    return total;
  }
  kgpEnsureStyles();
  const ov = document.createElement("div");
  ov.style.cssText = "position:fixed;right:24px;bottom:96px;z-index:2147483647;pointer-events:none;display:flex;flex-direction:column;align-items:flex-end;gap:6px";
  const stamp = document.createElement("div");
  stamp.style.cssText = "display:flex;align-items:center;gap:8px;padding:10px 16px;border-radius:14px;background:#1a1714;border:2px solid #c9a24b;color:#f5efe3;font:700 14px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.45);animation:kgpStampIn .5s ease-out both";
  stamp.innerHTML = '<span style="display:inline-flex;width:22px;height:22px;align-items:center;justify-content:center">' + KGP_BRIDGE_SVG + '</span><span>' + KGP_WIT[Math.floor(Math.random() * KGP_WIT.length)] + "</span>";
  ov.appendChild(stamp);
  const counter = document.createElement("div");
  counter.style.cssText = "padding:5px 12px;border-radius:999px;background:#119a8e;color:#fff;font:700 12px/1 -apple-system,sans-serif;animation:kgpStampIn .5s ease-out both";
  ov.appendChild(counter);
  if (milestone) {
    const badge = document.createElement("div");
    badge.style.cssText = "padding:6px 14px;border-radius:999px;background:#c9a24b;color:#1a1714;font:800 13px/1 -apple-system,sans-serif;animation:kgpStampIn .55s ease-out both";
    badge.textContent = milestone + "건 달성!";
    ov.appendChild(badge);
  }
  document.body.appendChild(ov);
  const t0 = performance.now(), dur = 650;
  (function tick(now) {
    const p = Math.min(1, (now - t0) / dur);
    counter.textContent = "누적 " + Math.round(prev + (total - prev) * p) + "건";
    if (p < 1) requestAnimationFrame(tick);
  })(t0);
  setTimeout(() => { ov.style.transition = "opacity .4s"; ov.style.opacity = "0"; setTimeout(() => ov.remove(), 420); }, milestone ? 3400 : 2300);
  return total;
}

// v47 STEP4: MAIN world 추출 결과 병합 — 격리월드(content_script)가 못 읽는 페이지 live 전역
//   (Temu 등 XHR로 렌더 후 채우는 초기 상태)을 MAIN world(kgp-main.js)에서 읽어 넘긴 meta와 병합.
//   비어 있는 필드는 채우고, 배열(이미지·옵션·리뷰·상세)은 더 완전한 쪽 채택. 응답 없으면 격리월드만(정직).
function kgpMergeMeta(base, extra) {
  if (!extra || typeof extra !== "object") return base;
  const out = Object.assign({}, base);
  const empty = (v) => v == null || v === "" || (Array.isArray(v) && v.length === 0);
  ["title", "price", "currency", "description", "rating", "review_count", "price_status", "source"].forEach((k) => {
    if (empty(out[k]) && !empty(extra[k])) out[k] = extra[k];
  });
  ["images", "gallery_images", "detail_images", "options", "skus", "reviews", "detail_specs"].forEach((k) => {
    const a = Array.isArray(out[k]) ? out[k] : [], b = Array.isArray(extra[k]) ? extra[k] : [];
    if (b.length > a.length) out[k] = b;
  });
  if (empty(out.image) && out.images && out.images.length) out.image = out.images[0];
  if (empty(out.thumbnail) && out.images && out.images.length) out.thumbnail = out.images[0];
  out.detail_fold = !!(out.detail_fold || extra.detail_fold);   // v57 STEP3: 어느 월드든 접힘 감지 시 표기
  if (!empty(out.price) && Array.isArray(out.images) && out.images.length) out.partial = false;  // 병합으로 핵심 확보
  // field_sources 병합: MAIN이 json 준 필드는 json 우선(수집 로그가 실제 소스 표기).
  if (extra.field_sources) {
    out.field_sources = Object.assign({}, out.field_sources || {});
    for (const fk in extra.field_sources) {
      // MAIN(Tier1/JSON)이 준 소스는 격리월드(DOM/none) 위에 우선(실제 소스 표기).
      if (extra.field_sources[fk] === "tier1" || extra.field_sources[fk] === "json") out.field_sources[fk] = extra.field_sources[fk];
      else if (!out.field_sources[fk] || out.field_sources[fk] === "none") out.field_sources[fk] = extra.field_sources[fk];
    }
  }
  return out;
}
function kgpExtractMerged(cb) {
  let isolated;
  try { isolated = extractProductMeta(); }
  catch (e) { isolated = { url: location.href, partial: true, warnings: ["추출 실패"] }; }
  let done = false;
  const reqId = "kgpq_" + Date.now() + "_" + Math.floor(Math.random() * 1e6);
  function onMsg(e) {
    if (e.source !== window || !e.data || e.data.__kgpRes !== reqId) return;
    window.removeEventListener("message", onMsg);
    if (done) return; done = true;
    const merged = kgpMergeMeta(isolated, e.data.meta);
    // v55 STEP1: MAIN meta의 Tier1 채택 URL 전파(sources=tier1:{URL}).
    try { if (e.data.meta && e.data.meta.tier1_source && !merged.tier1_source) merged.tier1_source = e.data.meta.tier1_source; } catch (_) {}
    // v55 STEP1 / v56 STEP4: Tier1 자동 진단 — 기여했으면 확인, 아니면 원인 1줄(무음 금지).
    //   v56: 진단 결과를 payload에 동봉(tier1_diag) → 서버 저장·드로어 표기(콘솔 안 봐도 최종 판정 확인).
    try {
      var diag = e.data.diag || {};
      var usedTier1 = !!(merged.tier1_source) || (merged.field_sources && merged.field_sources.price === "tier1");
      var cause = "";
      if (usedTier1) {
        console.log("%c[고가수집기] Tier1 동작 ✓ — 채택 " + (merged.tier1_source || "(API 응답)") + " (최고점 " + (diag.topScore || 0) + "/4)", "color:#119a8e;font-weight:bold");
        try { if (diag.topUrl) chrome.storage && chrome.storage.local && chrome.storage.local.set({ ["kgp_api_pat:" + location.hostname]: diag.topUrl }); } catch (_) {}
      } else {
        cause = !diag.netBound ? "인터셉터 미주입(MAIN world 로드 실패 — 확장 재로딩 필요)"
          // v62 STEP2: 내 goods_id 응답 미포착 — 다른 상품 응답 오채택 방지 위해 Tier2 폴백(정직 안내).
          : (diag.pageGoodsId && diag.mismatch ? "이 상품의 API 응답 미포착(goods_id " + diag.pageGoodsId + ") — 페이지 새로고침 후 재시도"
          : (diag.captured === 0 ? "매치 0건(상품 API 응답을 아직 못 잡음 — 페이지 새로고침 후 다시 수집)"
          : "시그니처 미달(최고점 " + (diag.topScore || 0) + "/4 — 팝업 '자가진단 모드'로 후보 표 확인)"));
        console.warn("%c[고가수집기] Tier1 무동작 → DOM 폴백 사용. 원인: " + cause, "color:#c2503c;font-weight:bold");
      }
      merged.tier1_diag = { used: usedTier1, netBound: !!diag.netBound, captured: diag.captured || 0, topScore: diag.topScore || 0, source: merged.tier1_source || "", cause: cause, page_goods_id: diag.pageGoodsId || "", goods_matched: !!diag.matched };
      console.log("[고가수집기] MAIN world 병합 — 이미지 " + ((isolated.images || []).length) + "→" + ((merged.images || []).length)
        + ", 가격 " + (isolated.price || "-") + "→" + (merged.price || "-"));
    } catch (_) {}
    cb(merged);
  }
  window.addEventListener("message", onMsg, false);
  try { window.postMessage({ __kgpReq: reqId }, "*"); } catch (e) {}
  setTimeout(() => {
    if (done) return; done = true;
    window.removeEventListener("message", onMsg);
    try { console.warn("%c[고가수집기] Tier1 무동작 → DOM 폴백. 원인: MAIN world 미응답(kgp-main 미로드/타임아웃 — 확장 재로딩 권장)", "color:#c2503c;font-weight:bold"); } catch (_) {}
    cb(isolated);   // MAIN world 미응답(비지원 크롬/타임아웃) → 격리월드 추출만(정직 폴백)
  }, 900);
}

function handleFabClick(btn, opts) {
  opts = opts || {};
  if (btn._kgpDragged || btn.dataset.busy) return;
  setFabState(btn, "loading");
  // v57 STEP3: 상세 '더보기' 접힘을 먼저 펼친 뒤 추출(테무 상세이미지 전량) — 접힘 없으면 즉시 진행(지연 0).
  var _reveal = (typeof window.kgpRevealDetailFolds === "function")
    ? window.kgpRevealDetailFolds : function (cb) { cb && cb(); };
  _reveal(function () {
  kgpExtractMerged(function (meta) {
  const corr = kgpNewCorr();
  meta.corr_id = corr;                    // 서버 로깅·알럿 dedupe 기준
  if (opts.force) meta.force = true;      // 다시 수집(덮어쓰기) — 가격·이미지 갱신
  // v49 STEP4 포렌식: 전송 직전 클라 추출 요약(어느 필드가 비었는지 콘솔에서 즉시 확인).
  try {
    console.log("[고가수집기] 전송요약", {
      price: meta.price, currency: meta.currency, images: (meta.images || []).length,
      desc: (meta.description || "").length + "자", options: (meta.options || []).length,
      reviews: (meta.reviews || []).length, rating: meta.rating, source: meta.source, partial: meta.partial,
    });
  } catch (e) { /* noop */ }
  kgpSendMessage({ action: "collect", meta }, (resp) => {
    setFabState(btn, "idle");
    if (!resp || resp.ok !== true) {
      kgpAlertOnce(corr, () => {          // 실패 알럿도 건당 1회
        if (resp && resp.authRequired) {
          kgpToast("확장 옵션에서 토큰을 다시 설정해 주세요.\n(토큰이 만료됐거나 삭제됐어요)", false);
        } else {
          var _st = resp && resp.httpStatus ? ` (HTTP ${resp.httpStatus})` : "";
          kgpToast(((resp && resp.error) || "수집 실패") + _st, false);
        }
      });
      return;
    }
    // 다시 수집(덮어쓰기) 결과 — 가격·이미지 갱신됨(단일 메시지).
    if (resp.updated === true) {
      kgpAlertOnce(corr, () => kgpResultToast("다시 수집 완료 — 가격·이미지를 갱신했어요", true,
        [{ label: "이력 열기", fn: kgpOpenHistory }]));
      return;
    }
    // 중복 — '이미 수집한 상품' 하나만(완료 토스트와 동시 출력 금지) + '다시 수집(덮어쓰기)'.
    if (resp.duplicate === true) {
      kgpAlertOnce(corr, () => kgpResultToast("이미 수집한 상품 — 이력에서 확인", true, [
        { label: "이력 열기", fn: kgpOpenHistory },
        { label: "다시 수집(덮어쓰기)", fn: () => handleFabClick(btn, { force: true }) },
      ]));
      return;
    }
    // v47/v49 STEP2·5: 서버 필드 상태(성공/부분/실패)로 정직 표기 — 무음 실패·가짜 성공 금지.
    //   서버 field_status가 단일 소스. 없으면(구서버) 클라 meta.partial 폴백.
    var fs = resp.field_status || null;
    // v49 STEP5: 실패(핵심 3 전부 미확보) — 원인 명시, 축하 없음.
    if (fs && fs.status === "실패") {
      try { console.warn("[고가수집기] 수집 실패 —", fs.cause || "핵심 정보 미확보"); } catch (e) {}
      kgpAlertOnce(corr, () => kgpResultToast(
        "수집 실패 — " + (fs.cause || "핵심 정보(제목·가격·이미지)를 못 읽었어요") + "\n드로어에서 직접 입력하거나 다시 시도하세요",
        false, [{ label: "이력 열기", fn: kgpOpenHistory }]));
      return;
    }
    var isPartial = fs ? (fs.status === "부분") : !!(meta && meta.partial);
    if (isPartial) {
      var _ml = fs && ((fs.missing_short && fs.missing_short.length) ? fs.missing_short : fs.missing);
      var miss = (_ml && _ml.length) ? _ml.join("·") : "";
      try { console.warn("[고가수집기] 부분 수집 — 누락:", (fs && fs.missing) || (meta && meta.warnings) || []); } catch (e) {}
      var _msg = miss
        ? ("부분 수집 — " + miss + " 누락 (" + (fs.filled) + "/" + (fs.total) + " 필드)\n드로어에서 확인·보완하세요")
        : "부분 수집 — 페이지에서 정보를 충분히 못 읽었어요.\n드로어에서 가격·이미지를 확인·보완하세요";
      kgpAlertOnce(corr, () => kgpResultToast(_msg, false, [{ label: "이력 열기", fn: kgpOpenHistory }]));
      return;
    }
    // 성공 — '수집 완료(N/7 필드)' 하나만 + 축하 스탬프(토스트는 하나). 가격 경고 있으면 함께 안내.
    kgpAlertOnce(corr, () => {
      var _warn = (meta && Array.isArray(meta.warnings) && meta.warnings.length) ? "\n⚠ " + meta.warnings[0] : "";
      var _cnt = fs ? (" (" + fs.filled + "/" + fs.total + " 필드)") : "";
      // v58 STEP3: 확장 버전 스탬프(죽은 버전 혼동 차단) — 매니페스트 버전 표기.
      var _ev = "";
      try { _ev = " · ext v" + (chrome.runtime.getManifest && chrome.runtime.getManifest().version || ""); } catch (e) {}
      kgpCelebrate(1, true);           // 스탬프만(silent) — 토스트는 아래 하나
      kgpResultToast("수집 완료" + _cnt + _ev + " — 이력에서 확인" + _warn, true, [{ label: "이력 열기", fn: kgpOpenHistory }]);
    });
  });
  });   // v47 STEP4: kgpExtractMerged 콜백 닫기
  });   // v57 STEP3: kgpRevealDetailFolds 콜백 닫기
}

function injectCollectButton() {
  // v16 P1: FAB off면 표시 안 함 — 단, v17: 앱에서 띄운 진입 세션이면 강제 노출.
  if (!KGP_FAB_ENABLED && !kgpEntrySession()) { kgpRemoveFab(); return; }
  if (!kgpHostAllowed() && !kgpEntrySession()) return;   // 지정 소싱처 또는 앱 진입 세션(v10/v17)
  if (document.getElementById(KGP_BTN_ID)) return;
  if (window.top !== window.self) return;       // iframe 안에서는 표시 안 함
  if (!document.body) return;
  // v38 #4: 지정 소싱처(또는 앱 진입)에서는 상품 페이지 휴리스틱과 무관하게 '항상' 노출.
  //   기존엔 looksLikeProductPage/디테일 URL 가드 때문에 SPA(Temu)·카테고리·검색·홈에서 버튼이 안 떠
  //   "어떤 창은 안 뜸"이 발생. 이미 host 게이트(위)로 소싱처에 한정되므로 추가 가드는 제거한다.

  const btn = document.createElement("button");
  btn.id = KGP_BTN_ID;
  btn.type = "button";
  btn.innerHTML =
    '<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;' +
    'background:transparent;border:0;flex-shrink:0">' + KGP_BRIDGE_SVG + '</span>' +
    '<span style="display:flex;flex-direction:column;align-items:flex-start;line-height:1.12">' +
    '<span class="kgp-fab-label" style="font-weight:700;font-size:14px;color:#f5efe3">고가수집기</span>' +
    '<span style="font-size:10px;color:#c9a24b;font-family:Georgia,\'Times New Roman\',serif">번역까지 한 번에</span>' +
    '</span>';
  btn.title = "고가브릿지로 수집 (한국어 번역 포함)";
  // 고가브릿지 토큰: 먹 매트 pill + 금 얇은 링 + 청록 미세 악센트. (네이비+주황 폐기, v4)
  // 위치: 우측 '중앙'(v7) — 콘텐츠 안 가리게. 드래그로 옮기면 위치 기억(kgp_fab_pos).
  btn.style.cssText = [
    "position:fixed", "right:16px", "top:calc(50% - 24px)", "z-index:2147483647",
    "display:flex", "align-items:center", "gap:10px", "max-width:min(82vw,300px)", "box-sizing:border-box",
    "padding:9px 16px 9px 10px", "border:1px solid #c9a24b", "border-radius:999px",
    "background:#1a1714", "color:#f5efe3",
    "font:14px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    "cursor:pointer", "box-shadow:0 6px 20px rgba(0,0,0,.4),0 0 0 4px rgba(17,154,142,.10)",
    "transition:transform .12s,opacity .12s,box-shadow .12s"
  ].join(";");
  btn.addEventListener("mouseenter", () => {
    btn.style.transform = "translateY(-2px)";
    btn.style.boxShadow = "0 10px 26px rgba(0,0,0,.5),0 0 0 5px rgba(17,154,142,.18)";
  });
  btn.addEventListener("mouseleave", () => {
    btn.style.transform = "none";
    btn.style.boxShadow = "0 6px 20px rgba(0,0,0,.4),0 0 0 4px rgba(17,154,142,.10)";
  });
  btn.addEventListener("click", () => handleFabClick(btn));
  _kgpMount(btn);                            // v45 P5: <html> 직속(본문 재렌더에도 상시 표시)
  kgpMakeDraggable(btn, "kgp_fab_pos");      // 드래그 이동 + 위치 기억(v7)

  // 처음 등장 시 한 번 살짝 강조(인지성↑, 과하지 않게). reduced-motion이면 생략.
  if (!KGP_RM) {
    btn.animate(
      [{ transform: "scale(1)" }, { transform: "scale(1.06)" }, { transform: "scale(1)" }],
      { duration: 600, iterations: 2, easing: "ease-in-out" }
    );
  }
}

// ---------------------------------------------------------------------------
// 리스팅/검색 페이지 다중 상품 수집 (Phase 221)
// 상품 카드마다 '수집' 체크 배지 + 상단 툴바(전체선택/선택수집/전체수집).
// 확장 background가 토큰으로 서버에 전송하므로 페이지 CSP 영향 없음.
// ---------------------------------------------------------------------------
const KGP_TOOLBAR_ID = "kgp-listing-toolbar";
const KGP_SELECTED = new Set();   // 선택된 상품 url 집합(재스캔에도 유지)
let _kgpCards = [];
let _kgpCardByUrl = {};           // url → 카드 데이터(el 포함) — 재스캔 시 '병합'(절대 비우지 않음)
let _kgpScannedCount = 0;         // 마지막 스캔에서 본 후보 카드 총수(상품 M개 / 전체 N개 표기용)
let _kgpClosed = false;           // 사용자가 툴바를 닫았으면 자동 재생성 안 함(같은 URL 동안)
// v65 STEP2: 제외 사유별 분해 카운트('제외 (광고 등)' 뭉뚱그림 금지). 스캔마다 초기화.
//   ad=광고(스폰서, 태깅만·전체선택 제외) · region=비상품영역(추천/푸터) · parse=카드 파싱 실패(제목/ASIN 등)
//   · url=URL 추출 실패(앵커 없음) · dup=중복(같은 상품).
let _kgpExcl = { ad: 0, region: 0, parse: 0, url: 0, dup: 0, reco: 0 };
function _kgpExclReset() { _kgpExcl = { ad: 0, region: 0, parse: 0, url: 0, dup: 0, reco: 0 }; }

// v64 STEP2 / v67 STEP1: 전체선택/전체수집 대상 — 기본은 **메인 그리드 실상품만**(추천·광고 제외).
//   '추천 포함'(kgp_incl_reco)·'광고 포함'(kgp_incl_ads) 토글로 확장. 버튼은 전 타일에 부착돼 개별 수집은 항상 가능.
function _kgpInclAds() { return kgpLSget("kgp_incl_ads", "0") === "1"; }
function _kgpInclReco() { return kgpLSget("kgp_incl_reco", "0") === "1"; }
function _kgpSelectableUrls() {
  const inclAds = _kgpInclAds(), inclReco = _kgpInclReco();
  return Object.keys(_kgpCardByUrl).filter((u) => {
    const c = _kgpCardByUrl[u];
    if (c && c.sponsored && !inclAds) return false;
    if (c && c.region === "reco" && !inclReco) return false;
    return true;
  });
}
function _kgpAdCount() {
  return Object.keys(_kgpCardByUrl).filter((u) => _kgpCardByUrl[u] && _kgpCardByUrl[u].sponsored).length;
}
function _kgpRecoCount() {
  return Object.keys(_kgpCardByUrl).filter((u) => _kgpCardByUrl[u] && _kgpCardByUrl[u].region === "reco").length;
}
function _kgpMainCount() {
  return Object.keys(_kgpCardByUrl).filter((u) => { const c = _kgpCardByUrl[u]; return c && c.region !== "reco" && !c.sponsored; }).length;
}

function _kgpPrice(text) {
  const m = String(text || "").match(/([\d][\d.,]{1,})\s*원|(?:₩|\$|¥|€|£)\s*([\d][\d.,]{1,})/);
  if (!m) return { price: "", currency: "" };
  const raw = (m[1] || m[2] || "").replace(/,/g, "");
  let cur = "";
  if (/원|₩/.test(m[0])) cur = "KRW";
  else if (/\$/.test(m[0])) cur = "USD";
  else if (/¥/.test(m[0])) cur = "JPY";
  else if (/€/.test(m[0])) cur = "EUR";
  else if (/£/.test(m[0])) cur = "GBP";
  return { price: raw, currency: cur };
}

// ---------------------------------------------------------------------------
// v10 P0 — 지정 소싱처에서만 노출 (아무 사이트 ✕).
//   기본셋(ON) + 사용자 지정 도메인(옵션에서 추가/삭제). 비매치 사이트엔 아무것도 안 그림.
// ---------------------------------------------------------------------------
const KGP_DEFAULT_SOURCES = [
  { id: "taobao", label: "타오바오", test: (h) => /(^|\.)taobao\.com$/.test(h) },
  { id: "tmall", label: "티몰", test: (h) => /(^|\.)tmall\.com$/.test(h) },
  { id: "1688", label: "1688", test: (h) => /(^|\.)1688\.com$/.test(h) },
  { id: "temu", label: "테무", test: (h) => /(^|\.)temu\.com$/.test(h) },
  { id: "amazon", label: "아마존", test: (h) => /(^|\.)amazon\.[a-z.]+$/.test(h) },
  { id: "aliexpress", label: "알리익스프레스", test: (h) => /(^|\.)aliexpress\.(com|us)$/.test(h) },
  // v15: 대형 크로스보더 마켓 디폴트 확장(도메인 검증된 것만). 니치/브랜드(요시다카반 등)는 유저 추가 전용.
  { id: "iherb", label: "아이허브", test: (h) => /(^|\.)iherb\.com$/.test(h) },
  { id: "dhgate", label: "DHgate", test: (h) => /(^|\.)dhgate\.com$/.test(h) },
  { id: "qoo10", label: "큐텐", test: (h) => /(^|\.)qoo10\.[a-z.]+$/.test(h) },
  { id: "mercari", label: "메루카리", test: (h) => /(^|\.)mercari\.com$/.test(h) },
  { id: "rakuten", label: "라쿠텐(Rakuten Fashion 포함)", test: (h) => /(^|\.)rakuten\.(co\.jp|com)$/.test(h) },
  // v42 E-2: 오너 지정 어댑터 도메인 상시 노출(야후쇼핑 재팬·요시다카반).
  { id: "yahoo", label: "야후쇼핑(재팬)", test: (h) => /(shopping\.yahoo\.co\.jp|paypaymall\.yahoo\.co\.jp)$/.test(h) },
  { id: "yoshida", label: "요시다카반", test: (h) => /(^|\.)yoshidakaban\.com$/.test(h) },
];
let KGP_SOURCES = null;   // chrome.storage의 사용자 설정 { defaults:{id:bool}, custom:[{host,on}] }
let KGP_FAB_ENABLED = true;   // v16 P1: 인페이지 수집 버튼(FAB) on/off (popup 토글, 기본 ON)

// v17 P0: 우리 앱에서 띄운 마켓/소싱처 진입이면(URL 마커 kgpsrc=app) 그 탭 세션 동안 수집기를
// 강제 노출한다(유저가 FAB를 off 했어도 진입 세션엔 보장). 마커는 sessionStorage로 SPA 이동에도 유지.
function kgpEntrySession() {
  try {
    if (/[?&]kgpsrc=app\b/.test(location.search || "")) sessionStorage.setItem("kgp_entry", "1");
    return sessionStorage.getItem("kgp_entry") === "1";
  } catch (e) { return false; }
}

function _kgpHostMatch(host, domain) {
  domain = String(domain || "").toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/^www\./, "");
  if (!domain) return false;
  return host === domain || host.endsWith("." + domain);
}

// 현재 사이트가 '지정 소싱처'인가? (기본셋 토글 + 커스텀 도메인)
function kgpHostAllowed() {
  const host = (location.hostname || "").toLowerCase();
  if (!host) return false;
  const s = KGP_SOURCES || {};
  const defs = s.defaults || {};
  for (const src of KGP_DEFAULT_SOURCES) {
    if (defs[src.id] !== false && src.test(host)) return true;   // 기본 ON(명시적 false만 끔)
  }
  for (const c of (s.custom || [])) {
    if (c && c.on !== false && _kgpHostMatch(host, c.host)) return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// v10 P0 — 실제 제품만 감지. 사이트 어댑터(정확) + 엄격 휴리스틱(폴백).
//   썸네일·추천레일·"본 적 있음"·캐러셀·푸터·광고 제외. "N개 발견" = 실제 수집 가능 수.
// ---------------------------------------------------------------------------
// 카드가 추천/푸터/캐러셀/광고 같은 '제품 그리드 아님' 영역에 속하면 제외.
// v64 STEP2: 구조적 비상품 영역(추천/캐러셀/푸터)과 광고 영역을 분리.
//   opts.allowAds=true면 sponsor/ad/promo/deal 토큰으로 '영역 제외'하지 않는다 — 아마존
//   스폰서는 실상품이므로 명시 신호(_kgpAmazonSponsored)로 '태깅'만 하고 카드는 살린다
//   (과잉 휴리스틱 제외 = 66중 48 오제외의 근본 원인 제거). 구조적 비상품은 여전히 제외.
function _kgpInBadRegion(el, opts) {
  opts = opts || {};
  const structRe = /(footer|recommend|related|carousel|slider|viewed|recently|history|also-?viewed|also-?bought|similar|banner|rcmd)/;
  const adRe = /(sponsor|advert|\bads?\b|promo|deal-?strip)/;
  let n = el;
  for (let i = 0; n && i < 9; i++, n = n.parentElement) {
    let cls = "";
    try { cls = (typeof n.className === "string" ? n.className : (n.getAttribute && n.getAttribute("class")) || ""); } catch (e) { cls = ""; }
    const tag = (n.tagName || "").toLowerCase();
    const meta = ((n.id || "") + " " + cls + " " + ((n.getAttribute && (n.getAttribute("aria-label") || n.getAttribute("data-component-type"))) || "")).toLowerCase();
    if (tag === "footer" || tag === "header" || tag === "nav") return true;
    // v67 STEP1: structuralOnly면 추천/캐러셀은 '제외' 안 함(전 타일 버튼 부착 — region 태깅으로 카운트만 구분).
    if (!opts.structuralOnly && structRe.test(meta)) return true;
    if (!opts.allowAds && adRe.test(meta)) return true;   // 광고 영역 제외(아마존은 allowAds로 유지)
  }
  return false;
}

// v67 STEP1: 카드가 추천/캐러셀/frequently-viewed 영역인지(제외 아님 — region='reco' 태그용).
function _kgpIsRecoRegion(el) {
  const recoRe = /(recommend|related|carousel|slider|viewed|recently|also-?viewed|also-?bought|similar|frequently|rcmd|sponsored-products|p13n|cross-?sell|up-?sell|you-?may)/i;
  let n = el;
  for (let i = 0; n && i < 9; i++, n = n.parentElement) {
    let cls = "";
    try { cls = (typeof n.className === "string" ? n.className : (n.getAttribute && n.getAttribute("class")) || ""); } catch (e) { cls = ""; }
    const meta = ((n.id || "") + " " + cls + " " + ((n.getAttribute && (n.getAttribute("aria-label") || n.getAttribute("data-component-type"))) || "")).toLowerCase();
    if (recoRe.test(meta)) return true;
  }
  return false;
}

// v41 X-1: 리스팅 카드의 대표 이미지가 lazy-load placeholder(빈/공용 src)라, 스크롤 전엔
// 여러 상품이 같은 placeholder src를 공유 → '상품 A에 상품 B 이미지'가 붙는 문제.
// 실제 이미지 소스(currentSrc·data-src·srcset 등)를 우선 선택해 상품별 '자기 이미지'로 귀속.
function _kgpBestImg(img) {
  if (!img) return "";
  const _isPlaceholder = (s) => !s || s.indexOf("data:") === 0 ||
    /(1x1|blank|spacer|placeholder|loading|transparent\.|pixel|lazy(load)?[-_.]|grey\.gif|gray\.gif|s\.gif)/i.test(s);
  const cand = [
    img.currentSrc || "",
    img.getAttribute("data-src") || "",
    img.getAttribute("data-original") || "",
    img.getAttribute("data-lazy") || "",
    img.getAttribute("data-lazy-src") || "",
  ];
  const ss = img.getAttribute("srcset") || img.getAttribute("data-srcset") || "";
  if (ss) {
    const parts = ss.split(",");
    cand.push((parts[parts.length - 1] || "").trim().split(" ")[0]);
  }
  cand.push(img.src || "");   // 마지막 폴백(placeholder일 수 있음)
  for (const c of cand) { if (c && !_isPlaceholder(c)) return c; }
  return img.currentSrc || img.src || "";   // 전부 placeholder면 그거라도(정직: 서버가 이후 보강/빈값)
}

// 스폰서(광고) 카드 판별 — 클래스/라벨 기반(보수적, 오탐 최소).
function _kgpAmazonSponsored(el) {
  try {
    if (el.querySelector('.s-sponsored-label-text, .puis-sponsored-label-text, [data-component-type="sp-sponsored-result"], [aria-label*="Sponsored"], [data-component-type="s-sponsored-label-info-icon"]')) {
      return true;
    }
  } catch (e) { /* noop */ }
  return false;
}

// 아마존 검색결과 어댑터 — 실제 '상품' 카드(유효 ASIN + 상품URL). 뮤직/앱/미디어 위젯 제외.
// v25 P0: data-asin(10자) 필수로 비-상품 위젯 제외.
// v45 P3: '버튼이 카드마다 있다 없다' 해소 — 셀렉터를 s-search-result만이 아니라 **유효 data-asin을
//   가진 카드 전부**로 넓히고(레이아웃 변형·스폰서 컨테이너 커버), **스폰서(광고) 상품도 포함**한다
//   (유효 ASIN=실제 소싱 가능 상품). 비-상품 미디어(ASIN 없음)는 자연 제외 = v25 '광고·미디어 제외' 의도 유지.
function _kgpAmazonCards() {
  const cards = [], seen = {};
  // v67 STEP1: **전 타일 버튼(대형 셀러툴 패리티)** — 메인 그리드뿐 아니라 추천 캐러셀·frequently-viewed
  //   배너 타일에도 버튼 부착. 메인/추천 구분은 region 태그로(카운트 표시에만). 구조적 비상품(footer/nav)만 제외.
  const mainSlot = (document.querySelector && document.querySelector('.s-main-slot, [data-component-type="s-search-results"]')) || null;
  const set = new Set();
  document.querySelectorAll('[data-component-type="s-search-result"], div[data-asin]:not([data-asin=""])')
    .forEach((e) => set.add(e));
  const all = Array.from(set);
  _kgpScannedCount = all.length;                          // '전체 N개'(메인+추천 상품/비상품 합)
  all.forEach((el) => {
    try {
      // v67: 구조적 비상품(footer/nav)만 제외 — 추천/캐러셀은 버튼 부착(region='reco' 태깅).
      if (_kgpInBadRegion(el, { allowAds: true, structuralOnly: true })) { _kgpExcl.region++; return; }
      const asin = (el.getAttribute("data-asin") || "").trim();
      if (!/^[A-Z0-9]{10}$/.test(asin)) { _kgpExcl.parse++; return; }   // v65 STEP2: 유효 ASIN 없음=파싱 실패
      const parentAsin = el.parentElement && el.parentElement.closest('[data-asin]:not([data-asin=""])');
      if (parentAsin && parentAsin !== el && (parentAsin.getAttribute("data-asin") || "").trim() === asin) { _kgpExcl.dup++; return; }
      const sponsored = _kgpAmazonSponsored(el);           // v45 P3: 제외 아님 — 태깅만(스폰서 상품도 수집).
      if (sponsored) _kgpExcl.ad++;                        // v65 STEP2: 광고 카운트(제외 아님)
      // v67 STEP1: region = 메인 그리드 안이면 main, 밖(추천/캐러셀)이면 reco. 버튼은 둘 다 부착.
      const region = (mainSlot ? mainSlot.contains(el) : !_kgpIsRecoRegion(el)) ? "main" : "reco";
      if (region === "reco") _kgpExcl.reco++;
      const a = el.querySelector('a.a-link-normal[href*="/dp/"], h2 a, a.a-link-normal.s-no-outline, a[href*="/dp/"]');
      let href = a && a.href ? a.href.split("?")[0].split("#")[0] : "";
      if (!href || href.indexOf("http") !== 0) href = location.origin + "/dp/" + asin;   // ASIN 폴백
      if (seen[href]) { _kgpExcl.dup++; return; }
      const img = el.querySelector("img.s-image") || el.querySelector("img");
      const titleEl = el.querySelector("h2 span") || el.querySelector("h2 a span") || el.querySelector("h2")
        || el.querySelector('[data-cy="title-recipe"] span') || el.querySelector(".a-size-base-plus, .a-size-medium");
      let title = titleEl ? (titleEl.innerText || titleEl.textContent || "").trim() : "";
      if (!title && img && img.alt) title = img.alt.trim();
      if (!title && !img) { _kgpExcl.parse++; return; }     // 제목·이미지 둘 다 없으면 상품 아님
      const priceEl = el.querySelector(".a-price .a-offscreen") || el.querySelector(".a-price");
      const pr = _kgpPrice(priceEl ? priceEl.textContent : (el.innerText || ""));
      seen[href] = 1;
      const bimg = _kgpBestImg(img);                        // v41 X-1: lazy placeholder 대신 실제 이미지
      cards.push({
        url: href, title: (title || "(제목 없음)").slice(0, 200),
        image: bimg, images: bimg ? [bimg] : [], price: pr.price, currency: pr.currency,
        sponsored: sponsored, region: region, el: el,   /* v67: region 태그(main/reco) */
      });
    } catch (e) { /* noop */ }
  });
  return cards;
}

// 특정 href가 상품 '상세 페이지' 링크인지(가격 없는 카드의 대체 상품 신호).
function _kgpIsDetailHref(href) {
  return /(\/dp\/|\/gp\/product\/|item\.htm|offer\/detail|\/g-?\d|\/goods\/|\/product\/|-i\.\d+\.\d+|\/products?\/)/i.test(href || "");
}

// 폴백 휴리스틱 — 제목+제품링크+충분히 큰 이미지. v43-2: 가격이 없어도 '상품 상세 링크'면 인식(미렌더 가격 카드 복구).
function _kgpGenericCards() {
  const cards = [], seen = {};
  let scanned = 0;
  try {
    const imgs = document.querySelectorAll("img");
    for (let i = 0; i < imgs.length; i++) {
      const img = imgs[i];
      const w = img.naturalWidth || img.width || 0;
      const h = img.naturalHeight || img.height || 0;
      if (w < 140 || h < 140) continue;                    // 작은 썸네일/아이콘 제외
      let a = img.closest("a[href]");
      // v63 STEP1: 테무 등 SPA는 이미지를 <a>로 안 감쌀 수 있음 → 카드 컨테이너의 상세링크 앵커로 폴백.
      let card = (a && a.closest("li,article,div"))
        || img.closest("li,article,[class*='card' i],[class*='item' i],[class*='product' i],[class*='goods' i]");
      if ((!a || !a.href || a.href.indexOf("http") !== 0) && card) {
        const cand = card.querySelectorAll("a[href]");
        for (let j = 0; j < cand.length; j++) {
          const hh = cand[j].href || "";
          if (hh.indexOf("http") === 0 && _kgpIsDetailHref(hh)) { a = cand[j]; break; }  // 상세링크 우선
        }
        if ((!a || (a.href || "").indexOf("http") !== 0) && cand.length && (cand[0].href || "").indexOf("http") === 0) a = cand[0];
      }
      if (!a || !a.href || a.href.indexOf("http") !== 0) { _kgpExcl.url++; continue; }   // v65 STEP2: URL 추출 실패
      const href = a.href.split("#")[0];
      if (seen[href]) { _kgpExcl.dup++; continue; }
      if (!card) card = a.closest("li,article,div") || a;
      // v67 STEP1: 구조적 비상품(footer/nav)만 제외 — 추천/캐러셀 상품 타일도 버튼 부착(region='reco').
      if (_kgpInBadRegion(card, { structuralOnly: true })) { _kgpExcl.region++; continue; }
      const text = (card.innerText || "").trim();
      const pr = _kgpPrice(text);
      const titleEl = card.querySelector("h1,h2,h3,h4,[class*='title'],[class*='name']");
      const title = ((img.alt || "").trim()) || (titleEl ? titleEl.innerText : "") || text;
      if (!title || title.trim().length < 4) { _kgpExcl.parse++; continue; }     // 제목 없으면 상품 후보 아님
      scanned++;                                           // 상품 후보(제목+이미지+링크+영역OK)
      // v43-2: 가격 또는 상세링크 중 하나면 상품 인식(가격만 필수였던 옛 규칙이 27중16 누락 유발).
      if (!pr.price && !_kgpIsDetailHref(href)) { _kgpExcl.parse++; continue; }  // 둘 다 없으면 제외(정직 카운트에 반영)
      seen[href] = 1;
      const region = _kgpIsRecoRegion(card) ? "reco" : "main";   // v67: 추천 영역 태깅(버튼은 부착)
      if (region === "reco") _kgpExcl.reco++;
      const bimg = _kgpBestImg(img) || img.src;             // v41 X-1: 실제 이미지 우선(placeholder 공유 방지)
      cards.push({
        url: href, title: title.trim().replace(/\s+/g, " ").slice(0, 200),
        image: bimg, images: bimg ? [bimg] : [], price: pr.price, currency: pr.currency, region: region, el: card,
      });
    }
  } catch (e) { /* noop */ }
  if (scanned > cards.length) _kgpScannedCount = scanned;   // v43-2: 정직 '전체 N 중 상품 M · 제외 K'
  return cards;
}

// v63 STEP1: 상품 고유키 — 어댑터/제네릭이 같은 상품을 다른 URL 형태로 잡아도 하나로 묶는다.
//   아마존 ASIN(/dp/·/gp/product/), 테무·굿즈(goods_id·-g-<n>·/goods/<n>) 우선, 그 외 쿼리/ref 제거 URL.
function _kgpCardKey(url) {
  const u = url || "";
  let m = u.match(/\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})/i);
  if (m) return "asin:" + m[1].toUpperCase();
  m = u.match(/[?&]goods_id=(\d+)/i) || u.match(/[/-]g-(\d{4,})/i) || u.match(/\/goods\/(\d+)/i);
  if (m) return "goods:" + m[1];
  return u.split("#")[0].split("?")[0].replace(/\/(?:ref|spm|dp)=.*$/i, "").replace(/\/+$/, "").toLowerCase();
}

// v63 STEP1: 감지 역전 — 제네릭(요시다에서 검증된 건강 경로)을 항상 먼저, 어댑터는 정밀 보강만.
//   같은 상품키는 어댑터 결과로 덮어써(정밀: 스폰서 태그·정돈된 제목/가격), 제네릭만 잡은 상품은 유지한다.
//   → 어댑터 셀렉터가 현행 DOM과 불일치(사망)해도 제네릭 커버리지를 절대 막지 않는다(폴백 차단 구조 제거).
function _kgpMergeCards(generic, adapter) {
  const byKey = {}, order = [];
  (generic || []).forEach((c) => {
    const k = _kgpCardKey(c && c.url); if (!k) return;
    if (!byKey[k]) order.push(k);
    byKey[k] = c;
  });
  (adapter || []).forEach((c) => {
    const k = _kgpCardKey(c && c.url); if (!k) return;
    if (!byKey[k]) order.push(k);
    byKey[k] = c;                          // 어댑터 우선(정밀 보강) — 없으면 신규 추가
  });
  return order.map((k) => byKey[k]);
}

// v63 STEP1: 마지막 감지 스냅샷(팝업 디버그 패널이 조회) — 추측이 아니라 실측을 보고한다.
let _kgpLastDetect = { generic: 0, adapter: 0, merged: 0, adapterMatched: false };
function kgpFindCards() {
  const host = (location.hostname || "").toLowerCase();
  _kgpScannedCount = 0;            // 매 스캔 초기화(어댑터/제네릭이 '전체 N개'를 설정)
  _kgpExclReset();                 // v65 STEP2: 제외 사유 카운트 초기화
  let generic = [], gScanned = 0;
  try { generic = _kgpGenericCards(); gScanned = _kgpScannedCount; } catch (e) { generic = []; }
  let adapter = [];
  try { if (/(^|\.)amazon\.[a-z.]+$/.test(host)) { _kgpScannedCount = 0; adapter = _kgpAmazonCards(); } } catch (e) { adapter = []; }
  // 정직 카운트: 어댑터가 스캔한 전체(있으면)와 제네릭 스캔 중 큰 값 유지('전체 N 중 상품 M').
  _kgpScannedCount = Math.max(_kgpScannedCount || 0, gScanned || 0);
  const merged = _kgpMergeCards(generic, adapter);
  _kgpLastDetect = { generic: generic.length, adapter: adapter.length, merged: merged.length, adapterMatched: adapter.length > 0 };
  return merged;
}

function kgpCardBadgeStyle(selected) {
  return [
    "position:absolute", "top:6px", "left:6px", "z-index:2147483640",
    "padding:3px 8px", "border-radius:7px", "cursor:pointer", "user-select:none",
    "font:700 11px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    selected ? "background:#119a8e" : "background:#1a1714", "color:#fff",
    "border:1.5px solid " + (selected ? "#0f8c80" : "#c9a24b"),
    "box-shadow:0 2px 8px rgba(0,0,0,.35)",
  ].join(";");
}

function kgpSetCardSelected(url, badge, el, selected) {
  if (selected) {
    KGP_SELECTED.add(url);
    if (badge) { badge.textContent = "✓ 선택"; badge.style.cssText = kgpCardBadgeStyle(true); }
    if (el) { el.style.outline = "3px solid #119a8e"; el.style.outlineOffset = "-3px"; el.setAttribute("data-kgp-outline", "1"); }
  } else {
    KGP_SELECTED.delete(url);
    if (badge) { badge.textContent = "수집"; badge.style.cssText = kgpCardBadgeStyle(false); }
    if (el) { el.style.outline = ""; el.removeAttribute("data-kgp-outline"); }
  }
}

function kgpToggleCard(url, badge, el) {
  kgpSetCardSelected(url, badge, el, !KGP_SELECTED.has(url));
  kgpUpdateToolbar();
}

function kgpSetStatus(msg) {
  const s = document.getElementById("kgp-tb-status");
  if (s) s.textContent = msg || "";
}

// ── v42 E-3: 목록 카드 호버 즉시 수집 ──
const KGP_TOUCH = (() => { try { return matchMedia("(pointer: coarse)").matches; } catch (e) { return false; } })();
let _kgpCollectedUrls = new Set();   // 이미 수집된 상품 URL(호버 버튼 '수집됨 ✓' 선표시)
const KGP_BRIDGE_MINI = '<svg width="14" height="14" viewBox="0 0 512 512" aria-hidden="true">' +
  '<circle cx="256" cy="205" r="92" fill="none" stroke="#c9a24b" stroke-width="46"/>' +
  '<line x1="80" y1="356" x2="432" y2="356" stroke="#119a8e" stroke-width="46" stroke-linecap="round"/>' +
  '<circle cx="256" cy="108" r="40" fill="#f5821f"/></svg>';

// v64 STEP3: 호버 수집 버튼 스펙 확정 — 이미지 영역 오버레이 앵커(요시다 '수집됨✓' 스타일).
//   원 과대·글자 과소 → 지름 절반(min-height 66→34)·텍스트 위주 필(아이콘 21→14, 글자 위계 ↑).
//   앵커: 기본 중앙, 설정(kgp_hover_anchor)에서 좌하 7시(bl)/우하 5시(br) 선택. 터치는 우상단 상시 소형.
//   토큰: 먹(#1a1714)·금(#c9a24b) 테, 수집됨=청록(#119a8e). 임의 색 금지.
let KGP_HOVER_ANCHOR = "center";   // v64 STEP3: chrome.storage.local(사이트 무관 공유) — 팝업이 설정.
function kgpHoverAnchor() {
  const a = KGP_HOVER_ANCHOR;
  return (a === "bl" || a === "br" || a === "center") ? a : "center";
}
function _kgpAnchorCss(mode) {
  // v65 STEP3: mode='corner'(이미지 못 찾음) → 좌상단 폴백(허공 금지). 그 외 이미지 영역 앵커.
  if (mode === "corner") return ["top:6px", "left:6px"];
  if (KGP_TOUCH) return ["top:8px", "right:8px"];       // 터치: 우상단 상시
  const a = kgpHoverAnchor();
  if (a === "bl") return ["bottom:10px", "left:10px"];   // 7시
  if (a === "br") return ["bottom:10px", "right:10px"];  // 5시
  return ["top:50%", "left:50%", "transform:translate(-50%,-50%)"];  // 중앙(기본)
}
// v65 STEP3: 카드에서 대표 이미지 요소 찾기(가장 큰 상품 이미지) — 버튼을 이 이미지 위에 앵커.
function _kgpCardImage(card) {
  if (!card || !card.querySelectorAll) return null;
  let best = null, bestArea = 0;
  try {
    const imgs = card.querySelectorAll("img");
    for (let i = 0; i < imgs.length; i++) {
      const im = imgs[i];
      const w = im.naturalWidth || im.width || im.clientWidth || 0;
      const h = im.naturalHeight || im.height || im.clientHeight || 0;
      if (w < 60 || h < 60) continue;                    // 아이콘/썸네일 제외
      const area = w * h;
      if (area > bestArea) { bestArea = area; best = im; }
    }
  } catch (e) {}
  return best;
}
function kgpQuickBtnStyle(collected, mode) {
  return [
    "position:absolute", "z-index:2147483639",
  ].concat(_kgpAnchorCss(mode)).concat([
    "display:flex", "align-items:center", "justify-content:center",
    "gap:6px", "white-space:nowrap",
    KGP_TOUCH ? "padding:5px 11px" : "padding:6px 14px", "border-radius:999px", "cursor:pointer",
    "min-height:34px",                 // v64: 지름 절반(66→34), 텍스트 위주 필
    "font:800 " + (KGP_TOUCH ? "13px" : "15px") + "/1 -apple-system,BlinkMacSystemFont,sans-serif",
    "letter-spacing:-.01em",
    "background:" + (collected ? "#119a8e" : "#1a1714"), "color:#fff",
    "border:1.5px solid " + (collected ? "#0f8c80" : "#c9a24b"),
    "box-shadow:0 3px 12px rgba(0,0,0,.34)", "pointer-events:auto",
    "opacity:" + ((KGP_TOUCH || collected) ? "1" : "0"), "transition:opacity .12s",
  ]).join(";");
}
function kgpMarkQuickCollected(btn) {
  btn.dataset.collected = "1";
  const lbl = btn.querySelector(".kgp-q-label");
  if (lbl) lbl.textContent = "수집됨 ✓";
  btn.style.cssText = kgpQuickBtnStyle(true, btn.dataset.anchorMode || "");   // v65 STEP3: 앵커 모드 보존
  btn.style.cursor = "default";
}
function kgpQuickCollect(card, btn) {
  if (btn.dataset.collected === "1" || btn.dataset.busy === "1") return;
  btn.dataset.busy = "1";
  const lbl = btn.querySelector(".kgp-q-label");
  const prev = lbl ? lbl.textContent : "수집";
  if (lbl) lbl.textContent = "수집 중…";
  const corr = kgpNewCorr();
  const meta = { url: card.url, title: card.title, image: card.image, images: card.images, price: card.price, currency: card.currency, corr_id: corr };
  kgpSendMessage({ action: "collectBulk", items: [meta] }, (resp) => {
    btn.dataset.busy = "";
    if (resp && resp.ok === true && ((resp.success || 0) > 0 || (resp.duplicate || 0) > 0)) {
      _kgpCollectedUrls.add(card.url);
      kgpMarkQuickCollected(btn);
      if ((resp.success || 0) > 0) kgpAlertOnce(corr, () => kgpCelebrate(1));   // 실제 새 수집만 축하(건당 1회·중복은 조용)
    } else {
      kgpAlertOnce(corr, () => {
        if (lbl) lbl.textContent = prev;
        kgpToast((resp && resp.error) || "수집 실패", false);
      });
    }
  });
}
// 스캔한 카드 중 이미 수집된 것을 서버에 물어 '수집됨 ✓'로 선표시(중복 방지 연동).
function kgpMarkExisting(cards) {
  const urls = cards.map((c) => c.url).filter((u) => u && !_kgpCollectedUrls.has(u));
  if (!urls.length) return;
  kgpSendMessage({ action: "collectExists", urls }, (resp) => {
    if (!resp || !resp.ok || !Array.isArray(resp.collected)) return;
    resp.collected.forEach((u) => _kgpCollectedUrls.add(u));
    document.querySelectorAll(".kgp-card-quick").forEach((q) => {
      if (_kgpCollectedUrls.has(q.dataset.url) && q.dataset.collected !== "1") kgpMarkQuickCollected(q);
    });
  });
}

function kgpUpdateToolbar() {
  const c = document.getElementById("kgp-tb-count");
  if (!c) return;
  // v42 E-4: 정직 표기 — 인식된 상품 수 + 제외(광고 등) 수를 눈에 보이게(조용한 누락 금지).
  // v64 STEP2: 광고(스폰서) 수를 명시(오너가 분류 정합을 눈으로 검증). 제외=구조적 비상품(광고 아님).
  // v67 STEP1: 카운트 표기 [메인 n / 추천 m / 광고 k] — 버튼은 전 타일 부착, 카운트만 구분.
  const ads = _kgpAdCount(), reco = _kgpRecoCount(), main = _kgpMainCount();
  const recoTxt = reco ? ` · 추천 ${reco}` : "";
  const adTxt = ads ? ` · 광고 ${ads}` : "";
  c.textContent = `메인 ${main}${recoTxt}${adTxt} · ${KGP_SELECTED.size}개 선택`;
}

function kgpCollect(urls) {
  const items = (urls || []).map(u => _kgpCardByUrl[u]).filter(Boolean).map(c => (
    { url: c.url, title: c.title, image: c.image, images: c.images, price: c.price, currency: c.currency }
  ));
  if (!items.length) { kgpSetStatus("선택된 상품이 없어요. 상품의 ‘수집’ 배지를 눌러 선택하세요."); return; }
  kgpRunBulk(items);
}

// v42 E-5: 벌크 실행 코어 — 정직 요약(완료/중복/실패) + 실패 항목 재시도. 전체수집·선택수집·재시도가 공용.
function kgpRunBulk(items) {
  if (!items || !items.length) return;
  kgpSetStatus(`수집 중… (0/${items.length})`);
  const btns = document.querySelectorAll(".kgp-tb-btn");
  btns.forEach(b => b.disabled = true);
  const oldRetry = document.getElementById("kgp-tb-retry");
  if (oldRetry) oldRetry.remove();
  kgpSendMessage({ action: "collectBulk", items }, (resp) => {
    btns.forEach(b => b.disabled = false);
    if (!resp || resp.ok !== true) { kgpSetStatus(((resp && resp.error) || "수집 실패")); return; }
    if (resp.success > 0) kgpCelebrate(resp.success);   // 실제(중복 제외) 성공 건수만 축하
    const dup = resp.duplicate || 0, fail = resp.failed || 0;
    let msg = `총 ${resp.total}: 완료 ${resp.success}`;
    if (dup) msg += ` · 중복 ${dup}`;
    if (fail) msg += ` · 실패 ${fail}`;
    msg += fail ? " — 아래 ‘재시도’를 누르세요." : ". 셀러 콘솔 수집 이력에서 확인하세요.";
    kgpSetStatus(msg);
    kgpRenderRetry(resp.failedItems || []);   // 실패분만 재시도 버튼
    // v64 STEP1: 2단 상세 보강 시작 — 목록 저장분(item_id)을 백그라운드 탭으로 순차 방문해 보강.
    const targets = resp.enrichTargets || [];
    if (targets.length) {
      kgpSendMessage({ action: "enrichStart", targets }, (er) => {
        if (er && er.ok) kgpSetStatus(msg + ` · 상세 보강 시작(0/${er.total})`);
      });
    }
  });
}

// v64 STEP1: 상세 보강 진행률을 벌크바 상태에 실시간 표시(background가 1건마다 전송).
try {
  chrome.runtime.onMessage.addListener((m) => {
    if (m && m.action === "enrichProgress" && m.state) {
      const s = m.state;
      if (s.total > 0 && document.getElementById(KGP_TOOLBAR_ID)) {
        let t = `상세 보강 ${s.done}/${s.total}`;
        if (s.failed) t += ` · 보강 실패 ${s.failed}`;
        if (s.paused) t += " · 일시정지";
        else if (!s.running && s.done >= s.total) t += " · 완료";
        kgpSetStatus(t);
      }
    }
    return false;
  });
} catch (e) { /* noop */ }

// 실패 항목 재시도 버튼(정직: 조용한 누락 금지 — 실패 N건을 눈에 보이게).
function kgpRenderRetry(failedItems) {
  const old = document.getElementById("kgp-tb-retry");
  if (old) old.remove();
  if (!failedItems || !failedItems.length) return;
  const tb = document.getElementById(KGP_TOOLBAR_ID);
  if (!tb) return;
  const b = document.createElement("button");
  b.id = "kgp-tb-retry";
  b.className = "kgp-tb-btn";
  b.textContent = `실패 ${failedItems.length}건 재시도`;
  b.style.cssText = "background:#f5821f;color:#fff;border:0;border-radius:8px;padding:6px 12px;font-weight:700;cursor:pointer";
  b.addEventListener("click", () => kgpRunBulk(failedItems));
  tb.appendChild(b);
}

function kgpBuildToolbar() {
  const bar = document.createElement("div");
  bar.id = KGP_TOOLBAR_ID;
  bar.style.cssText = [
    "position:fixed", "top:12px", "left:50%", "transform:translateX(-50%)",
    "z-index:2147483647", "display:flex", "align-items:center", "gap:12px",
    "padding:10px 18px", "border-radius:999px", "border:1px solid #c9a24b",   // v45 P1: 벌크바 +25%
    "background:#1a1714", "color:#f5efe3",
    "font:16px/1.2 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    "box-shadow:0 8px 24px rgba(0,0,0,.45)", "max-width:96vw", "flex-wrap:wrap",
  ].join(";");
  // 버튼 위계: 전체 수집=청록 채움(Primary), 선택 수집=금 아웃라인(Secondary), 전체선택/해제=고스트. (+25% 확대)
  const btnBase = "padding:7px 14px;border-radius:9px;cursor:pointer;font-weight:700;font-size:15px;min-height:40px;";
  const ghost = btnBase + "background:transparent;color:#e7ddc9;border:1px solid #4a4234;";
  const gold = btnBase + "background:transparent;color:#e8d6a8;border:1.5px solid #c9a24b;";
  const teal = btnBase + "background:#119a8e;color:#fff;border:1px solid #0f8c80;";
  const autoOn = kgpLSget("kgp_bar_auto", "1") !== "0";
  bar.innerHTML =
    '<span id="kgp-tb-grip" style="display:flex;align-items:center;gap:7px">' +
    '<span style="display:flex;align-items:center;justify-content:center;width:33px;height:33px;background:transparent;border:0">' + KGP_BRIDGE_SVG + '</span>' +
    '<strong style="color:#ecdcb0">고가수집기</strong></span>' +
    '<span id="kgp-tb-count" style="opacity:.85"></span>' +
    '<span style="width:1px;height:22px;background:#4a4234"></span>' +
    '<button class="kgp-tb-btn" data-act="all-sel" style="' + ghost + '">전체 선택</button>' +
    '<button class="kgp-tb-btn" data-act="clear" style="' + ghost + '">선택 해제</button>' +
    '<button class="kgp-tb-btn" data-act="collect-sel" style="' + gold + '">선택 수집</button>' +
    '<button class="kgp-tb-btn" data-act="collect-all" style="' + teal + '">전체 수집</button>' +
    '<button class="kgp-tb-btn" data-act="incl-reco" title="전체선택·전체수집에 추천/캐러셀 상품을 포함할지" style="' + ghost + '">' + (_kgpInclReco() ? '추천 포함 ✓' : '추천 포함') + '</button>' +
    '<button class="kgp-tb-btn" data-act="incl-ads" title="전체선택·전체수집에 광고(스폰서) 상품을 포함할지" style="' + ghost + '">' + (_kgpInclAds() ? '광고 포함 ✓' : '광고 포함') + '</button>' +
    '<span id="kgp-tb-status" style="opacity:.95;font-size:15px;max-width:420px"></span>' +
    '<button class="kgp-tb-btn" data-act="auto" title="새 목록 페이지에서 자동으로 열지 여부" style="' + ghost + '">' + (autoOn ? '자동' : '수동') + '</button>' +
    '<button data-act="close" title="접기(구석 배지로)" style="' + btnBase + 'background:transparent;color:#c9bda6;border:none;font-size:19px">✕</button>';
  bar.addEventListener("click", (e) => {
    const t = e.target.closest("[data-act]");
    if (!t) return;
    const act = t.dataset.act;
    if (act === "all-sel") {
      // v64 STEP2: 전체선택 = 실상품 전체(광고 제외, '광고 포함' 켜면 전부).
      const pick = new Set(_kgpSelectableUrls());
      document.querySelectorAll(".kgp-card-chk").forEach((b) => {
        const url = b.dataset.url;
        if (!pick.has(url)) return;
        const c = _kgpCardByUrl[url];
        kgpSetCardSelected(url, b, c && c.el, true);
      });
      kgpUpdateToolbar();
    } else if (act === "incl-ads") {
      const next = _kgpInclAds() ? "0" : "1";
      kgpLSset("kgp_incl_ads", next);
      t.textContent = next === "1" ? "광고 포함 ✓" : "광고 포함";
      kgpUpdateToolbar();
    } else if (act === "incl-reco") {
      const next = _kgpInclReco() ? "0" : "1";
      kgpLSset("kgp_incl_reco", next);
      t.textContent = next === "1" ? "추천 포함 ✓" : "추천 포함";
      kgpUpdateToolbar();
    } else if (act === "clear") {
      document.querySelectorAll(".kgp-card-chk").forEach((b) => {
        const url = b.dataset.url;
        const c = _kgpCardByUrl[url];
        kgpSetCardSelected(url, b, c && c.el, false);
      });
      KGP_SELECTED.clear();
      kgpUpdateToolbar();
    } else if (act === "collect-sel") {
      kgpCollect([...KGP_SELECTED]);
    } else if (act === "collect-all") {
      kgpCollect(_kgpSelectableUrls());          // v64 STEP2: 광고 제외(광고 포함 토글로 전부)
    } else if (act === "auto") {
      // 팝업 자동표시 on/off(v7). 끄면 지금 접고, 이후 목록 페이지는 구석 배지로만 시작.
      const next = kgpLSget("kgp_bar_auto", "1") === "0" ? "1" : "0";
      kgpLSset("kgp_bar_auto", next);
      t.textContent = next === "0" ? "수동" : "자동";
      if (next === "0") {
        _kgpClosed = true;
        bar.remove();
        document.querySelectorAll(".kgp-card-chk, .kgp-card-quick").forEach((b) => b.remove());
        kgpShowReopenPill();
      } else {
        kgpSetStatus("이제 목록 페이지에서 자동으로 열려요.");
      }
    } else if (act === "close") {
      // 접으면 같은 페이지에서 자동으로 다시 뜨지 않게 한다(URL 변경 시 초기화).
      // 대신 구석에 작은 '수집 열기' 배지(선택 개수·펄스)를 남긴다(선택은 유지).
      _kgpClosed = true;
      bar.remove();
      document.querySelectorAll(".kgp-card-chk, .kgp-card-quick").forEach((b) => b.remove());
      kgpShowReopenPill();
    }
  });
  _kgpMount(bar);                          // v45 P4: <html> 직속(상단중앙 고정, 좌상단 처박힘 방지)
  try { _kgpKeepBarPinned(); } catch (e) {}  // v64 STEP4: 마운트 즉시 뷰포트 상단 고정 보정(변형 조상 대응)
  // 드래그로 이동 + 위치 기억(grip 영역만 잡기, 버튼 클릭은 드래그 제외).
  kgpMakeDraggable(bar, "kgp_bar_pos", { handle: bar, ignore: "button,[data-act]" });
}

const KGP_REOPEN_ID = "kgp-listing-reopen";

// 접었을 때 구석에 작은 '수집 열기' 배지 → 클릭 시 바를 다시 띄운다.
// 선택 개수 뱃지 + (선택 있으면) 청록 펄스. 드래그로 옮기면 위치 기억(kgp_bar_pos).
function kgpShowReopenPill() {
  let pill = document.getElementById(KGP_REOPEN_ID);
  const sel = KGP_SELECTED.size;
  if (pill) {   // 이미 있으면 개수/펄스만 갱신
    const cnt = pill.querySelector(".kgp-pill-count");
    if (cnt) cnt.textContent = sel ? String(sel) : "";
    if (cnt) cnt.style.display = sel ? "inline-block" : "none";
    pill.style.animation = (sel && !KGP_RM) ? "kgpPulse 1.6s ease-in-out infinite" : "none";
    return;
  }
  if (!document.body) return;
  kgpEnsureStyles();
  pill = document.createElement("button");
  pill.id = KGP_REOPEN_ID;
  pill.type = "button";
  pill.title = "고가수집기 바 열기";
  pill.innerHTML =
    '<span style="display:flex;align-items:center;justify-content:center;width:22px;height:22px;background:transparent;border:0">' + KGP_BRIDGE_SVG + '</span>' +
    '<span style="font-weight:700;font-size:12px">수집 열기</span>' +
    '<span class="kgp-pill-count" style="display:' + (sel ? "inline-block" : "none") + ';background:#119a8e;color:#fff;border-radius:999px;padding:1px 7px;font-size:11px;font-weight:800">' + (sel || "") + '</span>';
  pill.style.cssText = [
    "position:fixed", "top:12px", "left:12px", "z-index:2147483647",
    "display:flex", "align-items:center", "gap:6px", "padding:5px 10px 5px 6px",
    "border:1px solid #c9a24b", "border-radius:999px",
    "background:#1a1714", "color:#f5efe3",
    "cursor:pointer", "box-shadow:0 4px 14px rgba(0,0,0,.45)",
    "font:12px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    (sel && !KGP_RM) ? "animation:kgpPulse 1.6s ease-in-out infinite" : "",
  ].join(";");
  pill.addEventListener("click", () => {
    if (pill._kgpDragged) return;     // 드래그였으면 클릭 무시
    pill.remove();
    _kgpClosed = false;
    kgpInjectListing();               // 바 + 배지 복원(선택 유지)
  });
  _kgpMount(pill);                         // v45 P5: <html> 직속(본문 재렌더에도 상시 표시)
  kgpMakeDraggable(pill, "kgp_bar_pos", {});
}

let _kgpAutoApplied = false;       // 이 페이지에서 '수동(auto off)' 초기 접힘을 한 번만 적용

function kgpInjectListing() {
  if (window.top !== window.self || !document.body) return;
  if (!kgpHostAllowed() && !kgpEntrySession()) { kgpTeardown(); return; }   // 지정 소싱처 또는 앱 진입(v10/v17)
  const cards = kgpFindCards();
  if (cards.length < 3) {                        // 리스팅 아님 → 정리(배지/바/배지펄스 제거)
    const ex = document.getElementById(KGP_TOOLBAR_ID);
    if (ex) { ex.remove(); document.querySelectorAll(".kgp-card-chk, .kgp-card-quick").forEach((b) => b.remove()); }
    const _pill = document.getElementById(KGP_REOPEN_ID);
    if (_pill) _pill.remove();
    return;
  }
  // '수동' 설정이면 새 목록 페이지를 접힌(배지) 상태로 시작(v7 팝업 on/off).
  if (!_kgpAutoApplied) {
    _kgpAutoApplied = true;
    if (kgpLSget("kgp_bar_auto", "1") === "0") _kgpClosed = true;
  }
  // 재스캔(무한스크롤/동적로딩)에도 선택을 지우지 않는다.
  // ★중요★ 카드맵을 비우지 않고 '병합'한다 — 비우면 선택된 url의 카드 데이터가 사라져
  //   '선택 수집/전체 수집'이 '선택된 상품 없음'으로 실패하던 버그(오너 리포트) 방지.
  _kgpCards = cards;
  cards.forEach((c) => { _kgpCardByUrl[c.url] = c; });
  if (_kgpClosed) {                              // 접힘 → 구석 배지(개수·펄스)만 유지
    const ex = document.getElementById(KGP_TOOLBAR_ID);
    if (ex) { ex.remove(); document.querySelectorAll(".kgp-card-chk, .kgp-card-quick").forEach((b) => b.remove()); }
    kgpShowReopenPill();
    return;
  }
  cards.forEach((c) => {
    try {
      const existing = c.el.querySelector(":scope > .kgp-card-chk");
      const sel = KGP_SELECTED.has(c.url);
      if (existing) {
        // 이미 배지 있음 — 선택 상태만 동기화(선택을 풀지 않음)
        existing.textContent = sel ? "✓ 선택" : "수집";
        existing.style.cssText = kgpCardBadgeStyle(sel);
        if (sel) { c.el.style.outline = "3px solid #119a8e"; c.el.style.outlineOffset = "-3px"; c.el.setAttribute("data-kgp-outline", "1"); }
        return;
      }
      if (getComputedStyle(c.el).position === "static") c.el.style.position = "relative";
      const badge = document.createElement("div");
      badge.className = "kgp-card-chk";
      badge.dataset.url = c.url;
      badge.textContent = sel ? "✓ 선택" : "수집";
      badge.style.cssText = kgpCardBadgeStyle(sel);
      if (sel) { c.el.style.outline = "3px solid #119a8e"; c.el.style.outlineOffset = "-3px"; c.el.setAttribute("data-kgp-outline", "1"); }
      badge.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        kgpToggleCard(c.url, badge, c.el);
      });
      c.el.appendChild(badge);

      // v64 STEP2: 광고(스폰서) 카드는 우상단 'AD' 미니 배지로 시각화(오너가 분류 오판을 눈으로 검증).
      //   토큰 준수(먹 배경·금 테). 실상품이므로 카드는 살리되, 전체선택은 기본 제외(광고 포함 토글로 켬).
      if (c.sponsored && !c.el.querySelector(":scope > .kgp-card-ad")) {
        const ad = document.createElement("div");
        ad.className = "kgp-card-ad";
        ad.textContent = "AD";
        ad.style.cssText = [
          "position:absolute", "top:6px", "right:6px", "z-index:2147483640",
          "padding:2px 7px", "border-radius:6px", "pointer-events:none", "user-select:none",
          "font:800 10px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
          "letter-spacing:.06em", "background:#1a1714", "color:#e8d6a8", "border:1px solid #c9a24b",
        ].join(";");
        c.el.appendChild(ad);
      }

      // v42 E-3 / v65 STEP3: 호버 즉시 수집 버튼 — 카드 우측 허공이 아니라 **상품 이미지 요소 위**에 앵커.
      //   이미지를 못 찾으면 카드 좌상단 폴백(mode=corner, 허공 금지). 데스크톱=hover 노출/터치=우상단 상시.
      if (!c.el.querySelector(".kgp-card-quick")) {
        const done = _kgpCollectedUrls.has(c.url);
        const imgEl = _kgpCardImage(c.el);
        const host = (imgEl && imgEl.parentElement) ? imgEl.parentElement : c.el;
        const mode = imgEl ? "" : "corner";
        const q = document.createElement("div");
        q.className = "kgp-card-quick";
        q.dataset.url = c.url;
        q.dataset.anchorMode = mode;
        if (done) q.dataset.collected = "1";
        q.innerHTML = '<span style="display:flex;width:14px;height:14px;flex:none">' + KGP_BRIDGE_MINI +   // v64 STEP3: 아이콘 축소(21→14), 텍스트 위주
          '</span><span class="kgp-q-label">' + (done ? "수집됨 ✓" : "수집") + "</span>";
        q.style.cssText = kgpQuickBtnStyle(done, mode);
        q.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); kgpQuickCollect(c, q); });
        if (!KGP_TOUCH) {
          c.el.addEventListener("mouseenter", () => { if (q.dataset.collected !== "1") q.style.opacity = "1"; });
          c.el.addEventListener("mouseleave", () => { if (q.dataset.collected !== "1") q.style.opacity = "0"; });
        }
        try { if (getComputedStyle(host).position === "static") host.style.position = "relative"; } catch (e) {}
        host.appendChild(q);
      }
    } catch (e) { /* noop */ }
  });
  kgpMarkExisting(cards);   // v42 E-3: 이미 수집된 카드 '수집됨 ✓' 선표시
  const _pill = document.getElementById(KGP_REOPEN_ID);
  if (_pill) _pill.remove();                     // 펼침 → 구석 배지 제거
  if (!document.getElementById(KGP_TOOLBAR_ID)) { kgpBuildToolbar(); kgpMaybeCoach(); }
  kgpUpdateToolbar();
}

// '전체 수집' 1회성 코치마크(처음 리스팅 바를 만났을 때만). reduced-motion이면 생략.
function kgpMaybeCoach() {
  if (KGP_RM || kgpLSget("kgp_coach_all", "") === "1") return;
  const target = document.querySelector('.kgp-tb-btn[data-act="collect-all"]');
  if (!target) return;
  kgpLSset("kgp_coach_all", "1");
  const r = target.getBoundingClientRect();
  const tip = document.createElement("div");
  tip.style.cssText = "position:fixed;z-index:2147483647;max-width:248px;padding:11px 14px;border-radius:12px;background:#119a8e;color:#fff;font:600 12.5px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;box-shadow:0 10px 28px rgba(0,0,0,.45)";
  tip.style.top = (r.bottom + 12) + "px";
  tip.style.left = Math.max(8, Math.min(window.innerWidth - 256, r.left - 90)) + "px";
  tip.innerHTML = '<b>전체 수집</b>으로 이 페이지의 상품을 한 번에 담을 수 있어요.' +
    '<div style="margin-top:8px;text-align:right"><span id="kgp-coach-x" style="cursor:pointer;text-decoration:underline;opacity:.92">알겠어요</span></div>';
  document.body.appendChild(tip);
  const close = () => { try { tip.remove(); } catch (e) { /* noop */ } };
  tip.querySelector("#kgp-coach-x").addEventListener("click", close);
  setTimeout(close, 7000);
}

// 비-소싱처(또는 설정으로 꺼진 사이트)에선 모든 UI 제거(경량, DOM 손 안 댐).
function kgpTeardown() {
  try {
    const fab = document.getElementById(KGP_BTN_ID); if (fab) fab.remove();
    const bar = document.getElementById(KGP_TOOLBAR_ID); if (bar) bar.remove();
    const pill = document.getElementById(KGP_REOPEN_ID); if (pill) pill.remove();
    document.querySelectorAll(".kgp-card-chk, .kgp-card-quick").forEach((b) => b.remove());
    document.querySelectorAll('[data-kgp-outline="1"]').forEach((e) => { e.style.outline = ""; e.removeAttribute("data-kgp-outline"); });
  } catch (e) { /* noop */ }
}

// 상세 페이지로 보이는 URL 패턴(아마존 /dp//gp/product, 타오바오 item.htm, 1688 offer/detail, Temu g-, 일반 /product//goods/).
function kgpIsDetailUrl() {
  return /(\/dp\/|\/gp\/product\/|item\.htm|offer\/detail|\/g-?\d|\/goods\/|\/product\/)/i.test(location.href);
}

// FAB(우측)만 제거 / 리스팅(중앙 바·배지·구석배지)만 제거 — 모드 전환 시 상호배타.
function kgpRemoveFab() {
  const fab = document.getElementById(KGP_BTN_ID);
  if (fab) fab.remove();
}
function kgpRemoveListing() {
  const bar = document.getElementById(KGP_TOOLBAR_ID); if (bar) bar.remove();
  const pill = document.getElementById(KGP_REOPEN_ID); if (pill) pill.remove();
  document.querySelectorAll(".kgp-card-chk, .kgp-card-quick").forEach((b) => b.remove());
  document.querySelectorAll('[data-kgp-outline="1"]').forEach((e) => { e.style.outline = ""; e.removeAttribute("data-kgp-outline"); });
}

// v53 STEP1: 페이지 타입 점수제 감지기 — 단일 상품 vs 목록.
//   증상: 단일 상품 페이지에 중앙(벌크) 버튼이 떠 수집·선택 불가(옛 판정=카드 3개+면 무조건 목록).
//   URL 어댑터 매치 최우선, DOM 휴리스틱 보조. 동점/무신호=불능→우측 단건(안전 기본값).
const KGP_DETAIL_URL_RE = /(\/dp\/|\/gp\/product\/|\/vp\/products\/|item\.htm|aliexpress\.[^/]+\/item\/|[?&]goods_id=|[/-]g-\d{3,}|\/goods\/\d|\/product\/\d|\/products\/[\w-]+|\/itm\/)/i;
const KGP_LIST_URL_RE = /(\/s\?|\/s\/|\/search|\/sch\b|[?&](q|keyword|query|search|k)=|\/category|\/categories|\/c\/|\/list\b|\/best\b|\/ranking|\/plp|\/browse|\/deals)/i;

// v60 STEP5: 디폴트 소싱처(어댑터 등록 사이트) — 여기선 판정불능('unknown') 금지, URL로 결정적 판정.
const KGP_DEFAULT_SRC_RE = /(^|\.)(amazon\.[a-z.]+|temu\.com|aliexpress\.[a-z.]+|taobao\.com|tmall\.com|1688\.com|(shopping\.)?yahoo\.co\.jp|paypaymall\.yahoo\.co\.jp|mercari\.com|rakuten\.co\.jp)$/i;
function kgpIsDefaultSourcing() {
  try { return KGP_DEFAULT_SRC_RE.test((location.hostname || "").toLowerCase()); } catch (e) { return false; }
}

function kgpDetectPageType() {
  // 수동 오버라이드 최우선(감지 실패 대비 탈출구) — 경로 단위 기억.
  try {
    const ov = sessionStorage.getItem("kgp_pt_ov:" + location.pathname);
    if (ov === "single" || ov === "list") return ov;
  } catch (e) {}
  const href = location.href;
  const isDetail = KGP_DETAIL_URL_RE.test(href);
  const isList = KGP_LIST_URL_RE.test(href);
  // v60 STEP5: 디폴트 소싱처는 URL 패턴으로 **결정적** 판정(불능 금지) — 상세패턴=단건, 그 외 도메인 전체=벌크.
  if (kgpIsDefaultSourcing()) return isDetail ? "single" : "list";
  // v55 STEP5: URL 규칙 하드매치 최우선(결정적) — 테무 -g-{숫자}=단일, /search 등=목록. DOM 휴리스틱은
  //   URL이 애매할 때만(둘 다/둘 다 아님). 지연로드·DOM변이와 무관하게 판정 즉시 확정(점멸 제거).
  if (isDetail && !isList) return "single";
  if (isList && !isDetail) return "list";
  // URL 애매 → DOM 신호 1회 점수화(이후 kgpPageType 캐시로 세션 내 불변).
  let single = isDetail ? 3 : 0, list = isList ? 3 : 0;
  try { const h1 = document.querySelectorAll("h1"); if (h1.length === 1 && (h1[0].textContent || "").trim().length > 6) single += 1; } catch (e) {}
  try { if (document.querySelector('[class*="gallery" i],[class*="swiper" i],[class*="carousel" i],[aria-roledescription="carousel"]')) single += 1; } catch (e) {}
  try {
    document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
      const t = s.textContent || "";
      if (/"@type"\s*:\s*"Product"/i.test(t)) single += 2;
      if (/"@type"\s*:\s*"ItemList"/i.test(t)) list += 2;
    });
  } catch (e) {}
  try { const n = kgpFindCards().length; if (n >= 6) list += 3; else if (n >= 3) list += 1; } catch (e) {}

  if (single === 0 && list === 0) return "unknown";
  if (list > single) return "list";
  if (single > list) return "single";
  return "unknown";                                   // 동점 → 불능(안전 기본값으로)
}

// v55 STEP5: URL별 판정 캐시(세션 내 불변 = 히스테리시스) — 같은 URL은 재판정 안 함(왔다갔다 금지).
//   오버라이드는 캐시 무시(즉시 반영). 'unknown'은 캐시 안 함(DOM 준비 후 재판정 여지).
const KGP_PT_CACHE = {};
function kgpPageType() {
  try {
    const ov = sessionStorage.getItem("kgp_pt_ov:" + location.pathname);
    if (ov === "single" || ov === "list") return ov;
  } catch (e) {}
  const key = location.pathname + location.search;
  if (KGP_PT_CACHE[key]) return KGP_PT_CACHE[key];
  const pt = kgpDetectPageType();
  if (pt !== "unknown") KGP_PT_CACHE[key] = pt;       // 결정된 판정만 고정(번복 금지)
  return pt;
}

// 수동 오버라이드: 버튼 롱프레스(≥600ms) → 이 페이지를 단일↔목록 강제 토글(감지 실패 대비).
function kgpAttachOverride(el) {
  if (!el || el._kgpOv) return; el._kgpOv = 1;
  let timer = null;
  const start = () => { timer = setTimeout(() => {
    let cur = "";
    try { cur = sessionStorage.getItem("kgp_pt_ov:" + location.pathname) || kgpDetectPageType(); } catch (e) { cur = "single"; }
    const next = cur === "list" ? "single" : "list";
    try { sessionStorage.setItem("kgp_pt_ov:" + location.pathname, next); } catch (e) {}
    try { kgpToast("이 페이지를 '" + (next === "list" ? "목록(벌크)" : "단일 상품") + "'으로 강제했어요", true); } catch (e) {}
    kgpRefresh();
  }, 600); };
  const cancel = () => { if (timer) { clearTimeout(timer); timer = null; } };
  el.addEventListener("mousedown", start); el.addEventListener("touchstart", start, { passive: true });
  ["mouseup", "mouseleave", "touchend", "touchcancel"].forEach((ev) => el.addEventListener(ev, cancel));
  el.addEventListener("contextmenu", (e) => { e.preventDefault(); cancel();
    let cur = ""; try { cur = sessionStorage.getItem("kgp_pt_ov:" + location.pathname) || kgpDetectPageType(); } catch (x) {}
    const next = cur === "list" ? "single" : "list";
    try { sessionStorage.setItem("kgp_pt_ov:" + location.pathname, next); } catch (x) {}
    try { kgpToast("이 페이지를 '" + (next === "list" ? "목록(벌크)" : "단일 상품") + "'으로 강제했어요", true); } catch (x) {}
    kgpRefresh();
  });
}

// SPA 대응 + v53 STEP1: 페이지 타입 감지로 버튼 자동 전환(목록=중앙 바만, 단일/불능=우측 FAB만 — 동시 노출 0).
function kgpRefresh() {
  if (!kgpHostAllowed() && !kgpEntrySession()) { kgpTeardown(); return; }   // 지정 소싱처 또는 앱 진입(v10/v17)
  // v55 STEP5: URL별 캐시 판정 사용(재판정 안 함). inject*/remove*는 멱등(이미 마운트면 no-op) → 점멸 0.
  const pt = kgpPageType();
  if (pt === "list") {
    if (document.getElementById(KGP_BTN_ID)) kgpRemoveFab();   // 상호배타(있을 때만 제거)
    kgpInjectListing();                               // 중앙 바만(1.5배, 멱등)
    try { kgpAttachOverride(document.getElementById(KGP_TOOLBAR_ID)); } catch (e) {}
  } else {
    if (document.getElementById(KGP_TOOLBAR_ID) || document.getElementById(KGP_REOPEN_ID)) kgpRemoveListing();
    injectCollectButton();                            // 우측 단건 FAB만(멱등, 안전 기본값)
    try { kgpAttachOverride(document.getElementById(KGP_BTN_ID)); } catch (e) {}
  }
}

// 설정 로드 후 첫 렌더. 설정 바뀌면(소싱처 추가/삭제·토글·FAB on/off) 즉시 반영.
// v54 STEP2: 자가진단 모드 — ON이면 MAIN world(kgp-net 채점)에 진단 표를 콘솔 출력하도록 주기 요청.
let KGP_DIAG = false;
let _kgpDiagTimer = null;
function kgpDiagPing() { try { window.postMessage({ __kgpDiagReq: 1 }, "*"); } catch (e) {} }
function kgpDiagApply() {
  if (_kgpDiagTimer) { clearInterval(_kgpDiagTimer); _kgpDiagTimer = null; }
  if (KGP_DIAG) { setTimeout(kgpDiagPing, 1500); _kgpDiagTimer = setInterval(kgpDiagPing, 4000); }   // 응답이 들어오는 대로 표 갱신
}
function kgpLoadSourcesThen(cb) {
  try {
    chrome.storage.local.get(["kgp_sources", "kgp_fab_enabled", "kgp_diag", "kgp_hover_anchor"], (r) => {
      KGP_SOURCES = (r && r.kgp_sources) || {};
      KGP_FAB_ENABLED = !(r && r.kgp_fab_enabled === false);   // 기본 ON
      KGP_DIAG = !!(r && r.kgp_diag);                          // 진단 모드 기본 OFF
      KGP_HOVER_ANCHOR = (r && r.kgp_hover_anchor) || "center";  // v64 STEP3: 수집 버튼 위치
      kgpDiagApply();
      cb && cb();
    });
  } catch (e) { KGP_SOURCES = {}; cb && cb(); }
}
try {
  chrome.storage.onChanged.addListener((changes, area) => {
    let changed = false;
    if (changes && changes.kgp_sources) { KGP_SOURCES = changes.kgp_sources.newValue || {}; changed = true; }
    if (changes && changes.kgp_fab_enabled) {
      KGP_FAB_ENABLED = changes.kgp_fab_enabled.newValue !== false;
      if (!KGP_FAB_ENABLED) kgpRemoveFab();             // 끄면 즉시 제거
      changed = true;
    }
    if (changes && changes.kgp_diag) { KGP_DIAG = !!changes.kgp_diag.newValue; kgpDiagApply(); }
    if (changes && changes.kgp_hover_anchor) {          // v64 STEP3: 위치 변경 즉시 반영
      KGP_HOVER_ANCHOR = changes.kgp_hover_anchor.newValue || "center";
      document.querySelectorAll(".kgp-card-quick").forEach((q) => { q.style.cssText = kgpQuickBtnStyle(q.dataset.collected === "1", q.dataset.anchorMode || ""); });
    }
    if (changed) kgpRefresh();                          // 런타임 즉시 반영
  });
} catch (e) { /* noop */ }

kgpLoadSourcesThen(kgpRefresh);
let _kgpLastUrl = location.href;
setInterval(() => {
  if (location.href !== _kgpLastUrl) {
    _kgpLastUrl = location.href;
    // 새 페이지로 이동 → 닫음 상태/선택 초기화(다른 상품 목록이므로).
    _kgpClosed = false;
    _kgpAutoApplied = false;
    KGP_SELECTED.clear();
    _kgpCardByUrl = {};
    const _pill = document.getElementById(KGP_REOPEN_ID);
    if (_pill) _pill.remove();
    setTimeout(kgpRefresh, 900);
  }
}, 1500);
// v55 STEP5: 주기적 always-refresh(4초) 제거 — 점멸의 원인(지속 재판정). 재판정은 URL 변경 시로 한정.

// v55 STEP5: 재주입 전용 옵저버 — 우리 오버레이가 사이트 재렌더로 사라졌을 때만 **캐시된 판정 그대로** 재마운트.
//   DOM 변이 기반 '재판정'은 제거(kgpRefresh는 kgpPageType 캐시 사용 → 판정 번복 0). URL 변경은 history 훅으로.
(function () {
  let _t = null;
  function _remountIfGone() {
    if (_t) return;
    _t = setTimeout(() => {
      _t = null;
      try {
        if (!(kgpHostAllowed() || kgpEntrySession())) return;
        const gone = !document.getElementById(KGP_BTN_ID) && !document.getElementById(KGP_TOOLBAR_ID) && !document.getElementById(KGP_REOPEN_ID);
        if (gone) kgpRefresh();          // 사라졌을 때만 재마운트(캐시 판정 사용, 재판정 아님)
      } catch (e) {}
    }, 400);
  }
  function _onUrlChange() {
    // URL 변경 = 새 페이지 → 판정 재평가(새 URL은 캐시 없음). 상태 초기화는 아래 URL 폴링과 공유.
    if (_t) { clearTimeout(_t); _t = null; }
    try { if (kgpHostAllowed() || kgpEntrySession()) setTimeout(kgpRefresh, 300); } catch (e) {}
  }
  try {
    const obs = new MutationObserver(() => { _remountIfGone(); });   // 오버레이 소실 감지 전용(재판정 아님)
    const _start = () => { if (document.body) obs.observe(document.body, { childList: true, subtree: true }); else setTimeout(_start, 300); };
    _start();
  } catch (e) { /* MutationObserver 미지원 환경 무시 */ }
  // SPA: history API 후킹(pushState/replaceState/popstate) → URL 변경 시에만 재판정.
  try {
    ["pushState", "replaceState"].forEach((fn) => {
      const orig = history[fn];
      if (typeof orig === "function") {
        history[fn] = function () { const r = orig.apply(this, arguments); _onUrlChange(); return r; };
      }
    });
    window.addEventListener("popstate", _onUrlChange, { passive: true });
  } catch (e) { /* noop */ }
})();
