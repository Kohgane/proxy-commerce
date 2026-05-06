/**
 * background.js — Service Worker (Manifest V3)
 * 코가네 퍼센티 수집기 백그라운드 서비스
 */

const DEFAULT_SERVER_URL = "https://kohganepercentiii.com";

// 컨텍스트 메뉴 생성
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "kohgane-collect",
    title: "코가네 퍼센티에 보내기",
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
      title: "코가네 퍼센티",
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
      title: "코가네 퍼센티",
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
        title: "코가네 퍼센티 ✅",
        message: `수집 완료: ${meta.title || meta.url}`
      });
    } else {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/48.png",
        title: "코가네 퍼센티 ❌",
        message: data.error || "수집 실패"
      });
    }
  } catch (err) {
    const result = { ok: false, error: err.message || "서버 연결 실패" };
    if (sendResponse) sendResponse(result);
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/48.png",
      title: "코가네 퍼센티 ❌",
      message: result.error
    });
  }
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

  return {
    url: location.href,
    title: getMeta("og:title") || document.title,
    image: getMeta("og:image"),
    price: getMeta("product:price:amount"),
    currency: getMeta("product:price:currency") || "USD",
    description: getMeta("og:description") || getMeta("description"),
    jsonld: jsonldScripts,
    collected_at: new Date().toISOString()
  };
}
