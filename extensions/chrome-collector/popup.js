/**
 * popup.js — 팝업 UI 로직
 * 코가네 퍼센티 수집기
 */

const btnCollect = document.getElementById("btnCollect");
const statusEl = document.getElementById("status");
const pageUrlEl = document.getElementById("pageUrl");
const statusText = document.getElementById("statusText");
const optionsLink = document.getElementById("optionsLink");

// 현재 탭 URL 표시
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (tabs[0]) {
    const url = tabs[0].url || "";
    pageUrlEl.textContent = url.length > 60 ? url.slice(0, 57) + "..." : url;
  }
});

// 설정 페이지 열기
optionsLink.addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

// 수집 버튼 클릭
btnCollect.addEventListener("click", async () => {
  btnCollect.disabled = true;
  showStatus("loading", "⏳ 상품 정보를 수집하는 중...");
  statusText.textContent = "수집 중...";

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
      showStatus("success", `✅ 수집 완료!<br><small>${meta.title || meta.url}</small>`);
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
      statusText.textContent = "수집 완료";
    } else {
      const errMsg = (response && response.error) || "수집 실패";
      showStatus("error", `❌ ${errMsg}`);
      statusText.textContent = "오류 발생";
    }
  } catch (err) {
    showStatus("error", `❌ ${err.message || "오류가 발생했습니다"}`);
    statusText.textContent = "오류 발생";
  } finally {
    btnCollect.disabled = false;
  }
});

function showStatus(type, html) {
  statusEl.className = `status ${type}`;
  statusEl.innerHTML = html;
  statusEl.style.display = "block";
}
