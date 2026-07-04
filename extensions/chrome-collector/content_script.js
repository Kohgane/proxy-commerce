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
function _kgpScopedPrice() {
  let nodes = [];
  try {
    nodes = Array.from(document.querySelectorAll('[class*="price" i],[class*="Price"],[itemprop="price"],[data-price],[class*="amount" i]'));
  } catch (e) { nodes = []; }
  for (const el of nodes) {
    if (_kgpInNonProd(el) || _kgpPriceIsOriginal(el)) continue;
    const raw = el.getAttribute("content") || el.getAttribute("data-price") || (el.textContent || "").trim();
    const p = _kgpParsePrice(raw);
    if (p) return p;
  }
  return { price: "", currency: "" };
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
    price: heuristicPrice,                 // v42 1-1: 렌더 DOM 현재가 우선(위에서 scoped→meta→본문 순 해결)
    currency: heuristicCurrency,           // 기본값 USD 금지 — 못 얻으면 빈 값 → 서버 '가격 확인 필요'
    description: _kgpRealDescription(),
    brand: getMeta("og:brand") || "",
    jsonld: jsonldScripts,
    html: pageHtml,
    collected_at: new Date().toISOString()
  };
}

// 백그라운드 서비스 워커 메시지 리스너
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "extractMeta") {
    sendResponse(extractProductMeta());
    return true;
  }
  // v42 E-5: 벌크 수집 진행률 실시간 갱신(background가 1건마다 전송).
  if (msg.action === "bulkProgress") {
    kgpSetStatus(`수집 중… (${msg.done}/${msg.total})`);
    return false;
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
function kgpCelebrate(added) {
  added = Math.max(1, added || 1);
  const total = kgpBumpCount(added);
  const prev = total - added;
  const milestones = [10, 50, 100, 300, 500, 1000];
  let milestone = 0;
  for (const m of milestones) { if (prev < m && total >= m) milestone = m; }
  if (KGP_RM) {
    kgpToast(`수집 완료 · 누적 ${total}건` + (milestone ? `\n${milestone}건 달성!` : ""), true);
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

function handleFabClick(btn) {
  if (btn._kgpDragged || btn.dataset.busy) return;
  setFabState(btn, "loading");
  const meta = extractProductMeta();
  kgpSendMessage({ action: "collect", meta }, (resp) => {
    setFabState(btn, "idle");
    if (!resp || resp.ok !== true) {
      kgpToast(((resp && resp.error) || "수집 실패"), false);
      return;
    }
    if (resp.duplicate === true) {   // v42 1-3: 이미 수집한 상품 — 새 항목 만들지 않고 안내(가짜 축하 0)
      kgpToast((resp.message || "이미 수집한 상품입니다.") + "\n셀러 콘솔의 수집 이력에서 확인하세요.", true);
      return;
    }
    kgpCelebrate(1);          // 실제 성공 시에만 도장+카운트업(따라하기 재미)
    const tk = resp.title_ko && resp.title_ko !== resp.title ? `\n→ ${resp.title_ko}` : "";
    if (tk) kgpToast(`수집 완료${tk}\n셀러 콘솔에서 확인·편집하세요.`, true);
  });
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
function _kgpInBadRegion(el) {
  let n = el;
  for (let i = 0; n && i < 9; i++, n = n.parentElement) {
    let cls = "";
    try { cls = (typeof n.className === "string" ? n.className : (n.getAttribute && n.getAttribute("class")) || ""); } catch (e) { cls = ""; }
    const tag = (n.tagName || "").toLowerCase();
    const meta = ((n.id || "") + " " + cls + " " + ((n.getAttribute && (n.getAttribute("aria-label") || n.getAttribute("data-component-type"))) || "")).toLowerCase();
    if (tag === "footer" || tag === "header" || tag === "nav") return true;
    if (/(footer|recommend|related|carousel|slider|sponsor|advert|\bads?\b|viewed|recently|history|also-?viewed|also-?bought|similar|banner|promo|deal-?strip|rcmd)/.test(meta)) return true;
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
  // s-search-result ∪ div[data-asin]:not([data-asin=""]) — 요소 단위 dedupe.
  const set = new Set();
  document.querySelectorAll('[data-component-type="s-search-result"], div[data-asin]:not([data-asin=""])')
    .forEach((e) => set.add(e));
  const all = Array.from(set);
  _kgpScannedCount = all.length;                          // '전체 N개' (상품/비상품 합)
  all.forEach((el) => {
    try {
      if (_kgpInBadRegion(el)) return;
      // 유효 ASIN(B0… 등 10자 영숫자)만 = 실제 상품. 뮤직/앱/프로모 위젯은 ASIN이 없거나 비정상.
      const asin = (el.getAttribute("data-asin") || "").trim();
      if (!/^[A-Z0-9]{10}$/.test(asin)) return;
      // 중첩(스폰서 컨테이너 안 상품 카드) 시 같은 ASIN을 가진 조상이 있으면 스킵(중복 방지).
      const parentAsin = el.parentElement && el.parentElement.closest('[data-asin]:not([data-asin=""])');
      if (parentAsin && parentAsin !== el && (parentAsin.getAttribute("data-asin") || "").trim() === asin) return;
      const sponsored = _kgpAmazonSponsored(el);           // v45 P3: 제외 아님 — 태깅만(스폰서 상품도 수집).
      // v42 E-4: 유효 ASIN이면 상품 — 앵커 셀렉터 변형·가격 없는 카드('옵션 보기' 등)도 누락하지 않는다.
      //   href는 앵커 없으면 ASIN으로 구성, 제목/이미지 셀렉터를 넓힌다. 가격은 선택.
      const a = el.querySelector('a.a-link-normal[href*="/dp/"], h2 a, a.a-link-normal.s-no-outline, a[href*="/dp/"]');
      let href = a && a.href ? a.href.split("?")[0].split("#")[0] : "";
      if (!href || href.indexOf("http") !== 0) href = location.origin + "/dp/" + asin;   // ASIN 폴백
      if (seen[href]) return;
      const img = el.querySelector("img.s-image") || el.querySelector("img");
      const titleEl = el.querySelector("h2 span") || el.querySelector("h2 a span") || el.querySelector("h2")
        || el.querySelector('[data-cy="title-recipe"] span') || el.querySelector(".a-size-base-plus, .a-size-medium");
      let title = titleEl ? (titleEl.innerText || titleEl.textContent || "").trim() : "";
      if (!title && img && img.alt) title = img.alt.trim();
      if (!title && !img) return;                           // 제목·이미지 둘 다 없으면 상품 아님
      const priceEl = el.querySelector(".a-price .a-offscreen") || el.querySelector(".a-price");
      const pr = _kgpPrice(priceEl ? priceEl.textContent : (el.innerText || ""));
      seen[href] = 1;
      const bimg = _kgpBestImg(img);                        // v41 X-1: lazy placeholder 대신 실제 이미지
      cards.push({
        url: href, title: (title || "(제목 없음)").slice(0, 200),
        image: bimg, images: bimg ? [bimg] : [], price: pr.price, currency: pr.currency,
        sponsored: sponsored, el: el,   /* v42 1-1: USD 기본값 금지 · v45 P3: 스폰서 태깅(제외 아님) */
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
      const a = img.closest("a[href]");
      if (!a || !a.href || a.href.indexOf("http") !== 0) continue;
      const href = a.href.split("#")[0];
      if (seen[href]) continue;
      const card = a.closest("li,article,div") || a;
      if (_kgpInBadRegion(card)) continue;                 // 추천/푸터/캐러셀 제외
      const text = (card.innerText || "").trim();
      const pr = _kgpPrice(text);
      const titleEl = card.querySelector("h1,h2,h3,h4,[class*='title'],[class*='name']");
      const title = ((img.alt || "").trim()) || (titleEl ? titleEl.innerText : "") || text;
      if (!title || title.trim().length < 4) continue;     // 제목 없으면 상품 후보 아님
      scanned++;                                           // 상품 후보(제목+이미지+링크+영역OK)
      // v43-2: 가격 또는 상세링크 중 하나면 상품 인식(가격만 필수였던 옛 규칙이 27중16 누락 유발).
      if (!pr.price && !_kgpIsDetailHref(href)) continue;  // 둘 다 없으면 제외(정직 카운트에 반영)
      seen[href] = 1;
      const bimg = _kgpBestImg(img) || img.src;             // v41 X-1: 실제 이미지 우선(placeholder 공유 방지)
      cards.push({
        url: href, title: title.trim().replace(/\s+/g, " ").slice(0, 200),
        image: bimg, images: bimg ? [bimg] : [], price: pr.price, currency: pr.currency, el: card,
      });
    }
  } catch (e) { /* noop */ }
  if (scanned > cards.length) _kgpScannedCount = scanned;   // v43-2: 정직 '전체 N 중 상품 M · 제외 K'
  return cards;
}

function kgpFindCards() {
  const host = (location.hostname || "").toLowerCase();
  _kgpScannedCount = 0;            // 매 스캔 초기화(어댑터가 '전체 N개'를 설정)
  let cards = [];
  try { if (/(^|\.)amazon\.[a-z.]+$/.test(host)) cards = _kgpAmazonCards(); } catch (e) { cards = []; }
  if (!cards.length) { try { cards = _kgpGenericCards(); } catch (e) { cards = []; } }
  return cards;
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

function kgpQuickBtnStyle(collected) {
  return [
    "position:absolute", "z-index:2147483639",
    KGP_TOUCH ? "top:6px" : "top:50%", KGP_TOUCH ? "right:6px" : "left:50%",
    KGP_TOUCH ? "" : "transform:translate(-50%,-50%)",
    "display:flex", "align-items:center", "gap:6px", "white-space:nowrap",
    KGP_TOUCH ? "padding:3px 8px" : "padding:7px 14px", "border-radius:999px", "cursor:pointer",
    "font:800 " + (KGP_TOUCH ? "10px" : "13px") + "/1 -apple-system,BlinkMacSystemFont,sans-serif",
    "background:" + (collected ? "#119a8e" : "#1a1714"), "color:#fff",
    "border:1.5px solid " + (collected ? "#0f8c80" : "#c9a24b"),
    "box-shadow:0 4px 14px rgba(0,0,0,.4)", "pointer-events:auto",
    "opacity:" + ((KGP_TOUCH || collected) ? "1" : "0"), "transition:opacity .12s",
  ].join(";");
}
function kgpMarkQuickCollected(btn) {
  btn.dataset.collected = "1";
  const lbl = btn.querySelector(".kgp-q-label");
  if (lbl) lbl.textContent = "수집됨 ✓";
  btn.style.cssText = kgpQuickBtnStyle(true);
  btn.style.cursor = "default";
}
function kgpQuickCollect(card, btn) {
  if (btn.dataset.collected === "1" || btn.dataset.busy === "1") return;
  btn.dataset.busy = "1";
  const lbl = btn.querySelector(".kgp-q-label");
  const prev = lbl ? lbl.textContent : "수집";
  if (lbl) lbl.textContent = "수집 중…";
  const meta = { url: card.url, title: card.title, image: card.image, images: card.images, price: card.price, currency: card.currency };
  kgpSendMessage({ action: "collectBulk", items: [meta] }, (resp) => {
    btn.dataset.busy = "";
    if (resp && resp.ok === true && ((resp.success || 0) > 0 || (resp.duplicate || 0) > 0)) {
      _kgpCollectedUrls.add(card.url);
      kgpMarkQuickCollected(btn);
      if ((resp.success || 0) > 0) kgpCelebrate(1);   // 실제 새 수집만 축하(중복은 조용)
    } else {
      if (lbl) lbl.textContent = prev;
      kgpToast((resp && resp.error) || "수집 실패", false);
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
  if (_kgpScannedCount > _kgpCards.length) {
    const miss = _kgpScannedCount - _kgpCards.length;
    c.textContent = `전체 ${_kgpScannedCount}개 중 상품 ${_kgpCards.length}개 · 제외 ${miss}(광고 등) · ${KGP_SELECTED.size}개 선택`;
  } else {
    c.textContent = `${_kgpCards.length}개 발견 · ${KGP_SELECTED.size}개 선택`;
  }
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
  });
}

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
    "z-index:2147483647", "display:flex", "align-items:center", "gap:10px",
    "padding:8px 14px", "border-radius:999px", "border:1px solid #c9a24b",
    "background:#1a1714", "color:#f5efe3",
    "font:13px/1.2 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    "box-shadow:0 8px 24px rgba(0,0,0,.45)", "max-width:94vw", "flex-wrap:wrap",
  ].join(";");
  // 버튼 위계: 전체 수집=청록 채움(Primary), 선택 수집=금 아웃라인(Secondary), 전체선택/해제=고스트.
  const btnBase = "padding:5px 11px;border-radius:8px;cursor:pointer;font-weight:700;font-size:12px;";
  const ghost = btnBase + "background:transparent;color:#e7ddc9;border:1px solid #4a4234;";
  const gold = btnBase + "background:transparent;color:#e8d6a8;border:1.5px solid #c9a24b;";
  const teal = btnBase + "background:#119a8e;color:#fff;border:1px solid #0f8c80;";
  const autoOn = kgpLSget("kgp_bar_auto", "1") !== "0";
  bar.innerHTML =
    '<span id="kgp-tb-grip" style="display:flex;align-items:center;gap:7px">' +
    '<span style="display:flex;align-items:center;justify-content:center;width:26px;height:26px;background:transparent;border:0">' + KGP_BRIDGE_SVG + '</span>' +
    '<strong style="color:#ecdcb0">고가수집기</strong></span>' +
    '<span id="kgp-tb-count" style="opacity:.85"></span>' +
    '<span style="width:1px;height:18px;background:#4a4234"></span>' +
    '<button class="kgp-tb-btn" data-act="all-sel" style="' + ghost + '">전체 선택</button>' +
    '<button class="kgp-tb-btn" data-act="clear" style="' + ghost + '">선택 해제</button>' +
    '<button class="kgp-tb-btn" data-act="collect-sel" style="' + gold + '">선택 수집</button>' +
    '<button class="kgp-tb-btn" data-act="collect-all" style="' + teal + '">전체 수집</button>' +
    '<span id="kgp-tb-status" style="opacity:.95;font-size:12px;max-width:360px"></span>' +
    '<button class="kgp-tb-btn" data-act="auto" title="새 목록 페이지에서 자동으로 열지 여부" style="' + ghost + '">' + (autoOn ? '자동' : '수동') + '</button>' +
    '<button data-act="close" title="접기(구석 배지로)" style="' + btnBase + 'background:transparent;color:#c9bda6;border:none;font-size:15px">✕</button>';
  bar.addEventListener("click", (e) => {
    const t = e.target.closest("[data-act]");
    if (!t) return;
    const act = t.dataset.act;
    if (act === "all-sel") {
      document.querySelectorAll(".kgp-card-chk").forEach((b) => {
        const url = b.dataset.url;
        const c = _kgpCardByUrl[url];
        kgpSetCardSelected(url, b, c && c.el, true);
      });
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
      kgpCollect(Object.keys(_kgpCardByUrl));
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

      // v42 E-3: 호버 즉시 수집 버튼(썸네일 중앙, 데스크톱=hover 노출/터치=우상단 상시).
      if (!c.el.querySelector(":scope > .kgp-card-quick")) {
        const done = _kgpCollectedUrls.has(c.url);
        const q = document.createElement("div");
        q.className = "kgp-card-quick";
        q.dataset.url = c.url;
        if (done) q.dataset.collected = "1";
        q.innerHTML = '<span style="display:flex;width:14px;height:14px;flex:none">' + KGP_BRIDGE_MINI +
          '</span><span class="kgp-q-label">' + (done ? "수집됨 ✓" : "수집") + "</span>";
        q.style.cssText = kgpQuickBtnStyle(done);
        q.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); kgpQuickCollect(c, q); });
        if (!KGP_TOUCH) {
          c.el.addEventListener("mouseenter", () => { if (q.dataset.collected !== "1") q.style.opacity = "1"; });
          c.el.addEventListener("mouseleave", () => { if (q.dataset.collected !== "1") q.style.opacity = "0"; });
        }
        c.el.appendChild(q);
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

// SPA 대응 + v11 P0: 페이지 종류에 따라 버튼 자동 전환(목록=중앙 바만, 상세=우측 FAB만 — 동시 노출 0).
function kgpRefresh() {
  if (!kgpHostAllowed() && !kgpEntrySession()) { kgpTeardown(); return; }   // 지정 소싱처 또는 앱 진입(v10/v17)
  const cards = kgpFindCards();
  const isList = cards.length >= 3;                   // 제품 그리드(여러 제품) = 목록
  if (isList) {
    kgpRemoveFab();                                   // 목록: 우측 FAB 숨김
    kgpInjectListing();                               // 중앙 바만
  } else {
    kgpRemoveListing();                               // 상세: 중앙 바/배지 숨김
    injectCollectButton();                            // 우측 FAB만(looksLikeProductPage/디테일 URL 가드)
  }
}

// 설정 로드 후 첫 렌더. 설정 바뀌면(소싱처 추가/삭제·토글·FAB on/off) 즉시 반영.
function kgpLoadSourcesThen(cb) {
  try {
    chrome.storage.local.get(["kgp_sources", "kgp_fab_enabled"], (r) => {
      KGP_SOURCES = (r && r.kgp_sources) || {};
      KGP_FAB_ENABLED = !(r && r.kgp_fab_enabled === false);   // 기본 ON
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
// 동적 로딩(무한 스크롤)·지연 렌더 대응: 주기적으로 모드 재평가(목록↔상세 자동 전환).
setInterval(() => { if (kgpHostAllowed()) kgpRefresh(); }, 4000);

// v38 #4: MutationObserver로 SPA 라우팅/사이트 재렌더에도 버튼을 일관 유지(재주입).
//   사이트가 본문을 갈아끼우며 우리 FAB/바를 날려도, 또는 늦게 렌더되는 SPA에서도 즉시 복구.
//   URL 변경(history.pushState) 감지도 겸해 setTimeout 디바운스로 과도호출 방지.
(function () {
  let _t = null;
  function _scheduleRefresh() {
    if (_t) return;
    _t = setTimeout(() => { _t = null; try { if (kgpHostAllowed() || kgpEntrySession()) kgpRefresh(); } catch (e) {} }, 400);
  }
  try {
    const obs = new MutationObserver((muts) => {
      // 우리 오버레이가 사라졌거나(사이트 재렌더) 본문이 크게 바뀌면 재주입.
      const fabGone = !document.getElementById(KGP_BTN_ID) && !document.getElementById(KGP_TOOLBAR_ID) && !document.getElementById(KGP_REOPEN_ID);
      if (fabGone || muts.some(m => m.addedNodes && m.addedNodes.length)) _scheduleRefresh();
    });
    const _start = () => { if (document.body) obs.observe(document.body, { childList: true, subtree: true }); else setTimeout(_start, 300); };
    _start();
  } catch (e) { /* MutationObserver 미지원 환경 무시 */ }
  // SPA: history API 후킹(pushState/replaceState/popstate) → 라우팅 즉시 재평가.
  try {
    ["pushState", "replaceState"].forEach((fn) => {
      const orig = history[fn];
      if (typeof orig === "function") {
        history[fn] = function () { const r = orig.apply(this, arguments); _scheduleRefresh(); return r; };
      }
    });
    window.addEventListener("popstate", _scheduleRefresh, { passive: true });
  } catch (e) { /* noop */ }
})();
