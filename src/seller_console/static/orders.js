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
setInterval(refreshOrders, POLL_INTERVAL);

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
  document.getElementById("tm-tracking-no").value = "";
  const modal = new bootstrap.Modal(document.getElementById("trackingModal"));
  modal.show();
}

/** 운송장 저장 */
async function saveTracking() {
  const marketplace = document.getElementById("tm-marketplace").value;
  const orderId = document.getElementById("tm-order-id").value;
  const courier = document.getElementById("tm-courier").value;
  const trackingNo = document.getElementById("tm-tracking-no").value.trim();

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
