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
  function _goodsIdFromObj(root) {
    var stack = [root], seen = 0;
    while (stack.length && seen < 4000) {
      seen++;
      var v = stack.pop();
      if (!v || typeof v !== "object") continue;
      if (v.length !== undefined && typeof v.length === "number") {
        for (var i = 0; i < v.length && i < 200; i++) if (v[i] && typeof v[i] === "object") stack.push(v[i]);
        continue;
      }
      for (var k in v) {
        var kl = ("" + k).toLowerCase();
        if ((kl === "goodsid" || kl === "goods_id") && (typeof v[k] === "number" || typeof v[k] === "string")) {
          var g = String(v[k]).replace(/\D/g, ""); if (g.length >= 5) return g;
        }
        if (v[k] && typeof v[k] === "object") stack.push(v[k]);
      }
    }
    return "";
  }
  // v62 STEP2: goods_id 정확 매칭용 캡처 조회 — 현재 페이지 goods_id와 일치하는 최신 응답(TTL 10분), 없으면 null.
  //   '이전 상품 응답 오채택' 방지 — 점수 최고가 아니라 **내 goods_id** 우선.
  window.__kgpPageGoodsId = function () { return _goodsIdFromUrl((window.location && window.location.href) || ""); };
  window.__kgpMatchCapture = function (goodsId) {
    goodsId = String(goodsId || "").replace(/\D/g, "");
    if (!goodsId) return null;
    var now = Date.now(), best = null;
    var cap = window.__kgpCaptured || [];
    for (var i = 0; i < cap.length; i++) {
      var e = cap[i];
      if (e.goods_id === goodsId && (now - (e.ts || 0)) <= 600000) {   // TTL 10분
        if (!best || (e.ts || 0) > (best.ts || 0)) best = e;           // 최신 우선
      }
    }
    return best;
  };

  function stash(text, url) {
    try {
      if (!text || text.length > MAXLEN || !JSONISH.test(text)) return;
      var o = JSON.parse(text);
      if (!o || typeof o !== "object") return;
      var s = _kgpScore(o);
      if (s.score <= 0) return;               // 상품 신호 0 → 버림(비상품 응답)
      var gid = _goodsIdFromUrl(url) || _goodsIdFromObj(o);   // v62 STEP2: goods_id 키(URL 우선, 없으면 응답)
      window.__kgpCaptured.push({ url: url || "", size: text.length, price: s.price, images: s.images, sku: s.sku, reviews: s.reviews, score: s.score, goods_id: gid, ts: Date.now(), obj: o });
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

  // ── 진단 표 데이터(메타만, obj 제외) — 격리월드가 postMessage로 요청하면 kgp-main이 console.table ──
  window.__kgpDiagRows = function () {
    return (window.__kgpCaptured || []).map(function (e) {
      return { url: (e.url || "").slice(0, 80), size: e.size, price: !!e.price, images: !!e.images, sku: !!e.sku, reviews: !!e.reviews, score: e.score };
    });
  };
})();
