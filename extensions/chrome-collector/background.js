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
    localData = await chrome.storage.local.get(["serverUrl", "token", "kgp_enrich_mode"]);
  } catch (_) {}
  return {
    serverUrl: syncData.serverUrl || localData.serverUrl || DEFAULT_SERVER_URL,
    token: syncData.token || localData.token || "",
    enrichMode: localData.kgp_enrich_mode || "window",   // v67 STEP2: 보강 렌더 모드(window 기본)
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
  // v64 STEP1: 벌크 상세 보강 큐 제어.
  if (msg.action === "enrichStart") { handleEnrichStart(msg.targets, sendResponse); return true; }
  if (msg.action === "enrichState") { sendResponse(_kgpEnrichSnapshot()); return false; }
  if (msg.action === "enrichPause") { KgpEnrich.paused = !!msg.paused; _kgpBroadcastEnrich(); sendResponse(_kgpEnrichSnapshot()); return false; }
  if (msg.action === "enrichStop") { KgpEnrich.stopped = true; KgpEnrich.queue = []; _kgpBroadcastEnrich(); sendResponse(_kgpEnrichSnapshot()); return false; }
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

// ── v64 STEP1: 벌크 2단 수집 — 상세 보강 큐 ──────────────────────────────────
//   1단(목록 데이터)은 이미 저장됨. 2단: 확장이 백그라운드 탭으로 각 상품 상세를 순차 방문해
//   옵션·상세·리뷰·갤러리를 읽어 서버 /enrich로 기존 항목에 병합(fill-only). 사용자 브라우저
//   컨텍스트라 차단 리스크 최소. 동시 1탭·항목당 3~6초 랜덤 간격·실패 1회 재시도·일시정지/중단.
const KgpEnrich = {
  queue: [], done: 0, total: 0, failed: 0, ok: 0,
  paused: false, stopped: false, running: false, current: "",
};
function _kgpEnrichSnapshot() {
  return { done: KgpEnrich.done, total: KgpEnrich.total, failed: KgpEnrich.failed,
    ok: KgpEnrich.ok, paused: KgpEnrich.paused, stopped: KgpEnrich.stopped,
    running: KgpEnrich.running, current: KgpEnrich.current };
}
// 항목당 대기(3~6초 랜덤). rng 주입 가능(테스트).
function _kgpEnrichDelayMs(rng) {
  const r = (typeof rng === "function") ? rng() : Math.random();
  return 3000 + Math.floor(r * 3000);
}
function _kgpSleep(ms) { return new Promise((res) => setTimeout(res, ms)); }
function _kgpWaitTabComplete(tabId, timeoutMs) {
  return new Promise((resolve) => {
    let done = false;
    const to = setTimeout(() => { if (!done) { done = true; try { chrome.tabs.onUpdated.removeListener(li); } catch (e) {} resolve(false); } }, timeoutMs || 20000);
    function li(id, info) {
      if (id === tabId && info.status === "complete" && !done) {
        done = true; clearTimeout(to);
        try { chrome.tabs.onUpdated.removeListener(li); } catch (e) {}
        resolve(true);
      }
    }
    chrome.tabs.onUpdated.addListener(li);
  });
}
function _kgpSendTab(tabId, msg) {
  return new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, msg, (resp) => {
        if (chrome.runtime && chrome.runtime.lastError) return resolve(null);
        resolve(resp || null);
      });
    } catch (e) { resolve(null); }
  });
}
function _kgpBroadcastEnrich() {
  const snap = _kgpEnrichSnapshot();
  try { chrome.runtime.sendMessage({ action: "enrichProgress", state: snap }); } catch (e) {}
}
// v67 STEP2: 테무 렌더 성공 기준(백그라운드 탭 스로틀로 lazy 미출현 방지) — 가격 실가 + 갤러리 자기 상품 ≥3장.
function _kgpEnrichVerdict(item, meta) {
  const gallery = (meta && (meta.gallery_images || meta.images)) || [];
  const galN = Array.isArray(gallery) ? gallery.length : 0;
  const priceOk = !!(meta && meta.price && String(meta.price).trim());
  const isTemu = /(^|\.)temu\.com/i.test(item.url || "");
  if (meta && meta.interstitial) return { ok: false, reason: "테무 로그인/게이트로 보강 불가(인터스티셜)" };
  if (isTemu && (!priceOk || galN < 3)) {
    return { ok: false, reason: "테무 렌더 미완 — " + (!priceOk ? "가격 노드 미출현 " : "") + (galN < 3 ? "갤러리 " + galN + "장(3장 미만)" : "") };
  }
  return { ok: true, reason: "" };
}
async function _kgpEnrichOne(item, settings) {
  // v67 STEP2: 렌더 보장 — 기본은 별도 소형 창(popup 480×640, 탭 활성=렌더 보장, 화면 점유 최소).
  //   설정으로 탭 활성화 사이클(tab-activate)/기존 백그라운드(background) 선택. 서버 크롤 아님(확장 DOM).
  const mode = (settings && settings.enrichMode) || "window";
  let win = null, tabId = null;
  try {
    if (mode === "window") {
      // v70 STEP6: 소형 창이 안 뜨는 환경(정책·API 부재) 대비 — 실패 시 조용히 죽지 않고 백그라운드 탭 폴백.
      try {
        if (!(chrome.windows && chrome.windows.create)) throw new Error("chrome.windows 미가용");
        win = await chrome.windows.create({ url: item.url, type: "popup", width: 480, height: 640, top: 90, left: 90, focused: false });
        tabId = win && win.tabs && win.tabs[0] && win.tabs[0].id;
        // 창은 떴는데 tabs 미포함(타이밍) → 창의 탭 id 조회(url 불필요, id만 — tabs 권한 불요).
        if (win && win.id != null && tabId == null) {
          try { const ts = await chrome.tabs.query({ windowId: win.id }); tabId = ts && ts[0] && ts[0].id; } catch (e) {}
        }
        if (tabId == null) throw new Error("소형 창 탭 없음");
      } catch (e) {
        try { console.warn("[고가수집기 보강] 소형 창 실패 → 백그라운드 탭 폴백:", e && e.message); } catch (e2) {}
        if (win && win.id != null) { try { await chrome.windows.remove(win.id); } catch (e3) {} }
        win = null;
        const tab = await chrome.tabs.create({ url: item.url, active: false });
        tabId = tab && tab.id;
      }
    } else {
      const tab = await chrome.tabs.create({ url: item.url, active: (mode === "tab-activate") });
      tabId = tab && tab.id;
    }
    KgpEnrich.current = item.url;
    _kgpBroadcastEnrich();
    if (tabId != null) await _kgpWaitTabComplete(tabId, 22000);
    // 렌더 완료 대기 후 추출(자동스크롤·인터스티셜·12초 — content_script extractMetaWait).
    const meta = (tabId != null) ? await _kgpSendTab(tabId, { action: "extractMetaWait" }) : null;
    if (!meta) throw new Error("상세 추출 실패(빈 응답)");
    // v67 STEP2: 렌더 미보장 상태로 '보강 완료' 금지 — 테무 성공 기준 미달이면 정직 실패(재시도/보강 실패).
    const verdict = _kgpEnrichVerdict(item, meta);
    if (!verdict.ok) throw new Error(verdict.reason);
    const body = {
      item_id: item.item_id,
      options: meta.options || [],
      description: meta.description || "",
      detail_images: meta.detail_images || [],
      gallery: meta.gallery_images || meta.images || [],
      reviews: meta.reviews || [],
      rating: meta.rating || "",
      review_count: meta.review_count || "",
    };
    const r = await fetch(`${settings.serverUrl}/api/v1/collect/enrich`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${settings.token}` },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d || !d.ok) throw new Error("서버 보강 실패 HTTP " + r.status);
    return true;
  } finally {
    if (win && win.id != null) { try { await chrome.windows.remove(win.id); } catch (e) {} }
    else if (tabId != null) { try { await chrome.tabs.remove(tabId); } catch (e) {} }
  }
}
async function _kgpEnrichLoop() {
  if (KgpEnrich.running) return;
  KgpEnrich.running = true;
  const settings = await getSettings();
  while (KgpEnrich.queue.length && !KgpEnrich.stopped) {
    if (KgpEnrich.paused) { await _kgpSleep(600); continue; }
    const item = KgpEnrich.queue.shift();
    try {
      await _kgpEnrichOne(item, settings);
      KgpEnrich.ok++;
    } catch (e) {
      if ((item.retries || 0) < 1) {          // 실패 1회 재시도(뒤에 다시 넣음)
        item.retries = (item.retries || 0) + 1;
        KgpEnrich.queue.push(item);
        KgpEnrich.done++; _kgpBroadcastEnrich();
        if (!KgpEnrich.stopped) await _kgpSleep(_kgpEnrichDelayMs());
        continue;
      }
      KgpEnrich.failed++;                       // 재시도도 실패 → '보강 실패' 정직 집계
    }
    KgpEnrich.done++;
    KgpEnrich.current = "";
    _kgpBroadcastEnrich();
    if (KgpEnrich.queue.length && !KgpEnrich.stopped) await _kgpSleep(_kgpEnrichDelayMs());
  }
  KgpEnrich.running = false;
  KgpEnrich.current = "";
  _kgpBroadcastEnrich();
}
function handleEnrichStart(targets, sendResponse) {
  const items = (Array.isArray(targets) ? targets : [])
    .filter((t) => t && t.item_id && t.url)
    .map((t) => ({ item_id: String(t.item_id), url: String(t.url), retries: 0 }));
  if (!items.length) { if (sendResponse) sendResponse({ ok: false, error: "보강할 항목이 없습니다." }); return; }
  // 새 배치: 카운터 초기화(진행 중이면 이어붙임).
  if (!KgpEnrich.running) { KgpEnrich.done = 0; KgpEnrich.failed = 0; KgpEnrich.ok = 0; KgpEnrich.stopped = false; KgpEnrich.paused = false; KgpEnrich.total = 0; }
  KgpEnrich.queue.push(...items);
  KgpEnrich.total += items.length;
  if (sendResponse) sendResponse({ ok: true, total: KgpEnrich.total });
  _kgpEnrichLoop();
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
  // P0 진단: 요청에 인증 토큰이 실렸는지 콘솔에 노출(값은 마스킹). 미인증(HTML 로그인 응답) 원인 규명용.
  console.log(`[고가수집기] 인증 토큰 ${token ? "첨부됨(Bearer …" + String(token).slice(-4) + ")" : "없음 — 확장 옵션에서 토큰을 설정하세요"} → POST ${endpoint}`);
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
  const enrichTargets = [];   // v64 STEP1: 2단 보강 대상(서버가 회신한 item_id + 상세 URL)
  let _extVer = ""; try { _extVer = chrome.runtime.getManifest().version; } catch (e) {}
  // P0 진단: 벌크도 인증 토큰 첨부 여부를 콘솔에 노출(마스킹).
  console.log(`[고가수집기] 벌크 ${items.length}건 · 인증 토큰 ${token ? "첨부됨(Bearer …" + String(token).slice(-4) + ")" : "없음"}`);
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
      // v64 STEP1: 성공·중복 항목은 상세 보강 대상(item_id + 상세 URL). 실패는 제외.
      if (d && d.ok && d.item_id && meta && meta.url) enrichTargets.push({ item_id: d.item_id, url: meta.url });
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
  if (sendResponse) sendResponse({ ok: true, success, failed, duplicate, total: items.length, failedItems, enrichTargets });
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
