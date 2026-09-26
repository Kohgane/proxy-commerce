/* kgp-rules.js — F50: 사이트 규칙(셀렉터·카드 탐지·타일 표시)을 **재설치 없이** 바꾸는 자리.
 *
 * 규칙은 **데이터**다(코드 아님 — MV3 원격 코드 금지와 무관). background가 시작할 때 서버
 * `/api/v1/collect/rules`에서 받아 해시를 확인하고 chrome.storage.local.kgp_rules에 둔다.
 * 여기서는 그 캐시를 읽고, 없거나 깨졌으면 아래 BUNDLED(이 확장에 들어 있는 기본값)를 쓴다.
 * 어느 쪽을 쓰는지는 KGPRules.info()가 말한다(page_diag.rules — 진단 파일에 「규칙 버전」).
 */
(function (g) {
  "use strict";
  var BUNDLED = {"hash": "658b8a848231e483c5af1c05634c27df49ddfe5fef550adb262c8fbf5631820e", "rules": {"diag_selectors": {"taobao": {"detail": "#description img, #J_DivItemDesc img, [class*='desc'] img, [class*='Detail'] img", "gallery": "#J_UlThumb img, .tb-thumb img, [class*='thumbnail'] img, [class*='PicGallery'] img, [class*='mainPic'] img, [class*='MainPic'] img, [class*='preview'] img", "options": "#J_isku .tb-prop, [class*='SkuContent'] [class*='valueItemWrapper'], [class*='skuItem']", "title": "[class*='mainTitle'], [class*='ItemTitle'], h1"}}, "list_cards": {"taobao": {"anchor": "a.item-link, a.tb-pick-content-item", "saved_block": "[class*='mytao-collectitem']"}}, "tiles": {"label": {"taobao": "고가 수집"}, "rest_opacity": {"taobao": 0.6}}}, "version": "2026-09-26.1"};   // @generated build_ext_rules_bundle.py
  var cur = { version: BUNDLED.version || "", hash: BUNDLED.hash || "", rules: BUNDLED.rules || {}, source: "bundled" };

  function _walk(obj, path) {
    var parts = String(path || "").split(".");
    var o = obj;
    for (var i = 0; i < parts.length; i++) {
      if (!o || typeof o !== "object" || !(parts[i] in o)) return undefined;
      o = o[parts[i]];
    }
    return o;
  }
  function _valid(r) {
    return !!(r && typeof r === "object" && typeof r.version === "string" && r.version
              && typeof r.hash === "string" && r.hash && r.rules && typeof r.rules === "object");
  }
  // 캐시 값이 있으면 그걸, 그 경로가 없으면 번들, 그것도 없으면 호출부 기본값.
  function get(path, dflt) {
    var v = _walk(cur.rules, path);
    if (v === undefined) v = _walk(BUNDLED.rules || {}, path);
    return v === undefined ? dflt : v;
  }
  function info() { return { version: cur.version, hash: String(cur.hash || "").slice(0, 12), source: cur.source }; }
  function _apply(r) {
    if (_valid(r)) cur = { version: r.version, hash: r.hash, rules: r.rules, source: "remote" };
  }
  try {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(["kgp_rules"], function (o) { _apply(o && o.kgp_rules); });
      if (chrome.storage.onChanged) {
        chrome.storage.onChanged.addListener(function (ch, area) {
          if (area === "local" && ch && ch.kgp_rules) _apply(ch.kgp_rules.newValue);
        });
      }
    }
  } catch (e) { /* 번들로 동작 */ }
  g.KGPRules = { get: get, info: info, _bundled: BUNDLED, _valid: _valid };
})(typeof window !== "undefined" ? window : globalThis);
