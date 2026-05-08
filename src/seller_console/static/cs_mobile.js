// cs_mobile.js — Phase 138 모바일 PWA 헬퍼

let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const banner = document.getElementById('install-banner');
  if (banner) banner.style.display = 'inline-block';
});

function installPWA() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(() => { deferredPrompt = null; });
  }
}

function toggleAI(msgId) {
  const el = document.getElementById('ai-' + msgId);
  if (!el) return;
  el.classList.toggle('expanded');
}

// 빠른 답변 버튼: AI 제안을 textarea에 붙여넣기
document.querySelectorAll('.ai-suggestion').forEach(el => {
  el.addEventListener('longpress', () => {
    const msgId = el.id.replace('ai-', '');
    const card = document.getElementById('card-' + msgId);
    if (!card) return;
    const ta = card.querySelector('textarea[name="final_reply"]');
    if (ta) ta.value = el.textContent.trim().replace(/^💡\s*/, '');
  });
});

// Long press simulation (mobile)
let pressTimer;
document.querySelectorAll('.ai-suggestion').forEach(el => {
  el.addEventListener('touchstart', () => {
    pressTimer = setTimeout(() => {
      const msgId = el.id.replace('ai-', '');
      const card = document.getElementById('card-' + msgId);
      if (!card) return;
      const ta = card.querySelector('textarea[name="final_reply"]');
      if (ta) {
        ta.value = el.textContent.trim().replace(/^💡\s*/, '');
        ta.focus();
      }
    }, 500);
  });
  el.addEventListener('touchend', () => clearTimeout(pressTimer));
});
