/**
 * options.js — 설정 페이지 로직 (고가수집기)
 * 서버/토큰 + v10 소싱처 관리(기본셋 토글 + 사용자 도메인 추가/삭제).
 */

const serverUrlInput = document.getElementById("serverUrl");
const tokenInput = document.getElementById("token");
const saveBtn = document.getElementById("saveBtn");
const clearBtn = document.getElementById("clearBtn");
const toggleToken = document.getElementById("toggleToken");
const statusMsg = document.getElementById("statusMsg");
const getTokenLink = document.getElementById("getTokenLink");

// content_script.js의 KGP_DEFAULT_SOURCES와 동일하게 유지(표시용 라벨/호스트).
const DEFAULT_SOURCES = [
  { id: "taobao", label: "타오바오", host: "taobao.com" },
  { id: "tmall", label: "티몰", host: "tmall.com" },
  { id: "1688", label: "1688", host: "1688.com" },
  { id: "temu", label: "테무", host: "temu.com" },
  { id: "amazon", label: "아마존", host: "amazon.*" },
  { id: "aliexpress", label: "알리익스프레스", host: "aliexpress.com" },
  { id: "iherb", label: "아이허브", host: "iherb.com" },
  { id: "dhgate", label: "DHgate", host: "dhgate.com" },
  { id: "qoo10", label: "큐텐", host: "qoo10.com" },
  { id: "mercari", label: "메루카리", host: "mercari.com" },
  { id: "rakuten", label: "라쿠텐(Rakuten Fashion 포함)", host: "rakuten.co.jp" },
];

// ---- 서버/토큰 (chrome.storage.sync) ----
chrome.storage.sync.get(["serverUrl", "token"], (data) => {
  if (data.serverUrl) serverUrlInput.value = data.serverUrl;
  if (data.token) tokenInput.value = data.token;
  const server = data.serverUrl || "https://kohganepercentiii.com";
  getTokenLink.href = server + "/seller/me/tokens";
  getTokenLink.target = "_blank";
});

toggleToken.addEventListener("click", () => {
  if (tokenInput.type === "password") { tokenInput.type = "text"; toggleToken.textContent = "🙈"; }
  else { tokenInput.type = "password"; toggleToken.textContent = "👁"; }
});

serverUrlInput.addEventListener("input", () => {
  const server = serverUrlInput.value.trim() || "https://kohganepercentiii.com";
  try { getTokenLink.href = new URL("/seller/me/tokens", server).href; }
  catch (_) { getTokenLink.href = "https://kohganepercentiii.com/seller/me/tokens"; }
});

saveBtn.addEventListener("click", () => {
  const serverUrl = serverUrlInput.value.trim();
  const token = tokenInput.value.trim();
  if (!token) { showStatus(statusMsg, "error", "액세스 토큰을 입력해주세요."); return; }
  chrome.storage.sync.set({ serverUrl, token }, () => showStatus(statusMsg, "success", "✅ 설정이 저장되었습니다."));
});

clearBtn.addEventListener("click", () => {
  if (confirm("서버/토큰 설정을 초기화하시겠습니까?")) {
    chrome.storage.sync.remove(["serverUrl", "token"], () => {
      serverUrlInput.value = ""; tokenInput.value = "";
      showStatus(statusMsg, "success", "초기화되었습니다.");
    });
  }
});

// ---- v10 소싱처 관리 (chrome.storage.local: kgp_sources) ----
const defaultSourcesEl = document.getElementById("defaultSources");
const customSourcesEl = document.getElementById("customSources");
const customHostInput = document.getElementById("customHost");
const addHostBtn = document.getElementById("addHostBtn");
const srcStatus = document.getElementById("srcStatus");

let _sources = { defaults: {}, custom: [] };

function loadSources() {
  chrome.storage.local.get("kgp_sources", (r) => {
    _sources = (r && r.kgp_sources) || {};
    if (!_sources.defaults) _sources.defaults = {};
    if (!Array.isArray(_sources.custom)) _sources.custom = [];
    renderSources();
  });
}

function saveSources(msg) {
  chrome.storage.local.set({ kgp_sources: _sources }, () => {
    if (msg) showStatus(srcStatus, "success", msg);
  });
}

function _row(name, hostText, checked, onToggle, onRemove, faviconHost) {
  const row = document.createElement("div");
  row.className = "src-row";
  const left = document.createElement("div");
  left.style.cssText = "display:flex;align-items:center;gap:8px";
  // v15: 등록 소싱처를 사이트 아이콘(파비콘)으로 — 칩처럼 깔끔히. 실패 시 자동 숨김.
  if (faviconHost) {
    const ico = document.createElement("img");
    const fh = String(faviconHost).replace(/\.\*$/, ".com").replace(/\*/g, "");  // amazon.* → amazon.com
    ico.src = "https://www.google.com/s2/favicons?domain=" + encodeURIComponent(fh) + "&sz=32";
    ico.width = 18; ico.height = 18; ico.alt = "";
    ico.style.cssText = "border-radius:4px;flex-shrink:0";
    ico.onerror = function () { ico.style.display = "none"; };
    left.appendChild(ico);
  }
  const txt = document.createElement("div");
  txt.innerHTML = '<span class="src-name"></span><span class="src-host"></span>';
  txt.querySelector(".src-name").textContent = name;
  txt.querySelector(".src-host").textContent = hostText;
  left.appendChild(txt);
  const right = document.createElement("div");
  right.style.cssText = "display:flex;align-items:center;gap:10px";
  const sw = document.createElement("label");
  sw.className = "switch";
  const cb = document.createElement("input");
  cb.type = "checkbox"; cb.checked = checked;
  cb.addEventListener("change", () => onToggle(cb.checked));
  const sl = document.createElement("span"); sl.className = "slider";
  sw.appendChild(cb); sw.appendChild(sl);
  right.appendChild(sw);
  if (onRemove) {
    const rm = document.createElement("button");
    rm.className = "rm-btn"; rm.textContent = "삭제";
    rm.addEventListener("click", onRemove);
    right.appendChild(rm);
  }
  row.appendChild(left); row.appendChild(right);
  return row;
}

function renderSources() {
  defaultSourcesEl.innerHTML = "";
  DEFAULT_SOURCES.forEach((src) => {
    const on = _sources.defaults[src.id] !== false;   // 기본 ON
    defaultSourcesEl.appendChild(_row(src.label, src.host, on, (val) => {
      _sources.defaults[src.id] = val;
      saveSources(val ? `${src.label} 켜짐` : `${src.label} 꺼짐`);
    }, null, src.host));
  });
  customSourcesEl.innerHTML = "";
  (_sources.custom || []).forEach((c, idx) => {
    customSourcesEl.appendChild(_row(c.host, "직접 추가", c.on !== false, (val) => {
      _sources.custom[idx].on = val; saveSources(val ? "켜짐" : "꺼짐");
    }, () => {
      _sources.custom.splice(idx, 1); saveSources("삭제됨"); renderSources();
    }, c.host));
  });
}

function _normHost(v) {
  return String(v || "").trim().toLowerCase()
    .replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/^www\./, "");
}

addHostBtn.addEventListener("click", () => {
  const host = _normHost(customHostInput.value);
  if (!host || host.indexOf(".") < 0) { showStatus(srcStatus, "error", "도메인을 정확히 입력하세요 (예: vvic.com)"); return; }
  if (!Array.isArray(_sources.custom)) _sources.custom = [];
  if (_sources.custom.some((c) => c.host === host)) { showStatus(srcStatus, "error", "이미 추가된 도메인이에요."); return; }
  _sources.custom.push({ host, on: true });
  customHostInput.value = "";
  saveSources(`${host} 추가됨`); renderSources();
});
customHostInput.addEventListener("keydown", (e) => { if (e.key === "Enter") addHostBtn.click(); });

function showStatus(el, type, msg) {
  el.className = `status-msg ${type}`;
  el.textContent = msg;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 2500);
}

loadSources();
