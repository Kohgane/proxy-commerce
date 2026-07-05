/* kgp-fastscroll.js — 긴 목록 인덱스 패스트 스크롤(폰 앱서랍 방식).
 *
 * 이름순 정렬일 때만 활성: 목록을 초성(ㄱ~ㅎ)·A~Z·#(숫자·기호)로 섹션 그룹핑 +
 * sticky 섹션 헤더 + 우측 세로 인덱스 레일. 모바일=터치 스크럽+버블, 데스크탑=클릭 점프·
 * 드래그 스크럽·hover 확대. 성능=content-visibility(네이티브 가상화)로 1천+ 항목 대응.
 * 디자인 토큰은 app.css(.kgp-fs-*) 단일 소스. 하드코딩 색 없음.
 *
 * 사용:
 *   <div data-fs-root>
 *     <div data-fs-list> ... 각 항목에 data-fs-key="정렬키(제목)" ... </div>
 *   </div>
 *   KGPFastScroll.init(rootEl, { enabled: true });   // enabled=이름순일 때만
 */
(function (global) {
  "use strict";

  // 초성 14 + A~Z + # 순서(레일 순서)
  var CHO = ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];
  // 유니코드 초성 인덱스(19개) → 표시 초성(쌍자음은 기본자음으로 접기)
  var CHO19 = ["ㄱ", "ㄱ", "ㄴ", "ㄷ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅂ", "ㅅ", "ㅅ", "ㅇ", "ㅈ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"];
  // 호환 자모(단독 자음) → 기본 초성
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
    if (code >= 0xAC00 && code <= 0xD7A3) {          // 완성형 한글 → 초성
      return CHO19[Math.floor((code - 0xAC00) / 588)];
    }
    if (COMPAT[ch]) return COMPAT[ch];               // 단독 자음
    if (ch >= "a" && ch <= "z") return ch.toUpperCase();
    if (ch >= "A" && ch <= "Z") return ch;
    return "#";                                       // 숫자·기호·기타
  }

  function KGPFastScroll(root, opts) {
    this.root = root;
    this.opts = opts || {};
    this.list = root.querySelector("[data-fs-list]");
    this.rail = null;
    this.bubble = null;
    this.headers = {};        // bucket -> header element
    this.present = {};        // bucket -> true
    this.scrubbing = false;
  }

  KGPFastScroll.prototype.destroy = function () {
    if (this.rail) this.rail.remove();
    if (this.bubble) this.bubble.remove();
    this.root.classList.remove("kgp-fs-on");
    // 삽입한 섹션 헤더 제거
    Array.prototype.forEach.call(this.list.querySelectorAll(".kgp-fs-head"), function (h) { h.remove(); });
    Array.prototype.forEach.call(this.list.querySelectorAll("[data-fs-key]"), function (el) {
      el.classList.remove("kgp-fs-item");
    });
  };

  KGPFastScroll.prototype.build = function () {
    var self = this;
    var items = Array.prototype.slice.call(this.list.querySelectorAll("[data-fs-key]"));
    if (items.length < 2) return false;

    // 1) 버킷 순서로 정렬(서버 정렬 순서와 무관하게 레일 순서 보장) — 안정 정렬
    items.forEach(function (el, i) { el._fsIdx = i; el._fsBucket = bucketOf(el.getAttribute("data-fs-key")); });
    items.sort(function (a, b) {
      var d = ORDER[a._fsBucket] - ORDER[b._fsBucket];
      if (d) return d;
      var k = String(a.getAttribute("data-fs-key")).localeCompare(String(b.getAttribute("data-fs-key")), "ko");
      return k || (a._fsIdx - b._fsIdx);
    });

    // 2) DOM 재배치 + 섹션 헤더(같은 태그로 삽입: 테이블이면 tr) + content-visibility
    var isRow = items[0].tagName === "TR";
    var colspan = isRow ? (items[0].children.length || 1) : 0;
    var lastBucket = null;
    items.forEach(function (el) {
      el.classList.add("kgp-fs-item");
      if (el._fsBucket !== lastBucket) {
        lastBucket = el._fsBucket;
        self.present[lastBucket] = true;
        var head = self._makeHeader(lastBucket, isRow, colspan);
        self.list.appendChild(head);
        self.headers[lastBucket] = head;
      }
      self.list.appendChild(el);      // 정렬 순서대로 재배치
    });
    return true;
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

  KGPFastScroll.prototype._makeRail = function () {
    var self = this;
    var rail = document.createElement("div");
    rail.className = "kgp-fs-rail";
    rail.setAttribute("role", "navigation");
    rail.setAttribute("aria-label", "인덱스 빠른 이동");
    BUCKETS.forEach(function (b) {
      var a = document.createElement("button");
      a.type = "button";
      a.className = "kgp-fs-letter" + (self.present[b] ? "" : " kgp-fs-dim");
      a.setAttribute("data-fs-bucket", b);
      a.textContent = b;
      a.tabIndex = self.present[b] ? 0 : -1;
      rail.appendChild(a);
    });
    var bubble = document.createElement("div");
    bubble.className = "kgp-fs-bubble";
    bubble.setAttribute("aria-hidden", "true");
    this.root.appendChild(rail);
    this.root.appendChild(bubble);
    this.rail = rail;
    this.bubble = bubble;
    this._wire();
  };

  KGPFastScroll.prototype._bucketAtY = function (y) {
    var rect = this.rail.getBoundingClientRect();
    var letters = this.rail.children;
    var rel = Math.max(0, Math.min(letters.length - 1, Math.floor((y - rect.top) / (rect.height / letters.length))));
    return letters[rel] ? letters[rel].getAttribute("data-fs-bucket") : null;
  };

  KGPFastScroll.prototype._jump = function (bucket, showBubble) {
    if (!bucket) return;
    // 없는 글자면 가장 가까운 존재 버킷으로
    if (!this.present[bucket]) {
      var idx = ORDER[bucket], best = null, bestD = 1e9;
      for (var b in this.present) { var d = Math.abs(ORDER[b] - idx); if (d < bestD) { bestD = d; best = b; } }
      bucket = best;
    }
    var head = this.headers[bucket];
    if (head) {
      head.scrollIntoView({ block: "start", behavior: (this.scrubbing ? "auto" : "smooth") });
      this._setActive(bucket);
      if (showBubble) this._showBubble(bucket);
    }
  };

  KGPFastScroll.prototype._setActive = function (bucket) {
    Array.prototype.forEach.call(this.rail.children, function (a) {
      a.classList.toggle("kgp-fs-active", a.getAttribute("data-fs-bucket") === bucket);
    });
  };

  KGPFastScroll.prototype._showBubble = function (bucket) {
    var self = this;
    this.bubble.textContent = bucket;
    this.bubble.classList.add("kgp-fs-bubble-on");
    clearTimeout(this._bt);
    this._bt = setTimeout(function () { self.bubble.classList.remove("kgp-fs-bubble-on"); }, 700);
  };

  KGPFastScroll.prototype._wire = function () {
    var self = this;
    // 데스크탑 클릭 점프
    this.rail.addEventListener("click", function (e) {
      var t = e.target.closest(".kgp-fs-letter");
      if (t) { self._jump(t.getAttribute("data-fs-bucket"), false); }
    });
    // 포인터 스크럽(마우스 드래그 + 터치) — 레일을 누르고 긁으면 즉시 점프 + 버블
    var onMove = function (e) {
      if (!self.scrubbing) return;
      e.preventDefault();
      var y = (e.touches ? e.touches[0].clientY : e.clientY);
      var b = self._bucketAtY(y);
      if (b) self._jump(b, true);
    };
    var onUp = function () {
      self.scrubbing = false;
      self.bubble.classList.remove("kgp-fs-bubble-on");
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onUp);
    };
    var onDown = function (e) {
      self.scrubbing = true;
      var y = (e.touches ? e.touches[0].clientY : e.clientY);
      var b = self._bucketAtY(y);
      if (b) self._jump(b, true);
      document.addEventListener("pointermove", onMove, { passive: false });
      document.addEventListener("pointerup", onUp);
      document.addEventListener("touchmove", onMove, { passive: false });
      document.addEventListener("touchend", onUp);
      e.preventDefault();
    };
    this.rail.addEventListener("pointerdown", onDown);
    this.rail.addEventListener("touchstart", onDown, { passive: false });

    // 스크롤 위치 → 활성 글자(sticky 헤더 관찰)
    if ("IntersectionObserver" in global) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) self._setActive(en.target.getAttribute("data-fs-bucket"));
        });
      }, { rootMargin: "0px 0px -85% 0px", threshold: 0 });
      for (var b in this.headers) io.observe(this.headers[b]);
    }
  };

  KGPFastScroll.prototype.init = function () {
    if (!this.opts.enabled) return this;     // 이름순일 때만
    if (!this.list) return this;
    if (!this.build()) return this;
    this.root.classList.add("kgp-fs-on");
    this._makeRail();
    return this;
  };

  var API = {
    bucketOf: bucketOf,
    BUCKETS: BUCKETS,
    init: function (root, opts) {
      if (!root) return null;
      var inst = new KGPFastScroll(root, opts);
      return inst.init();
    }
  };
  global.KGPFastScroll = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;   // node 테스트용
})(typeof window !== "undefined" ? window : this);
