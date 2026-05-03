/* src/seller_console/static/seller.js — 셀러 콘솔 공통 스크립트 (Phase 122) */

/**
 * 숫자를 한국식 단위로 포맷 (1234567 → "123.5만")
 */
function formatKRW(value) {
  if (value >= 100_000_000) return (value / 100_000_000).toFixed(1) + '억';
  if (value >= 10_000) return (value / 10_000).toFixed(1) + '만';
  return value.toLocaleString();
}

/**
 * 날짜 포맷 (ISO 8601 → 로컬 시간 "MM/DD HH:mm")
 */
function formatDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${mm}/${dd} ${hh}:${min}`;
}

/**
 * 토스트 메시지 표시 (Bootstrap 5)
 * @param {string} message - 표시할 메시지
 * @param {string} type - 'success' | 'error' | 'info'
 */
function showToast(message, type = 'info') {
  const toastEl = document.getElementById('uploadToast');
  if (!toastEl) return;
  const body = document.getElementById('toastBody');
  const title = document.getElementById('toastTitle');
  if (body) body.textContent = message;
  if (title) {
    title.textContent = type === 'success' ? '✅ 성공' : type === 'error' ? '❌ 오류' : 'ℹ️ 알림';
  }
  const toast = new bootstrap.Toast(toastEl, {delay: 4000});
  toast.show();
}

/**
 * API 호출 래퍼 (fetch + JSON 파싱 + 오류 처리)
 */
async function apiPost(url, payload) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  return resp.json();
}

/* 페이지 로드 완료 이벤트 */
document.addEventListener('DOMContentLoaded', function () {
  // 현재 페이지 사이드바 링크 강조 (fallback)
  const path = window.location.pathname;
  document.querySelectorAll('.sidebar .nav-link').forEach(link => {
    if (link.getAttribute('href') === path) {
      link.classList.remove('text-secondary');
      link.classList.add('text-white', 'fw-semibold');
    }
  });
});
