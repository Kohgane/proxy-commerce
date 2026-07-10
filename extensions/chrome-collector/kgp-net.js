/* kgp-net.js — Tier 1 캡처 (v51 STEP1, 테무 근본).
 *
 * 확정 사실(오너): 테무 KR 상품 페이지엔 window.rawData/초기상태 전역이 없고 og:title/image도 없다.
 *   상품 데이터는 **부팅 후 API 응답(JSON)으로만** 존재한다. → 서버·인라인 스크립트 파싱 불가.
 *
 * 해결: 이 스크립트를 manifest "world":"MAIN" + run_at:document_start 로 **페이지가 API를 부르기 전에**
 *   주입해 window.fetch·XMLHttpRequest 를 래핑한다. 페이지가 이미 받은 응답만 읽어 상품형 JSON을
 *   window.__kgpCaptured 에 최근 N개 보관한다(캡처만 — 추가 요청 0건, 우리가 테무 API를 부르지 않음).
 *   수집 시 kgp-extractor 가 이 캡처본에서 가격/갤러리/옵션/상세/리뷰를 매핑(Tier 1).
 */
(function () {
  "use strict";
  if (window.__kgpNetBound) return;   // 중복 주입 방지(SPA 재주입)
  window.__kgpNetBound = true;

  var CAP = 8;                 // 최근 상품형 응답 최대 보관 수
  var MAXLEN = 3000000;        // 3MB 초과 응답은 무시(과대 페이로드 방지)
  window.__kgpCaptured = window.__kgpCaptured || [];

  // 상품형 응답 빠른 판별(파싱 전 텍스트 토큰) — 오검출·불필요 파싱 최소화.
  var PRODUCT_HINT = /("sku|"skuList|"goods|"goodsId|"gallery|"galleryList|"detailGallery|"salePrice|"skuPrice|"reviewNum|"mallSku|"specKey|"productProperty)/i;

  function stash(text) {
    try {
      if (!text || text.length > MAXLEN || !PRODUCT_HINT.test(text)) return;
      var o = JSON.parse(text);
      if (!o || typeof o !== "object") return;
      window.__kgpCaptured.push(o);
      if (window.__kgpCaptured.length > CAP) window.__kgpCaptured.shift();
    } catch (e) { /* JSON 아님 — 무시 */ }
  }

  // ── fetch 래핑 ──
  try {
    var _fetch = window.fetch;
    if (typeof _fetch === "function") {
      window.fetch = function () {
        var p = _fetch.apply(this, arguments);
        try {
          p.then(function (r) {
            try {
              var ct = (r && r.headers && r.headers.get && r.headers.get("content-type")) || "";
              if (/json/i.test(ct) && r.clone) r.clone().text().then(stash).catch(function () {});
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
              if (/json/i.test(ct) || /^[\[{]/.test((xhr.responseText || "").slice(0, 1))) stash(xhr.responseText);
            } else if (rt === "json" && xhr.response && typeof xhr.response === "object") {
              try {
                var t = JSON.stringify(xhr.response);
                stash(t);
              } catch (e) {}
            }
          } catch (e) {}
        });
      } catch (e) {}
      return _send.apply(this, arguments);
    };
  } catch (e) {}
})();
