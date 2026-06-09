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

function getSelectedOrderCheckboxes() {
  return Array.from(document.querySelectorAll(".order-row-chk:checked"));
}

function getSelectedOrders() {
  return getSelectedOrderCheckboxes().map((checkbox) => ({
    orderId: checkbox.dataset.orderId || checkbox.value || "",
    marketplace: checkbox.dataset.marketplace || "",
    status: checkbox.dataset.status || "",
  }));
}

function getAllowedStatusesForSelection(selectedOrders) {
  if (!selectedOrders.length) return [];
  return selectedOrders.reduce((allowed, order, index) => {
    const nextStatuses = STATUS_TRANSITIONS[order.status] || [];
    if (index === 0) return [...nextStatuses];
    return allowed.filter((status) => nextStatuses.includes(status));
  }, []);
}

function syncOrdersSelectAllState() {
  const selectAll = document.getElementById("ordersSelectAll");
  const checkboxes = Array.from(document.querySelectorAll(".order-row-chk"));
  if (!selectAll || !checkboxes.length) return;
  const checkedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
  selectAll.checked = checkedCount > 0 && checkedCount === checkboxes.length;
  selectAll.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;
}

function updateBulkActionState() {
  const selectedOrders = getSelectedOrders();
  const allowedStatuses = getAllowedStatusesForSelection(selectedOrders);
  const selectionCountEl = document.getElementById("bulkSelectionCount");
  const hintEl = document.getElementById("bulkActionHint");
  const bulkTrackingButton = document.getElementById("bulkTrackingButton");
  const bulkShipButton = document.getElementById("bulkShipButton");
  const bulkStatusButton = document.getElementById("bulkStatusButton");

  if (selectionCountEl) {
    selectionCountEl.textContent = `${selectedOrders.length}건 선택`;
  }
  if (bulkTrackingButton) {
    bulkTrackingButton.disabled = selectedOrders.length === 0;
    bulkTrackingButton.title = selectedOrders.length === 0
      ? "주문을 1건 이상 선택하면 일괄 운송장 등록을 사용할 수 있습니다."
      : "";
  }
  if (bulkShipButton) {
    bulkShipButton.disabled = !allowedStatuses.includes("shipped");
    bulkShipButton.title = allowedStatuses.includes("shipped")
      ? ""
      : "선택한 주문에 배송중(shipped)으로 가능한 공통 상태 전이가 없습니다.";
  }
  if (bulkStatusButton) {
    bulkStatusButton.disabled = allowedStatuses.length === 0;
    bulkStatusButton.title = allowedStatuses.length === 0
      ? "공통 상태 흐름이 있는 주문을 선택하면 일괄 상태 변경을 사용할 수 있습니다."
      : "";
  }
  if (hintEl) {
    if (!selectedOrders.length) {
      hintEl.textContent = "선택한 주문이 없어 일괄 액션을 사용할 수 없습니다.";
    } else if (!allowedStatuses.length) {
      hintEl.textContent = "선택한 주문들의 현재 상태가 달라 공통으로 가능한 일괄 상태 변경이 없습니다.";
    } else {
      hintEl.textContent = `공통 상태 변경 가능: ${allowedStatuses.join(", ")}`;
    }
  }

  syncOrdersSelectAllState();
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

function initOrderSelection() {
  const selectAll = document.getElementById("ordersSelectAll");
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      document.querySelectorAll(".order-row-chk").forEach((checkbox) => {
        checkbox.checked = selectAll.checked;
      });
      updateBulkActionState();
    });
  }
  document.querySelectorAll(".order-row-chk").forEach((checkbox) => {
    checkbox.addEventListener("change", updateBulkActionState);
  });
  updateBulkActionState();
}

/** 현재 URL 파라미터 유지하며 페이지 새로고침 */
function refreshOrders() {
  window.location.reload();
}

async function parseJsonSafe(response, context) {
  try {
    return await response.json();
  } catch (error) {
    console.warn(`${context} 응답 파싱 실패`, error);
    return { ok: false, error: "응답 파싱에 실패했습니다." };
  }
}

function getRetryHint(statusCode) {
  if (statusCode === 503) return " 서비스가 준비되면 다시 시도하세요.";
  if (statusCode >= 500) return " 내부 오류입니다. 잠시 후 다시 시도하세요.";
  return "";
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

function openBulkTrackingModal() {
  const selectedOrders = getSelectedOrders();
  if (!selectedOrders.length) {
    showToast("운송장을 등록할 주문을 먼저 선택하세요.", "warning");
    return;
  }

  const rowsEl = document.getElementById("bulkTrackingRows");
  const summaryEl = document.getElementById("bulkTrackingSelectionSummary");
  const courierInput = document.getElementById("btm-courier");
  if (!rowsEl || !summaryEl || !courierInput) return;

  summaryEl.textContent = `${selectedOrders.length}건의 주문에 공통 택배사를 적용합니다. 운송장 번호는 주문별로 입력하세요.`;
  courierInput.value = "";
  rowsEl.replaceChildren();
  selectedOrders.forEach((order) => {
    const group = document.createElement("div");
    group.className = "input-group input-group-sm";

    const label = document.createElement("span");
    label.className = "input-group-text";
    label.textContent = `${order.marketplace}/${order.orderId}`;

    const input = document.createElement("input");
    input.type = "text";
    input.className = "form-control bulk-tracking-no";
    input.dataset.orderId = order.orderId;
    input.dataset.marketplace = order.marketplace;
    input.placeholder = "운송장 번호";
    input.setAttribute("aria-label", `${order.orderId} 운송장 번호`);

    group.append(label, input);
    rowsEl.appendChild(group);
  });

  const modal = new bootstrap.Modal(document.getElementById("bulkTrackingModal"));
  modal.show();
  setTimeout(() => document.querySelector(".bulk-tracking-no")?.focus(), MODAL_FOCUS_DELAY_MS);
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

  const saveButton = document.getElementById("trackingSaveButton");
  if (window.setButtonLoading && saveButton) {
    window.setButtonLoading(saveButton, true, "저장 중…");
  }

  try {
    const resp = await fetch(`/seller/orders/${encodeURIComponent(marketplace)}/${encodeURIComponent(orderId)}/tracking`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ courier, tracking_no: trackingNo }),
    });
    const data = await parseJsonSafe(resp, "운송장 등록");
    if (!resp.ok || !data.ok) {
      const retryHint = getRetryHint(resp.status);
      showToast("운송장 등록 실패: " + (data.error || "오류") + retryHint, "danger");
      return;
    }
    const modalEl = document.getElementById("trackingModal");
    bootstrap.Modal.getInstance(modalEl)?.hide();
    if (data.ok) {
      showToast("운송장이 등록되었습니다.");
      setTimeout(refreshOrders, 1000);
    }
  } catch (e) {
    showToast("요청 실패: " + e.message + " (네트워크 상태를 확인하고 다시 시도하세요.)", "danger");
  } finally {
    if (window.setButtonLoading && saveButton) {
      window.setButtonLoading(saveButton, false);
    }
  }
}

async function saveBulkTracking() {
  const courier = document.getElementById("btm-courier")?.value.trim() || "";
  if (!courier) {
    showToast("택배사를 입력하세요.", "warning");
    return;
  }

  const inputs = Array.from(document.querySelectorAll(".bulk-tracking-no"));
  if (!inputs.length) {
    showToast("선택된 주문이 없습니다.", "warning");
    return;
  }

  const items = inputs.map((input) => ({
    order_id: input.dataset.orderId || "",
    marketplace: input.dataset.marketplace || "",
    courier,
    tracking_no: input.value.trim(),
  }));
  const invalidRows = items.filter((item) => !item.order_id || !item.marketplace);
  if (invalidRows.length) {
    showToast("선택 주문 정보가 올바르지 않아 일괄 운송장을 저장할 수 없습니다.", "danger");
    return;
  }
  const missing = items.filter((item) => !item.tracking_no);
  if (missing.length) {
    showToast(`운송장 번호가 비어 있는 주문이 ${missing.length}건 있습니다.`, "warning");
    return;
  }

  const saveButton = document.getElementById("bulkTrackingSaveButton");
  if (window.setButtonLoading) {
    window.setButtonLoading(saveButton, true, "저장 중…");
  }

  try {
    const resp = await fetch("/seller/orders/bulk/tracking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      showToast(data.error || "일괄 운송장 등록 실패", "danger");
      return;
    }
    const failedCount = Array.isArray(data.results) ? data.results.filter((item) => !item.ok).length : 0;
    bootstrap.Modal.getInstance(document.getElementById("bulkTrackingModal"))?.hide();
    if (failedCount) {
      showToast(`일괄 운송장 등록 완료 (${items.length - failedCount}/${items.length}건 성공)`, "warning");
    } else {
      showToast(`일괄 운송장 등록 완료 (${items.length}건)`);
    }
    setTimeout(refreshOrders, REFRESH_DELAY_MS);
  } catch (error) {
    showToast("일괄 운송장 등록 요청 실패: " + error.message, "danger");
  } finally {
    if (window.setButtonLoading) {
      window.setButtonLoading(saveButton, false);
    }
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
  const statusSelect = document.getElementById("sm-next-status");
  const reasonInput = document.getElementById("sm-reason");
  const helpEl = document.getElementById("sm-status-help");
  if (!statusSelect || !reasonInput || !helpEl) return;
  document.getElementById("sm-marketplace").value = marketplace;
  document.getElementById("sm-order-id").value = orderId;
  statusSelect.innerHTML = options.map((status) => `<option value="${status}">${status}</option>`).join("");
  reasonInput.value = "";
  helpEl.textContent = `현재 상태: ${currentStatus} · 가능 값: ${options.join(", ")}`;
  const modal = new bootstrap.Modal(document.getElementById("statusModal"));
  modal.show();
  setTimeout(() => statusSelect.focus(), MODAL_FOCUS_DELAY_MS);
}

async function updateOrderStatus(marketplace, orderId, nextStatus, reason = "") {
  try {
    const resp = await fetch(`/seller/orders/${encodeURIComponent(marketplace)}/${encodeURIComponent(orderId)}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ next_status: nextStatus, reason }),
    });
    const data = await parseJsonSafe(resp, "상태 변경");
    if (!resp.ok || !data.ok) {
      const retryHint = getRetryHint(resp.status);
      showToast((data.error || "상태 변경 실패") + retryHint, "danger");
      return false;
    }
    const simulated = !!(data.adapter && data.adapter.simulated && !data.adapter.applied);
    showToast(
      simulated
        ? `상태 저장 완료(${nextStatus}) · 외부 연동 미설정으로 로컬 반영`
        : `상태가 ${nextStatus}(으)로 변경되었습니다.`,
      simulated ? "warning" : "success",
    );
    setTimeout(refreshOrders, REFRESH_DELAY_MS);
    return true;
  } catch (e) {
    showToast("상태 변경 요청 실패: " + e.message + " (네트워크 확인 후 재시도하세요.)", "danger");
    return false;
  }
}

async function submitStatusChange() {
  const marketplace = document.getElementById("sm-marketplace")?.value || "";
  const orderId = document.getElementById("sm-order-id")?.value || "";
  const nextStatus = document.getElementById("sm-next-status")?.value || "";
  const reason = document.getElementById("sm-reason")?.value.trim() || "";
  if (!nextStatus) {
    showToast("변경할 상태를 선택하세요.", "warning");
    return;
  }
  const saveButton = document.getElementById("statusSaveButton");
  if (window.setButtonLoading) {
    window.setButtonLoading(saveButton, true, "저장 중…");
  }
  try {
    const ok = await updateOrderStatus(marketplace, orderId, nextStatus, reason);
    if (ok) {
      bootstrap.Modal.getInstance(document.getElementById("statusModal"))?.hide();
    }
  } finally {
    if (window.setButtonLoading) {
      window.setButtonLoading(saveButton, false);
    }
  }
}

function openBulkStatusModal() {
  const selectedOrders = getSelectedOrders();
  const allowedStatuses = getAllowedStatusesForSelection(selectedOrders);
  if (!selectedOrders.length) {
    showToast("상태를 변경할 주문을 먼저 선택하세요.", "warning");
    return;
  }
  if (!allowedStatuses.length) {
    showToast("선택한 주문에 공통으로 적용할 수 있는 다음 상태가 없습니다.", "warning");
    return;
  }

  const select = document.getElementById("bsm-next-status");
  const reason = document.getElementById("bsm-reason");
  const helpEl = document.getElementById("bsm-status-help");
  const summaryEl = document.getElementById("bulkStatusSelectionSummary");
  if (!select || !reason || !helpEl || !summaryEl) return;

  select.innerHTML = allowedStatuses.map((status) => `<option value="${status}">${status}</option>`).join("");
  reason.value = "";
  summaryEl.textContent = `${selectedOrders.length}건 선택 · 공통으로 가능한 상태만 표시합니다.`;
  helpEl.textContent = `가능 값: ${allowedStatuses.join(", ")}`;

  const modal = new bootstrap.Modal(document.getElementById("bulkStatusModal"));
  modal.show();
  setTimeout(() => select.focus(), MODAL_FOCUS_DELAY_MS);
}

async function runBulkStatusChange(nextStatus, reason = "") {
  const selectedOrders = getSelectedOrders();
  if (!selectedOrders.length) {
    showToast("상태를 변경할 주문을 먼저 선택하세요.", "warning");
    return false;
  }

  const saveButton = document.getElementById("bulkStatusSaveButton");
  if (window.setButtonLoading && saveButton) {
    window.setButtonLoading(saveButton, true, "저장 중…");
  }

  try {
    const resp = await fetch("/seller/orders/bulk/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items: selectedOrders.map((order) => ({ order_id: order.orderId, marketplace: order.marketplace })),
        next_status: nextStatus,
        reason,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      showToast(data.error || "일괄 상태 변경 실패", "danger");
      return false;
    }
    const successCount = data.success_count || 0;
    const failedCount = data.failed_count || 0;
    bootstrap.Modal.getInstance(document.getElementById("bulkStatusModal"))?.hide();
    if (failedCount) {
      showToast(`일괄 상태 변경 완료 (${successCount}/${successCount + failedCount}건 성공)`, "warning");
    } else {
      showToast(`선택 주문 ${successCount}건을 ${nextStatus}(으)로 변경했습니다.`);
    }
    setTimeout(refreshOrders, REFRESH_DELAY_MS);
    return true;
  } catch (error) {
    showToast("일괄 상태 변경 요청 실패: " + error.message, "danger");
    return false;
  } finally {
    if (window.setButtonLoading && saveButton) {
      window.setButtonLoading(saveButton, false);
    }
  }
}

async function submitBulkStatusChange() {
  const nextStatus = document.getElementById("bsm-next-status")?.value || "";
  const reason = document.getElementById("bsm-reason")?.value.trim() || "";
  if (!nextStatus) {
    showToast("변경할 상태를 선택하세요.", "warning");
    return;
  }
  await runBulkStatusChange(nextStatus, reason);
}

function bulkUpdateSelectedStatus(nextStatus) {
  const allowedStatuses = getAllowedStatusesForSelection(getSelectedOrders());
  if (!allowedStatuses.includes(nextStatus)) {
    showToast("선택한 주문에 공통으로 적용할 수 없는 상태입니다.", "warning");
    return;
  }
  runBulkStatusChange(nextStatus);
}

initCourierTypeahead();
initOrderSelection();
