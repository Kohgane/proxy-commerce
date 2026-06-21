/**
 * content_script.js — 페이지 컨텍스트에서 메타 추출 + 인페이지 '수집' 버튼 (Phase 202)
 * 코고가네 수집기
 *
 * 1) 백그라운드/팝업에서 "extractMeta" 메시지 요청 시 메타 응답.
 * 2) 상품 페이지로 판단되면 우하단에 떠 있는 '수집' 버튼을 주입한다.
 *    버튼 클릭 → 메타 추출 → background로 전송(번역은 서버에서 수행) → 인페이지 토스트.
 */

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
  const _isProductImg = (s) =>
    s && s.indexOf("data:") !== 0 &&
    !/(logo|sprite|icon|favicon|avatar|placeholder|loading|blank|pixel|banner|badge|rating|star_|flag_|emoji)/i.test(s);
  const images = [];
  const _seenImg = new Set();
  const _pushImg = (s) => { if (_isProductImg(s) && !_seenImg.has(s)) { _seenImg.add(s); images.push(s); } };
  if (ogImage) _pushImg(ogImage);
  try {
    document.querySelectorAll("img").forEach((im) => {
      let src = im.currentSrc || im.src || im.getAttribute("data-src") || im.getAttribute("data-original") || "";
      if (!src && im.getAttribute("srcset")) {
        const parts = im.getAttribute("srcset").split(",");
        src = (parts[parts.length - 1] || "").trim().split(" ")[0];
      }
      const w = im.naturalWidth || im.width || 0;
      const h = im.naturalHeight || im.height || 0;
      if (src && w >= 250 && h >= 250) _pushImg(src);
    });
  } catch (e) { /* noop */ }

  // 가격 휴리스틱 (og:price 없을 때)
  let heuristicPrice = "";
  let heuristicCurrency = "";
  if (!getMeta("product:price:amount")) {
    const pricePatterns = [
      /[¥￥]\s*([\d,]+)/,
      /\$([\d,]+(?:\.\d{1,2})?)/,
      /€\s*([\d,]+(?:\.\d{1,2})?)/,
      /₩\s*([\d,]+)/
    ];
    const bodyText = document.body ? document.body.innerText.slice(0, 3000) : "";
    for (const pattern of pricePatterns) {
      const m = bodyText.match(pattern);
      if (m) {
        heuristicPrice = m[1].replace(/,/g, "");
        if (pattern.source.includes("¥") || pattern.source.includes("￥")) {
          heuristicCurrency = "JPY";
        } else if (pattern.source.includes("\\$")) {
          heuristicCurrency = "USD";
        } else if (pattern.source.includes("€")) {
          heuristicCurrency = "EUR";
        } else if (pattern.source.includes("₩")) {
          heuristicCurrency = "KRW";
        }
        break;
      }
    }
  }

  // 봇 차단(403) 사이트도 수집되도록 페이지 HTML을 함께 전송 → 서버가 파싱(가격/이미지/옵션 보강).
  // 대용량 방지를 위해 상한(600KB)으로 자른다.
  let pageHtml = "";
  try {
    pageHtml = (document.documentElement ? document.documentElement.outerHTML : "").slice(0, 600000);
  } catch (e) {
    pageHtml = "";
  }

  return {
    url: location.href,
    title: getMeta("og:title") || document.title || "",
    image: ogImage,
    images: images,
    price: getMeta("product:price:amount") || heuristicPrice,
    currency: getMeta("product:price:currency") || heuristicCurrency || "USD",
    description: getMeta("og:description") || getMeta("description") || "",
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
  return false;
});

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
    btn.querySelector(".kgp-fab-label").textContent = "코고가네 수집";
  }
}

// 코고가네 글로브 모노그램(먹 글로브 + 금 링 + 청록 궤도) — 코고가네 디자인 토큰.
// 네이비+주황 폐기(v4). 우아·세련·은은하되 금 링/청록으로 식별.
const KGP_GLOBE_SVG =
  '<svg width="20" height="20" viewBox="0 0 512 512" aria-hidden="true" style="display:block">' +
  '<circle cx="256" cy="256" r="150" fill="#1a1714"/>' +
  '<circle cx="256" cy="256" r="150" fill="none" stroke="#c9a24b" stroke-width="12"/>' +
  '<ellipse cx="256" cy="256" rx="210" ry="76" fill="none" stroke="#c9a24b" stroke-width="16" opacity="0.55" transform="rotate(32 256 256)"/>' +
  '<ellipse cx="256" cy="256" rx="210" ry="76" fill="none" stroke="#119a8e" stroke-width="20" transform="rotate(-32 256 256)"/>' +
  '<circle cx="256" cy="256" r="40" fill="#119a8e"/>' +
  '</svg>';

function handleFabClick(btn) {
  if (btn.dataset.busy) return;
  setFabState(btn, "loading");
  const meta = extractProductMeta();
  try {
    chrome.runtime.sendMessage({ action: "collect", meta }, (resp) => {
      setFabState(btn, "idle");
      if (chrome.runtime.lastError) {
        kgpToast("확장 연결 실패: " + chrome.runtime.lastError.message, false);
        return;
      }
      if (resp && resp.ok) {
        const tk = resp.title_ko && resp.title_ko !== resp.title ? `\n→ ${resp.title_ko}` : "";
        kgpToast(`✅ 수집 완료${tk}\n셀러 콘솔에서 확인·편집하세요.`, true);
      } else {
        kgpToast("❌ " + ((resp && resp.error) || "수집 실패"), false);
      }
    });
  } catch (err) {
    setFabState(btn, "idle");
    kgpToast("❌ " + (err.message || "수집 실패"), false);
  }
}

function injectCollectButton() {
  if (document.getElementById(KGP_BTN_ID)) return;
  if (window.top !== window.self) return;       // iframe 안에서는 표시 안 함
  if (!document.body) return;
  if (!looksLikeProductPage()) return;

  const btn = document.createElement("button");
  btn.id = KGP_BTN_ID;
  btn.type = "button";
  btn.innerHTML =
    '<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;' +
    'background:#0f0d0b;border:1px solid #c9a24b;border-radius:50%;flex-shrink:0">' + KGP_GLOBE_SVG + '</span>' +
    '<span style="display:flex;flex-direction:column;align-items:flex-start;line-height:1.12">' +
    '<span class="kgp-fab-label" style="font-weight:700;font-size:14px;color:#f5efe3">코고가네 수집</span>' +
    '<span style="font-size:10px;color:#c9a24b;font-family:Georgia,\'Times New Roman\',serif">번역까지 한 번에</span>' +
    '</span>';
  btn.title = "코고가네로 수집 (한국어 번역 포함)";
  // 코고가네 토큰: 먹 매트 pill + 금 얇은 링 + 청록 미세 악센트. (네이비+주황 폐기, v4)
  // 위치: 우측 가장자리 상단부(콘텐츠 안 가리게 살짝 안쪽).
  btn.style.cssText = [
    "position:fixed", "right:16px", "top:120px", "z-index:2147483646",
    "display:flex", "align-items:center", "gap:10px",
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
  document.body.appendChild(btn);

  // 처음 등장 시 한 번 살짝 강조(인지성↑, 과하지 않게 1.2초)
  btn.animate(
    [{ transform: "scale(1)" }, { transform: "scale(1.06)" }, { transform: "scale(1)" }],
    { duration: 600, iterations: 2, easing: "ease-in-out" }
  );
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

function kgpFindCards() {
  const cards = [];
  const seen = {};
  try {
    const imgs = document.querySelectorAll("img");
    for (let i = 0; i < imgs.length; i++) {
      const img = imgs[i];
      const w = img.naturalWidth || img.width || 0;
      const h = img.naturalHeight || img.height || 0;
      if (w < 120 || h < 120) continue;
      const a = img.closest("a[href]");
      if (!a || !a.href || a.href.indexOf("http") !== 0) continue;
      const href = a.href.split("#")[0];
      if (seen[href]) continue;
      const card = a.closest("li,article,div") || a;
      const text = (card.innerText || "").trim();
      const pr = _kgpPrice(text);
      if (!pr.price) continue;  // 가격 없는 블록은 상품 카드로 보지 않음(오탐 감소)
      const titleEl = card.querySelector("h1,h2,h3,h4,[class*='title'],[class*='name']");
      const title = (img.alt || "").trim() || (titleEl ? titleEl.innerText : "") || text;
      seen[href] = 1;
      cards.push({
        url: href,
        title: (title || "").trim().replace(/\s+/g, " ").slice(0, 200),
        image: img.src, images: [img.src],
        price: pr.price, currency: pr.currency, el: card,
      });
    }
  } catch (e) { /* noop */ }
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

function kgpUpdateToolbar() {
  const c = document.getElementById("kgp-tb-count");
  if (c) c.textContent = `${_kgpCards.length}개 발견 · ${KGP_SELECTED.size}개 선택`;
}

async function kgpCollect(urls) {
  const items = (urls || []).map(u => _kgpCardByUrl[u]).filter(Boolean).map(c => (
    { url: c.url, title: c.title, image: c.image, images: c.images, price: c.price, currency: c.currency }
  ));
  if (!items.length) { kgpSetStatus("선택된 상품이 없어요. 상품의 ‘수집’ 배지를 눌러 선택하세요."); return; }
  kgpSetStatus(`수집 중… (0/${items.length})`);
  const btns = document.querySelectorAll(".kgp-tb-btn");
  btns.forEach(b => b.disabled = true);
  try {
    chrome.runtime.sendMessage({ action: "collectBulk", items }, (resp) => {
      btns.forEach(b => b.disabled = false);
      if (chrome.runtime.lastError) { kgpSetStatus("확장 연결 실패: " + chrome.runtime.lastError.message); return; }
      if (resp && resp.ok) {
        kgpSetStatus(`✅ 수집 완료 — 성공 ${resp.success} / 실패 ${resp.failed}. 셀러 콘솔 수집 이력에서 확인하세요.`);
      } else {
        kgpSetStatus("❌ " + ((resp && resp.error) || "수집 실패"));
      }
    });
  } catch (err) {
    btns.forEach(b => b.disabled = false);
    kgpSetStatus("❌ " + (err.message || "수집 실패"));
  }
}

function kgpBuildToolbar() {
  const bar = document.createElement("div");
  bar.id = KGP_TOOLBAR_ID;
  bar.style.cssText = [
    "position:fixed", "top:12px", "left:50%", "transform:translateX(-50%)",
    "z-index:2147483646", "display:flex", "align-items:center", "gap:10px",
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
  bar.innerHTML =
    '<span style="display:flex;align-items:center;justify-content:center;width:24px;height:24px;background:#0f0d0b;border:1px solid #c9a24b;border-radius:50%">' + KGP_GLOBE_SVG + '</span>' +
    '<strong style="color:#ecdcb0">코고가네 수집</strong>' +
    '<span id="kgp-tb-count" style="opacity:.85"></span>' +
    '<span style="width:1px;height:18px;background:#4a4234"></span>' +
    '<button class="kgp-tb-btn" data-act="all-sel" style="' + ghost + '">전체 선택</button>' +
    '<button class="kgp-tb-btn" data-act="clear" style="' + ghost + '">선택 해제</button>' +
    '<button class="kgp-tb-btn" data-act="collect-sel" style="' + gold + '">선택 수집</button>' +
    '<button class="kgp-tb-btn" data-act="collect-all" style="' + teal + '">전체 수집</button>' +
    '<span id="kgp-tb-status" style="opacity:.95;font-size:12px;max-width:360px"></span>' +
    '<button data-act="close" title="닫기" style="' + btnBase + 'background:transparent;color:#c9bda6;border:none;font-size:15px">✕</button>';
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
    } else if (act === "close") {
      // 닫으면 같은 페이지에서 자동으로 다시 뜨지 않게 한다(URL 변경 시 초기화).
      // 대신 작은 '다시 열기' 알약을 남겨 사용자가 켜고 끌 수 있게 한다(선택은 유지).
      _kgpClosed = true;
      bar.remove();
      document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove());
      kgpShowReopenPill();
    }
  });
  document.body.appendChild(bar);
}

const KGP_REOPEN_ID = "kgp-listing-reopen";

// 닫았을 때 화면 좌상단에 작은 '코고가네 수집 열기' 알약 → 클릭 시 바를 다시 띄운다.
function kgpShowReopenPill() {
  if (document.getElementById(KGP_REOPEN_ID) || !document.body) return;
  const pill = document.createElement("button");
  pill.id = KGP_REOPEN_ID;
  pill.type = "button";
  pill.title = "코고가네 수집 바 다시 열기";
  pill.innerHTML =
    '<span style="display:flex;align-items:center;justify-content:center;width:20px;height:20px;background:#0f0d0b;border:1px solid #c9a24b;border-radius:50%">' + KGP_GLOBE_SVG + '</span>' +
    '<span style="font-weight:700;font-size:12px">수집 열기</span>';
  pill.style.cssText = [
    "position:fixed", "top:12px", "left:12px", "z-index:2147483646",
    "display:flex", "align-items:center", "gap:6px", "padding:5px 10px 5px 6px",
    "border:1px solid #c9a24b", "border-radius:999px",
    "background:#1a1714", "color:#f5efe3",
    "cursor:pointer", "box-shadow:0 4px 14px rgba(10,31,92,.45)",
    "font:12px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
  ].join(";");
  pill.addEventListener("click", () => {
    pill.remove();
    _kgpClosed = false;
    kgpInjectListing();          // 바 + 배지 복원(선택 유지)
  });
  document.body.appendChild(pill);
}

function kgpInjectListing() {
  if (window.top !== window.self || !document.body) return;
  if (_kgpClosed) return;                        // 사용자가 닫음 → 자동 재생성 안 함(알약으로만 재오픈)
  const cards = kgpFindCards();
  if (cards.length < 3) {                        // 리스팅 아님 → 정리
    const ex = document.getElementById(KGP_TOOLBAR_ID);
    if (ex) { ex.remove(); document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove()); }
    return;
  }
  // 재스캔(무한스크롤/동적로딩)에도 선택을 지우지 않는다.
  // ★중요★ 카드맵을 비우지 않고 '병합'한다 — 비우면 선택된 url의 카드 데이터가 사라져
  //   '선택 수집/전체 수집'이 '선택된 상품 없음'으로 실패하던 버그(오너 리포트) 방지.
  _kgpCards = cards;
  cards.forEach((c) => { _kgpCardByUrl[c.url] = c; });
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
    } catch (e) { /* noop */ }
  });
  if (!document.getElementById(KGP_TOOLBAR_ID)) kgpBuildToolbar();
  kgpUpdateToolbar();
}

// SPA 대응: 최초 + URL 변경 시 재시도 (단일 상품 FAB + 리스팅 다중수집)
function kgpRefresh() {
  injectCollectButton();
  kgpInjectListing();
}
kgpRefresh();
let _kgpLastUrl = location.href;
setInterval(() => {
  if (location.href !== _kgpLastUrl) {
    _kgpLastUrl = location.href;
    // 새 페이지로 이동 → 닫음 상태/선택 초기화(다른 상품 목록이므로).
    _kgpClosed = false;
    KGP_SELECTED.clear();
    _kgpCardByUrl = {};
    const _pill = document.getElementById(KGP_REOPEN_ID);
    if (_pill) _pill.remove();
    setTimeout(kgpRefresh, 900);
  }
}, 1500);
// 동적 로딩(무한 스크롤) 대응: 주기적으로 리스팅 재스캔
setInterval(kgpInjectListing, 4000);
