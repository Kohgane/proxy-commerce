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
setInterval(refreshOrders, POLL_INTERVAL);

/** 현재 URL 파라미터 유지하며 페이지 새로고침 */
function refreshOrders() {
  window.location.reload();
}

/** 동기화 버튼 핸들러 */
async function syncNow() {
  const btn = document.querySelector("button[onclick='syncNow()']");
  const spinner = document.getElementById("sync-spinner");
  if (btn) btn.disabled = true;
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
    if (btn) btn.disabled = false;
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
