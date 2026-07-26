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

// v81 STEP3: 소싱처 목록/매처는 kgp-sources.js(단일 진실원천)에 위임 — 콘텐츠스크립트와 byte-동일 판정.
//   과거엔 popup이 6개만 든 자체 목록이라 rakuten 등에서 콘텐츠스크립트와 모순됐다(팝업 미지정/FAB 노출).

function getSettings() {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "getSettings" }, (resp) => {
      if (chrome.runtime.lastError) {
        resolve({});
        return;
      }
      resolve(resp || {});
    });
  });
}

// URL이 상품/목록 페이지로 보이나? — kgp-detect의 URL 규칙 재사용(팝업은 페이지 DOM이 없어 URL만 판정).
function _looksCollectable(url) {
  try {
    const D = (typeof KGPDetect !== "undefined") ? KGPDetect : null;
    if (!D) return true;   // 규칙 미로드 시 보수적으로 '수집 가능'(안내만 다름).
    if (D.DETAIL_URL_RE.test(url) || D.LIST_URL_RE.test(url)) return true;
    // 톱/홈(경로 없음)만 '아직 아님'으로 안내 — 그 외(상세/목록 애매)는 수집 가능으로 둔다.
    let path = "/";
    try { path = new URL(url).pathname || "/"; } catch (e) {}
    return !(path === "/" || path === "");
  } catch (e) { return true; }
}

// 현재 탭이 지정 소싱처인지 표시. v81 STEP3: 세 상태로 분리.
//   ① 호스트 미등록 → "지정 소싱처가 아니에요"  ② 소싱처+상품/목록 → "수집 버튼이 표시돼요"
//   ③ 소싱처지만 톱/홈 → "○○입니다. 상품/목록 페이지에서 수집할 수 있어요"(호스트 등록 O·페이지 타입 X).
function updateSourceBadge(url) {
  let host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch (e) { host = ""; }
  chrome.storage.local.get("kgp_sources", (r) => {
    const s = (r && r.kgp_sources) || {};
    const m = (typeof KGPSources !== "undefined") ? KGPSources.matchHost(host, s) : null;
    if (!m) {
      srcBadge.className = "src-badge off";
      srcBadge.textContent = "여긴 지정 소싱처가 아니에요. ‘소싱처 관리’에서 추가할 수 있어요.";
      return;
    }
    if (_looksCollectable(url)) {
      srcBadge.className = "src-badge on";
      srcBadge.textContent = `지정 소싱처 (${m.label}) — 수집 버튼이 표시돼요`;
    } else {
      srcBadge.className = "src-badge on";
      srcBadge.textContent = `${m.label}입니다 (소싱처 ✓). 상품·목록 페이지에서 수집 버튼이 나와요.`;
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

// v83.1 STEP1: 한국어 번역 토글 — 상태 기억(chrome.storage.local.kgp_translate, 기본 ON).
//   OFF면 background가 수집 페이로드에 translate:false를 실어 서버 번역 파이프라인을 건너뛴다(원문 그대로 저장).
//   **원문은 토글과 무관하게 항상 보존**된다 — 번역본(title_ko 등)은 파생 필드일 뿐이다.
//   같은 키를 인페이지 수집 카드도 읽고 쓴다(onChanged로 양방향 즉시 동기).
const translateToggle = document.getElementById("translateToggle");
const translateNote = document.getElementById("translateNote");
function _kgpRenderTranslateNote(on) {
  if (translateNote) translateNote.textContent = on ? "(원문은 항상 보존돼요)" : "(원문 그대로 저장돼요)";
}
if (translateToggle) {
  chrome.storage.local.get("kgp_translate", (r) => {
    const on = !(r && r.kgp_translate === false);
    translateToggle.checked = on;
    _kgpRenderTranslateNote(on);
  });
  translateToggle.addEventListener("change", () => {
    chrome.storage.local.set({ kgp_translate: translateToggle.checked });
    _kgpRenderTranslateNote(translateToggle.checked);
  });
  // 인페이지 카드에서 껐다 켜면 팝업도 따라 바뀐다(양방향 동기).
  try {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local" || !changes || !changes.kgp_translate) return;
      const on = changes.kgp_translate.newValue !== false;
      translateToggle.checked = on;
      _kgpRenderTranslateNote(on);
    });
  } catch (e) { /* noop */ }
}

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

// v54 STEP2: 자가진단 모드 토글 — ON이면 content_script가 F12 콘솔에 캡처·채점 표를 출력(상품 API 자가발견).
const diagToggle = document.getElementById("diagToggle");
if (diagToggle) {
  chrome.storage.local.get("kgp_diag", (r) => { diagToggle.checked = !!(r && r.kgp_diag); });
  diagToggle.addEventListener("change", () => {
    chrome.storage.local.set({ kgp_diag: diagToggle.checked });   // content_script가 onChanged로 즉시 반영
  });
}

// v70 STEP5: 진단 스냅샷 저장 — 현재 탭의 렌더된 DOM을 파일로 내려받아 실페이지 하네스 픽스처로.
const btnSnapshot = document.getElementById("btnSnapshot");
const snapshotNote = document.getElementById("snapshotNote");
if (btnSnapshot) {
  btnSnapshot.addEventListener("click", () => {
    if (snapshotNote) snapshotNote.textContent = "페이지 DOM 수집 중…";
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tab = tabs && tabs[0];
      if (!tab || !tab.id) { if (snapshotNote) snapshotNote.textContent = "활성 탭을 찾지 못했어요."; return; }
      chrome.tabs.sendMessage(tab.id, { action: "kgpSnapshot" }, (res) => {
        if (chrome.runtime.lastError || !res || !res.ok || !res.html) {
          if (snapshotNote) snapshotNote.textContent = "이 페이지에서는 스냅샷을 못 떴어요(확장 새로고침 후 재시도).";
          return;
        }
        try {
          const host = (res.host || "page").replace(/[^a-z0-9.-]/gi, "_");
          const slug = (res.url || "").replace(/^https?:\/\//, "").replace(/[^a-z0-9]+/gi, "-").slice(0, 60) || host;
          const blob = new Blob([res.html], { type: "text/html" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "kgp-snapshot-" + slug + ".html";
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 2000);
          if (snapshotNote) snapshotNote.textContent = "저장됨 · fixtures/realpages/ 에 커밋하면 하네스 픽스처가 됩니다.";
        } catch (e) {
          if (snapshotNote) snapshotNote.textContent = "저장 실패: " + (e && e.message);
        }
      });
    });
  });
}

// v75 STEP3: '이 페이지 수집이 이상해요' — 스냅샷 HTML + 추출 결과 + 감지 로그를 하나의 진단 파일로 저장.
//   파일 하나(HTML=픽스처 + 임베드 JSON=실제 추출 결과)만 전달하면 하네스가 그대로 재현·대조.
const btnDiagBundle = document.getElementById("btnDiagBundle");
if (btnDiagBundle) {
  btnDiagBundle.addEventListener("click", () => {
    if (snapshotNote) snapshotNote.textContent = "진단 번들 생성 중…";
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tab = tabs && tabs[0];
      if (!tab || !tab.id) { if (snapshotNote) snapshotNote.textContent = "활성 탭을 찾지 못했어요."; return; }
      chrome.tabs.sendMessage(tab.id, { action: "kgpDiagBundle" }, (res) => {
        if (chrome.runtime.lastError || !res || !res.ok || !res.html) {
          if (snapshotNote) snapshotNote.textContent = "이 페이지에선 진단을 못 떴어요(확장 새로고침 후 재시도).";
          return;
        }
        try {
          const host = (res.host || "page").replace(/[^a-z0-9.-]/gi, "_");
          const slug = (res.url || "").replace(/^https?:\/\//, "").replace(/[^a-z0-9]+/gi, "-").slice(0, 60) || host;
          // 진단 메타(추출 결과·감지·버전)를 스냅샷 HTML 안에 <script type="application/json"> 로 임베드.
          //   → 파일 = 실페이지 픽스처 그대로 + 하네스가 읽을 실제 추출 결과. 하나로 재현.
          // v85 STEP2: **화이트리스트 금지** — content_script가 보낸 필드를 전부 싣는다(html만 제외).
          //   예전엔 키를 손으로 나열해서, content_script에 새 진단 필드(ui·git_commit·style_injected…)를
          //   추가해도 파일엔 안 찍혔다(오너 지적: "회수 완료 보고와 불일치"). 목록을 없애 drift를 원천 차단.
          const diag = {};
          Object.keys(res || {}).forEach((k) => { if (k !== "html" && k !== "ok") diag[k] = res[k]; });
          const embed = '\n<script type="application/json" id="kgp-diagnostic">'
            + JSON.stringify(diag).replace(/<\/script>/gi, "<\\/script>") + "<\/script>\n";
          const bundle = res.html + embed;
          const blob = new Blob([bundle], { type: "text/html" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "kgp-diagnostic-" + slug + ".html";
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 2000);
          const e = res.extracted || {};
          const summ = "제목=" + (e.title ? "○" : "×") + " 가격=" + ((e.price ? "○" : "×")) + " 이미지=" + ((e.images && e.images.length) || 0);
          if (snapshotNote) snapshotNote.textContent = "진단 파일 저장됨 (" + summ + ") · 이 파일 하나만 보내주시면 재현합니다.";
        } catch (e) {
          if (snapshotNote) snapshotNote.textContent = "저장 실패: " + (e && e.message);
        }
      });
    });
  });
}

// v64 STEP1: 벌크 상세 보강 큐 진행률 패널(n/총 · 일시정지 · 중단).
(function () {
  const panel = document.getElementById("enrichPanel");
  const countEl = document.getElementById("enrichCount");
  const noteEl = document.getElementById("enrichNote");
  const pauseBtn = document.getElementById("enrichPause");
  const stopBtn = document.getElementById("enrichStop");
  if (!panel) return;
  function render(s) {
    if (!s || !s.total) { panel.style.display = "none"; return; }
    panel.style.display = "block";
    countEl.textContent = s.done + "/" + s.total;
    pauseBtn.textContent = s.paused ? "재개" : "일시정지";
    let note = "";
    if (s.failed) note = "보강 실패 " + s.failed + "건";
    if (!s.running && s.done >= s.total) note = (note ? note + " · " : "") + "완료";
    else if (s.paused) note = (note ? note + " · " : "") + "일시정지됨";
    noteEl.textContent = note;
  }
  try { chrome.runtime.sendMessage({ action: "enrichState" }, (s) => { if (!chrome.runtime.lastError) render(s); }); } catch (e) {}
  try {
    chrome.runtime.onMessage.addListener((m) => { if (m && m.action === "enrichProgress") render(m.state); return false; });
  } catch (e) {}
  if (pauseBtn) pauseBtn.addEventListener("click", () => {
    const paused = pauseBtn.textContent !== "재개";   // 현재 '일시정지'면 → 정지 요청
    chrome.runtime.sendMessage({ action: "enrichPause", paused }, (s) => { if (!chrome.runtime.lastError) render(s); });
  });
  if (stopBtn) stopBtn.addEventListener("click", () => {
    chrome.runtime.sendMessage({ action: "enrichStop" }, (s) => { if (!chrome.runtime.lastError) render(s); });
  });
})();

// v67 STEP2: 상세 보강 렌더 모드(소형 창/탭 활성화/백그라운드) — background가 getSettings로 읽음.
const enrichMode = document.getElementById("enrichMode");
if (enrichMode) {
  chrome.storage.local.get("kgp_enrich_mode", (r) => { enrichMode.value = (r && r.kgp_enrich_mode) || "window"; });
  enrichMode.addEventListener("change", () => { chrome.storage.local.set({ kgp_enrich_mode: enrichMode.value }); });
}

// v64 STEP3: 호버 수집 버튼 위치(이미지 영역 앵커) — 사이트 무관 chrome.storage.local, content_script가 즉시 반영.
const hoverAnchor = document.getElementById("hoverAnchor");
if (hoverAnchor) {
  chrome.storage.local.get("kgp_hover_anchor", (r) => { hoverAnchor.value = (r && r.kgp_hover_anchor) || "center"; });
  hoverAnchor.addEventListener("change", () => {
    chrome.storage.local.set({ kgp_hover_anchor: hoverAnchor.value });   // onChanged로 즉시 반영
  });
}

// v63 STEP1: 감지 진단 패널 — 현재 탭의 실측(판정·카드수·어댑터 매치·버튼상태)을 표시.
//   추측 서술이 아니라 content_script가 실제로 계산한 값 → '왜 안 떠?'를 캡처 한 장으로 진단.
(function () {
  const body = document.getElementById("detectBody");
  if (!body) return;
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const PT = { single: "단일", list: "목록", unknown: "불능" };
  const BTN = { fab: "단건 FAB", bulkbar: "중앙 벌크바", reopen: "구석 배지", none: "없음" };
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    if (!tab || !tab.id) { body.textContent = "탭을 찾을 수 없어요"; return; }
    chrome.tabs.sendMessage(tab.id, { action: "kgpDetectState" }, (r) => {
      const err = chrome.runtime && chrome.runtime.lastError;
      if (err || !r || !r.ok) {
        body.innerHTML = "이 페이지에선 수집기가 실행되지 않았어요<br><span style='color:#b9a08c'>지정 소싱처가 아니거나 새로고침 필요</span>";
        return;
      }
      const adap = r.adapterMatched ? ("매치 " + r.adapter + "건") : "미스(제네릭 폴백)";
      const supported = r.allowed ? "✓ 소싱처" : "✗ 비지정";
      // v65 STEP2: 제외 사유 분해('제외 (광고 등)' 뭉뚱그림 금지).
      const ex = r.excl || {};
      // v67 STEP1: 제외 사유(광고·reco는 '제외'가 아니라 태그 — 버튼 부착됨). 진짜 제외만.
      const exclLine = "제외: 파싱실패 " + (ex.parse || 0)
        + " · URL실패 " + (ex.url || 0) + " · 중복 " + (ex.dup || 0) + " · 비상품영역 " + (ex.region || 0);
      // v67 STEP1: 감지 = 전 타일 버튼 부착. [메인 / 추천 / 광고] 구분(카운트만).
      const mainLine = "감지: 상품 " + r.cards + "개 (추천 " + (ex.reco || 0) + " · 광고 " + (ex.ad || 0) + " 포함) / 스캔 " + r.scanned;
      body.innerHTML = [
        "호스트: " + esc(r.host) + " · " + supported,
        "판정: " + (PT[r.pageType] || r.pageType) + " · 버튼: " + (BTN[r.button] || r.button),
        mainLine,
        "제네릭 " + r.generic + " · 어댑터 " + adap,
        exclLine,
      ].map(esc).join("<br>");
    });
  });
})();

// v82 STEP3: 페이지타입 게이트 — 단일 추출은 pageType==='single'에서만. 문구 분기(unknown/list).
//   KGPDetect(단일 소스)와 동일 규칙을 팝업에 인라인(팝업은 content_script 모듈을 로드하지 않음).
function kgpSingleGateMessage(pt) {
  if (pt === "single") return null;
  if (pt === "list") return "목록 페이지예요. 타일의 [수집] 버튼이나 벌크바를 쓰세요";
  return "상품 페이지가 아니에요. 상품/목록 페이지에서 수집할 수 있어요";
}
// 현재 탭의 pageType을 content_script(kgpDetectState)에서 조회. 미실행/오류면 'unknown'.
function kgpGetPageType() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tab = tabs && tabs[0];
      if (!tab || !tab.id) { resolve("unknown"); return; }
      chrome.tabs.sendMessage(tab.id, { action: "kgpDetectState" }, (r) => {
        if (chrome.runtime.lastError || !r || !r.ok) { resolve("unknown"); return; }
        resolve(r.pageType || "unknown");
      });
    });
  });
}
// 로드 시 게이트 반영 — single 아니면 버튼 비활성 + 안내.
(async function kgpApplySingleGate() {
  const pt = await kgpGetPageType();
  const msg = kgpSingleGateMessage(pt);
  if (msg) {
    btnCollect.disabled = true;
    btnCollect.title = msg;
    showStatus("error", msg);
  }
})();

// 수집 버튼 클릭
btnCollect.addEventListener("click", async () => {
  // v82 STEP3: 클릭 시 재확인 — single이 아니면 추출/저장하지 않고 분기 문구만.
  const gatePt = await kgpGetPageType();
  const gateMsg = kgpSingleGateMessage(gatePt);
  if (gateMsg) { showStatus("error", gateMsg); return; }

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
        const settings = await getSettings();
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
