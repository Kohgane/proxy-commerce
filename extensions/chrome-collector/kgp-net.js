/* kgp-net.js — Tier 1 캡처 + 자가진단 채점 (v51 근본 / v54 STEP2 자가발견).
 *
 * 확정 사실(오너): 테무 KR 상품 페이지엔 초기상태 전역·og 없음. 상품 데이터는 부팅 후 API 응답(JSON)으로만
 *   존재. 이 스크립트를 manifest world:MAIN + document_start 로 주입해 fetch/XMLHttpRequest 를 래핑하고
 *   페이지가 이미 받은 응답만 읽는다(추가 요청 0, 차단 0).
 *
 * v54 STEP2: 하드코딩 URL 패턴은 테무 변경에 취약 → **응답을 필드 시그니처로 채점해 스스로 발견**한다.
 *   가로챈 모든 JSON 응답을 [가격·이미지배열·sku/스펙·리뷰] 존재로 채점(0~4) → 최고점 응답을 상품 소스로
 *   자동 채택. 진단 모드(팝업 토글)면 콘솔 표로 후보를 보여준다. 매 방문 재채점 → 구조가 바뀌어도 재적응.
 *
 * v86-E 스코프 한정: manifest matches = `*://*.temu.com/*`.
 *   종전 `<all_urls>`는 **로컬 file:// HTML에까지** 이 래퍼를 주입했다. 그러면 페이지 자신의 fetch 실패가
 *   `_fetch.apply` 프레임을 지나면서 **귀속만 우리 스크립트로 잡혀** 확장 오류함에 쌓인다(오너 실기기 실측).
 *   위 확정 사실대로 Tier1 캡처는 테무 전용 설계이므로 스코프를 설계 범위로 되돌린다.
 *   ※ 다른 소싱처가 필요해지면 그때 도메인을 추가하는 게 정공 — <all_urls>로 되돌리지 말 것.
 *   ※ 래퍼 자체는 unhandled rejection을 만들지 않는다: 후처리는 p.then(...).catch()로 닫혀 있고 원
 *      promise를 그대로 반환해 페이지의 에러 처리를 가리지 않는다(XHR은 addEventListener라 promise 없음).
 */
(function () {
  "use strict";
  if (window.__kgpNetBound) return;   // 중복 주입 방지(SPA 재주입)
  window.__kgpNetBound = true;

  var CAP = 12;                // 최근 상품형 응답 최대 보관 수(점수순)
  var MAXLEN = 4000000;        // 4MB 초과 응답은 무시
  window.__kgpCaptured = window.__kgpCaptured || [];

  // v86-G: **계측 사각** — `__kgpCaptured`는 채점 통과분(score>=1)만 담는다. 그래서 종전 진단의
  //   `captured:0`은 "래퍼가 아무 트래픽도 못 봤다(월드/타이밍 실패)"와 "봤지만 전부 0점이었다
  //   (시그니처 채점 실패)"를 **구분하지 못했다** — 테무 '흔적 무'의 판독을 막던 지점이 정확히 여기다.
  //   → stash에 들어온 응답을 단계별로 센다: seen(호출) → jsonish(JSON 파싱 성공) → kept/dropped(채점).
  //   dropped 표본 URL도 3개까지 남긴다(트래픽은 있었다는 물증 = 채점 갈래 확정).
  window.__kgpNetStats = window.__kgpNetStats || { seen: 0, jsonish: 0, kept: 0, dropped: 0, droppedUrls: [] };

  // 상품형 응답 빠른 판별(파싱 전 텍스트 토큰) — 명백한 비상품 응답 스킵으로 파싱 비용 절감(정확도는 채점이 담당).
  var JSONISH = /^[\s﻿]*[\[{]/;

  // ── 필드 시그니처 채점(0~4): 가격·이미지배열·sku/스펙·리뷰 ──
  function _kgpScore(root) {
    var sig = { price: 0, images: 0, sku: 0, reviews: 0 };
    var stack = [root], seen = 0;
    while (stack.length && seen < 6000) {
      seen++;
      var v = stack.pop();
      if (v && typeof v === "object" && v.length !== undefined && typeof v.length === "number" && !(v instanceof String)) {
        // 배열
        var first = v[0];
        if (!sig.images && v.length >= 2 && typeof first === "string" && /^https?:\/\/.+\.(jpg|jpeg|png|webp|avif)/i.test(first)) sig.images = 1;
        for (var i = 0; i < v.length && i < 300; i++) { if (v[i] && typeof v[i] === "object") stack.push(v[i]); }
        continue;
      }
      if (!v || typeof v !== "object") continue;
      for (var k in v) {
        var val = v[k]; var kl = ("" + k).toLowerCase();
        if (!sig.price && /(^|[^a-z])(price|amount|saleprice|skuprice|lowprice)([^a-z]|$)/.test(kl)
            && (typeof val === "number" ? val > 0 : (typeof val === "string" && /^[\d.,]+$/.test(val) && parseFloat(val.replace(/,/g, "")) > 0))) sig.price = 1;
        if (!sig.sku && /(sku|skulist|speckey|productproperty|goodsattr|specvalue|variation)/.test(kl)) sig.sku = 1;
        if (!sig.images && /(gallery|images|imagelist|imglist|picurl|photolist|carousel|thumbnail)/.test(kl) && val && typeof val === "object" && val.length >= 2) {
          var f0 = val[0];
          if ((typeof f0 === "string" && /https?:/.test(f0)) || (f0 && typeof f0 === "object" && (f0.url || f0.contentUrl || f0.imgUrl || f0.picUrl))) sig.images = 1;
        }
        if (!sig.reviews && /(review|comment)/.test(kl) && val && typeof val === "object" && val.length >= 1 && typeof val[0] === "object") {
          var s0 = "";
          try { s0 = JSON.stringify(val[0]); } catch (e) {}
          if (s0 && s0.length > 20 && /(content|text|comment|reviewbody|rating|star)/i.test(s0)) sig.reviews = 1;
        }
        if (val && typeof val === "object") stack.push(val);
      }
    }
    return { price: sig.price, images: sig.images, sku: sig.sku, reviews: sig.reviews, score: sig.price + sig.images + sig.sku + sig.reviews };
  }

  // v62 STEP2: 테무 goods_id 추출 — URL(-g-{n}·goods_id=·goodsId=) + 응답 객체 walk(goodsId/goods_id 키).
  var GID_URL = /(?:[-_/]g-|[?&](?:_x_)?goods_?id=|\/goods\/)(\d{5,})/i;
  function _goodsIdFromUrl(u) {
    try { var m = String(u || "").match(GID_URL); return m ? m[1] : ""; } catch (e) { return ""; }
  }
  function _isGidKey(kl) { return kl === "goodsid" || kl === "goods_id"; }
  function _gidVal(v) {
    if (typeof v !== "number" && typeof v !== "string") return "";
    var g = String(v).replace(/\D/g, "");
    return g.length >= 5 ? g : "";
  }

  // v86-G(수리): 응답 **전체의** goods_id 집합. 종전 `_goodsIdFromObj`는 DFS 첫 히트 **하나**만 키로 박았다.
  //   테무 PDP 렌더 응답은 내 상품 블록과 추천 캐러셀(다른 goodsId 다수)이 **한 응답에 같이** 온다. 그래서
  //   키 선택이 walk 순서에 좌우돼 추천 상품 id가 잡히면 `__kgpMatchCapture`가 불일치로 보고 Tier1 후보를
  //   **통째로 폐기** → 가격·옵션·갤러리 전부 공백('merged 0', tier1 흔적 무)이 된다. jsdom 재현 확인.
  //   → 집합으로 바꿔 "내 상품이 이 응답 안에 있는가"를 순서와 무관하게 판정한다.
  var GID_MAX = 60;
  function _goodsIdsFromObj(root) {
    var ids = [], seenIds = {}, stack = [root], seen = 0;
    while (stack.length && seen < 8000 && ids.length < GID_MAX) {
      seen++;
      var v = stack.pop();
      if (!v || typeof v !== "object") continue;
      if (v.length !== undefined && typeof v.length === "number") {
        for (var i = 0; i < v.length && i < 300; i++) if (v[i] && typeof v[i] === "object") stack.push(v[i]);
        continue;
      }
      for (var k in v) {
        var kl = ("" + k).toLowerCase();
        if (_isGidKey(kl)) {
          var g = _gidVal(v[k]);
          if (g && !seenIds[g]) { seenIds[g] = 1; ids.push(g); }
        }
        if (v[k] && typeof v[k] === "object") stack.push(v[k]);
      }
    }
    return ids;
  }

  // ── v86-G(수리): 내 goods_id 서브트리로 스코프 축소 ──
  //   매칭이 붙어도 **응답 통짜**를 후보로 넘기면 추출기가 추천 캐러셀의 가격·제목·이미지를 집을 수 있다
  //   (walk 순서 의존 = 조용한 오염). 내 goods 노드에서 위로 올라가되 **외래 goods_id가 섞이는 순간 멈춰**
  //   가장 넓은 '순수' 조상을 고른다(= 내 상품의 sku·price·gallery는 품고, 추천 블록은 배제).
  //   축소가 신호를 없애면(score 0) 통짜로 되돌린다 — 스코프가 수집을 악화시키지 않는다.
  function _hasForeignGid(node, gid) {
    var stack = [node], seen = 0;
    while (stack.length && seen < 6000) {
      seen++;
      var v = stack.pop();
      if (!v || typeof v !== "object") continue;
      if (v.length !== undefined && typeof v.length === "number") {
        for (var i = 0; i < v.length && i < 300; i++) if (v[i] && typeof v[i] === "object") stack.push(v[i]);
        continue;
      }
      for (var k in v) {
        if (_isGidKey(("" + k).toLowerCase())) {
          var g = _gidVal(v[k]);
          if (g && g !== gid) return true;
        }
        if (v[k] && typeof v[k] === "object") stack.push(v[k]);
      }
    }
    return false;
  }
  // v86-G(수리): **특정** gid 한 개만 찾는 탐색 — `_goodsIdsFromObj`는 수집 상한(60개·8000노드)이 있어
  //   대형 응답(테무 렌더 응답은 MB급)에서 내 id가 상한 밖으로 밀려날 수 있다. 그러면 매칭이 다시 깨져
  //   같은 버그로 되돌아간다. 값 하나를 찾는 일은 훨씬 싸므로 예산을 크게 잡고 발견 즉시 끝낸다.
  function _hasGid(root, gid) {
    var stack = [root], seen = 0;
    while (stack.length && seen < 60000) {
      seen++;
      var v = stack.pop();
      if (!v || typeof v !== "object") continue;
      if (v.length !== undefined && typeof v.length === "number") {
        for (var i = 0; i < v.length && i < 500; i++) if (v[i] && typeof v[i] === "object") stack.push(v[i]);
        continue;
      }
      for (var k in v) {
        if (_isGidKey(("" + k).toLowerCase()) && _gidVal(v[k]) === gid) return true;
        if (v[k] && typeof v[k] === "object") stack.push(v[k]);
      }
    }
    return false;
  }
  function _pathsToGoods(root, gid, maxHits) {
    var out = [], stack = [{ n: root, p: [] }], seen = 0;
    while (stack.length && seen < 40000 && out.length < (maxHits || 5)) {
      seen++;
      var cur = stack.pop(), v = cur.n;
      if (!v || typeof v !== "object") continue;
      var path = cur.p.concat([v]);
      if (v.length !== undefined && typeof v.length === "number") {
        for (var i = 0; i < v.length && i < 300; i++) if (v[i] && typeof v[i] === "object") stack.push({ n: v[i], p: path });
        continue;
      }
      var isMine = false;
      for (var k in v) {
        if (_isGidKey(("" + k).toLowerCase()) && _gidVal(v[k]) === gid) isMine = true;
        if (v[k] && typeof v[k] === "object") stack.push({ n: v[k], p: path });
      }
      if (isMine) out.push(path);
    }
    return out;
  }
  window.__kgpScopeToGoods = function (root, gid) {
    gid = String(gid || "").replace(/\D/g, "");
    var fallback = { obj: root, scoped: false, reason: gid ? "no_gid_node" : "no_page_gid" };
    if (!gid || !root || typeof root !== "object") return fallback;
    try {
      // 빠른 경로: 응답에 외래 goods_id가 아예 없으면(=추천 미동봉) 축소할 이유가 없다. 큰 응답에서
      //   경로 탐색·조상별 서브트리 검사를 통째로 건너뛴다(추출 900ms 예산 보호).
      if (!_hasForeignGid(root, gid)) return { obj: root, scoped: false, reason: "already_pure" };
      var paths = _pathsToGoods(root, gid, 3);
      if (!paths.length) return fallback;
      var best = null;
      for (var p = 0; p < paths.length; p++) {
        var path = paths[p];
        var node = path[path.length - 1];              // 내 goods 노드
        var climbed = 0;
        for (var i = path.length - 2; i >= 0 && climbed < 12; i--, climbed++) {   // 위로 올라가며 순수 조상 확장
          if (_hasForeignGid(path[i], gid)) break;
          node = path[i];
        }
        var sc = _kgpScore(node).score;
        if (!best || sc > best.score) best = { node: node, score: sc, widened: node !== path[path.length - 1] };
      }
      if (!best || best.score <= 0) return { obj: root, scoped: false, reason: "scope_lost_signal" };
      if (best.node === root) return { obj: root, scoped: false, reason: "already_pure" };
      return { obj: best.node, scoped: true, reason: "narrowed", score: best.score };
    } catch (e) { return fallback; }
  };

  // v62 STEP2: goods_id 정확 매칭용 캡처 조회 — 현재 페이지 goods_id와 일치하는 응답(TTL 10분), 없으면 null.
  //   '이전 상품 응답 오채택' 방지 — 점수 최고가 아니라 **내 goods_id** 우선.
  // v86-G(수리): 판정 기준을 '캡처의 대표 id 1개 == 내 id'에서 **'내 id가 응답 안에 있는가'**로 넓히고,
  //   여러 후보는 (URL에 내 id 있음 → 시그니처 점수 → 최신) 순으로 고른다. 종전엔 walk 순서 한 번의
  //   운으로 Tier1 전체가 날아갔다. 넓힘의 대가(추천에 내 id가 스친 응답 채택)는 위 스코프 축소가 막는다.
  window.__kgpPageGoodsId = function () { return _goodsIdFromUrl((window.location && window.location.href) || ""); };
  window.__kgpMatchCapture = function (goodsId) {
    goodsId = String(goodsId || "").replace(/\D/g, "");
    if (!goodsId) return null;
    var now = Date.now(), best = null, bestRank = null;
    var cap = window.__kgpCaptured || [];
    for (var i = 0; i < cap.length; i++) {
      var e = cap[i];
      if ((now - (e.ts || 0)) > 600000) continue;                       // TTL 10분
      var urlHit = _goodsIdFromUrl(e.url || "") === goodsId;
      var inBody = e.goods_id === goodsId ||
        (e.goods_ids && e.goods_ids.indexOf && e.goods_ids.indexOf(goodsId) >= 0);
      // 수집 상한(60개)에 밀려 목록에 없을 수 있다 → 응답 본체에서 그 id만 한 번 더 확인(대형 응답 대비).
      if (!urlHit && !inBody && e.obj) inBody = _hasGid(e.obj, goodsId);
      if (!urlHit && !inBody) continue;
      var rank = [urlHit ? 1 : 0, e.score || 0, e.ts || 0];
      if (!best || rank[0] > bestRank[0] ||
          (rank[0] === bestRank[0] && rank[1] > bestRank[1]) ||
          (rank[0] === bestRank[0] && rank[1] === bestRank[1] && rank[2] > bestRank[2])) {
        best = e; bestRank = rank;
      }
    }
    return best;
  };

  function _note(bucket, url) {
    try {
      var st = window.__kgpNetStats;
      st[bucket] = (st[bucket] || 0) + 1;
      if (bucket === "dropped" && st.droppedUrls.length < 3 && url) st.droppedUrls.push(String(url).slice(0, 120));
    } catch (e) {}
  }

  function stash(text, url) {
    _note("seen", url);
    try {
      if (!text || text.length > MAXLEN || !JSONISH.test(text)) return;
      var o = JSON.parse(text);
      if (!o || typeof o !== "object") return;
      _note("jsonish", url);
      var s = _kgpScore(o);
      if (s.score <= 0) { _note("dropped", url); return; }   // 상품 신호 0 → 버림(비상품 응답)
      _note("kept", url);
      // v62 STEP2 → v86-G: 대표 goods_id(URL 우선)에 더해 **응답 안의 전 goods_id 집합**을 함께 보관.
      //   대표 하나만으론 추천 캐러셀 id가 뽑혀 내 상품 응답이 불일치로 버려졌다(재현 확인).
      var gids = _goodsIdsFromObj(o);
      var gid = _goodsIdFromUrl(url) || gids[0] || "";
      window.__kgpCaptured.push({ url: url || "", size: text.length, price: s.price, images: s.images, sku: s.sku, reviews: s.reviews, score: s.score, goods_id: gid, goods_ids: gids, ts: Date.now(), obj: o });
      window.__kgpCaptured.sort(function (a, b) { return b.score - a.score; });   // 점수순(폴백용 — 매칭 우선)
      if (window.__kgpCaptured.length > CAP) window.__kgpCaptured.length = CAP;
    } catch (e) { /* JSON 아님 — 무시 */ }
  }

  // ── fetch 래핑 ──
  try {
    var _fetch = window.fetch;
    if (typeof _fetch === "function") {
      window.fetch = function () {
        var _url = "";
        try { _url = (typeof arguments[0] === "string") ? arguments[0] : (arguments[0] && arguments[0].url) || ""; } catch (e) {}
        var p = _fetch.apply(this, arguments);
        try {
          p.then(function (r) {
            try {
              var ct = (r && r.headers && r.headers.get && r.headers.get("content-type")) || "";
              if ((/json/i.test(ct) || !ct) && r.clone) r.clone().text().then(function (t) { stash(t, (r && r.url) || _url); }).catch(function () {});
            } catch (e) {}
          }).catch(function () {});
        } catch (e) {}
        return p;
      };
    }
  } catch (e) {}

  // ── XMLHttpRequest 래핑 ──
  try {
    var XP = XMLHttpRequest.prototype;
    var _open = XP.open, _send = XP.send;
    XP.open = function () { try { this.__kgpUrl = arguments[1]; } catch (e) {} return _open.apply(this, arguments); };
    XP.send = function () {
      var xhr = this;
      try {
        xhr.addEventListener("load", function () {
          try {
            var rt = xhr.responseType;
            if (rt === "" || rt === "text") {
              var ct = (xhr.getResponseHeader && xhr.getResponseHeader("content-type")) || "";
              if (/json/i.test(ct) || JSONISH.test(xhr.responseText || "")) stash(xhr.responseText, xhr.__kgpUrl || "");
            } else if (rt === "json" && xhr.response && typeof xhr.response === "object") {
              try { stash(JSON.stringify(xhr.response), xhr.__kgpUrl || ""); } catch (e) {}
            }
          } catch (e) {}
        });
      } catch (e) {}
      return _send.apply(this, arguments);
    };
  } catch (e) {}

  // v86-G: 최고점 후보 1건 요약(obj 제외) — 진단에 실어 서버·드로어에서 "무엇을 잡았나"를 바로 본다.
  //   점수만으로는 "가격만 잡힌 2점"과 "가격+옵션+갤러리 3점"을 구분 못 해 수리 방향이 안 잡힌다.
  window.__kgpTopCandidate = function () {
    var cap = window.__kgpCaptured || [];
    if (!cap.length) return null;
    var e = cap[0];
    return { url: (e.url || "").slice(0, 160), score: e.score || 0, size: e.size || 0,
             price: !!e.price, images: !!e.images, sku: !!e.sku, reviews: !!e.reviews,
             goods_id: e.goods_id || "",
             // v86-G(수리): 응답 안 goods_id 개수. 1보다 크면 추천 캐러셀 동봉 응답 —
             //   대표 id 하나로 매칭하던 종전 방식이 깨지던 조건 그 자체다(실기기 판독용).
             goods_ids_n: (e.goods_ids && e.goods_ids.length) || 0 };
  };

  // ── 진단 표 데이터(메타만, obj 제외) — 격리월드가 postMessage로 요청하면 kgp-main이 console.table ──
  window.__kgpDiagRows = function () {
    return (window.__kgpCaptured || []).map(function (e) {
      return { url: (e.url || "").slice(0, 80), size: e.size, price: !!e.price, images: !!e.images, sku: !!e.sku, reviews: !!e.reviews, score: e.score };
    });
  };
})();
