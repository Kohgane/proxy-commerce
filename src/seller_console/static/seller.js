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

function showGlobalToast(message, type = 'info', options = {}) {
  const toastEl = options.toastId
    ? document.getElementById(options.toastId)
    : (document.getElementById('catalogToast') || document.getElementById('toast') || document.getElementById('uploadToast'));
  if (!toastEl) {
    return;
  }
  const body = options.bodyId
    ? document.getElementById(options.bodyId)
    : (
      document.getElementById('catalogToastBody')
      || document.getElementById('toast-msg')
      || document.getElementById('toastBody')
    );
  if (body) body.textContent = message;
  const map = {success: 'success', danger: 'danger', warning: 'warning', error: 'danger', info: 'info'};
  const tone = map[type] || 'info';
  toastEl.className = `toast text-bg-${tone} border-0`;
  new bootstrap.Toast(toastEl, {delay: 3000}).show();
}

/**
 * 전역 토스트 알림 (pcToast) — 페이지에 별도 토스트 엘리먼트가 없어도 동작한다.
 * `_base.html`의 #pcToastContainer에 동적으로 토스트를 생성/표시/제거한다.
 * 차단형 alert()를 대체하는 honest-UI 비차단 알림.
 * @param {string} message - 표시할 메시지 (텍스트로 안전하게 삽입)
 * @param {string} type - 'success' | 'error' | 'danger' | 'warning' | 'info'
 */
function pcToast(message, type = 'info') {
  let container = document.getElementById('pcToastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'pcToastContainer';
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    container.style.zIndex = '1090';
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-atomic', 'true');
    document.body.appendChild(container);
  }
  const toneMap = {success: 'success', error: 'danger', danger: 'danger', warning: 'warning', info: 'secondary'};
  const iconMap = {success: '✅', error: '❌', danger: '❌', warning: '⚠️', info: 'ℹ️'};
  const tone = toneMap[type] || 'secondary';

  const toastEl = document.createElement('div');
  toastEl.className = `toast align-items-center text-bg-${tone} border-0`;
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', 'assertive');
  toastEl.setAttribute('aria-atomic', 'true');

  const flex = document.createElement('div');
  flex.className = 'd-flex';
  const body = document.createElement('div');
  body.className = 'toast-body';
  body.textContent = `${iconMap[type] || ''} ${message}`.trim();
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn-close btn-close-white me-2 m-auto';
  closeBtn.setAttribute('data-bs-dismiss', 'toast');
  closeBtn.setAttribute('aria-label', '닫기');
  flex.appendChild(body);
  flex.appendChild(closeBtn);
  toastEl.appendChild(flex);
  container.appendChild(toastEl);

  const delay = (type === 'error' || type === 'danger') ? 6000 : 3500;
  if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
    const toast = new bootstrap.Toast(toastEl, {delay});
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    toast.show();
  } else {
    // bootstrap 미로딩 폴백: 잠깐 보여주고 제거
    toastEl.classList.add('show');
    setTimeout(() => toastEl.remove(), delay);
  }
}

/**
 * 전역 확인 모달 (pcConfirm) — 차단형 네이티브 confirm()을 대체한다.
 * Promise<boolean>을 반환하므로 `if (!(await pcConfirm('...'))) return;` 형태로 사용.
 * `_base.html`의 #pcConfirmModal을 재사용하며, bootstrap/모달이 없으면 네이티브 confirm 폴백.
 * @param {string} message - 본문 메시지 (개행 \n 지원, textContent로 안전 삽입)
 * @param {object} [options] - {title, confirmLabel, cancelLabel, danger}
 * @returns {Promise<boolean>}
 */
function pcConfirm(message, options = {}) {
  return new Promise((resolve) => {
    const modalEl = document.getElementById('pcConfirmModal');
    if (!modalEl || typeof bootstrap === 'undefined' || !bootstrap.Modal) {
      resolve(window.confirm(message));
      return;
    }
    const titleEl = document.getElementById('pcConfirmTitle');
    const bodyEl = document.getElementById('pcConfirmBody');
    const okBtn = document.getElementById('pcConfirmOk');
    const cancelBtn = document.getElementById('pcConfirmCancel');

    if (titleEl) titleEl.textContent = options.title || '확인';
    // 개행을 보존하면서 XSS 없이 삽입
    if (bodyEl) {
      bodyEl.textContent = '';
      String(message).split('\n').forEach((line, idx) => {
        if (idx > 0) bodyEl.appendChild(document.createElement('br'));
        bodyEl.appendChild(document.createTextNode(line));
      });
    }
    if (okBtn) {
      okBtn.textContent = options.confirmLabel || '확인';
      okBtn.className = 'btn btn-' + (options.danger === false ? 'primary' : 'danger');
    }
    if (cancelBtn) cancelBtn.textContent = options.cancelLabel || '취소';

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    let settled = false;
    const onOk = () => { settled = true; cleanup(); modal.hide(); resolve(true); };
    const onHide = () => { if (!settled) { cleanup(); resolve(false); } };
    function cleanup() {
      if (okBtn) okBtn.removeEventListener('click', onOk);
      modalEl.removeEventListener('hidden.bs.modal', onHide);
    }
    if (okBtn) okBtn.addEventListener('click', onOk);
    modalEl.addEventListener('hidden.bs.modal', onHide);
    modal.show();
  });
}

function setButtonLoading(button, isLoading, loadingText = '처리 중…') {
  if (!button) return;
  if (isLoading) {
    button.dataset.originalText = button.innerHTML;
    button.classList.add('pc-btn-loading');
    button.disabled = true;
    button.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${loadingText}`;
    return;
  }
  if (button.dataset.originalText) {
    button.innerHTML = button.dataset.originalText;
    delete button.dataset.originalText;
  }
  button.classList.remove('pc-btn-loading');
  button.disabled = false;
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
