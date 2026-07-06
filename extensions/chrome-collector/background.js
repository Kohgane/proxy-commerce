/**
 * background.js — Service Worker (Manifest V3)
 * 고가수집기 백그라운드 서비스
 */

const DEFAULT_SERVER_URL = "https://kohganepercentiii.com";

async function getSettings() {
  let syncData = {};
  let localData = {};
  try {
    syncData = await chrome.storage.sync.get(["serverUrl", "token"]);
  } catch (_) {}
  try {
    localData = await chrome.storage.local.get(["serverUrl", "token"]);
  } catch (_) {}
  return {
    serverUrl: syncData.serverUrl || localData.serverUrl || DEFAULT_SERVER_URL,
    token: syncData.token || localData.token || "",
  };
}

// 컨텍스트 메뉴 생성
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "kohgane-collect",
    title: "고가브릿지에 보내기",
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
    handleCollectBulk(msg.items, sendResponse, sender && sender.tab && sender.tab.id);
    return true; // 비동기 응답
  }
  if (msg.action === "getSettings") {
    getSettings().then((data) => sendResponse(data));
    return true;
  }
  if (msg.action === "collectExists") {   // v42 E-3: 이미 수집된 URL 조회(호버 버튼 '수집됨 ✓' 선표시)
    handleExists(msg.urls, sendResponse);
    return true;
  }
});

async function handleExists(urls, sendResponse) {
  const settings = await getSettings();
  if (!settings.token) { if (sendResponse) sendResponse({ ok: false, collected: [] }); return; }
  try {
    const r = await fetch(`${settings.serverUrl}/api/v1/collect/exists`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${settings.token}` },
      body: JSON.stringify({ urls: Array.isArray(urls) ? urls : [] }),
    });
    const d = await r.json().catch(() => ({}));
    if (sendResponse) sendResponse({ ok: !!(d && d.ok), collected: (d && d.collected) || [] });
  } catch (e) {
    if (sendResponse) sendResponse({ ok: false, collected: [] });
  }
}

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
      title: "고가브릿지",
      message: "수집 실패: " + (err.message || "알 수 없는 오류")
    });
  }
}

async function handleCollect(meta, sendResponse) {
  const settings = await getSettings();
  const serverUrl = settings.serverUrl;
  const token = settings.token;

  if (!token) {
    // v42 E-1: 미인증 자동 토스트 남발 금지 — 알림 만들지 않고 호출부(FAB 클릭)에만 안내 반환.
    const result = { ok: false, authRequired: true,
                     error: "토큰이 설정되지 않았습니다. 확장 옵션에서 토큰을 설정해주세요." };
    if (sendResponse) sendResponse(result);
    return;
  }

  const endpoint = `${serverUrl}/api/v1/collect/extension`;
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
      body: JSON.stringify(meta)
    });
    // P0 진단: 엔드포인트·HTTP 상태·응답 본문(원문)을 확장 콘솔에 로그 → 원인 1줄(401/404/500/CORS).
    const raw = await response.text();
    let data = {};
    try { data = JSON.parse(raw); } catch (e) { data = {}; }
    console.log(`[고가수집기] POST ${endpoint} → ${response.status} ${response.statusText}`,
                "\n응답:", raw.slice(0, 400));
    if (response.status === 401) data.authRequired = true;
    // 서버가 JSON을 못 준 경우(로그인 리다이렉트·HTML 오류 페이지 등)도 조용한 실패 금지.
    const _looksHtml = /^\s*<(!doctype|html)/i.test(raw);
    if (!data || (typeof data.ok === "undefined")) {
      data = { ok: false,
               error: _looksHtml ? `서버 응답 오류(로그인 확인이 필요할 수 있어요). HTTP ${response.status}`
                                 : `서버 오류 (HTTP ${response.status}). 잠시 후 다시 시도하세요.`,
               httpStatus: response.status };
    }
    if (!data.error && !data.ok) data.error = `수집 실패 (HTTP ${response.status})`;
    if (data.httpStatus === undefined) data.httpStatus = response.status;

    if (sendResponse) sendResponse(data);
    // 알럿 중복 방지: content_script가 인페이지 토스트로 결과를 보여주는 경로(sendResponse 있음)에서는
    //   OS 알림을 만들지 않는다(토스트+OS알림 이중 알럿 제거). 컨텍스트 메뉴 등 토스트 없는 경로만 OS 알림.
    if (!sendResponse) {
      chrome.notifications.create({
        type: "basic", iconUrl: "icons/48.png", title: "고가브릿지",
        message: data.ok ? `수집 완료: ${meta.title || meta.url}`
                         : `수집 실패 (${response.status}): ${data.error || ""}`.slice(0, 180)
      });
    }
  } catch (err) {
    // 네트워크/CORS 실패 등 — 엔드포인트와 함께 로그.
    console.error(`[고가수집기] 수집 요청 실패 POST ${endpoint}:`, err);
    const result = { ok: false, error: `네트워크 오류: ${err.message || "서버에 연결하지 못했습니다"}`, networkError: true };
    if (sendResponse) sendResponse(result);
    chrome.notifications.create({
      type: "basic", iconUrl: "icons/48.png", title: "고가브릿지", message: result.error
    });
  }
}

// 리스팅 다중 상품 일괄 수집 (Phase 221)
// content_script가 보낸 상품 카드 메타 배열을 토큰으로 순차 전송한다.
// background fetch라 페이지 CSP의 영향을 받지 않는다.
async function handleCollectBulk(items, sendResponse, tabId) {
  const settings = await getSettings();
  const serverUrl = settings.serverUrl;
  const token = settings.token;
  items = Array.isArray(items) ? items : [];

  if (!token) {
    if (sendResponse) sendResponse({ ok: false, authRequired: true,
      error: "토큰이 설정되지 않았습니다. 확장 옵션에서 토큰을 설정하세요." });
    return;
  }
  if (!items.length) {
    if (sendResponse) sendResponse({ ok: false, error: "수집할 상품이 없습니다." });
    return;
  }

  // v42 E-5: 항목별 서버 커밋(+ID 회신) 후에만 성공 카운트. 중복/실패 분리 집계 + 실패 항목 반환(재시도).
  //   순차 처리(동시 폭주로 인한 유실 방지) + 1건마다 진행률을 탭에 전송(bulkProgress).
  let success = 0, failed = 0, duplicate = 0;
  const failedItems = [];
  let _extVer = ""; try { _extVer = chrome.runtime.getManifest().version; } catch (e) {}
  for (let i = 0; i < items.length; i++) {
    const meta = items[i];
    if (meta && !meta.ext_version) meta.ext_version = _extVer;   // P0 하위호환·진단
    try {
      const r = await fetch(`${serverUrl}/api/v1/collect/extension`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify(meta),
      });
      const raw = await r.text();
      let d = {}; try { d = JSON.parse(raw); } catch (e) { d = {}; }
      if (!r.ok || typeof d.ok === "undefined") {   // P0 진단: 실패 1건 상태·본문 로그(첫 실패만 상세)
        if (failed === 0) console.log(`[고가수집기] 벌크 실패 HTTP ${r.status}:`, raw.slice(0, 300));
      }
      if (d && d.ok && d.duplicate) duplicate++;      // 이미 수집(중복) — '완료'로 부풀리지 않음
      else if (d && d.ok) success++;                  // 서버 커밋 성공(STEP 1-0 write-then-verify)
      else { failed++; failedItems.push(meta); }      // 502 등 정직 실패 → 재시도 대상
    } catch (e) {
      if (failed === 0) console.error("[고가수집기] 벌크 네트워크 오류:", e);
      failed++; failedItems.push(meta);
    }
    if (tabId != null) {
      try { chrome.tabs.sendMessage(tabId, { action: "bulkProgress", done: i + 1, total: items.length }); } catch (_) {}
    }
  }

  const parts = [`완료 ${success}`];
  if (duplicate) parts.push(`중복 ${duplicate}`);
  if (failed) parts.push(`실패 ${failed}`);
  // 알럿 중복 방지: content가 인페이지 요약을 보여주는 경로(sendResponse)에선 OS 알림 생략.
  if (!sendResponse) {
    chrome.notifications.create({
      type: "basic", iconUrl: "icons/48.png", title: "고가브릿지",
      message: `일괄 수집 (총 ${items.length}): ${parts.join(" · ")}`,
    });
  }
  if (sendResponse) sendResponse({ ok: true, success, failed, duplicate, total: items.length, failedItems });
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
