/* kgp-fastscroll.js — 나이아(naia) 인덱스 레일. 정답지: docs/design/naia_rail_demo.html.
 *
 * 레일은 **항상 노출**(정렬 조건 없음). ㄱ~ㅎ(14)+A~Z(26)+#(1)=41글자, 우측 가장자리 고정.
 * - 이름순(enabled=true): 목록을 41섹션으로 그룹핑(빈 섹션은 '아직 없음' 1행) + sticky 헤더.
 *   레일 스크럽/클릭 → 해당 섹션 점프 + 대형 버블(먹 배경+한지 글자).
 * - 다른 정렬(enabled=false): 레일은 보이되, 조작 시 **이름순으로 자동 전환 + 해당 초성 점프**
 *   (switchUrl + #kgpfs=<초성>, 토스트 '이름순으로 전환됨').
 * 항목 없는 글자는 dim(레일에서 빼지 않음). touch-action:none으로 페이지 스크롤 충돌 방지.
 * 디자인 토큰은 app.css(.kgp-fs-*) 단일 소스.
 */
(function (global) {
  "use strict";

  var CHO = ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];
  var CHO19 = ["ㄱ", "ㄱ", "ㄴ", "ㄷ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅂ", "ㅅ", "ㅅ", "ㅇ", "ㅈ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];
  var COMPAT = {
    "ㄱ": "ㄱ", "ㄲ": "ㄱ", "ㄳ": "ㄱ", "ㄴ": "ㄴ", "ㄵ": "ㄴ", "ㄶ": "ㄴ", "ㄷ": "ㄷ", "ㄸ": "ㄷ",
    "ㄹ": "ㄹ", "ㄺ": "ㄹ", "ㄻ": "ㄹ", "ㄼ": "ㄹ", "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㄿ": "ㄹ", "ㅀ": "ㄹ",
    "ㅁ": "ㅁ", "ㅂ": "ㅂ", "ㅃ": "ㅂ", "ㅄ": "ㅂ", "ㅅ": "ㅅ", "ㅆ": "ㅅ", "ㅇ": "ㅇ",
    "ㅈ": "ㅈ", "ㅉ": "ㅈ", "ㅊ": "ㅊ", "ㅋ": "ㅋ", "ㅌ": "ㅌ", "ㅍ": "ㅍ", "ㅎ": "ㅎ"
  };
  var BUCKETS = CHO.concat("ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("")).concat(["#"]);
  var ORDER = {};
  BUCKETS.forEach(function (b, i) { ORDER[b] = i; });

  function bucketOf(key) {
    if (!key) return "#";
    var ch = String(key).trim().charAt(0);
    if (!ch) return "#";
    var code = ch.charCodeAt(0);
    if (code >= 0xAC00 && code <= 0xD7A3) return CHO19[Math.floor((code - 0xAC00) / 588)];
    if (COMPAT[ch]) return COMPAT[ch];
    if (ch >= "a" && ch <= "z") return ch.toUpperCase();
    if (ch >= "A" && ch <= "Z") return ch;
    return "#";
  }

  function toast(msg) {
    try { if (typeof global.pcToast === "function") global.pcToast(msg, "info"); } catch (e) {}
  }

  function KGPFastScroll(root, opts) {
    this.root = root;
    this.opts = opts || {};
    this.enabled = !!this.opts.enabled;
    this.list = root.querySelector("[data-fs-list]");
    this.rail = null;
    this.bubble = null;
    this.headers = {};      // bucket -> header element (enabled 모드)
    this.present = {};      // bucket -> true
  }

  KGPFastScroll.prototype.groupSections = function () {
    // 이름순: 항목을 버킷 순서로 재배치 + 41섹션 전부 생성(빈 섹션 '아직 없음').
    var self = this;
    var items = Array.prototype.slice.call(this.list.querySelectorAll("[data-fs-key]"));
    items.forEach(function (el, i) { el._fsIdx = i; el._fsBucket = bucketOf(el.getAttribute("data-fs-key")); self.present[el._fsBucket] = true; });
    items.sort(function (a, b) {
      var d = ORDER[a._fsBucket] - ORDER[b._fsBucket];
      if (d) return d;
      var k = String(a.getAttribute("data-fs-key")).localeCompare(String(b.getAttribute("data-fs-key")), "ko");
      return k || (a._fsIdx - b._fsIdx);
    });
    var isRow = (items[0] && items[0].tagName === "TR") || this.list.tagName === "TBODY";
    var colspan = isRow ? this._colspan() : 0;
    var byBucket = {};
    items.forEach(function (el) { (byBucket[el._fsBucket] = byBucket[el._fsBucket] || []).push(el); el.classList.add("kgp-fs-item"); });
    // 41섹션 전부: 헤더 + (항목 or '아직 없음')
    BUCKETS.forEach(function (b) {
      var head = self._makeHeader(b, isRow, colspan);
      self.list.appendChild(head);
      self.headers[b] = head;
      var group = byBucket[b] || [];
      if (group.length) {
        group.forEach(function (el) { self.list.appendChild(el); });
      } else {
        self.list.appendChild(self._emptyRow(isRow, colspan));  // '아직 없음'
      }
    });
  };

  KGPFastScroll.prototype._colspan = function () {
    var firstRow = this.list.querySelector("[data-fs-key]");
    return (firstRow && firstRow.children.length) || 1;
  };

  KGPFastScroll.prototype._makeHeader = function (bucket, isRow, colspan) {
    var head;
    if (isRow) {
      head = document.createElement("tr");
      head.className = "kgp-fs-head";
      var td = document.createElement("td");
      td.setAttribute("colspan", colspan);
      td.textContent = bucket;
      head.appendChild(td);
    } else {
      head = document.createElement("div");
      head.className = "kgp-fs-head";
      head.textContent = bucket;
    }
    head.setAttribute("data-fs-bucket", bucket);
    return head;
  };

  KGPFastScroll.prototype._emptyRow = function (isRow, colspan) {
    var el;
    if (isRow) {
      el = document.createElement("tr");
      el.className = "kgp-fs-empty";
      var td = document.createElement("td");
      td.setAttribute("colspan", colspan);
      td.textContent = "아직 없음";
      el.appendChild(td);
    } else {
      el = document.createElement("div");
      el.className = "kgp-fs-empty";
      el.textContent = "아직 없음";
    }
    return el;
  };

  KGPFastScroll.prototype.buildRail = function () {
    var self = this;
    var rail = document.createElement("div");
    rail.className = "kgp-fs-rail";
    rail.setAttribute("role", "navigation");
    rail.setAttribute("aria-label", "인덱스 빠른 이동");
    BUCKETS.forEach(function (b) {
      var s = document.createElement("span");
      // dim: enabled 모드에서 항목 없는 글자만(다른 정렬 모드는 항목 유무를 모르므로 dim 없음)
      s.className = "kgp-fs-letter" + (self.enabled && !self.present[b] ? " kgp-fs-dim" : "");
      s.setAttribute("data-fs-bucket", b);
      s.textContent = b;
      rail.appendChild(s);
    });
    var bubble = document.createElement("div");
    bubble.className = "kgp-fs-bubble";
    bubble.setAttribute("aria-hidden", "true");
    document.body.appendChild(rail);
    document.body.appendChild(bubble);
    this.rail = rail;
    this.bubble = bubble;
    this._wire();
  };

  KGPFastScroll.prototype._bucketAtPoint = function (clientY) {
    var rect = this.rail.getBoundingClientRect();
    var el = document.elementFromPoint(rect.left + rect.width / 2, clientY);
    if (el && el.getAttribute && el.getAttribute("data-fs-bucket")) return el.getAttribute("data-fs-bucket");
    // 폴백: Y 비례
    var n = this.rail.children.length;
    var rel = Math.max(0, Math.min(n - 1, Math.floor((clientY - rect.top) / (rect.height / n))));
    var c = this.rail.children[rel];
    return c ? c.getAttribute("data-fs-bucket") : null;
  };

  KGPFastScroll.prototype._go = function (bucket, clientY) {
    if (!bucket) return;
    if (!this.enabled) {
      // 다른 정렬 중 → 이름순 자동 전환 + 해당 초성 점프(해시로 전달)
      toast("이름순으로 전환됨");
      var url = this.opts.switchUrl || (location.pathname + location.search);
      location.href = url + "#kgpfs=" + encodeURIComponent(bucket);
      return;
    }
    var head = this.headers[bucket];
    if (head) head.scrollIntoView({ block: "start" });
    this._setActive(bucket);
    this._bubble(bucket, clientY);
  };

  KGPFastScroll.prototype._setActive = function (bucket) {
    Array.prototype.forEach.call(this.rail.children, function (a) {
      a.classList.toggle("kgp-fs-on", a.getAttribute("data-fs-bucket") === bucket);
    });
  };

  KGPFastScroll.prototype._bubble = function (bucket, clientY) {
    var self = this, b = this.bubble;
    b.textContent = bucket;
    b.classList.add("kgp-fs-bubble-on");
    var y = (clientY || (global.innerHeight / 2));
    b.style.top = Math.min(Math.max(y - 37, 80), global.innerHeight - 120) + "px";
    clearTimeout(this._bt);
    this._bt = setTimeout(function () { b.classList.remove("kgp-fs-bubble-on"); }, 650);
  };

  KGPFastScroll.prototype._wire = function () {
    var self = this;
    var scrubbing = false;
    var pick = function (clientY) { self._go(self._bucketAtPoint(clientY), clientY); };

    this.rail.addEventListener("click", function (e) {
      var t = e.target.closest ? e.target.closest(".kgp-fs-letter") : null;
      if (t) { e.preventDefault(); self._go(t.getAttribute("data-fs-bucket"), e.clientY); }
    });
    // 터치 스크럽(엄지) — touch-action:none으로 페이지 스크롤 방지
    this.rail.addEventListener("touchstart", function (e) { scrubbing = true; e.preventDefault(); pick(e.touches[0].clientY); }, { passive: false });
    this.rail.addEventListener("touchmove", function (e) { if (scrubbing) { e.preventDefault(); pick(e.touches[0].clientY); } }, { passive: false });
    this.rail.addEventListener("touchend", function () { scrubbing = false; });
    // 마우스 드래그 스크럽
    this.rail.addEventListener("mousedown", function (e) {
      if (!self.enabled) return;   // 다른 정렬은 클릭 1회로 전환(드래그 불필요)
      e.preventDefault(); pick(e.clientY);
      var mv = function (ev) { pick(ev.clientY); };
      var up = function () { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); };
      document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
    });

    if (this.enabled && "IntersectionObserver" in global) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) self._setActive(en.target.getAttribute("data-fs-bucket")); });
      }, { rootMargin: "0px 0px -85% 0px", threshold: 0 });
      for (var b in this.headers) io.observe(this.headers[b]);
    }
  };

  KGPFastScroll.prototype._jumpFromHash = function () {
    if (!this.enabled) return;
    var m = /#kgpfs=([^&]+)/.exec(location.hash || "");
    if (!m) return;
    var bucket = decodeURIComponent(m[1]);
    var head = this.headers[bucket];
    if (head) {
      var self = this;
      setTimeout(function () { head.scrollIntoView({ block: "start" }); self._setActive(bucket); }, 60);
    }
  };

  KGPFastScroll.prototype.destroy = function () {
    if (this.rail) this.rail.remove();
    if (this.bubble) this.bubble.remove();
  };

  KGPFastScroll.prototype.init = function () {
    if (this.enabled && this.list) this.groupSections();
    this.buildRail();          // 레일은 항상
    this._jumpFromHash();
    return this;
  };

  var API = {
    bucketOf: bucketOf,
    BUCKETS: BUCKETS,
    init: function (root, opts) {
      if (!root) return null;
      // 중복 레일 방지(재초기화)
      var old = document.querySelector(".kgp-fs-rail");
      if (old) old.remove();
      var oldB = document.querySelector(".kgp-fs-bubble");
      if (oldB) oldB.remove();
      return new KGPFastScroll(root, opts).init();
    }
  };
  global.KGPFastScroll = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : this);
