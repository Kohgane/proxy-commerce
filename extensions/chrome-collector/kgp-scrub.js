/*
 * SEC-1: 진단·스냅샷 파일에서 로그인 비밀을 지운다.
 *
 * 실측(2026-09-27, 티몰 617129397971 진단 파일): 페이지 DOM의 `<img src="https://pass.tmall.com/add?…">`와
 * page_diag.errors의 리소스 주소에 로그인 쿠키(cookie1·cookie2·_tb_token_·unb…)가 **쿼리스트링 그대로** 실렸다.
 * 그 파일이 레포에 커밋됐다. 그래서 두 겹으로 막는다.
 *   1) page_diag에 싣는 주소는 **경로까지만**(쿼리·해시 제거, 상품 id 계열 키만 남김).
 *   2) 파일로 내보내는 텍스트 전체에서 비밀 키 값을 `***`로 가린다(주소 안이든 스크립트 문자열 안이든).
 * 키 목록은 서버 `src/collectors/secret_scrub.py`와 같다(계약 테스트가 둘을 대조한다).
 */
(function (root) {
  "use strict";
  // 값이 로그인 세션·계정을 가리키는 키. 소문자로 비교한다.
  var KGP_SECRET_KEYS = [
    "cookie", "cookie1", "cookie2", "cookie17", "sgcookie", "_tb_token_", "tb_token", "_l_g_", "sg", "csg",
    "unb", "wk_unb", "_nk_", "nk", "tracknick", "lgc", "lid", "nick", "uc1", "uc3", "uc4", "skt", "cookie14",
    "existshop", "sid", "sessionid", "session", "session_id", "session-id", "session-token", "x5sec",
    "token", "access_token", "refresh_token", "id_token", "auth", "authorization", "password", "passwd",
    "at-main", "sess-at-main", "x-main", "ubid-main", "dnk"
  ];
  // 로그인 계정을 가리키는 값(닉네임·회원번호) — 주소 밖(내비바 닉네임, JSON)에도 찍히므로 값 자체를 모아
  //   문서 전체에서 가린다.
  var _IDENT_PAIR = { lid: 1, lgc: 1, tracknick: 1, dnk: 1, _nk_: 1, nick: 1, unb: 1 };
  var _IDENT_JSON_RE = /"(nick|displayNick|userNumId|userNick|tracknick|loginId)"\s*:\s*"?([^",}\s]{5,64})/g;
  var _SET = {};
  KGP_SECRET_KEYS.forEach(function (k) { _SET[k] = 1; });
  // 이름에 이게 들어가면 비밀로 본다(키 목록에 없는 변형까지).
  var _NAME_RE = /(cookie|token|session|passw)/i;
  function kgpIsSecretKey(k) {
    var s = String(k || "").toLowerCase();
    return !!_SET[s] || _NAME_RE.test(s);
  }
  // 구분자(주소의 ?·&·&amp;·%26·JSON 안의 &, 쿠키 문자열의 「; 」) 뒤의 key=value.
  //   공백·따옴표 뒤는 보지 않는다 — 페이지 JS(`var sid=…`)까지 바꾸면 스냅샷이 원본과 달라진다.
  var _PAIR_RE = /([?&]|&amp;|%26|\\u0026|;\s?)([A-Za-z0-9_\-]{1,40})=([^&;#"'<>\s\\]*)/g;
  function kgpIdentityValues(text) {
    var s = String(text == null ? "" : text), vals = {}, m;
    _PAIR_RE.lastIndex = 0;
    while ((m = _PAIR_RE.exec(s))) {
      if (_IDENT_PAIR[String(m[2]).toLowerCase()] && m[3] && m[3] !== "***") {
        vals[m[3]] = 1;
        try { vals[decodeURIComponent(m[3])] = 1; } catch (e) { /* noop */ }
      }
    }
    _IDENT_JSON_RE.lastIndex = 0;
    while ((m = _IDENT_JSON_RE.exec(s))) vals[m[2]] = 1;
    return Object.keys(vals).filter(function (v) { return v.length >= 5 && v.indexOf("*") < 0; })
      .sort(function (a, b) { return b.length - a.length; });
  }
  function kgpScrubText(text) {
    if (text == null) return text;
    var idents = kgpIdentityValues(text);
    var out = String(text).replace(_PAIR_RE, function (m, pre, key, val) {
      if (!val || val === "***" || !kgpIsSecretKey(key)) return m;
      return pre + key + "=***";
    });
    idents.forEach(function (v) { out = out.split(v).join("***"); });
    return out;
  }
  // page_diag용: 쿼리·해시를 지우고 상품 id 계열만 남긴다(어느 상품이었는지는 알아야 하니까).
  var _KEEP = { id: 1, itemid: 1, item_id: 1, goods_id: 1, offerid: 1, asin: 1 };
  function kgpScrubUrl(u) {
    var s = String(u || "");
    if (!s) return s;
    var hashAt = s.indexOf("#");
    if (hashAt >= 0) s = s.slice(0, hashAt);
    var q = s.indexOf("?");
    if (q < 0) return s;
    var keep = [];
    s.slice(q + 1).split("&").forEach(function (p) {
      var k = p.split("=")[0];
      if (_KEEP[String(k).toLowerCase()]) keep.push(p);
    });
    return s.slice(0, q) + (keep.length ? "?" + keep.join("&") : "");
  }
  // 문장 안의 모든 http(s) 주소를 경로까지만으로 바꾼 뒤, 남은 비밀 키도 가린다.
  function kgpScrubLine(line) {
    var s = String(line == null ? "" : line).replace(/https?:\/\/[^\s"'<>)]+/g, function (u) { return kgpScrubUrl(u); });
    return kgpScrubText(s);
  }
  var api = { KGP_SECRET_KEYS: KGP_SECRET_KEYS, kgpIsSecretKey: kgpIsSecretKey, kgpIdentityValues: kgpIdentityValues, kgpScrubText: kgpScrubText,
              kgpScrubUrl: kgpScrubUrl, kgpScrubLine: kgpScrubLine };
  Object.keys(api).forEach(function (k) { root[k] = api[k]; });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof self !== "undefined" ? self : (typeof window !== "undefined" ? window : globalThis));
