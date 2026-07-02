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
const connStatus = document.getElementById("connStatus");

// v42 E-1: 토큰 연결 상태 확인 — 서버에 /api/v1/collect/me 호출해 '연결됨 ✓ (계정)' 표시.
//   유효 200 → 연결됨, 401 → 토큰 무효·만료(재설정), 그 외/네트워크 → 확인 불가(정직).
function _setConn(kind, text) {
  if (!connStatus) return;
  connStatus.style.display = "block";
  const palette = {
    ok: ["#0f7b6c", "#e6f4f1"], bad: ["#b42318", "#fde8e6"], warn: ["#8a6d1f", "#fdf6e3"],
  }[kind] || ["#555", "#eee"];
  connStatus.style.color = palette[0];
  connStatus.style.background = palette[1];
  connStatus.textContent = text;
}
function checkConnection(server, token) {
  if (!token) { if (connStatus) connStatus.style.display = "none"; return; }
  const base = (server || "https://kohganepercentiii.com").replace(/\/+$/, "");
  _setConn("warn", "연결 확인 중…");
  fetch(base + "/api/v1/collect/me", { headers: { "Authorization": "Bearer " + token } })
    .then((r) => r.status === 401 ? { _bad: true } : r.json().catch(() => ({})))
    .then((d) => {
      if (d && d._bad) { _setConn("bad", "토큰이 무효하거나 만료됐어요 — 재발급 후 다시 저장하세요."); return; }
      if (d && d.ok) {
        const who = d.email || d.name || d.user_id || "";
        _setConn("ok", "연결됨 ✓" + (who ? "  ·  " + who : ""));
      } else {
        _setConn("warn", "연결 상태를 확인하지 못했어요 (네트워크/서버). 토큰은 저장돼 있어요.");
      }
    })
    .catch(() => _setConn("warn", "연결 상태를 확인하지 못했어요 (네트워크). 토큰은 저장돼 있어요."));
}

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
  { id: "yahoo", label: "야후쇼핑(재팬)", host: "shopping.yahoo.co.jp" },
  { id: "yoshida", label: "요시다카반", host: "yoshidakaban.com" },
];

// ---- 서버/토큰 (sync 우선 + local 폴백) ----
function readSettings(callback) {
  chrome.storage.sync.get(["serverUrl", "token"], (syncData) => {
    const syncErr = chrome.runtime.lastError;
    chrome.storage.local.get(["serverUrl", "token"], (localData) => {
      const localErr = chrome.runtime.lastError;
      const merged = {
        serverUrl: (syncData && syncData.serverUrl) || (localData && localData.serverUrl) || "",
        token: (syncData && syncData.token) || (localData && localData.token) || "",
      };
      callback(merged, syncErr, localErr);
    });
  });
}

function writeSettings(settings, callback) {
  chrome.storage.sync.set(settings, () => {
    const syncErr = chrome.runtime.lastError;
    chrome.storage.local.set(settings, () => {
      const localErr = chrome.runtime.lastError;
      callback(syncErr, localErr);
    });
  });
}

function removeSettings(callback) {
  chrome.storage.sync.remove(["serverUrl", "token"], () => {
    const syncErr = chrome.runtime.lastError;
    chrome.storage.local.remove(["serverUrl", "token"], () => {
      const localErr = chrome.runtime.lastError;
      callback(syncErr, localErr);
    });
  });
}

readSettings((data) => {
  if (data.serverUrl) serverUrlInput.value = data.serverUrl;
  if (data.token) tokenInput.value = data.token;
  const server = data.serverUrl || "https://kohganepercentiii.com";
  getTokenLink.href = server + "/seller/me/tokens";
  getTokenLink.target = "_blank";
  checkConnection(server, data.token);   // v42 E-1: 저장된 토큰이면 연결 상태 즉시 표시
});

toggleToken.addEventListener("click", () => {
  if (tokenInput.type === "password") { tokenInput.type = "text"; toggleToken.textContent = "숨김"; }
  else { tokenInput.type = "password"; toggleToken.textContent = "표시"; }
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
  writeSettings({ serverUrl, token }, (syncErr, localErr) => {
    if (syncErr && localErr) {
      showStatus(statusMsg, "error", "저장 실패: 브라우저 저장소에 접근하지 못했어요.");
      return;
    }
    if (syncErr && !localErr) {
      showStatus(statusMsg, "success", "이 기기에 저장되었습니다. 동기화는 잠시 후 다시 시도해주세요.");
      return;
    }
    showStatus(statusMsg, "success", "설정이 저장되었습니다.");
    checkConnection(serverUrl, token);   // v42 E-1: 저장 직후 연결 상태 검증해 '연결됨 ✓' 표시
  });
});

clearBtn.addEventListener("click", () => {
  if (confirm("서버/토큰 설정을 초기화하시겠습니까?")) {
    removeSettings((syncErr, localErr) => {
      if (syncErr && localErr) {
        showStatus(statusMsg, "error", "초기화 실패: 저장소 접근 오류");
        return;
      }
      serverUrlInput.value = ""; tokenInput.value = "";
      if (connStatus) connStatus.style.display = "none";   // v42 E-1
      showStatus(statusMsg, "success", "재설정되었습니다.");
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
