/* src/shop/static/shop/shop.js — 자체몰 공통 JS (Phase 131) */

/* ── 카트 뱃지 업데이트 ──────────────────── */
function updateCartBadge(count) {
  document.querySelectorAll('.cart-badge').forEach(el => {
    el.textContent = count;
    el.style.display = count > 0 ? '' : 'none';
  });
  // 헤더 카트 버튼의 badge
  const badges = document.querySelectorAll('.badge.rounded-pill.bg-danger');
  badges.forEach(el => {
    el.textContent = count;
    el.style.display = count > 0 ? '' : 'none';
  });
}

/* ── 토스트 알림 ─────────────────────────── */
function showToast(message, type = 'success') {
  // 기존 토스트 제거
  const existing = document.querySelector('.shop-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `shop-toast alert alert-${type === 'error' ? 'danger' : 'success'} shadow`;
  toast.innerHTML = `<i class="bi bi-${type === 'error' ? 'x-circle' : 'check-circle'} me-2"></i>${message}`;
  document.body.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 2500);
  });
}

/* ── 숫자 포맷 ───────────────────────────── */
function formatKRW(amount) {
  return '₩' + Number(amount).toLocaleString('ko-KR');
}

/* ── DOM 준비 ────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  // 수량 입력 최소값 강제
  document.querySelectorAll('input[type=number].qty-input').forEach(input => {
    input.addEventListener('change', function () {
      if (parseInt(this.value) < 1) this.value = 1;
    });
  });
});
