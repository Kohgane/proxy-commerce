/* Human region review. Snapshot reads only; Save writes review metadata only. */
(function () {
  'use strict';
  var root, state, generation = 0;
  function node(role) { return root.querySelector('[data-rp="' + role + '"]'); }
  function message(text) { node('status').textContent = text; }
  async function request(s, body) {
    var options = {credentials: 'same-origin', cache: 'no-store'};
    if (body) { options.method = 'POST'; options.headers = {'Content-Type': 'application/json'}; options.body = JSON.stringify(body); }
    var response = await fetch('/seller/collect/' + encodeURIComponent(s.item) + '/rep-protection/' + s.idx, options), data;
    try { data = await response.json(); } catch (_) { throw new Error('서버 응답을 읽지 못했어요'); }
    if (!response.ok || !data.ok) throw new Error(data.error || '검토를 불러오지 못했어요');
    return data;
  }
  function paint() {
    var svg = node('areas'); svg.replaceChildren();
    state.regions.concat(state.drag ? [state.drag] : []).forEach(function (r) {
      var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', Math.min(r[0], r[2])); rect.setAttribute('y', Math.min(r[1], r[3]));
      rect.setAttribute('width', Math.abs(r[2] - r[0])); rect.setAttribute('height', Math.abs(r[3] - r[1]));
      rect.setAttribute('vector-effect', 'non-scaling-stroke'); svg.appendChild(rect);
    });
    node('count').textContent = '상품 보호 영역 ' + state.regions.length + '곳';
    node('save').disabled = !state.ready || state.busy || !state.regions.length || !node('complete').checked;
    node('undo').disabled = state.busy || !state.regions.length;
  }
  function point(e) {
    var b = node('areas').getBoundingClientRect(), size = state.data.size;
    return [Math.max(0, Math.min(size[0], (e.clientX-b.left)/b.width*size[0])),
            Math.max(0, Math.min(size[1], (e.clientY-b.top)/b.height*size[1]))];
  }
  function build() {
    if (root) return;
    root = document.createElement('div'); root.className = 'kie'; root.hidden = true; root.dataset.role = 'rep-protection-review';
    root.innerHTML = '<div class="kie-panel" role="dialog" aria-modal="true" aria-labelledby="rpTitle">' +
      '<div class="kie-head"><strong id="rpTitle">상품 보호 영역 검토</strong><button type="button" class="kie-x" data-rp="close">닫기</button></div>' +
      '<div class="kie-body"><p class="kie-note">남겨야 할 상품 전체를 사각형으로 감싸 주세요. 여러 개면 각각 표시하세요. 자동 검출이 아닌 관리자 검토입니다.</p>' +
      '<p class="kie-note">모서리 두 곳을 차례로 누르거나 드래그하세요. 상품의 돌출부도 모두 포함해야 합니다.</p>' +
      '<div class="kie-stage" data-rp="stage" hidden><img alt="보호 영역을 검토할 현재 사진" data-rp="image">' +
      '<svg class="rp-areas" data-rp="areas" aria-label="상품 보호 영역 선택"></svg></div>' +
      '<p class="kie-note" data-rp="count"></p><div class="kie-acts"><button type="button" class="kie-btn" data-rp="undo">마지막 영역 취소</button></div>' +
      '<label class="kie-note"><input type="checkbox" data-rp="complete"> 상품 전체가 보호 영역에 포함된 것을 직접 확인했습니다</label>' +
      '<div class="kie-acts"><button type="button" class="kie-btn is-main" data-rp="save">검토 기록 저장</button></div>' +
      '<p class="kie-note" role="status" aria-live="polite" data-rp="status"></p></div></div>';
    document.body.appendChild(root);
    node('close').onclick = function () { if (!state.busy) { generation++; root.hidden = true; if (state.opener) state.opener.focus(); } };
    root.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') node('close').click();
      if (e.key === 'Tab') {
        var controls = Array.from(root.querySelectorAll('button:not(:disabled),input:not(:disabled)'));
        var first = controls[0], last = controls[controls.length-1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
    node('complete').onchange = paint;
    node('undo').onclick = function () { state.regions.pop(); state.corner = null; state.drag = null; node('complete').checked = false; paint(); };
    var svg = node('areas');
    svg.onpointerdown = function (e) {
      if (!state.ready || state.busy || !e.isPrimary) return;
      if (state.regions.length >= 24) { message('보호 영역은 최대 24곳까지 지정할 수 있어요.'); return; }
      e.preventDefault(); svg.setPointerCapture(e.pointerId); state.down = point(e); state.drag = state.down.concat(state.down);
    };
    svg.onpointermove = function (e) { if (state.down) { state.drag = state.down.concat(point(e)); paint(); } };
    svg.onpointercancel = function () { state.down = null; state.drag = null; paint(); };
    svg.onpointerup = function (e) {
      if (!state.down) return;
      var p = point(e), a = state.down;
      if (Math.abs(p[0]-a[0]) + Math.abs(p[1]-a[1]) < 4) {
        if (!state.corner) { state.corner = p; state.down = null; state.drag = null; message('반대쪽 모서리를 눌러 주세요.'); paint(); return; }
        a = state.corner;
      }
      var r = [Math.min(a[0],p[0]),Math.min(a[1],p[1]),Math.max(a[0],p[0]),Math.max(a[1],p[1])];
      if (r[2] > r[0] && r[3] > r[1]) state.regions.push(r);
      state.corner = null; state.down = null; state.drag = null; node('complete').checked = false;
      message('상품 전체가 포함됐는지 확인한 뒤 저장하세요.'); paint();
    };
    node('save').onclick = async function () {
      var s = state;
      if (!s.ready || s.busy || !s.regions.length || !node('complete').checked) return;
      s.busy = true; node('close').disabled = true; node('complete').disabled = true; paint(); message('사진을 다시 확인하고 저장하는 중…');
      try {
        var result = await request(s, {token:s.data.token, regions:s.regions, reviewed_complete:true});
        s.ready = false; message(result.message + ' 다음 사전검증에서 정리 후보로 검사합니다.');
      } catch (e) { s.ready = false; message(e.message + ' 닫고 다시 열어 주세요.'); }
      finally { s.busy = false; node('close').disabled = false; paint(); }
    };
  }
  window.kgpRepProtection = {open: async function (item, idx) {
    build(); if (state && state.busy) return;
    var ticket = ++generation;
    state = {item:item, idx:idx, regions:[], ready:false, busy:false, opener:document.activeElement};
    root.hidden = false; node('stage').hidden = true; node('complete').checked = false; node('complete').disabled = false;
    node('close').disabled = false; node('close').focus(); paint(); message('현재 사진을 읽는 중…');
    try {
      var data = await request(state); if (ticket !== generation) return;
      state.data = data; node('areas').setAttribute('viewBox', '0 0 ' + data.size.join(' '));
      node('image').onload = function () {
        if (ticket !== generation) return;
        if (this.naturalWidth !== data.size[0] || this.naturalHeight !== data.size[1]) { message('사진 방향과 좌표계가 달라 검토할 수 없어요.'); return; }
        state.ready = true; node('stage').hidden = false; message('검토 기록만 저장합니다. 사진 변경·마켓 전송은 하지 않습니다.'); paint();
      };
      node('image').onerror = function () { if (ticket === generation) message('사진을 표시하지 못했어요. 닫고 다시 열어 주세요.'); };
      node('image').src = data.image;
    } catch (e) { if (ticket === generation) message(e.message); }
  }};
})();
