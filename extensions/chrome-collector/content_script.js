/**
 * content_script.js — 페이지 컨텍스트에서 메타 추출 + 인페이지 '수집' 버튼 (Phase 202+)
 * 고가수집기
 *
 * 1) 백그라운드/팝업에서 "extractMeta" 메시지 요청 시 메타 응답.
 * 2) v10: '지정 소싱처' 도메인에서만 수집 UI(FAB/리스팅 바)를 주입한다(그 외 사이트엔 아무것도 안 그림).
 *    소싱처는 기본셋 + 사용자 지정(chrome.storage.local의 kgp_sources)로 관리, 런타임 즉시 반영.
 * 3) 리스팅은 사이트 어댑터(아마존 등) + 엄격 휴리스틱으로 '실제 제품 카드만' 감지(추천/푸터/썸네일 제외).
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
  // v11 P0: 무관 이미지(플래그·태그·픽셀·문서아이콘·화살표 등) 제외 — 서버 블랙리스트와 동일.
  const _isProductImg = (s) =>
    s && s.indexOf("data:") !== 0 &&
    !/(logo|sprite|icon|favicon|avatar|placeholder|loading|blank|pixel|spinner|banner|badge|button|arrow|chevron|caret|rating|star_|flags?|emoji|openingemail|supplier-public-tag|public-tag|\.slim\.|tracking|beacon|watermark|qr[-_]?code|coupon|nav_|\/pdf|pdf[-_]|\.pdf|\.doc|doc[-_]icon|\/doc\/|1x1|transparent\.|spacer)/i.test(s);
  const images = [];
  const _seenImg = new Set();
  const _pushImg = (s) => { if (_isProductImg(s) && !_seenImg.has(s)) { _seenImg.add(s); images.push(s); } };
  // v16 P0: 추천/연관/함께 본/스폰서/푸터 등 '다른 상품' 영역의 이미지는 제외(PDD 스코프, 혼입 방지).
  const _kgpNonProductRe = /(recommend|related|similar|also[-_ ]?(bought|viewed|like)|you[-_ ]?may|frequently[-_ ]?bought|sponsored|advert|promotion|ranking|best[-_ ]?seller|recently[-_ ]?viewed|carousel|slider|cross[-_ ]?sell|up[-_ ]?sell|comparison|footer|navbar|breadcrumb|other[-_ ]?products|popular|trending)/i;
  const _kgpInNonProductRegion = (el) => {
    let cur = el && el.parentElement, depth = 0;
    while (cur && depth < 8) {
      const tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && _kgpNonProductRe.test(tok)) return true;
      cur = cur.parentElement; depth++;
    }
    return false;
  };
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
      if (src && w >= 250 && h >= 250 && !_kgpInNonProductRegion(im)) _pushImg(src);
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

  // v16 P0: 사이트 공통 마케팅 필러(상품 설명 아님)는 보내지 않는다 — 서버 필러 가드와 동일 취지.
  const _kgpFiller = /(절약을\s*시작|쇼핑하여\s*절약|에서\s*쇼핑하여|최저가로\s*쇼핑|지금\s*쇼핑하세요|여기를\s*눌러|링크를\s*확인하세요|smarter\s+shopping|start\s+saving|save\s+big|free\s+shipping\s+on\s+(all\s+)?orders)/i;
  // 실제 상품 설명 우선: 설명 섹션 요소 텍스트 → 없으면 필러 아닌 og:description.
  function _kgpRealDescription() {
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
    image: ogImage,
    images: images,
    price: getMeta("product:price:amount") || heuristicPrice,
    currency: getMeta("product:price:currency") || heuristicCurrency || "USD",
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
    btn.querySelector(".kgp-fab-label").textContent = "고가수집기 수집";
  }
}

// 고가브릿지 게이트웨이(B) 마크 — 공식 브랜드 자산과 동일(금 아치 + 청록 다리 + 주황 키스톤).
// v21/v22: 글러브/지구본 폐기. (어두운 원형 배지 위 배치라 fill 없는 스트로크 아치)
const KGP_GLOVE_SVG =
  '<svg width="20" height="20" viewBox="0 0 512 512" aria-hidden="true" style="display:block">' +
  '<path d="M180 372 L180 240 A76 76 0 0 1 332 240 L332 372" fill="none" stroke="#c9a24b" stroke-width="26" stroke-linecap="round"/>' +
  '<line x1="150" y1="380" x2="362" y2="380" stroke="#119a8e" stroke-width="16" stroke-linecap="round"/>' +
  '<circle cx="256" cy="164" r="20" fill="#f5821f"/>' +
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

// 수집 누적 카운트 + 마일스톤 축하(실제 성공 시에만 호출).
function kgpBumpCount(n) {
  let c = parseInt(kgpLSget("kgp_collect_count", "0"), 10) || 0;
  c += (n || 0); kgpLSset("kgp_collect_count", String(c));
  return c;
}
const KGP_WIT = [
  "오늘도 한 건 +1 🧤", "담았습니다. 다음 상품 가시죠 🚀", "착! 도장 쾅 🟢",
  "글러브 장착, 수집 완료 🧤", "마진은 셀러님 몫 💰",
];
function kgpCelebrate(added) {
  added = Math.max(1, added || 1);
  const total = kgpBumpCount(added);
  const prev = total - added;
  const milestones = [10, 50, 100, 300, 500, 1000];
  let milestone = 0;
  for (const m of milestones) { if (prev < m && total >= m) milestone = m; }
  if (KGP_RM) {
    kgpToast(`✅ 수집 완료 · 누적 ${total}건` + (milestone ? `\n🏅 ${milestone}건 달성!` : ""), true);
    return total;
  }
  kgpEnsureStyles();
  const ov = document.createElement("div");
  ov.style.cssText = "position:fixed;right:24px;bottom:96px;z-index:2147483647;pointer-events:none;display:flex;flex-direction:column;align-items:flex-end;gap:6px";
  const stamp = document.createElement("div");
  stamp.style.cssText = "display:flex;align-items:center;gap:8px;padding:10px 16px;border-radius:14px;background:#1a1714;border:2px solid #c9a24b;color:#f5efe3;font:700 14px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.45);animation:kgpStampIn .5s ease-out both";
  stamp.innerHTML = '<span style="font-size:20px">🧤</span><span>' + KGP_WIT[Math.floor(Math.random() * KGP_WIT.length)] + "</span>";
  ov.appendChild(stamp);
  const counter = document.createElement("div");
  counter.style.cssText = "padding:5px 12px;border-radius:999px;background:#119a8e;color:#fff;font:700 12px/1 -apple-system,sans-serif;animation:kgpStampIn .5s ease-out both";
  ov.appendChild(counter);
  if (milestone) {
    const badge = document.createElement("div");
    badge.style.cssText = "padding:6px 14px;border-radius:999px;background:#c9a24b;color:#1a1714;font:800 13px/1 -apple-system,sans-serif;animation:kgpStampIn .55s ease-out both";
    badge.textContent = "🏅 " + milestone + "건 달성!";
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
      kgpToast("❌ " + ((resp && resp.error) || "수집 실패"), false);
      return;
    }
    kgpCelebrate(1);          // 실제 성공 시에만 도장+카운트업(따라하기 재미)
    const tk = resp.title_ko && resp.title_ko !== resp.title ? `\n→ ${resp.title_ko}` : "";
    if (tk) kgpToast(`✅ 수집 완료${tk}\n셀러 콘솔에서 확인·편집하세요.`, true);
  });
}

function injectCollectButton() {
  // v16 P1: FAB off면 표시 안 함 — 단, v17: 앱에서 띄운 진입 세션이면 강제 노출.
  if (!KGP_FAB_ENABLED && !kgpEntrySession()) { kgpRemoveFab(); return; }
  if (!kgpHostAllowed() && !kgpEntrySession()) return;   // 지정 소싱처 또는 앱 진입 세션(v10/v17)
  if (document.getElementById(KGP_BTN_ID)) return;
  if (window.top !== window.self) return;       // iframe 안에서는 표시 안 함
  if (!document.body) return;
  if (!looksLikeProductPage() && !kgpIsDetailUrl()) return;   // 상세 페이지(메타 또는 URL 패턴)

  const btn = document.createElement("button");
  btn.id = KGP_BTN_ID;
  btn.type = "button";
  btn.innerHTML =
    '<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;' +
    'background:#0f0d0b;border:1px solid #c9a24b;border-radius:50%;flex-shrink:0">' + KGP_GLOVE_SVG + '</span>' +
    '<span style="display:flex;flex-direction:column;align-items:flex-start;line-height:1.12">' +
    '<span class="kgp-fab-label" style="font-weight:700;font-size:14px;color:#f5efe3">고가수집기 수집</span>' +
    '<span style="font-size:10px;color:#c9a24b;font-family:Georgia,\'Times New Roman\',serif">번역까지 한 번에</span>' +
    '</span>';
  btn.title = "고가브릿지로 수집 (한국어 번역 포함)";
  // 고가브릿지 토큰: 먹 매트 pill + 금 얇은 링 + 청록 미세 악센트. (네이비+주황 폐기, v4)
  // 위치: 우측 '중앙'(v7) — 콘텐츠 안 가리게. 드래그로 옮기면 위치 기억(kgp_fab_pos).
  btn.style.cssText = [
    "position:fixed", "right:16px", "top:calc(50% - 24px)", "z-index:2147483646",
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
  document.body.appendChild(btn);
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

// 아마존 검색결과 어댑터 — 실제 제품 카드 컨테이너만.
function _kgpAmazonCards() {
  const cards = [], seen = {};
  document.querySelectorAll('[data-component-type="s-search-result"]').forEach((el) => {
    try {
      if (_kgpInBadRegion(el)) return;
      const a = el.querySelector('a.a-link-normal[href*="/dp/"], h2 a, a.a-link-normal.s-no-outline');
      const href = a && a.href ? a.href.split("?")[0].split("#")[0] : "";
      if (!href || href.indexOf("http") !== 0 || seen[href]) return;
      const img = el.querySelector("img.s-image") || el.querySelector("img");
      const titleEl = el.querySelector("h2 span") || el.querySelector("h2");
      const priceEl = el.querySelector(".a-price .a-offscreen") || el.querySelector(".a-price");
      const pr = _kgpPrice(priceEl ? priceEl.textContent : (el.innerText || ""));
      if (!img || !titleEl || !pr.price) return;            // 제목+가격+링크+이미지 모두 있어야 제품
      seen[href] = 1;
      cards.push({
        url: href, title: (titleEl.innerText || titleEl.textContent || "").trim().slice(0, 200),
        image: img.src, images: [img.src], price: pr.price, currency: pr.currency || "USD", el: el,
      });
    } catch (e) { /* noop */ }
  });
  return cards;
}

// 엄격 폴백 휴리스틱 — 제목+가격+제품링크+충분히 큰 이미지를 '모두' 가질 때만 제품.
function _kgpGenericCards() {
  const cards = [], seen = {};
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
      if (!pr.price) continue;                             // 가격 필수
      const titleEl = card.querySelector("h1,h2,h3,h4,[class*='title'],[class*='name']");
      const title = ((img.alt || "").trim()) || (titleEl ? titleEl.innerText : "") || text;
      if (!title || title.trim().length < 4) continue;     // 제목 필수
      seen[href] = 1;
      cards.push({
        url: href, title: title.trim().replace(/\s+/g, " ").slice(0, 200),
        image: img.src, images: [img.src], price: pr.price, currency: pr.currency, el: card,
      });
    }
  } catch (e) { /* noop */ }
  return cards;
}

function kgpFindCards() {
  const host = (location.hostname || "").toLowerCase();
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
  kgpSendMessage({ action: "collectBulk", items }, (resp) => {
    btns.forEach(b => b.disabled = false);
    if (!resp || resp.ok !== true) { kgpSetStatus("❌ " + ((resp && resp.error) || "수집 실패")); return; }
    if (resp.success > 0) kgpCelebrate(resp.success);   // 실제 성공 건수만 축하
    kgpSetStatus(`✅ 수집 완료 — 성공 ${resp.success} / 실패 ${resp.failed}. 셀러 콘솔 수집 이력에서 확인하세요.`);
  });
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
  const autoOn = kgpLSget("kgp_bar_auto", "1") !== "0";
  bar.innerHTML =
    '<span id="kgp-tb-grip" style="display:flex;align-items:center;gap:7px">' +
    '<span style="display:flex;align-items:center;justify-content:center;width:24px;height:24px;background:#0f0d0b;border:1px solid #c9a24b;border-radius:50%">' + KGP_GLOVE_SVG + '</span>' +
    '<strong style="color:#ecdcb0">고가수집기 수집</strong></span>' +
    '<span id="kgp-tb-count" style="opacity:.85"></span>' +
    '<span style="width:1px;height:18px;background:#4a4234"></span>' +
    '<button class="kgp-tb-btn" data-act="all-sel" style="' + ghost + '">전체 선택</button>' +
    '<button class="kgp-tb-btn" data-act="clear" style="' + ghost + '">선택 해제</button>' +
    '<button class="kgp-tb-btn" data-act="collect-sel" style="' + gold + '">선택 수집</button>' +
    '<button class="kgp-tb-btn" data-act="collect-all" style="' + teal + '">전체 수집</button>' +
    '<span id="kgp-tb-status" style="opacity:.95;font-size:12px;max-width:360px"></span>' +
    '<button class="kgp-tb-btn" data-act="auto" title="새 목록 페이지에서 자동으로 열지 여부" style="' + ghost + '">' + (autoOn ? '📌 자동' : '📌 수동') + '</button>' +
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
      t.textContent = next === "0" ? "📌 수동" : "📌 자동";
      if (next === "0") {
        _kgpClosed = true;
        bar.remove();
        document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove());
        kgpShowReopenPill();
      } else {
        kgpSetStatus("이제 목록 페이지에서 자동으로 열려요.");
      }
    } else if (act === "close") {
      // 접으면 같은 페이지에서 자동으로 다시 뜨지 않게 한다(URL 변경 시 초기화).
      // 대신 구석에 작은 '수집 열기' 배지(선택 개수·펄스)를 남긴다(선택은 유지).
      _kgpClosed = true;
      bar.remove();
      document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove());
      kgpShowReopenPill();
    }
  });
  document.body.appendChild(bar);
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
  pill.title = "고가수집기 수집 바 열기";
  pill.innerHTML =
    '<span style="display:flex;align-items:center;justify-content:center;width:20px;height:20px;background:#0f0d0b;border:1px solid #c9a24b;border-radius:50%">' + KGP_GLOVE_SVG + '</span>' +
    '<span style="font-weight:700;font-size:12px">수집 열기</span>' +
    '<span class="kgp-pill-count" style="display:' + (sel ? "inline-block" : "none") + ';background:#119a8e;color:#fff;border-radius:999px;padding:1px 7px;font-size:11px;font-weight:800">' + (sel || "") + '</span>';
  pill.style.cssText = [
    "position:fixed", "top:12px", "left:12px", "z-index:2147483646",
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
  document.body.appendChild(pill);
  kgpMakeDraggable(pill, "kgp_bar_pos", {});
}

let _kgpAutoApplied = false;       // 이 페이지에서 '수동(auto off)' 초기 접힘을 한 번만 적용

function kgpInjectListing() {
  if (window.top !== window.self || !document.body) return;
  if (!kgpHostAllowed() && !kgpEntrySession()) { kgpTeardown(); return; }   // 지정 소싱처 또는 앱 진입(v10/v17)
  const cards = kgpFindCards();
  if (cards.length < 3) {                        // 리스팅 아님 → 정리(배지/바/배지펄스 제거)
    const ex = document.getElementById(KGP_TOOLBAR_ID);
    if (ex) { ex.remove(); document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove()); }
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
    if (ex) { ex.remove(); document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove()); }
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
    } catch (e) { /* noop */ }
  });
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
  tip.innerHTML = '💡 <b>전체 수집</b>으로 이 페이지의 상품을 한 번에 담을 수 있어요.' +
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
    document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove());
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
  document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove());
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
