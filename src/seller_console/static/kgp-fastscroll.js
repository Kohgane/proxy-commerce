/* kgp-fastscroll.js — 나이아 인덱스 레일 v2. 정답지: docs/design/naia_rail_demo_v2.html.
 *
 * 레일 항상 노출(41글자). 이름순(enabled)이면 목록을 41섹션으로 그룹핑.
 * 스크럽 모드(핵심): 레일 터치 시작 → **빈 화면 오버레이** + 손가락 높이에 현재 초성 대형 표기 +
 *   그 초성 항목들만(실데이터) 표시. 손 떼면 해당 섹션 착지(조용히 — 토스트 없음).
 * 레일 벤딩: 손가락 근접 글자 translateX·scale 그라디언트(데모 bend()).
 * 다른 정렬 중 레일 조작 → 이름순 자동 전환(switchUrl + #kgpfs=<초성>) — 조용히(토스트 0).
 * 디자인 토큰은 app.css(.kgp-fs-*).
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

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function KGPFastScroll(root, opts) {
    this.root = root;
    this.opts = opts || {};
    this.enabled = !!this.opts.enabled;
    this.list = root.querySelector("[data-fs-list]");
    this.rail = null; this.scrub = null; this.sbig = null; this.sitems = null;
    this.spans = [];
    this.headers = {};       // bucket -> header element
    this.present = {};       // bucket -> true
    this.data = {};          // bucket -> [{title, img}]
    this.cur = null;
  }

  KGPFastScroll.prototype.groupSections = function () {
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
    items.forEach(function (el) {
      (byBucket[el._fsBucket] = byBucket[el._fsBucket] || []).push(el);
      el.classList.add("kgp-fs-item");
      // 스크럽 오버레이용 실데이터(제목 + 첫 이미지)
      var img = el.querySelector("img");
      (self.data[el._fsBucket] = self.data[el._fsBucket] || []).push({
        title: el.getAttribute("data-fs-key") || (el.textContent || "").trim().slice(0, 60),
        img: (img && (img.currentSrc || img.src)) || ""
      });
    });
    BUCKETS.forEach(function (b) {
      var head = self._makeHeader(b, isRow, colspan);
      self.list.appendChild(head);
      self.headers[b] = head;
      var group = byBucket[b] || [];
      if (group.length) group.forEach(function (el) { self.list.appendChild(el); });
      else self.list.appendChild(self._emptyRow(isRow, colspan));
    });
  };

  KGPFastScroll.prototype._colspan = function () {
    var f = this.list.querySelector("[data-fs-key]");
    return (f && f.children.length) || 1;
  };
  KGPFastScroll.prototype._makeHeader = function (bucket, isRow, colspan) {
    var head;
    if (isRow) { head = document.createElement("tr"); head.className = "kgp-fs-head"; var td = document.createElement("td"); td.setAttribute("colspan", colspan); td.textContent = bucket; head.appendChild(td); }
    else { head = document.createElement("div"); head.className = "kgp-fs-head"; head.textContent = bucket; }
    head.setAttribute("data-fs-bucket", bucket);
    return head;
  };
  KGPFastScroll.prototype._emptyRow = function (isRow, colspan) {
    var el;
    if (isRow) { el = document.createElement("tr"); el.className = "kgp-fs-empty"; var td = document.createElement("td"); td.setAttribute("colspan", colspan); td.textContent = "아직 없음"; el.appendChild(td); }
    else { el = document.createElement("div"); el.className = "kgp-fs-empty"; el.textContent = "아직 없음"; }
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
      s.className = "kgp-fs-letter" + (self.enabled && !self.present[b] ? " kgp-fs-dim" : "");
      s.setAttribute("data-fs-bucket", b);
      s.textContent = b;
      rail.appendChild(s);
    });
    document.body.appendChild(rail);
    this.rail = rail;
    this.spans = Array.prototype.slice.call(rail.children);
    // 스크럽 오버레이
    var sc = document.createElement("div");
    sc.className = "kgp-fs-scrub";
    sc.innerHTML = '<div class="kgp-fs-scrub-big"></div><div class="kgp-fs-scrub-items"></div>';
    document.body.appendChild(sc);
    this.scrub = sc;
    this.sbig = sc.querySelector(".kgp-fs-scrub-big");
    this.sitems = sc.querySelector(".kgp-fs-scrub-items");
    this._wire();
  };

  KGPFastScroll.prototype._bend = function (y) {
    // 손가락 근접 레일 글자 휘어짐(나이아 시그니처): transform만(컴포지터) — 리플로우 0.
    //   위치는 초기 1회 캐시한 중심 y(this._cy[i])로 계산 → 매 프레임 getBoundingClientRect(강제 리플로우) 회피.
    var cy = this._cy;
    this.spans.forEach(function (s, i) {
      var d = Math.abs((cy ? cy[i] : (s.getBoundingClientRect().top + 7)) - y);
      var k = Math.max(0, 1 - d / 140);
      s.style.transform = "translateX(" + (-34 * k) + "px) scale(" + (1 + 0.55 * k) + ")";
    });
  };

  KGPFastScroll.prototype._cacheGeom = function () {
    // 스크럽 시작 시 레일 글자 중심 y·경계를 1회 캐시(이후 프레임은 계산만 — 강제 리플로우 회피).
    var self = this;
    this._railRect = this.rail.getBoundingClientRect();
    this._cy = this.spans.map(function (s) { var r = s.getBoundingClientRect(); return r.top + r.height / 2; });
  };

  KGPFastScroll.prototype._bucketAt = function (y) {
    var rect = this._railRect || this.rail.getBoundingClientRect();
    // 여러 x에서 elementFromPoint 시도(벤딩으로 글자가 왼쪽으로 이동해도 히트) → 실패 시 캐시된 중심 y로 최근접.
    var xs = [rect.right - 8, rect.right - 20, rect.left + 10];
    for (var j = 0; j < xs.length; j++) {
      var el = document.elementFromPoint(xs[j], y);
      if (el && el.getAttribute && el.getAttribute("data-fs-bucket")) return el.getAttribute("data-fs-bucket");
    }
    var cy = this._cy, best = 0, bd = 1e9;
    if (cy) {
      for (var i = 0; i < cy.length; i++) { var d = Math.abs(cy[i] - y); if (d < bd) { bd = d; best = i; } }
    } else {
      var n = this.spans.length;
      best = Math.max(0, Math.min(n - 1, Math.floor((y - rect.top) / (rect.height / n))));
    }
    return this.spans[best] ? this.spans[best].getAttribute("data-fs-bucket") : null;
  };

  KGPFastScroll.prototype._showScrub = function (bucket, y) {
    this.scrub.classList.add("kgp-fs-scrub-on");
    this.rail.classList.add("kgp-fs-scrubbing");
    // 위치는 transform(translateY)만 — top 쓰기(리플로우) 금지, 60fps.
    var bigY = Math.min(Math.max(y - 20, 90), global.innerHeight - 240);
    var itemsY = Math.min(Math.max(y + 30, 140), global.innerHeight - 200);
    this.sbig.style.transform = "translateY(" + bigY + "px)";
    this.sitems.style.transform = "translateY(" + itemsY + "px)";
    // 항목 목록은 **버킷이 바뀔 때만** 재생성(innerHTML) — 매 move 리플로우 방지.
    if (bucket !== this.cur) {
      this.cur = bucket;
      this.sbig.textContent = bucket;
      var rows = (this.data[bucket] || []);
      this.sitems.innerHTML = rows.length
        ? rows.slice(0, 40).map(function (it) {
            return '<div class="kgp-fs-scrub-row">' +
              (it.img ? '<img src="' + esc(it.img) + '" alt="" referrerpolicy="no-referrer">' : '<span class="kgp-fs-scrub-ic"></span>') +
              '<b>' + esc(it.title) + '</b></div>';
          }).join("")
        : '<div class="kgp-fs-scrub-none">이 초성엔 아직 없어요</div>';
    }
  };

  KGPFastScroll.prototype._endScrub = function () {
    var bucket = this.cur;
    this.scrub.classList.remove("kgp-fs-scrub-on");
    this.rail.classList.remove("kgp-fs-scrubbing");
    this.spans.forEach(function (s) { s.style.transform = ""; s.style.color = ""; });
    if (bucket && this.headers[bucket]) this.headers[bucket].scrollIntoView({ block: "start" });   // 조용히 착지(토스트 0)
    this.cur = null;
  };

  KGPFastScroll.prototype._switch = function (bucket) {
    // 다른 정렬 중 → 이름순으로 조용히 전환(토스트 0) + 해당 초성 해시 점프
    var url = this.opts.switchUrl || (location.pathname + location.search);
    location.href = url + "#kgpfs=" + encodeURIComponent(bucket);
  };

  KGPFastScroll.prototype._wire = function () {
    var self = this;
    var pick = function (clientY, ev) {
      try {
        if (ev && ev.cancelable) ev.preventDefault();   // 페이지 스크롤 대신 스크럽(touch-action:none 보강)
        var b = self._bucketAt(clientY);
        self._bend(clientY);
        if (b) self._showScrub(b, clientY);
      } catch (err) {
        try { console.error("[고가레일] 스크럽 오류:", err); } catch (e) {}
      }
    };
    if (this.enabled) {
      this.rail.addEventListener("touchstart", function (e) { self._cacheGeom(); pick(e.touches[0].clientY, e); }, { passive: false });
      this.rail.addEventListener("touchmove", function (e) { pick(e.touches[0].clientY, e); }, { passive: false });
      this.rail.addEventListener("touchend", function () { self._endScrub(); });
      this.rail.addEventListener("touchcancel", function () { self._endScrub(); });
      this.rail.addEventListener("mousedown", function (e) {
        self._cacheGeom(); pick(e.clientY, e);
        var mv = function (ev) { pick(ev.clientY, ev); };
        var up = function () { self._endScrub(); document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); };
        document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up);
      });
    } else {
      // 그룹핑 없음(다른 정렬) → 레일 조작 시 이름순으로 조용히 전환
      var go = function (e) {
        var y = (e.touches ? e.touches[0].clientY : e.clientY);
        var b = self._bucketAt(y);
        if (b) { e.preventDefault(); self._switch(b); }
      };
      this.rail.addEventListener("click", go);
      this.rail.addEventListener("touchstart", go, { passive: false });
    }
  };

  KGPFastScroll.prototype._jumpFromHash = function () {
    if (!this.enabled) return;
    var m = /#kgpfs=([^&]+)/.exec(location.hash || "");
    if (!m) return;
    var bucket = decodeURIComponent(m[1]);
    var head = this.headers[bucket];
    if (head) setTimeout(function () { head.scrollIntoView({ block: "start" }); }, 60);
  };

  KGPFastScroll.prototype.init = function () {
    if (this.enabled && this.list) this.groupSections();
    this.buildRail();
    this._jumpFromHash();
    return this;
  };

  var API = {
    bucketOf: bucketOf,
    BUCKETS: BUCKETS,
    init: function (root, opts) {
      if (!root) return null;
      ["kgp-fs-rail", "kgp-fs-scrub"].forEach(function (c) { var o = document.querySelector("." + c); if (o) o.remove(); });
      return new KGPFastScroll(root, opts).init();
    }
  };
  global.KGPFastScroll = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : this);
