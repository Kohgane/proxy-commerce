/* m_shell.js — 오너 11-23 「앱이 실제 앱처럼」: 폰·앱 웹뷰 공용 셸 동작(partials/m_shell.html 짝).
 *  ① 앱 판정(standalone PWA·WKWebView) → html.kgp-app (서버가 이미 붙였으면 그대로)
 *  ② 뒤로 = history 기반(같은 사이트에서 왔을 때만 history.back, 아니면 화면이 정한 자리)
 *  ③ 탭 이동 = 누르는 즉시 스켈레톤(전체 새로고침 동안 빈 화면 대신)
 *  ④ 당겨서 새로고침(body[data-ptr]) — 목록·주문
 *  ⑤ 잡 진행 한 줄 — window.kgpJobLine.show/done/fail(text)
 */
(function () {
  var html = document.documentElement;
  try {
    var standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;
    var wk = !!(window.webkit && window.webkit.messageHandlers);
    // 고가브릿지 아이폰 앱(v1.1)은 스스로 `window.KG_APP`·`html.kg-app`을 붙인다 — 같은 뜻으로 받는다.
    if (window.KG_APP) html.classList.add('kg-app');
    if (standalone || wk || html.classList.contains('kg-app')) html.classList.add('kgp-app');
  } catch (e) {}

  function q(sel) { return document.querySelector(sel); }

  // ② 뒤로
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest && ev.target.closest('[data-role="m-back"]');
    if (!a) return;
    var sameSite = false;
    try { sameSite = !!document.referrer && new URL(document.referrer).origin === location.origin; } catch (e) {}
    if (sameSite && history.length > 1) { ev.preventDefault(); history.back(); }
  });

  // ③ 탭 → 즉시 스켈레톤(같은 탭을 다시 누르면 맨 위로)
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest && ev.target.closest('.kgp-mtab-item');
    if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
    if (a.classList.contains('active') && a.getAttribute('href').split('?')[0] === location.pathname && !location.search) {
      ev.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); return;
    }
    var sk = q('[data-role="m-skeleton"]');
    if (sk) { sk.hidden = false; html.classList.add('kgp-navigating'); }
    document.querySelectorAll('.kgp-mtab-item.active').forEach(function (x) { x.classList.remove('active'); });
    a.classList.add('active');
  });
  // bfcache로 돌아오면 스켈레톤을 걷는다(뒤로가기)
  window.addEventListener('pageshow', function () {
    var sk = q('[data-role="m-skeleton"]'); if (sk) sk.hidden = true;
    html.classList.remove('kgp-navigating');
  });

  // ④ 당겨서 새로고침 — 맨 위에서 70px 이상 끌었다 놓으면
  // 아이폰 앱은 네이티브 당겨서 새로고침(UIRefreshControl)이 있다 — 웹 것까지 켜면 두 번 돈다.
  if (document.body && document.body.hasAttribute('data-ptr') && 'ontouchstart' in window &&
      !document.documentElement.classList.contains('kg-app')) {
    var startY = null, pulled = 0, ind = document.createElement('div');
    ind.className = 'kgp-ptr'; ind.setAttribute('aria-hidden', 'true'); ind.innerHTML = '<i class="bi bi-arrow-clockwise"></i>';
    document.body.appendChild(ind);
    document.addEventListener('touchstart', function (e) {
      startY = (window.scrollY <= 0 && e.touches.length === 1) ? e.touches[0].clientY : null; pulled = 0;
    }, { passive: true });
    document.addEventListener('touchmove', function (e) {
      if (startY === null) return;
      pulled = Math.max(0, Math.min(120, e.touches[0].clientY - startY));
      ind.style.transform = 'translate(-50%,' + (pulled - 48) + 'px) rotate(' + (pulled * 3) + 'deg)';
      ind.style.opacity = String(Math.min(1, pulled / 50));
      ind.classList.toggle('ready', pulled >= 70);
    }, { passive: true });
    document.addEventListener('touchend', function () {
      if (startY === null) return;
      if (pulled >= 70) { ind.classList.add('spin'); location.reload(); }
      else { ind.style.transform = ''; ind.style.opacity = ''; ind.classList.remove('ready'); }
      startY = null;
    });
  }

  // ⑤ 잡 진행 한 줄
  var line = null, txt = null, timer = null;
  function el() { line = line || q('[data-role="m-jobline"]'); txt = txt || q('[data-role="m-jobline-text"]'); return line; }
  // 오너 11-25 ⑥: 한 줄이 떠 있는 동안 본문 아래 여백을 그 높이만큼 더 준다 — 마지막 버튼·글이 알약 밑에 깔리지 않게.
  function vis(on) { line.hidden = !on; document.body.classList.toggle('kgp-jobline-on', !!on); }
  window.kgpJobLine = {
    show: function (t) { if (!el()) return; clearTimeout(timer); line.className = 'kgp-jobline'; txt.textContent = t; vis(true); },
    done: function (t) { if (!el()) return; line.className = 'kgp-jobline ok'; txt.textContent = t; vis(true);
      clearTimeout(timer); timer = setTimeout(function () { vis(false); }, 2600); },
    fail: function (t) { if (!el()) return; clearTimeout(timer); line.className = 'kgp-jobline bad'; txt.textContent = t; vis(true); },
    hide: function () { if (el()) vis(false); },
  };
})();
