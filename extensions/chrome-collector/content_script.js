/**
 * content_script.js — 페이지 컨텍스트에서 메타 추출 + 인페이지 '수집' 버튼 (Phase 202)
 * 코가네 퍼센티 수집기
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

  // 이미지 후보: og:image 우선, 없으면 본문 큰 이미지
  const ogImage = getMeta("og:image") || getMeta("og:image:url") || "";
  const images = [];
  if (ogImage) images.push(ogImage);

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
    btn.querySelector(".kgp-fab-label").textContent = "수집";
  }
}

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
    '<span style="font-size:18px;line-height:1">🛒</span>' +
    '<span class="kgp-fab-label" style="font-weight:600">수집</span>';
  btn.title = "코가네 퍼센티로 수집 (번역 포함)";
  btn.style.cssText = [
    "position:fixed", "right:20px", "bottom:20px", "z-index:2147483646",
    "display:flex", "align-items:center", "gap:8px",
    "padding:10px 16px", "border:none", "border-radius:999px",
    "background:linear-gradient(135deg,#6f42c1,#8b5cf6)", "color:#fff",
    "font:14px/1 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    "cursor:pointer", "box-shadow:0 6px 18px rgba(111,66,193,.45)",
    "transition:transform .12s,opacity .12s"
  ].join(";");
  btn.addEventListener("mouseenter", () => { btn.style.transform = "translateY(-2px)"; });
  btn.addEventListener("mouseleave", () => { btn.style.transform = "none"; });
  btn.addEventListener("click", () => handleFabClick(btn));
  document.body.appendChild(btn);
}

// SPA 대응: 최초 + URL 변경 시 재시도
injectCollectButton();
let _kgpLastUrl = location.href;
setInterval(() => {
  if (location.href !== _kgpLastUrl) {
    _kgpLastUrl = location.href;
    setTimeout(injectCollectButton, 800);
  }
}, 1500);
