/**
 * orders.js — 주문 관리 페이지 스크립트 (Phase 129)
 * - 5분 자동 폴링
 * - 동기화 버튼
 * - 운송장 입력 모달
 * - 토스트 알림
 */

"use strict";

// 5분 자동 폴링
const POLL_INTERVAL = 5 * 60 * 1000;
const REFRESH_DELAY_MS = 900;
const TYPEAHEAD_DEBOUNCE_MS = 180;
const BLUR_CLOSE_DELAY_MS = 120;
const MODAL_FOCUS_DELAY_MS = 120;
const TYPEAHEAD_LIMIT = 10;
setInterval(refreshOrders, POLL_INTERVAL);
const typeaheadState = {
  activeIndex: -1,
  suggestions: [],
  debounceTimer: null,
};

function normalizeCourierText(value) {
  // 검색 매칭을 위해 공백/하이픈/언더스코어를 제거한 정규화 문자열을 만든다.
  return String(value || "").toLowerCase().trim().replace(/[\s_-]+/g, "");
}

function loadCourierCatalog() {
  const scriptEl = document.getElementById("tm-courier-catalog");
  if (!scriptEl) return [];
  try {
    const parsed = JSON.parse(scriptEl.textContent || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (_error) {
    return [];
  }
}

const COURIER_CATALOG = loadCourierCatalog();

function getCourierTypeaheadElements() {
  return {
    input: document.getElementById("tm-courier"),
    listbox: document.getElementById("tm-courier-listbox"),
    trackingInput: document.getElementById("tm-tracking-no"),
  };
}

function renderCourierSuggestions() {
  const { input, listbox } = getCourierTypeaheadElements();
  if (!input || !listbox) return;

  listbox.innerHTML = "";
  const isOpen = typeaheadState.suggestions.length > 0;
  listbox.classList.toggle("d-none", !isOpen);
  input.setAttribute("aria-expanded", isOpen ? "true" : "false");

  if (!isOpen) {
    input.removeAttribute("aria-activedescendant");
    return;
  }

  typeaheadState.suggestions.forEach((courier, index) => {
    const option = document.createElement("button");
    option.type = "button";
    option.className = `list-group-item list-group-item-action${index === typeaheadState.activeIndex ? " active" : ""}`;
    option.id = `tm-courier-option-${index}`;
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", index === typeaheadState.activeIndex ? "true" : "false");
    option.textContent = courier.name;
    option.addEventListener("mousedown", (event) => event.preventDefault());
    option.addEventListener("click", () => selectCourierSuggestion(index));
    listbox.appendChild(option);
  });

  if (typeaheadState.activeIndex >= 0) {
    input.setAttribute("aria-activedescendant", `tm-courier-option-${typeaheadState.activeIndex}`);
  } else {
    input.removeAttribute("aria-activedescendant");
  }
}

function closeCourierSuggestions() {
  typeaheadState.activeIndex = -1;
  typeaheadState.suggestions = [];
  renderCourierSuggestions();
}

function getCourierSuggestions(query) {
  const normalizedQuery = normalizeCourierText(query);
  const rows = COURIER_CATALOG.filter((courier) => {
    const terms = Array.isArray(courier.search_terms) ? courier.search_terms : [];
    return terms.some((term) => normalizeCourierText(term).includes(normalizedQuery));
  });
  rows.sort((a, b) => a.name.localeCompare(b.name, "ko-KR"));
  return rows.slice(0, TYPEAHEAD_LIMIT);
}

function selectCourierSuggestion(index) {
  const { input, trackingInput } = getCourierTypeaheadElements();
  const selected = typeaheadState.suggestions[index];
  if (!input || !selected) return;
  input.value = selected.name;
  closeCourierSuggestions();
  trackingInput?.focus();
}

function scheduleCourierFilter() {
  if (typeaheadState.debounceTimer) {
    clearTimeout(typeaheadState.debounceTimer);
  }
  typeaheadState.debounceTimer = setTimeout(() => {
    const { input } = getCourierTypeaheadElements();
    const query = normalizeCourierText(input?.value || "");
    if (!query) {
      closeCourierSuggestions();
      return;
    }
    typeaheadState.suggestions = getCourierSuggestions(query);
    typeaheadState.activeIndex = typeaheadState.suggestions.length ? 0 : -1;
    renderCourierSuggestions();
  }, TYPEAHEAD_DEBOUNCE_MS);
}

function initCourierTypeahead() {
  const { input, listbox } = getCourierTypeaheadElements();
  if (!input || !listbox) return;

  input.addEventListener("input", scheduleCourierFilter);
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!typeaheadState.suggestions.length) {
        scheduleCourierFilter();
        return;
      }
      typeaheadState.activeIndex = (typeaheadState.activeIndex + 1) % typeaheadState.suggestions.length;
      renderCourierSuggestions();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!typeaheadState.suggestions.length) return;
      typeaheadState.activeIndex =
        (typeaheadState.activeIndex - 1 + typeaheadState.suggestions.length) % typeaheadState.suggestions.length;
      renderCourierSuggestions();
      return;
    }
    if (event.key === "Enter" && typeaheadState.activeIndex >= 0 && typeaheadState.suggestions.length) {
      event.preventDefault();
      selectCourierSuggestion(typeaheadState.activeIndex);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeCourierSuggestions();
    }
  });
  input.addEventListener("focus", () => {
    if (normalizeCourierText(input.value)) {
      scheduleCourierFilter();
    }
  });
  input.addEventListener("blur", () => {
    setTimeout(closeCourierSuggestions, BLUR_CLOSE_DELAY_MS);
  });
  document.addEventListener("click", (event) => {
    if (!listbox.contains(event.target) && event.target !== input) {
      closeCourierSuggestions();
    }
  });
}

/** 현재 URL 파라미터 유지하며 페이지 새로고침 */
function refreshOrders() {
  window.location.reload();
}

/** 동기화 버튼 핸들러 */
async function syncNow() {
  const btn = document.getElementById("ordersSyncButton");
  const spinner = document.getElementById("sync-spinner");
  if (window.setButtonLoading) {
    window.setButtonLoading(btn, true, "동기화 중…");
  } else if (btn) {
    btn.disabled = true;
  }
  if (spinner) spinner.classList.remove("d-none");

  try {
    const resp = await fetch("/seller/orders/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await resp.json();
    if (data.ok) {
      const counts = Object.entries(data.results || {})
        .map(([k, v]) => `${k}: ${v.fetched ?? "?"}건`)
        .join(", ");
      showToast(`동기화 완료 — ${counts || "0건"}`);
      setTimeout(refreshOrders, 1500);
    } else {
      showToast("동기화 실패: " + (data.error || "알 수 없는 오류"), "danger");
    }
  } catch (e) {
    showToast("동기화 요청 실패: " + e.message, "danger");
  } finally {
    if (window.setButtonLoading) {
      window.setButtonLoading(btn, false);
    } else if (btn) {
      btn.disabled = false;
    }
    if (spinner) spinner.classList.add("d-none");
  }
}

/** 운송장 모달 열기 */
function openTrackingModal(marketplace, orderId) {
  document.getElementById("tm-marketplace").value = marketplace;
  document.getElementById("tm-order-id").value = orderId;
  document.getElementById("tm-courier").value = "";
  document.getElementById("tm-tracking-no").value = "";
  closeCourierSuggestions();
  const modal = new bootstrap.Modal(document.getElementById("trackingModal"));
  modal.show();
  setTimeout(() => document.getElementById("tm-courier")?.focus(), MODAL_FOCUS_DELAY_MS);
}

/** 운송장 저장 */
async function saveTracking() {
  const marketplace = document.getElementById("tm-marketplace").value;
  const orderId = document.getElementById("tm-order-id").value;
  // 저장 시에는 사용자가 입력한 free text를 유지하되 앞뒤 공백만 제거한다.
  const courier = document.getElementById("tm-courier").value.trim();
  const trackingNo = document.getElementById("tm-tracking-no").value.trim();

  if (!courier) {
    showToast("택배사를 입력하세요.", "warning");
    return;
  }
  if (!trackingNo) {
    showToast("운송장 번호를 입력하세요.", "warning");
    return;
  }

  try {
    const resp = await fetch(`/seller/orders/${encodeURIComponent(marketplace)}/${encodeURIComponent(orderId)}/tracking`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ courier, tracking_no: trackingNo }),
    });
    const data = await resp.json();
    const modalEl = document.getElementById("trackingModal");
    bootstrap.Modal.getInstance(modalEl)?.hide();
    if (data.ok) {
      showToast("운송장이 등록되었습니다.");
      setTimeout(refreshOrders, 1000);
    } else {
      showToast("운송장 등록 실패: " + (data.error || "오류"), "danger");
    }
  } catch (e) {
    showToast("요청 실패: " + e.message, "danger");
  }
}

/** 토스트 알림 헬퍼 */
function showToast(message, type = "success") {
  if (window.showGlobalToast) {
    window.showGlobalToast(message, type, { toastId: "toast", bodyId: "toast-msg" });
    return;
  }
  const toastEl = document.getElementById("toast");
  const msgEl = document.getElementById("toast-msg");
  if (!toastEl || !msgEl) return;
  msgEl.textContent = message;
  toastEl.className = `toast border-0 bg-${type === "success" ? "success" : type === "danger" ? "danger" : "warning"} text-white`;
  const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
  toast.show();
}

/** URL 파라미터 기반 필터 상태 관리 */
function getFilterState() {
  const params = new URLSearchParams(window.location.search);
  return {
    marketplace: params.getAll("marketplace"),
    status: params.get("status") || "",
    search: params.get("search") || "",
    date_from: params.get("date_from") || "",
    date_to: params.get("date_to") || "",
  };
}

function setFilterState(state) {
  const params = new URLSearchParams();
  (state.marketplace || []).forEach((mp) => params.append("marketplace", mp));
  if (state.status) params.set("status", state.status);
  if (state.search) params.set("search", state.search);
  if (state.date_from) params.set("date_from", state.date_from);
  if (state.date_to) params.set("date_to", state.date_to);
  window.location.search = params.toString();
}

const STATUS_TRANSITIONS = {
  new: ["paid", "canceled"],
  paid: ["preparing", "canceled", "refund_requested"],
  preparing: ["shipped", "canceled"],
  shipped: ["delivered", "returned", "exchanged"],
  delivered: ["returned", "exchanged"],
  refund_requested: ["returned", "canceled"],
};

function openStatusPrompt(marketplace, orderId, currentStatus) {
  const options = STATUS_TRANSITIONS[currentStatus] || [];
  if (!options.length) {
    showToast(`현재 상태(${currentStatus})에서는 변경 가능한 다음 상태가 없습니다.`, "warning");
    return;
  }
  const answer = window.prompt(
    `다음 상태를 입력하세요.\n가능 값: ${options.join(", ")}`,
    options[0],
  );
  if (!answer) return;
  const nextStatus = answer.trim().toLowerCase();
  if (!options.includes(nextStatus)) {
    showToast(`허용되지 않은 상태입니다: ${nextStatus}`, "warning");
    return;
  }
  updateOrderStatus(marketplace, orderId, nextStatus);
}

async function updateOrderStatus(marketplace, orderId, nextStatus) {
  try {
    const resp = await fetch(`/seller/orders/${encodeURIComponent(marketplace)}/${encodeURIComponent(orderId)}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ next_status: nextStatus }),
    });
    const data = await resp.json();
    if (!data.ok) {
      showToast(data.error || "상태 변경 실패", "danger");
      return;
    }
    const simulated = !!(data.adapter && data.adapter.simulated && !data.adapter.applied);
    showToast(
      simulated
        ? `상태 저장 완료(${nextStatus}) · 외부 연동 미설정으로 로컬 반영`
        : `상태가 ${nextStatus}(으)로 변경되었습니다.`,
      simulated ? "warning" : "success",
    );
    setTimeout(refreshOrders, REFRESH_DELAY_MS);
  } catch (e) {
    showToast("상태 변경 요청 실패: " + e.message, "danger");
  }
}

initCourierTypeahead();
