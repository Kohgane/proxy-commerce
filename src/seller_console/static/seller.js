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
  // v33 3-3: 네오-클래식 토스트 — 먹 배경·한지 텍스트·금 보더·유형 좌악센트·라인 아이콘(이모지 0).
  const toneMap = {success: 'success', error: 'danger', danger: 'danger', warning: 'warning', info: 'info'};
  const iconMap = {success: 'bi-check-circle', error: 'bi-x-circle', danger: 'bi-x-circle',
                   warning: 'bi-exclamation-triangle', info: 'bi-info-circle'};
  const tone = toneMap[type] || 'info';

  const toastEl = document.createElement('div');
  toastEl.className = `pc-toast pc-toast-${tone}`;
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', tone === 'danger' ? 'assertive' : 'polite');
  toastEl.setAttribute('aria-atomic', 'true');

  const ic = document.createElement('i');
  ic.className = `bi ${iconMap[type] || 'bi-info-circle'} pc-toast-ic`;
  ic.setAttribute('aria-hidden', 'true');
  const msg = document.createElement('div');
  msg.className = 'pc-toast-msg';
  msg.textContent = String(message == null ? '' : message);
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'pc-toast-x';
  closeBtn.setAttribute('aria-label', '닫기');
  closeBtn.innerHTML = '<i class="bi bi-x-lg" aria-hidden="true"></i>';

  toastEl.appendChild(ic);
  toastEl.appendChild(msg);
  toastEl.appendChild(closeBtn);
  container.appendChild(toastEl);

  let timer = null;
  const dismiss = () => {
    if (timer) { clearTimeout(timer); timer = null; }
    toastEl.style.transition = 'opacity .2s, transform .2s';
    toastEl.style.opacity = '0';
    toastEl.style.transform = 'translateX(16px)';
    setTimeout(() => toastEl.remove(), 220);
  };
  closeBtn.addEventListener('click', dismiss);     // 수동 닫기
  const delay = (type === 'error' || type === 'danger') ? 6000 : 3500;
  timer = setTimeout(dismiss, delay);              // 자동 닫기
}

/**
 * v19 P0: 친절한 오류 안내 — 어떤 실패든 '사람이 알아듣는 말'로(무엇+왜+다음 행동).
 * 개발 메시지(undefined/스택트레이스/HTTP 날것/env 이름 등)는 화면에 노출하지 않는다(정직하되 친절).
 * @param {*} raw - 서버 응답 문자열 / {error|message} / Error
 * @returns {string} 사용자용 한 줄 안내
 */
/** HTML 삽입 시 안전 이스케이프(친절 메시지를 innerHTML에 넣을 때). */
function kgpEscapeForHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function kgpFriendlyError(raw) {
  let msg = '';
  if (raw == null) msg = '';
  else if (typeof raw === 'string') msg = raw;
  else if (raw.error) msg = String(raw.error);
  else if (raw.message) msg = String(raw.message);
  else { try { msg = String(raw); } catch (e) { msg = ''; } }
  msg = (msg || '').trim();
  // 코드/패턴 → 쉬운 문장(무엇+왜+다음 행동). 서버가 env/HTTP를 줘도 친절 문장으로 가린다.
  const rules = [
    [/failed to fetch|networkerror|네트워크|연결이 불안정|timeout|시간\s*초과|타임아웃/i,
      '인터넷 연결이 불안정했어요 — 잠시 후 다시 시도해 주세요.'],
    [/401|403|unauthor|forbidden|인증|로그인이 필요|token.*(missing|없|필요)|권한/i,
      '로그인 또는 권한이 필요해요 — 다시 로그인하거나 ‘마켓 연동’에서 키를 확인해 주세요.'],
    [/가격|price/i,
      '가격을 못 읽었어요 — 상품 페이지에서 다시 수집하거나 가격을 직접 입력해 주세요.'],
    [/미연동|미설정|not\s*connected|연동.*안|키.*확인|credential/i,
      '마켓 연동이 안 됐어요 — ‘마켓 연동’에서 API 키를 확인해 주세요.'],
    [/업로드|등록 실패|등록에 실패|upload|발행/i,
      '마켓에 등록하지 못했어요 — 키와 필수값을 확인하고 다시 시도해 주세요.'],
    [/상품 정보|읽지 못|추출|수집.*실패|상세 페이지|collect/i,
      '상품 정보를 읽지 못했어요 — 상품 상세 페이지인지 확인하고 다시 수집해 주세요.'],
    [/이미지/i, '이미지 처리에 실패했어요 — 잠시 후 다시 시도해 주세요.'],
  ];
  for (const [re, friendly] of rules) { if (re.test(msg)) return friendly; }
  // 개발 메시지(undefined/스택/HTTP/env 대문자 토큰/HTML 등)는 가리고 일반 안내로.
  const devLike = !msg
    || /^(undefined|null)$/i.test(msg)
    || /traceback|stacktrace|<!doctype|<html|cannot read prop|is not defined|referenceerror|typeerror|\b[A-Z][A-Z0-9_]{6,}\b|\bhttp[s]?:\/\//i.test(msg)
    || /\b[45]\d\d\b/.test(msg);
  if (devLike) return '문제가 생겼어요 — 잠시 후 다시 시도해 주세요. 계속되면 도움말을 확인해 주세요.';
  // 서버가 이미 사람 말로 짧게 준 경우는 그대로 존중.
  return msg.length <= 140 ? msg : '문제가 생겼어요 — 잠시 후 다시 시도해 주세요.';
}

/**
 * v19 P0: 실패한 그 자리에 인라인 안내 + (선택)재시도 + 도움말. 토스트만으로 끝내지 않는다.
 * @param {HTMLElement|string} el - 표시 컨테이너(또는 id). 없으면 토스트로 폴백.
 * @param {*} raw - 원본 오류
 * @param {object} [opts] - { retry: fn, help: url }
 */
function kgpInlineError(el, raw, opts) {
  opts = opts || {};
  if (typeof el === 'string') el = document.getElementById(el);
  const msg = kgpFriendlyError(raw);
  if (!el) { pcToast(msg, 'error'); return; }
  const wrap = document.createElement('div');
  wrap.className = 'alert alert-warning d-flex flex-wrap align-items-center gap-2 mb-0';
  wrap.setAttribute('role', 'alert');
  const ic = document.createElement('i'); ic.className = 'bi bi-exclamation-triangle';
  const span = document.createElement('span'); span.className = 'small flex-grow-1'; span.textContent = msg;
  wrap.appendChild(ic); wrap.appendChild(span);
  if (opts.retry) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'btn btn-sm btn-outline-primary'; b.textContent = '다시 시도';
    b.addEventListener('click', opts.retry);
    wrap.appendChild(b);
  }
  const help = document.createElement('a');
  help.href = opts.help || '/seller/about'; help.className = 'small text-decoration-none'; help.textContent = '도움말';
  wrap.appendChild(help);
  el.innerHTML = '';
  el.appendChild(wrap);
  el.classList.remove('d-none');
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
