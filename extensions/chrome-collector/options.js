/**
 * options.js — 설정 페이지 로직
 * 코가네 퍼센티 수집기
 */

const serverUrlInput = document.getElementById("serverUrl");
const tokenInput = document.getElementById("token");
const saveBtn = document.getElementById("saveBtn");
const clearBtn = document.getElementById("clearBtn");
const toggleToken = document.getElementById("toggleToken");
const statusMsg = document.getElementById("statusMsg");
const getTokenLink = document.getElementById("getTokenLink");

// 저장된 설정 로드
chrome.storage.sync.get(["serverUrl", "token"], (data) => {
  if (data.serverUrl) serverUrlInput.value = data.serverUrl;
  if (data.token) tokenInput.value = data.token;

  // 토큰 발급 링크
  const server = data.serverUrl || "https://kohganepercentiii.com";
  getTokenLink.href = server + "/seller/me/tokens";
  getTokenLink.target = "_blank";
});

// 토큰 표시/숨기기
toggleToken.addEventListener("click", () => {
  if (tokenInput.type === "password") {
    tokenInput.type = "text";
    toggleToken.textContent = "🙈";
  } else {
    tokenInput.type = "password";
    toggleToken.textContent = "👁";
  }
});

// 서버 URL 변경시 토큰 발급 링크 갱신
serverUrlInput.addEventListener("input", () => {
  const server = serverUrlInput.value.trim() || "https://kohganepercentiii.com";
  try {
    const url = new URL("/seller/me/tokens", server);
    getTokenLink.href = url.href;
  } catch (_) {
    getTokenLink.href = "https://kohganepercentiii.com/seller/me/tokens";
  }
});

// 저장
saveBtn.addEventListener("click", () => {
  const serverUrl = serverUrlInput.value.trim();
  const token = tokenInput.value.trim();

  if (!token) {
    showStatus("error", "Personal Access Token을 입력해주세요.");
    return;
  }

  chrome.storage.sync.set({ serverUrl, token }, () => {
    showStatus("success", "✅ 설정이 저장되었습니다.");
  });
});

// 초기화
clearBtn.addEventListener("click", () => {
  if (confirm("설정을 초기화하시겠습니까?")) {
    chrome.storage.sync.remove(["serverUrl", "token"], () => {
      serverUrlInput.value = "";
      tokenInput.value = "";
      showStatus("success", "설정이 초기화되었습니다.");
    });
  }
});

function showStatus(type, msg) {
  statusMsg.className = `status-msg ${type}`;
  statusMsg.textContent = msg;
  statusMsg.style.display = "block";
  setTimeout(() => { statusMsg.style.display = "none"; }, 3000);
}
