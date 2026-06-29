/**
 * popup.js — 팝업 UI 로직
 * 고가수집기
 */

const btnCollect = document.getElementById("btnCollect");
const statusEl = document.getElementById("status");
const pageUrlEl = document.getElementById("pageUrl");
const optionsLink = document.getElementById("optionsLink");
const manageLink = document.getElementById("manageLink");
const srcBadge = document.getElementById("srcBadge");

// 기본 소싱처(content_script.js와 동일하게 유지).
const DEFAULT_SOURCE_TESTS = [
  { id: "taobao", label: "타오바오", test: (h) => /(^|\.)taobao\.com$/.test(h) },
  { id: "tmall", label: "티몰", test: (h) => /(^|\.)tmall\.com$/.test(h) },
  { id: "1688", label: "1688", test: (h) => /(^|\.)1688\.com$/.test(h) },
  { id: "temu", label: "테무", test: (h) => /(^|\.)temu\.com$/.test(h) },
  { id: "amazon", label: "아마존", test: (h) => /(^|\.)amazon\.[a-z.]+$/.test(h) },
  { id: "aliexpress", label: "알리익스프레스", test: (h) => /(^|\.)aliexpress\.(com|us)$/.test(h) },
];

function hostMatch(host, domain) {
  domain = String(domain || "").toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/^www\./, "");
  return !!domain && (host === domain || host.endsWith("." + domain));
}

// 현재 탭이 지정 소싱처인지 표시.
function updateSourceBadge(url) {
  let host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch (e) { host = ""; }
  chrome.storage.local.get("kgp_sources", (r) => {
    const s = (r && r.kgp_sources) || {};
    const defs = s.defaults || {};
    let label = "";
    for (const src of DEFAULT_SOURCE_TESTS) {
      if (defs[src.id] !== false && src.test(host)) { label = src.label; break; }
    }
    if (!label) {
      for (const c of (s.custom || [])) { if (c && c.on !== false && hostMatch(host, c.host)) { label = c.host; break; } }
    }
    if (label) {
      srcBadge.className = "src-badge on";
      srcBadge.textContent = `지정 소싱처 (${label}) — 수집 버튼이 표시돼요`;
    } else {
      srcBadge.className = "src-badge off";
      srcBadge.textContent = "여긴 지정 소싱처가 아니에요. ‘소싱처 관리’에서 추가할 수 있어요.";
    }
  });
}

// 현재 탭 URL 표시 + 소싱처 배지
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (tabs[0]) {
    const url = tabs[0].url || "";
    pageUrlEl.textContent = url.length > 60 ? url.slice(0, 57) + "..." : url;
    updateSourceBadge(url);
  }
});

// 설정/소싱처 관리 → 옵션 페이지 열기
optionsLink.addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });
manageLink.addEventListener("click", (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); });

// v16 P1: 인페이지 '수집' 버튼(FAB) on/off 토글 — 상태 기억(chrome.storage.local.kgp_fab_enabled, 기본 ON).
const fabToggle = document.getElementById("fabToggle");
if (fabToggle) {
  chrome.storage.local.get("kgp_fab_enabled", (r) => {
    fabToggle.checked = !(r && r.kgp_fab_enabled === false);
  });
  fabToggle.addEventListener("change", () => {
    chrome.storage.local.set({ kgp_fab_enabled: fabToggle.checked });   // content_script가 onChanged로 즉시 반영
  });
}

// 수집 버튼 클릭
btnCollect.addEventListener("click", async () => {
  btnCollect.disabled = true;
  showStatus("loading", "상품 정보를 수집하는 중...");

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      throw new Error("현재 탭을 찾을 수 없습니다.");
    }

    // 1차 시도: scripting.executeScript (권한 있고 허용된 페이지)
    let meta;
    try {
      if (chrome.scripting && chrome.scripting.executeScript) {
        const results = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => {
            const getMeta = (prop) => {
              const el = document.querySelector(`meta[property="${prop}"], meta[name="${prop}"]`);
              return el ? el.getAttribute("content") || "" : "";
            };
            const jsonldScripts = [...document.querySelectorAll('script[type="application/ld+json"]')]
              .map(s => { try { return JSON.parse(s.innerText || s.textContent || ""); } catch { return null; } })
              .filter(Boolean);
            return {
              url: location.href,
              title: getMeta("og:title") || document.title || "",
              image: getMeta("og:image") || "",
              price: getMeta("product:price:amount") || "",
              currency: getMeta("product:price:currency") || "USD",
              description: getMeta("og:description") || getMeta("description") || "",
              jsonld: jsonldScripts,
              collected_at: new Date().toISOString()
            };
          }
        });
        meta = results[0]?.result;
      }
    } catch (e) {
      console.warn("scripting.executeScript 실패, tabs.sendMessage로 폴백:", e);
    }

    // 2차 시도: content_script.js의 extractProductMeta() 메시지 패싱 폴백
    if (!meta) {
      meta = await new Promise((resolve) => {
        chrome.tabs.sendMessage(tab.id, { action: "extractMeta" }, (resp) => {
          if (chrome.runtime.lastError) {
            console.warn("tabs.sendMessage 실패:", chrome.runtime.lastError.message);
            resolve(null);
          } else {
            resolve(resp);
          }
        });
      });
    }

    if (!meta) throw new Error("메타 추출 실패 (scripting/messaging 모두)");

    // 백그라운드로 전송
    const response = await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ action: "collect", meta }, (resp) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(resp);
        }
      });
    });

    if (response && response.ok) {
      showStatus("success", `수집 완료!<br><small>${meta.title || meta.url}</small>`);
      if (response.preview_url) {
        const settings = await new Promise(resolve =>
          chrome.storage.sync.get(["serverUrl"], resolve)
        );
        const serverUrl = settings.serverUrl || "https://kohganepercentiii.com";
        const link = document.createElement("a");
        link.href = serverUrl + response.preview_url;
        link.target = "_blank";
        link.className = "preview-link";
        link.textContent = "→ 미리보기";
        statusEl.appendChild(link);
      }
    } else {
      const errMsg = (response && response.error) || "수집 실패";
      showStatus("error", `${errMsg}`);
    }
  } catch (err) {
    showStatus("error", `${err.message || "오류가 발생했습니다"}`);
  } finally {
    btnCollect.disabled = false;
  }
});

function showStatus(type, html) {
  statusEl.className = `status ${type}`;
  statusEl.innerHTML = html;
  statusEl.style.display = "block";
}
