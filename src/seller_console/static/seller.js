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
  // 선택: 어느 단계에서 실패했나(「사전검증 시작 실패」). `.map(kgpFriendlyError)`의 두 번째 인자(번호)는 단계가 아니다.
  const stage = (arguments.length > 1 && typeof arguments[1] === 'string') ? arguments[1] : '';
  // Y6-C C1(오너 2026-10-07): **숨기는 일반 문구 금지.** 「문제가 생겼어요 — 잠시 후 다시」만 띄우던 자리에
  //   HTTP 상태 + 서버가 준 사유코드·메시지 첫 120자를 같이 싣는다(예: 「사전검증 시작 실패 — 502 worker timeout」).
  //   실측(19:0x KST, 플리츠 세트): 사전검증 → 토스트가 원인 없이 이 문구뿐이었다. 쉬운 문장 규칙은 앞에 두되 원문을 지우지 않는다.
  const plain = function (s) {
    return String(s == null ? '' : s).replace(/<(head|script|style)[\s\S]*?<\/\1>/gi, ' ').replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120);
  };
  let status = (raw && typeof raw === 'object' && Number(raw.status) > 0) ? Number(raw.status) : 0;
  let httpText = '';
  try {                                           // 직전에 실패한 응답(감시가 적어 둔 것 — 15초 안)
    const L = (typeof window !== 'undefined') ? window._kgpLastHttp : null;
    if (L && Date.now() - L.at < 15000) { if (!status) status = L.status; httpText = L.text || ''; }
  } catch (e) { /* 감시 없음 */ }
  const prefix = stage ? (String(stage) + ' — ') : '';
  // F28: 서버가 **이미 셀러의 말로** 쓴 문장(user_message 표식)은 그대로.
  if (raw && typeof raw === 'object' && raw.user_message && (raw.error || raw.message)) {
    const s = String(raw.error || raw.message).trim();
    if (s && s.length <= 300 && !/<!doctype|<html|traceback|stacktrace|cannot read prop|is not defined/i.test(s)) return prefix + s;
  }
  let msg = '';
  if (raw == null) msg = '';
  else if (typeof raw === 'string') msg = raw;
  else if (raw.error) msg = String(raw.error);
  else if (raw.message) msg = String(raw.message);
  else if (raw.reason) msg = String(raw.reason);
  else if (Array.isArray(raw) || typeof raw === 'object') msg = '';
  else { try { msg = String(raw); } catch (e) { msg = ''; } }
  if (/^\[object \w+\]$/.test(msg)) msg = '';            // 6-j: [object Object]는 원문이 아니다
  msg = (msg || '').trim();
  // 스택트레이스는 통째로 싣지 않는다 — 마지막 줄(예외 종류·메시지)만 사유로.
  const wasTrace = /traceback|stacktrace/i.test(msg);
  if (wasTrace) {
    const lines = msg.split(/\n/).map(function (l) { return l.trim(); }).filter(Boolean);
    const last = lines[lines.length - 1] || '';
    msg = /traceback/i.test(last) ? last.replace(/^.*?(most recent call last\)\s*:?)/i, '').trim() : last;
  }
  // 응답이 JSON이 아니었다(502 HTML 등) — 파서 오류 문장보다 감시가 적어 둔 **응답 본문**이 사유다.
  if (httpText && /unexpected token|json\.parse|not valid json|unexpected end of json/i.test(msg)) msg = '';
  const code = (raw && typeof raw === 'object' && raw.error_code) ? String(raw.error_code) : '';
  const reason = plain(msg) || plain(httpText);
  const statusTxt = (status && reason.indexOf(String(status)) !== 0) ? String(status) : '';   // 본문이 「502 …」로 시작하면 한 번만
  const detail = [statusTxt, code, reason].filter(Boolean).join(' ').slice(0, 160);
  const withDetail = function (lead) { return prefix + lead + (detail ? ' — ' + detail : ''); };
  // 쉬운 문장(무엇+다음 행동) — 앞에 두고, 원문은 뒤에 그대로.
  const rules = [
    [/failed to fetch|networkerror|load failed|네트워크|연결이 불안정/i, '인터넷 연결이 끊겼거나 서버가 답하지 않았어요'],
    [/\b401\b|\b403\b|unauthor|forbidden|로그인이 필요|token.*(missing|없|필요)/i,
      '로그인 또는 권한이 필요해요 — 다시 로그인하거나 ‘마켓 연동’에서 키를 확인해 주세요'],
    [/가격[^.]{0,12}(못|실패|없|오류|확인\s*필요|안\s*읽|0\s*입니다|0원)|price[^.]{0,12}(fail|error|missing|invalid|is\s*0)/i,
      '가격을 못 읽었어요 — 다시 수집하거나 가격을 직접 입력해 주세요'],
    // F28: 「이미지」 낱말만으로는 안 바꾼다 — 실패 어형일 때만.
    [/이미지[^.]{0,14}(못|실패|없|오류|깨졌|안\s*올라)|image[^.]{0,14}(fail|error|invalid)/i,
      '이미지 처리에 실패했어요 — 잠시 후 다시 시도해 주세요'],
  ];
  if (status === 401 || status === 403) return withDetail(rules[1][1]);
  for (const [re, friendly] of rules) { if (re.test(msg)) return withDetail(friendly); }
  // 서버가 사람 말로 짧게 준 문장(코드·HTML 아님)은 그대로 — 상태만 붙인다.
  const devLike = wasTrace || !msg || /^(undefined|null)$/i.test(msg) || /<!doctype|<html|traceback|cannot read prop|is not defined/i.test(msg);
  if (!devLike && msg.length <= 140 && !status && !code) return prefix + msg;
  if (!devLike && msg.length <= 140) return prefix + [status ? String(status) : '', code, msg].filter(Boolean).join(' ');
  return prefix + '문제가 생겼어요 — ' + (detail || '사유 원문 없음(서버가 상태·본문을 주지 않았어요)');
}

/** Y6-C C1: 실패한 응답을 적어 둔다 — 호출부가 `resp.json()`에서 죽어도(502 HTML) 토스트가 상태·본문 첫 줄을 싣는다. */
(function () {
  if (typeof window === 'undefined' || !window.fetch || window._kgpFetchWatched) return;
  window._kgpFetchWatched = true;
  const orig = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = (typeof input === 'string') ? input : ((input && input.url) || '');
    return orig(input, init).then(function (r) {
      if (!r.ok) {
        window._kgpLastHttp = {url: url, status: r.status, text: '', at: Date.now()};
        try { r.clone().text().then(function (t) { if (window._kgpLastHttp && window._kgpLastHttp.url === url) window._kgpLastHttp.text = t; }); } catch (e) { /* 본문 못 읽음 */ }
      }
      return r;
    }, function (e) {
      window._kgpLastHttp = {url: url, status: 0, text: String((e && e.message) || e), at: Date.now()};
      throw e;
    });
  };
})();

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
