/**
 * kgp-sources.js — v81 STEP3: 소싱처 호스트 매칭 단일 진실원천(single source of truth).
 *
 * 배경: 팝업(popup.js)과 콘텐츠스크립트(content_script.js)가 각자 소싱처 목록/매처를 들고 있어
 *   drift가 났다 — 팝업 목록엔 rakuten·iherb·dhgate·qoo10·mercari·yahoo·yoshida가 빠져,
 *   www.rakuten.co.jp에서 콘텐츠스크립트는 FAB를 주입하는데 팝업은 "여긴 지정 소싱처가 아니에요"라고
 *   모순 표시했다. 이 모듈이 유일한 레지스트리 + 매처가 되고, 팝업·콘텐츠스크립트가 여기에 위임한다.
 *
 * 규칙:
 *   - 서브도메인 와일드카드: `(^|\.)rakuten\.(co\.jp|com)$` 하나로 www/item/search/books.rakuten 전부 커버.
 *   - 쿼리스트링·트래킹 파라미터 무시: 매칭은 **호스트명만** 본다(?l2-id=… 등은 hostname 파싱에서 자연 제거).
 *   - 아마존 국가 도메인 흡수: `(^|\.)amazon\.[a-z][a-z.]*$` 가 com/de/co.jp/co.uk/fr/it/es… 전부 매칭.
 *
 * 통화(currency)는 참고용 힌트만 — 실제 가격 통화 추론은 kgp-extractor._localeCurrency(로케일·경로·TLD)가 담당.
 */
(function (global) {
  "use strict";

  // 레지스트리(단일 소스). content_script·popup 모두 이 배열에서 파생.
  var SOURCES = [
    { id: "taobao", label: "타오바오", re: /(^|\.)taobao\.com$/, currency: "CNY" },
    { id: "tmall", label: "티몰", re: /(^|\.)tmall\.com$/, currency: "CNY" },
    { id: "1688", label: "1688", re: /(^|\.)1688\.com$/, currency: "CNY" },
    { id: "temu", label: "테무", re: /(^|\.)temu\.com$/, currency: "" },
    // 아마존 국가 도메인 와일드카드 — com/de/co.jp/co.uk/fr/it/es/… 전부 흡수.
    { id: "amazon", label: "아마존", re: /(^|\.)amazon\.[a-z][a-z.]*$/, currency: "" },
    { id: "aliexpress", label: "알리익스프레스", re: /(^|\.)aliexpress\.(com|us)$/, currency: "" },
    { id: "iherb", label: "아이허브", re: /(^|\.)iherb\.com$/, currency: "" },
    { id: "dhgate", label: "DHgate", re: /(^|\.)dhgate\.com$/, currency: "" },
    { id: "qoo10", label: "큐텐", re: /(^|\.)qoo10\.[a-z.]+$/, currency: "" },
    { id: "mercari", label: "메루카리", re: /(^|\.)mercari\.com$/, currency: "JPY" },
    { id: "rakuten", label: "라쿠텐(Rakuten Fashion 포함)", re: /(^|\.)rakuten\.(co\.jp|com)$/, currency: "JPY" },
    { id: "yahoo", label: "야후쇼핑(재팬)", re: /(shopping\.yahoo\.co\.jp|paypaymall\.yahoo\.co\.jp)$/, currency: "JPY" },
    { id: "yoshida", label: "요시다카반", re: /(^|\.)yoshidakaban\.com$/, currency: "JPY" },
  ];

  // URL/문자열 → 호스트명(소문자). 쿼리·해시·경로·프로토콜 제거(트래킹 파라미터 자연 무시).
  function hostOf(u) {
    var s = String(u || "").trim();
    try { return new URL(s).hostname.toLowerCase(); } catch (e) {}
    return s.toLowerCase().replace(/^[a-z]+:\/\//, "").replace(/[/?#].*$/, "").replace(/:\d+$/, "");
  }

  // 커스텀(사용자 추가) 도메인 매칭 — 서브도메인 포함.
  function _customMatch(host, domain) {
    domain = String(domain || "").toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/^www\./, "");
    return !!domain && (host === domain || host.endsWith("." + domain));
  }

  // 호스트가 지정 소싱처인가? settings = { defaults:{id:bool}, custom:[{host,on}] }.
  //   반환: 매치 { id, label, currency, custom:false } / 커스텀 { id:"custom", label:host, custom:true } / 미매치 null.
  function matchHost(host, settings) {
    host = String(host || "").toLowerCase();
    if (!host) return null;
    var s = settings || {}, defs = s.defaults || {};
    for (var i = 0; i < SOURCES.length; i++) {
      var src = SOURCES[i];
      if (defs[src.id] !== false && src.re.test(host)) {
        return { id: src.id, label: src.label, currency: src.currency || "", custom: false };
      }
    }
    var cust = s.custom || [];
    for (var j = 0; j < cust.length; j++) {
      var c = cust[j];
      if (c && c.on !== false && _customMatch(host, c.host)) {
        return { id: "custom", label: String(c.host || ""), currency: "", custom: true };
      }
    }
    return null;
  }

  function matchUrl(url, settings) { return matchHost(hostOf(url), settings); }
  function allowed(host, settings) { return !!matchHost(host, settings); }

  global.KGPSources = {
    SOURCES: SOURCES,
    hostOf: hostOf,
    matchHost: matchHost,
    matchUrl: matchUrl,
    allowed: allowed,
  };
})(typeof self !== "undefined" ? self : this);
