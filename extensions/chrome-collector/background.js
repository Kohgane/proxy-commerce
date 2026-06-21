/**
 * background.js — Service Worker (Manifest V3)
 * 코고가네 수집기 백그라운드 서비스
 */

const DEFAULT_SERVER_URL = "https://kohganepercentiii.com";

// 컨텍스트 메뉴 생성
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "kohgane-collect",
    title: "코고가네에 보내기",
    contexts: ["page"]
  });
});

// 컨텍스트 메뉴 클릭
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "kohgane-collect" && tab) {
    collectFromTab(tab);
  }
});

// 팝업에서 수집 요청
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "collect") {
    handleCollect(msg.meta, sendResponse);
    return true; // 비동기 응답
  }
  if (msg.action === "collectBulk") {
    handleCollectBulk(msg.items, sendResponse);
    return true; // 비동기 응답
  }
  if (msg.action === "getSettings") {
    chrome.storage.sync.get(["serverUrl", "token"], (data) => {
      sendResponse(data);
    });
    return true;
  }
});

async function collectFromTab(tab) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractMeta
    });
    if (results && results[0] && results[0].result) {
      const meta = results[0].result;
      await handleCollect(meta, null);
    }
  } catch (err) {
    console.error("수집 실패:", err);
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/48.png",
      title: "코고가네",
      message: "수집 실패: " + (err.message || "알 수 없는 오류")
    });
  }
}

async function handleCollect(meta, sendResponse) {
  const settings = await chrome.storage.sync.get(["serverUrl", "token"]);
  const serverUrl = settings.serverUrl || DEFAULT_SERVER_URL;
  const token = settings.token || "";

  if (!token) {
    const result = { ok: false, error: "토큰이 설정되지 않았습니다. 옵션 페이지에서 토큰을 입력해주세요." };
    if (sendResponse) sendResponse(result);
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/48.png",
      title: "코고가네",
      message: result.error
    });
    return;
  }

  try {
    const response = await fetch(`${serverUrl}/api/v1/collect/extension`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify(meta)
    });

    const data = await response.json();

    if (sendResponse) sendResponse(data);

    if (data.ok) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/48.png",
        title: "코고가네 ✅",
        message: `수집 완료: ${meta.title || meta.url}`
      });
    } else {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/48.png",
        title: "코고가네 ❌",
        message: data.error || "수집 실패"
      });
    }
  } catch (err) {
    const result = { ok: false, error: err.message || "서버 연결 실패" };
    if (sendResponse) sendResponse(result);
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/48.png",
      title: "코고가네 ❌",
      message: result.error
    });
  }
}

// 리스팅 다중 상품 일괄 수집 (Phase 221)
// content_script가 보낸 상품 카드 메타 배열을 토큰으로 순차 전송한다.
// background fetch라 페이지 CSP의 영향을 받지 않는다.
async function handleCollectBulk(items, sendResponse) {
  const settings = await chrome.storage.sync.get(["serverUrl", "token"]);
  const serverUrl = settings.serverUrl || DEFAULT_SERVER_URL;
  const token = settings.token || "";
  items = Array.isArray(items) ? items : [];

  if (!token) {
    if (sendResponse) sendResponse({ ok: false, error: "토큰이 설정되지 않았습니다. 확장 옵션에서 토큰을 입력하세요." });
    return;
  }
  if (!items.length) {
    if (sendResponse) sendResponse({ ok: false, error: "수집할 상품이 없습니다." });
    return;
  }

  let success = 0, failed = 0;
  for (const meta of items) {
    try {
      const r = await fetch(`${serverUrl}/api/v1/collect/extension`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify(meta),
      });
      const d = await r.json().catch(() => ({}));
      if (d && d.ok) success++; else failed++;
    } catch (e) {
      failed++;
    }
  }

  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/48.png",
    title: success ? "코고가네 ✅" : "코고가네 ❌",
    message: `일괄 수집: 성공 ${success} / 실패 ${failed} (총 ${items.length})`,
  });
  if (sendResponse) sendResponse({ ok: true, success, failed, total: items.length });
}

// content_script에서 호출할 메타 추출 함수 (executeScript용)
function extractMeta() {
  const getMeta = (prop) => {
    const el = document.querySelector(`meta[property="${prop}"], meta[name="${prop}"]`);
    return el ? el.getAttribute("content") : null;
  };

  const jsonldScripts = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map(s => { try { return JSON.parse(s.innerText || s.textContent); } catch { return null; } })
    .filter(Boolean);

  const ogImage = getMeta("og:image") || getMeta("og:image:url") || "";

  return {
    url: location.href,
    title: getMeta("og:title") || document.title,
    image: ogImage,
    images: ogImage ? [ogImage] : [],
    price: getMeta("product:price:amount"),
    currency: getMeta("product:price:currency") || "USD",
    description: getMeta("og:description") || getMeta("description"),
    brand: getMeta("og:brand") || "",
    jsonld: jsonldScripts,
    collected_at: new Date().toISOString()
  };
}
