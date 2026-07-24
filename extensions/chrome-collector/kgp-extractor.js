/* kgp-extractor.js — 공유 상품 추출기(확장·북마클릿 동일 코드).
 *
 * 소스 우선순위(오너): ①초기 상태 JSON(JSON-LD + 페이지 전역 상태) 파싱 → ②DOM 셀렉터 폴백 →
 *   ③둘 다 실패 시 partial=true('부분 수집' 정직 표기, 가짜 성공 금지).
 * 가격: 표시용(통화기호 포함) 문자열 우선 파싱, 정수/센트 애매하면 sanity 게이트로 넘김.
 *   sanity: 통화 미상 또는 비상식 하한(KRW<100 등) → price_status='needs_check' + 경고(warnings).
 *   재고 수·리뷰 수 숫자는 가격 후보에서 원천 배제.
 * 이미지: 갤러리 URL 배열(원본 해상도 우선) — 순서 보존 + 중복 제거, 1번=썸네일.
 * 옵션: 스펙(색상·사이즈…) + sku별 가격(있으면). 상세: 상세 이미지 배열 + 속성 텍스트 표(데이터만).
 * 리뷰: 평점·리뷰 수 + 초기 JSON에 이미 실린 텍스트 리뷰 상위 N건(추가 API 호출 없음). 없으면 없음.
 *
 * 전역 하나만 노출: window.kgpExtractProduct(). 확장은 manifest로, 북마클릿은 서버가 인라인해 공유.
 */
(function (global) {
  "use strict";
  if (global.kgpExtractProduct) return;   // 중복 로드 방지(확장+북마클릿 동시 상황)

  var REVIEW_MAX = 10;

  // ── 공통 유틸 ──────────────────────────────────────────────
  function _sym(s) {
    var M = { "$": "USD", "＄": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "￥": "JPY", "₩": "KRW", "￦": "KRW" };
    return M[s] || "";
  }
  // v83 STEP1: 통화 표기 사전 — 일본어 円(라쿠텐·요시다 '7,480円')이 빠져 있어 기호 단계가 통화를 못 읽고
  //   로케일 사다리로 떨어지던 근원(tsumugi 7,480円 → KRW 오판)의 한 갈래. 円/圓/¥ 추가.
  var CODE = { USD: "USD", EUR: "EUR", GBP: "GBP", JPY: "JPY", KRW: "KRW", CNY: "CNY",
               "원": "KRW", "엔": "JPY", "위안": "CNY", "元": "CNY", "円": "JPY", "圓": "JPY" };
  var PRICE_RE = /([\$＄€£¥￥₩￦])\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(USD|EUR|GBP|JPY|KRW|CNY|원|엔|위안|元|円|圓)/i;
  function parsePriceStr(raw) {
    var m = String(raw == null ? "" : raw).match(PRICE_RE);
    if (!m) return null;
    var sym = m[1] || "", num = (m[2] || m[3] || "").replace(/,/g, ""), code = m[4] || "";
    if (!num) return null;
    var cur = code ? (CODE[code] || CODE[code.toUpperCase()] || code.toUpperCase()) : (_sym(sym) || "");
    return { price: num, currency: cur };
  }
  // v74 STEP4: 숫자 정규화 공통 유틸(전 어댑터) — 천단위 콤마·공백·통화기호 제거 + **후행 점**('6620.'→6620)
  //   제거해 항상 \d+(\.\d+)? 형태로. (알리 등 후행 점/천단위 혼입 가격을 마켓이 거부하던 근원 봉인.)
  function _normNum(s) {
    var t = String(s == null ? "" : s).replace(/[,\s ]/g, "");   // 콤마·공백·NBSP 제거
    var m = t.match(/\d+(?:\.\d+)?/);                                 // 후행 점·기호·문자 절삭 → 정수 or 소수
    return m ? m[0] : "";
  }
  function uniqPush(arr, seen, v) {
    v = (v == null ? "" : String(v)).trim();
    if (v && !seen[v]) { seen[v] = 1; arr.push(v); }
  }

  // 원본 해상도화(썸네일 크기 토큰 제거 — 아마존 _AC_SX../Temu ...?imageView 등)
  function hiRes(u) {
    if (!u) return u;
    try {
      // 아마존 크기 토큰(image._AC_SX466_.jpg → image.jpg)은 통째로 제거(더블닷 방지).
      // v82 STEP2: 토큰 문자군 확장 — S[XYLS]만으론 _AC_US100_·_AC_UL320_·_SR38,50_(갤러리 저해상 근원)이
      //   안 걸려 원본 승격 실패. [SU][XYLSR]+US/UL/SR 추가로 아마존 사이즈/크롭 토큰 전군을 원본화.
      u = u.replace(/\._(AC_)?[SU][XYLSR]\d+_/gi, "").replace(/\._(SX|SY|SS|SL|SR|UX|UY|UL|US|CR)\d+(,\d+)*_/gi, "");
      // v83 STEP3: 복합 토큰 블록 통째 제거 — A+ 상세 이미지의 `.__CR0,0,200,225_PT0_SX200__.jpg`(200px 저해상)
      //   처럼 여러 토큰이 이중 언더스코어로 묶인 형태는 위 단일 토큰 치환으로 안 걸린다. 대문자 토큰 블록만
      //   (Amazon 수식자 문법) 잘라 원본으로 승격. 소문자 파일명은 건드리지 않는다(타 사이트 오작동 방지).
      u = u.replace(/\.(_{1,2}[A-Z0-9][A-Z0-9,_]*_{1,2})\.(jpg|jpeg|png|gif|webp)(?=$|\?)/g, ".$2");
      u = u.replace(/(\?|&)(imageView2?|thumb|w|width|h|height|size|quality|_ex)=[^&]*/gi, "");   // v76 STEP3: 라쿠텐 _ex=WxH(썸네일) 제거 → 원본
      // v79 STEP4: 알리 썸네일 변형(.jpg_80x80xz.jpg·.jpg_640x640q90.jpg) → 원본(.jpg)으로 정규화 → 변형 dedupe.
      u = u.replace(/\.(jpg|jpeg|png|webp|gif)_\d+x\d+[a-z0-9]*\.(jpg|jpeg|png|webp|gif)$/i, ".$1");
      u = u.replace(/[?&]$/, "").replace(/\.{2,}(jpg|jpeg|png|webp|gif)/i, ".$1");
    } catch (e) {}
    return u;
  }

  // v83 STEP3: 승격 실패 저해상 판정 — hiRes를 거치고도 크기/크롭 토큰이 남은 URL은 **원본이 아니다**.
  //   실기기 증거: 갤러리 `_AC_US100_`(100px 썸네일), A+ 상세 `__CR0,0,200,225_PT0_SX200__`(200px). 저해상을
  //   상품 이미지로 저장하면 마켓 등록 시 화질 반려 → 승격 못 하면 **제외**(정직: 흐린 이미지 대신 없음).
  // 토큰은 대문자 고정(아마존 수식자 문법) — 소문자 파일명(`.sr7.jpg` 등)을 저해상으로 오판하지 않도록 대소문자 구분.
  var _LOWRES_TOKEN_RE = /\.(_{0,2}(?:AC_)?(?:S[XYLS]|U[XYLS]|CR|SR|PT)\d)/;
  function _isLowResImg(u) {
    var s = String(u == null ? "" : u);
    if (!s) return true;
    if (!_LOWRES_TOKEN_RE.test(s)) return false;
    // 남은 토큰의 픽셀 수치가 충분히 크면(≥300) 원본급으로 인정, 아니면 저해상.
    var m = s.match(/(?:S[XYLS]|U[XYLS])(\d{2,4})/);
    if (m && parseInt(m[1], 10) >= 300) return false;
    return true;
  }

  // 비-상품 이미지(로고/아이콘/배너/픽셀…) 판정
  var NONPROD_IMG = /(logo|sprite|icon|favicon|avatar|placeholder|loading|blank|pixel|spinner|banner|badge|button|arrow|chevron|caret|rating|star_|flags?|emoji|watermark|qr[-_]?code|coupon|nav_|1x1|transparent\.|spacer)/i;
  function isProductImg(s) { return s && s.indexOf("data:") !== 0 && !NONPROD_IMG.test(s); }
  // v79 STEP4: 호스트별 갤러리 오염 필터 — 테무 kwcdn 배너·쿠폰(material-put·aimg·upload_aimg) 제외(상품
  //   /product/ 경로만), 라쿠텐 타상품(현재 shop 슬러그 밖 CDN 이미지) 제외. 비대상 호스트·비-CDN은 무영향.
  function _galleryScopeHost(list) {
    var h = ""; try { h = (location.hostname || "").toLowerCase(); } catch (e) {}
    if (/(^|\.)temu\.com$/.test(h)) {
      return list.filter(function (u) {
        if (!/kwcdn\.com/i.test(u)) return true;                                   // 비-kwcdn 유지
        if (/\/(material-put|marketing|activity|promo)\//i.test(u) || /(^|[\/_])(upload_)?aimg/i.test(u)) return false;   // 배너·쿠폰
        return /\/product\//i.test(u);                                            // 상품 경로만
      });
    }
    if (/(^|\.)rakuten\.(co\.jp|com)$/.test(h)) {
      var slug = ""; try { var mm = (location.pathname || "").match(/^\/([^\/]+)\//); slug = mm ? mm[1].toLowerCase() : ""; } catch (e) {}
      if (!slug) return list;
      return list.filter(function (u) {
        var lu = u.toLowerCase();
        if (/r10s\.jp|image\.rakuten\.co\.jp/i.test(lu) && lu.indexOf("/" + slug + "/") < 0 && lu.indexOf(slug) < 0) return false;   // 타 shop 추천
        return true;
      });
    }
    return list;
  }

  // 가격이 아닌 숫자(재고·쿠폰·수량·평점·판매수) 문맥 배제
  var NONPRICE = /(재고|남음|남았|개\s*남|수량|qty|quantity|stock|left|in\s*cart|장바구니|쿠폰|coupon|적립|포인트|point|리뷰|review|평점|rating|판매|sold|명이|배송비|shipping\s*fee|무료배송|free\s*shipping|할인율|% ?off|퍼센트)/i;

  // ── ① 초기 상태 JSON ──────────────────────────────────────
  // 스키마를 하드코딩하지 않는다(사이트별 구조 상이·추측 금지). JSON-LD Product + 페이지 전역 상태
  // 객체를 **키 이름 휴리스틱**으로 깊이 탐색해 가격/이미지/스펙/리뷰를 모은다.
  function _jsonLd() {
    var out = [];
    try {
      var s = document.querySelectorAll('script[type="application/ld+json"]');
      for (var i = 0; i < s.length; i++) {
        try { var j = JSON.parse(s[i].innerText || s[i].textContent || ""); if (j) out.push(j); } catch (e) {}
      }
    } catch (e) {}
    return out;
  }
  var STATE_KEYS = ["__NEXT_DATA__", "__NUXT__", "__INITIAL_STATE__", "__INIT_DATA__", "__STORE__",
                    "rawData", "__PRELOADED_STATE__", "__APOLLO_STATE__", "__data", "pageData", "window._d",
                    "runParams",       // v74 STEP4: 알리익스프레스 상세 초기 상태(window.runParams = {data:{…}})
                    "_init_data_", "__AER_DATA__", "icRenderData", "_d_c_"];   // v76 STEP2: 알리 SSR 변형 전역(신 레이아웃 imagePathList/skuPropertyList 소재)

  // 문자열에서 index 위치의 { 또는 [ 부터 문자열-인지 균형 매칭으로 JSON 조각을 잘라낸다.
  function _sliceBalanced(s, from) {
    var open = s.charAt(from), close = open === "{" ? "}" : "]";
    if (open !== "{" && open !== "[") return null;
    var depth = 0, inStr = false, esc = false, q = "";
    for (var i = from; i < s.length; i++) {
      var c = s.charAt(i);
      if (inStr) {
        if (esc) esc = false; else if (c === "\\") esc = true; else if (c === q) inStr = false;
      } else {
        if (c === '"' || c === "'") { inStr = true; q = c; }
        else if (c === "{" || c === "[") depth++;
        else if (c === "}" || c === "]") { depth--; if (depth === 0) return s.slice(from, i + 1); }
      }
    }
    return null;
  }

  // ★핵심(v46 STEP3): 확장 content script는 **격리 월드**라 페이지의 live window.rawData를 못 읽는다.
  //   → 인라인 <script> **텍스트**에서 'window.rawData = {...}' 류 초기 상태 할당을 파싱(DOM 텍스트라
  //   격리월드에서도 접근 가능). 북마클릿(페이지월드)도 동일 코드로 동작.
  function _scriptStates() {
    var out = [];
    try {
      var ss = document.querySelectorAll("script:not([src])");
      for (var i = 0; i < ss.length && i < 60; i++) {
        var t = ss[i].textContent || "";
        if (t.length < 20 || t.length > 6000000) continue;
        for (var k = 0; k < STATE_KEYS.length; k++) {
          var key = STATE_KEYS[k];
          var pos = 0, guard = 0;
          while (guard++ < 5) {
            var idx = t.indexOf(key, pos);
            if (idx < 0) break;
            pos = idx + key.length;
            var eq = t.indexOf("=", idx);
            if (eq < 0 || eq - idx > key.length + 8) continue;   // '=' 가 키 바로 뒤여야(할당)
            var seg = t.slice(eq, eq + 300);
            var mb = /[{\[]/.exec(seg);
            if (!mb) continue;
            var raw = _sliceBalanced(t, eq + mb.index);
            if (raw) { try { var o = JSON.parse(raw); if (o && typeof o === "object") out.push(o); } catch (e) {} }
          }
        }
      }
    } catch (e) {}
    return out;
  }

  function _globalStates() {
    // 흔한 초기 상태 전역/스크립트(next/nuxt/redux/사이트 커스텀). 값이 객체면 후보로.
    var cands = [];
    // (0) ★Tier 1(v51/v54): kgp-net.js가 캡처·채점한 상품 API 응답 — 초기상태 전역이 없고 데이터가 API
    //     응답으로만 존재하는 사이트(테무)의 핵심. v54: 점수순 정렬(최고점=자가발견 채택). 채택 응답 URL을
    //     __kgpTier1Url 에 기록(sources=tier1:{URL패턴}). MAIN world에서만 채워짐(추가 요청 0).
    try {
      var cap = global.__kgpCaptured;
      // v62 STEP2: goods_id 페이지(테무 등)면 **내 goods_id 매칭 캡처만** 채택(이전 상품 응답 오채택 금지).
      var pgid = (typeof global.__kgpPageGoodsId === "function") ? global.__kgpPageGoodsId() : "";
      if (pgid) {
        var m = (typeof global.__kgpMatchCapture === "function") ? global.__kgpMatchCapture(pgid) : null;
        if (m && m.obj) {
          cands.push(m.obj);
          try { global.__kgpTier1Url = m.url || ""; global.__kgpTier1Score = m.score || 0; global.__kgpTier1Mismatch = false; } catch (e2) {}
        } else {
          // 내 goods_id 응답 미포착 → 다른 상품 캡처 채택 금지. Tier2(DOM) 폴백 신호.
          try { global.__kgpTier1Mismatch = true; global.__kgpTier1Url = ""; global.__kgpTier1Score = 0; } catch (e2) {}
        }
      } else if (cap && cap.length) {
        // goods_id 없는 사이트(비테무) → 기존 점수순 후보(오채택 위험 낮음).
        for (var c = 0; c < cap.length; c++) {
          var e = cap[c];
          var obj = (e && e.obj !== undefined) ? e.obj : e;   // v54 구조({obj,score,url}) / 구버전 호환
          if (obj && typeof obj === "object") cands.push(obj);
        }
        try { global.__kgpTier1Url = (cap[0] && cap[0].url) || ""; global.__kgpTier1Score = (cap[0] && cap[0].score) || 0; global.__kgpTier1Mismatch = false; } catch (e2) {}
      }
    } catch (e) {}
    // (1) live 전역 — 북마클릿(페이지월드)에서만 유효. 확장(격리월드)에선 대개 undefined.
    for (var i = 0; i < STATE_KEYS.length; i++) {
      try { var v = global[STATE_KEYS[i]]; if (v && typeof v === "object") cands.push(v); } catch (e) {}
    }
    // (2) <script id=__NEXT_DATA__ type=application/json> 등 인라인 JSON(DOM 텍스트).
    try {
      var ss = document.querySelectorAll('script[type="application/json"]');
      for (var k = 0; k < ss.length && k < 12; k++) {
        try { var o = JSON.parse(ss[k].textContent || ""); if (o && typeof o === "object") cands.push(o); } catch (e) {}
      }
    } catch (e) {}
    // (3) ★인라인 <script> 텍스트의 상태 할당(window.rawData=... 등) — 격리월드 대응 핵심.
    var st = _scriptStates();
    for (var j = 0; j < st.length; j++) cands.push(st[j]);
    return cands;
  }
  function _walk(root, visit, maxNodes) {
    var stack = [root], n = 0;
    var seen = typeof WeakSet !== "undefined" ? new WeakSet() : null;
    while (stack.length && n < (maxNodes || 20000)) {
      var cur = stack.pop(); n++;
      if (!cur || typeof cur !== "object") continue;
      if (seen) { if (seen.has(cur)) continue; seen.add(cur); }
      visit(cur);
      for (var key in cur) {
        try { var val = cur[key]; if (val && typeof val === "object") stack.push(val); } catch (e) {}
      }
    }
  }
  // v71 STEP2: sku 스펙 객체 매퍼 — [옵션명·값 텍스트·값 이미지]를 필드로 추출. Object 통짜 문자열화·URL 값 금지.
  var _OPT_AXIS_KEY = /(speckeyname|speckey|specname|propertyname|propname|attrname|attributename|optionname|dimensionname|keyname|attrkey|categoryname)/i;
  // v74 STEP4: 알리 sku 값 키(propertyValueDisplayName/valueDisplayName) 추가 — 옵션값 미수집(options=0) 봉인.
  var _OPT_VAL_KEY = /(specvaluename|specvalue|valuename|propvalue|propertyvalue|valuedisplayname|attrvalue|optionvalue|valuetext|^value$|^val$)/i;
  var _OPT_VIMG_KEY = /(image|img|thumb|thumburl|hdthumburl|pic|photo)/i;
  // v76 STEP2: sku/옵션 스와치 썸네일 키 — 갤러리(대표 이미지) 오염 금지. 값→이미지는 option_image로만 귀속.
  var _OPT_SWATCH_KEY = /(skuproperty.*(image|img|pic)|property.*(image|img|pic)|swatch|coloroption|optionimage|variationimage|variantimage|skuimage)/i;
  function _optClean(s) { s = String(s == null ? "" : s).replace(/\s+/g, " ").trim(); return s.length <= 40 ? s : ""; }
  // v79 STEP3: 옵션 값 화이트리스트 — 옵션이 아닌 오염값 배제(전 마켓 공통). 화살표·캐러셀 내비 글리프,
  //   미디어 탭명(Product Image/Video·이미지·동영상), 순수 품번(5자리+ 숫자, 예 '900037')은 옵션 값이 아니다.
  //   사이즈(2~4자리 숫자·단위)는 보존(≤4자리·문자 포함). 라쿠텐 스펙 뭉침·아마존 캐러셀 컨트롤 박멸.
  function _isBadOptValue(v) {
    v = String(v == null ? "" : v).trim();
    if (!v) return true;
    if (/^[<>‹›«»←-⇿◀-◿⟨⟩⬅⬆⬇➡]+$/.test(v)) return true;   // 화살표·내비 글리프
    if (/^(product\s*)?(image|video|photo|이미지|동영상|사진|썸네일|thumbnail)s?$/i.test(v)) return true;                        // 미디어 탭명
    if (/roll ?over image|click to (zoom|enlarge|open)|zoom in/i.test(v)) return true;                                          // 미디어 안내 문구
    if (/^\d{5,}$/.test(v)) return true;                                                                                        // 순수 품번(5자리+)
    if (/^\d$/.test(v)) return true;                                                                                             // v82 STEP1: 단독 한 자리 숫자('1' — 아마존 색상옵션 오수집). 사이즈(2자리+·단위)는 보존.
    return false;
  }
  // v83 STEP3: 색상류 축의 **순수 숫자 값**은 옵션이 아니다(아마존 B0CF88RN17 색상 '1' 재현). v82 STEP1은 한
  //   자리 숫자만 막아 '01'·'12' 같은 변형이 남았고, tier2(트위터스터·스와치) 경로에도 축 단위 방어가 없었다.
  //   사이즈·수량 축의 숫자 값(38·XL 등)은 보존 — **색상류 축에서만** 적용한다.
  var _COLOR_AXIS_RE = /^(색상|색깔|컬러|color|colour|カラー|色|颜色)$/i;
  function _dropNumericColorValues(options) {
    var out = [];
    (options || []).forEach(function (o) {
      if (!o || !o.values) return;
      var vals = o.values;
      if (_COLOR_AXIS_RE.test(String(o.name || "").trim())) {
        vals = vals.filter(function (v) { return !/^\d{1,4}$/.test(String(v).trim()); });   // 순수 숫자 단독값 제외
      }
      if (!vals.length) return;
      var copy = { name: o.name, values: vals };
      if (o.option_image) copy.option_image = o.option_image;
      out.push(copy);
    });
    return out;
  }
  // v82 STEP1: 폴백 전치(_skusToOptions ②, 축명 소실) 경로 전용 값 필터. 정상 경로는 _isBadOptAxis(축명)로
  //   원산지·제조사를 막지만, 라쿠텐 스펙테이블이 축명 없이 sku spec로 전염되면 폴백에서 '옵션' 값으로 부활한다.
  //   원산지 국가명(タイ 등)·법인 접미(コーポレーション·株式会社·Corp/Inc/Ltd — アーガスコーポレーション)는 옵션 값이 아니다.
  function _isBadOptFallbackValue(v) {
    v = String(v == null ? "" : v).trim();
    if (!v) return true;
    if (/^(日本|中国|中國|韓国|韓國|台湾|臺灣|タイ|ベトナム|インド|アメリカ|ドイツ|イタリア|フランス|イギリス|スペイン|インドネシア|マレーシア|バングラデシュ|ミャンマー|カンボジア|フィリピン|パキスタン)$/.test(v)) return true;  // 원산지 국가명
    if (/(コーポレーション|株式会社|有限会社|corporation|co\.,?\s?ltd|,?\s?inc\.?$|,?\s?ltd\.?$|商事|製作所|工業|industries?)/i.test(v)) return true;  // 법인 접미(제조사명)
    return false;
  }
  // v80 STEP4: 옵션 축(이름) 화이트리스트 — 원산지·브랜드·제조사·품번·모델·JAN 등 **스펙 속성**은 사용자
  //   선택 옵션이 아니다(공통축). sku diff가 2값 이상이어도(예 原産地: 日本/タイ) 옵션 아님 → 축명으로 봉인.
  //   색상·사이즈·컬러·color·size 등 진짜 옵션 축은 보존(안전 화이트리스트 밖).
  function _isBadOptAxis(name) {
    var n = String(name == null ? "" : name).replace(/\s+/g, "").toLowerCase();
    if (!n) return false;
    return /(원산지|원산국|생산지|産地|原産|madein|countryoforigin|^origin$|브랜드|ブランド|^brand$|메이커|メーカー|^maker$|제조사|제조원|제조국|메이드|manufacturer|품번|품목번호|형번|品番|型番|모델명|모델번호|modelnumber|modelname|^jan$|^asin$|^upc$|^ean$|바코드|barcode|보증기간|warranty)/i.test(n);
  }
  // v78 STEP1: 키 정규화 — 구분자(_·-·공백) 제거 후 매칭. 실기기 테무 sku가 underscore 키(spec_key·spec_value)를
  //   쓰면 speckey/specvalue 패턴에 안 걸려 옵션 0이 되던 근원(skus>0·options=0). 정규화로 봉인.
  function _normKey(k) { return String(k == null ? "" : k).replace(/[_\-\s]/g, ""); }
  function _pickStrField(o, re, exclude) {
    for (var k in o) { if (exclude && k === exclude) continue; try { if (re.test(_normKey(k)) && typeof o[k] === "string" && o[k].trim()) return { k: k, v: o[k] }; } catch (e) {} }
    return null;
  }
  function _pickUrlField(o, re) {
    for (var k in o) { try { if (re.test(_normKey(k)) && typeof o[k] === "string" && /^https?:\/\//i.test(o[k])) return o[k]; } catch (e) {} }
    return "";
  }
  // sku 객체 → axisMap 갱신(축→값·값이미지) + 이 sku의 값 텍스트 배열 반환(값별 가격 매핑용).
  function _collectSkuSpecs(so, axisMap, SPEC_KEY) {
    var out = [];
    function add(axis, val, img) {
      axis = _optClean(axis); val = _optClean(val);
      if (!axis || !val || /^https?:\/\//i.test(val) || val === "[object Object]") return;   // URL·Object 문자열화 금지
      if (_isBadOptAxis(axis)) return;   // v80 STEP4: 원산지·브랜드·품번 등 스펙 축 배제(공통축 옵션화 금지)
      if (_isBadOptValue(val)) return;   // v79 STEP3: 화살표·미디어탭·품번 배제(옵션 값 화이트리스트)
      var a = axisMap[axis] || (axisMap[axis] = { order: [], set: {}, images: {} });
      if (!a.set[val]) { a.set[val] = 1; a.order.push(val); }
      if (img && /^https?:\/\//i.test(img) && !a.images[val]) a.images[val] = hiRes(img);
      out.push(val);
    }
    // 평면 sku: 축명·값명 필드가 sku 객체에 직접.
    var fnm = _pickStrField(so, _OPT_AXIS_KEY, null);
    var fvl = _pickStrField(so, _OPT_VAL_KEY, fnm ? fnm.k : null);
    if (fnm && fvl) add(fnm.v, fvl.v, _pickUrlField(so, _OPT_VIMG_KEY));
    // v74 STEP4: 알리식 축(부모=skuPropertyName) + 중첩 값(자식=propertyValueDisplayName) — 자식이 축명을
    //   안 들고 값만 있을 때 **부모 축명**을 물려줘 '옵션' 뭉뚱그림 대신 'Color/Size'로 귀속.
    var parentAxis = fnm ? fnm.v : "";
    // 중첩 스펙 컨테이너(배열/객체).
    for (var sk in so) {
      if (!SPEC_KEY.test(sk)) continue;
      var sv;
      try { sv = so[sk]; } catch (e) { continue; }
      if (Array.isArray(sv)) {
        for (var i = 0; i < sv.length && i < 60; i++) {
          var e2 = sv[i];
          if (e2 && typeof e2 === "object" && !Array.isArray(e2)) {
            var nm = _pickStrField(e2, _OPT_AXIS_KEY, null);
            var vl = _pickStrField(e2, _OPT_VAL_KEY, nm ? nm.k : null);
            var axisName = (nm && nm.v) || parentAxis || "옵션";
            if (vl) add(axisName, vl.v, _pickUrlField(e2, _OPT_VIMG_KEY));
            // 값 텍스트 필드 못 찾으면 스킵(Object 문자열화 방지 — 정직 미수집).
          } else if (typeof e2 === "string") add(parentAxis || "옵션", e2, "");
        }
      } else if (sv && typeof sv === "object") {
        for (var k2 in sv) { try { if (typeof sv[k2] === "string") add(k2, sv[k2], ""); } catch (e) {} }
      }
      // sv가 string이면 무시(평면 축명/값명 오분류 방지 — 위 평면 경로에서 처리).
    }
    return out;
  }
  function _fromJson() {
    var res = { title: "", price: "", currency: "", currencySrc: "", images: [], detailImages: [], specs: [],
                options: [], skus: [], reviews: [], rating: "", reviewCount: "", description: "", ok: false };
    var imgSeen = {}, detSeen = {};
    // JSON-LD Product 우선(표준·신뢰)
    var lds = _jsonLd();
    for (var i = 0; i < lds.length; i++) {
      var arr = Array.isArray(lds[i]) ? lds[i] : (lds[i]["@graph"] || [lds[i]]);
      for (var a = 0; a < arr.length; a++) {
        var p = arr[a]; if (!p || typeof p !== "object") continue;
        var t = p["@type"]; if (t && String(t).toLowerCase().indexOf("product") < 0) continue;
        if (p.name && !res.title) res.title = String(p.name).slice(0, 300);
        if (p.description && !res.description) res.description = String(p.description);
        var imgs = p.image || (p.offers && p.offers.image);
        if (imgs) [].concat(imgs).forEach(function (u) { if (isProductImg(u)) uniqPush(res.images, imgSeen, hiRes(u)); });
        var off = p.offers ? [].concat(p.offers) : [];
        for (var o = 0; o < off.length; o++) {
          var of = off[o]; if (!of) continue;
          if (of.price && !res.price) {
            res.price = String(of.price).replace(/,/g, "");
            res.currency = String(of.priceCurrency || "").toUpperCase();
            // v83 STEP1: priceCurrency는 **명시 통화 필드**(tier1) — 사다리 최상단. 기호 파생과 구분해 표기.
            if (res.currency) res.currencySrc = "tier1";
          }
        }
        var agg = p.aggregateRating;
        if (agg) { res.rating = String(agg.ratingValue || ""); res.reviewCount = String(agg.reviewCount || agg.ratingCount || ""); }
        var rv = p.review ? [].concat(p.review) : [];
        for (var r = 0; r < rv.length && res.reviews.length < REVIEW_MAX; r++) {
          var one = rv[r]; if (!one) continue;
          res.reviews.push({
            author: (one.author && (one.author.name || one.author)) || "",
            rating: (one.reviewRating && one.reviewRating.ratingValue) || "",
            text: String(one.reviewBody || one.description || "").slice(0, 500)
          });
        }
        res.ok = res.ok || !!(res.price || res.images.length);
      }
    }
    // 전역/스크립트 상태 딥워크(스키마 무관·키 이름 휴리스틱) — JSON-LD로 못 채운 것 보강.
    var IMG_KEY = /(image|img|pic|photo|thumb|gallery|carousel|album)/i;
    // v57 STEP3: 테무 상세이미지 키 보강(decoration/bottom/richtext/longimage 등 접힘 상세도 detail로 라우팅).
    var DET_KEY = /(detail|desc|content|decoration|bottomimage|richtext|longimage|goodsdesc)/i;
    var SKU_KEY = /(sku|variant|goodsspec|specsku|skulist|productlist)/i;
    var SPEC_KEY = /(spec|attr|prop|option|variation)/i;
    var PRICE_KEY = /(price|amount|sale|deal|salePrice|normalPrice)/i;
    var PRICE_BAD = /(count|qty|num|origin|list|regular|market|before|min|max|unit|discount|off|save)/i;
    var RATE_KEY = /(avgrating|averagerating|ratingvalue|goodsscore|starscore|score|rating)$/i;
    var CNT_KEY = /(reviewcount|reviewnum|commentcount|reviewtotal|totalreview|ratingcount)/i;

    function pushImgs(arr, dest, seen) {
      for (var i = 0; i < arr.length && dest.length < 40; i++) {
        var u = arr[i];
        if (typeof u === "object" && u) u = u.url || u.src || u.imageUrl || u.thumbUrl || u.image || "";
        if (typeof u === "string" && /^https?:\/\//.test(u) && isProductImg(u)) uniqPush(dest, seen, hiRes(u));
      }
    }
    // 숫자 가격의 센트/소단위 환산: 통화가 소단위(USD/EUR/GBP…) + 정수 + 큰 값이면 ÷100.
    function priceFromNum(n, cur) {
      var v = Number(n);
      if (!(v > 0)) return "";
      var CENTS = { USD: 1, EUR: 1, GBP: 1, CNY: 1, AUD: 1, CAD: 1 };  // 소단위 있는 통화
      if (cur && CENTS[cur] && v === Math.floor(v) && v >= 1000) return String(v / 100);
      return String(v);
    }
    function skuPrice(o) {
      for (var k in o) {
        try {
          if (PRICE_KEY.test(k) && !PRICE_BAD.test(k)) {
            var pv = o[k];
            // v83 STEP1: csrc = 통화 근거(symbol=표시 기호 파생 / tier1=명시 통화 필드). 사다리 순위 판정용.
            if (typeof pv === "string") { var pp = parsePriceStr(pv); if (pp) return { price: pp.price, currency: pp.currency, csrc: pp.currency ? "symbol" : "" }; }
            else if (typeof pv === "number") {
              var _curField = String(o.currency || o.currencyCode || o.priceCurrency || "").toUpperCase();
              var cur = _curField || String(res.currency || "").toUpperCase();
              var val = priceFromNum(pv, cur); if (val) return { price: val, currency: cur, csrc: _curField ? "tier1" : (cur ? (res.currencySrc || "") : "") };
            }
          }
        } catch (e) {}
      }
      return null;
    }
    var _skuPriceSet = false;
    var axisMap = {};               // v71 STEP2: sku 스펙 축 → {order,set,images} (Object 문자열화 방지)
    var states = _globalStates();   // live 전역 + 인라인 <script> 텍스트 상태(격리월드 대응)
    for (var s = 0; s < states.length; s++) {
      _walk(states[s], function (node) {
        for (var key in node) {
          try {
            var kv = String(key).toLowerCase(), v = node[key];
            // v76 STEP2: sku/옵션 스와치 썸네일은 갤러리 라우팅 제외(대표 이미지 오염 방지 — option_image로만).
            var _swatch = _OPT_SWATCH_KEY.test(kv);
            // (1) 이미지 배열(배열 키가 이미지류)
            if (Array.isArray(v) && IMG_KEY.test(kv) && !_swatch) {
              pushImgs(v, DET_KEY.test(kv) ? res.detailImages : res.images, DET_KEY.test(kv) ? detSeen : imgSeen);
            }
            // (2) 단일 이미지 url
            else if (typeof v === "string" && /^https?:\/\//.test(v) && IMG_KEY.test(kv) && isProductImg(v) && !_swatch) {
              uniqPush(DET_KEY.test(kv) ? res.detailImages : res.images, DET_KEY.test(kv) ? detSeen : imgSeen, hiRes(v));
            }
            // (3) SKU 배열 → 옵션·sku별 가격, 메인 가격(첫 유효 sku)
            else if (Array.isArray(v) && SKU_KEY.test(kv) && v.length && typeof v[0] === "object") {
              for (var i = 0; i < v.length && i < 200; i++) {
                var so = v[i]; if (!so || typeof so !== "object") continue;
                var sp = skuPrice(so);
                // v71 STEP2: 스펙 객체 → 축명·값텍스트·값이미지 구조 추출(Object 문자열화·URL 값 금지).
                var skuVals = _collectSkuSpecs(so, axisMap, SPEC_KEY);
                res.skus.push({ spec: skuVals, price: sp ? sp.price : "", currency: sp ? sp.currency : "" });
                if (sp && !_skuPriceSet) { res.price = sp.price; res.currency = sp.currency; res.currencySrc = sp.csrc || (sp.currency ? "symbol" : ""); _skuPriceSet = true; }
              }
            }
            // (4) 평점·리뷰수
            else if (RATE_KEY.test(kv) && !res.rating && (typeof v === "string" || typeof v === "number")) {
              // v78 STEP2: 더미 평점(0·1 — score:1 등 오채택) 방어 — (1,5]만 채택(뒤의 실 평점이 이기게).
              var rn = parseFloat(v); if (rn > 1 && rn <= 5) res.rating = String(v);
            }
            else if (CNT_KEY.test(kv) && !res.reviewCount && (typeof v === "string" || typeof v === "number")) {
              res.reviewCount = String(v);
            }
            // (5) 제목·설명
            else if (!res.title && /(^title$|goodsname|productname|itemname|^name$)/i.test(kv) && typeof v === "string" && v.length > 2) {
              res.title = v.slice(0, 300);
            }
            else if (!res.description && /(description|detailtext|goodsdesc|productdesc)/i.test(kv) && typeof v === "string" && v.length > 20) {
              res.description = v.slice(0, 4000);
            }
          } catch (e) {}
        }
        // (6) 가격: sku에서 못 얻었으면 표시 문자열(통화기호 포함) 우선.
        if (!res.price) {
          for (var k2 in node) {
            try {
              if (PRICE_KEY.test(k2) && !PRICE_BAD.test(k2)) {
                var pv2 = node[k2];
                if (typeof pv2 === "string") { var pp2 = parsePriceStr(pv2); if (pp2 && pp2.currency) { res.price = pp2.price; res.currency = pp2.currency; res.currencySrc = "symbol"; break; } }
              }
            } catch (e) {}
          }
        }
        // (7) 리뷰 텍스트(초기 JSON에 실린 것만) — 길이 완화.
        if (res.reviews.length < REVIEW_MAX) {
          try {
            var body = node.reviewBody || node.comment || node.content || node.text;
            var hasRating = node.rating != null || node.star != null || node.score != null;
            if (typeof body === "string" && body.length >= 2 && (hasRating || node.reviewId || node.commentId || node.reviewer)) {
              res.reviews.push({ author: node.author || node.userName || node.nickname || node.reviewer || "",
                                 rating: node.rating || node.star || node.score || "",
                                 text: String(body).slice(0, 500) });
            }
          } catch (e) {}
        }
      }, 30000);
    }
    // v79 STEP2: sku 정제 — 빈 항목(spec 없고 price 없음) 제거 + 동일 spec 중복 dedupe.
    //   _walk가 같은 sku 배열을 여러 상태에서 재방문해 2~3배 반복(테무·라쿠텐 확정). 동일 spec 서명은
    //   하나만 남기되, 무가격보다 유가격을 우선(정보 우위). 옵션(axisMap 파생)은 이미 dedup이라 무영향.
    (function () {
      var idx = {}, clean = [];
      for (var _si = 0; _si < res.skus.length; _si++) {
        var _sk = res.skus[_si] || {};
        var _spec = _sk.spec || [];
        var _price = _sk.price || "";
        if (!_spec.length && !_price) continue;                     // 빈 sku 제거(정직)
        var _key = _spec.slice().sort().join("");             // spec 값 집합 서명
        if (Object.prototype.hasOwnProperty.call(idx, _key)) {
          var _prev = clean[idx[_key]];                             // 동일 spec 재등장 = 중복
          if (!_prev.price && _price) clean[idx[_key]] = _sk;       // 무가격→유가격 교체
          continue;
        }
        idx[_key] = clean.length; clean.push(_sk);
      }
      res.skus = clean;
    })();
    // v71 STEP2 / v78 STEP1: 옵션 = sku 스펙 축별(색상·사이즈…) — 단일 변환. 값은 텍스트, 값 이미지는 option_image 분리.
    res.options = _skusToOptions(axisMap, res.skus);
    res.ok = !!(res.price || res.images.length || res.title);
    return res;
  }
  // v78 STEP1: sku→옵션 단일 변환 함수(하네스·확장 경로 통일). 계약: skus에 스펙 변형이 있으면 options>0.
  //   ① axisMap(이름 있는 축, 값 2+) 우선. ② 이름 축이 0인데 skus에 spec 값이 있으면 위치별 전치(fragmented
  //   축명 대비)로 '옵션'/'옵션2' 축 복원. 스펙 변형이 전혀 없으면 옵션 0(정직 — 날조 금지).
  function _skusToOptions(axisMap, skus) {
    var out = [];
    Object.keys(axisMap || {}).forEach(function (axis) {
      var a = axisMap[axis];
      if (a && a.order.length >= 2) {
        var opt = { name: axis, values: a.order.slice(0, 100) };
        if (Object.keys(a.images).length) opt.option_image = a.images;
        out.push(opt);
      }
    });
    if (out.length) return out;
    // ② 폴백: 이름 축 0 → skus[].spec를 위치별 전치. (예: 각 sku가 [색상값] 또는 [색상값,사이즈값])
    var maxLen = 0, hasSpec = false;
    (skus || []).forEach(function (s) { var sp = (s && s.spec) || []; if (sp.length) hasSpec = true; if (sp.length > maxLen) maxLen = sp.length; });
    if (!hasSpec) return out;   // 스펙 변형 없음 → 옵션 0(정직)
    for (var p = 0; p < maxLen && p < 4; p++) {
      var order = [], set = {};
      (skus || []).forEach(function (s) {
        var v = s && s.spec && s.spec[p];
        v = _optClean(v);
        // v82 STEP1: 폴백은 축명이 없어 _isBadOptAxis 방어를 못 받는다 → 값 단위로 오염(품번·화살표·원산지·제조사) 배제.
        if (v && !_isBadOptValue(v) && !_isBadOptFallbackValue(v) && !set[v]) { set[v] = 1; order.push(v); }
      });
      if (order.length >= 1) out.push({ name: maxLen > 1 ? ("옵션" + (p + 1)) : "옵션", values: order.slice(0, 100) });
    }
    return out;
  }

  // ── ② DOM 폴백 ────────────────────────────────────────────
  function _meta(prop) {
    var el = document.querySelector('meta[property="' + prop + '"],meta[name="' + prop + '"]');
    return el ? (el.getAttribute("content") || "") : "";
  }
  function _nonProdRegion(el) {
    // v70 STEP1: 아마존 광고·추천 위젯(정가 32.99 오채택 근원) 패턴 추가 — sims/multi-brand/video/sp_detail.
    var re = /(recommend|related|similar|also[-_ ]?bought|sponsored|advert|ranking|carousel|cross[-_ ]?sell|up[-_ ]?sell|footer|navbar|breadcrumb|review|comment|qna|feedback|seller|merchant|store[-_ ]?info|vendor|brand[-_ ]?header|sims|multi[-_ ]?brand|video|sp[-_]detail|octopus)/i;
    var cur = el && el.parentElement, d = 0;
    while (cur && d < 8) {
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && re.test(tok)) return true;
      cur = cur.parentElement; d++;
    }
    return false;
  }
  function _priceOriginal(el) {
    var re = /(original|was[-_ ]?price|strike|line[-_]?through|regular|list[-_]?price|old[-_]?price|compare[-_]?at|정가|원가|할인전)/i;
    var cur = el, d = 0;
    while (cur && d < 4) {
      var tag = (cur.tagName || "").toLowerCase();
      if (tag === "del" || tag === "s" || tag === "strike") return true;
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && re.test(tok)) return true;
      try { if ((getComputedStyle(cur).textDecorationLine || "").indexOf("line-through") >= 0) return true; } catch (e) {}
      cur = cur.parentElement; d++;
    }
    return false;
  }
  function _nonPriceCtx(el) {
    var cur = el, d = 0;
    while (cur && d < 4) {
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && NONPRICE.test(tok)) return true;
      cur = cur.parentElement; d++;
    }
    return NONPRICE.test((el.textContent || "").slice(0, 40));
  }
  function _nodePath(el) {
    var parts = [], cur = el, n = 0;
    while (cur && n < 4) {
      var t = (cur.tagName || "").toLowerCase();
      var c = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || ""));
      parts.unshift(t + (c ? "." + String(c).trim().split(/\s+/).slice(0, 2).join(".") : ""));
      cur = cur.parentElement; n++;
    }
    return parts.join(" > ");
  }
  // v66 STEP2: 컨테이너 합성 텍스트 가격 — 테무 등은 통화·숫자를 여러 span으로 분절(₩|1|,|899)해
  //   노드 단위 매칭이 실패한다. content·data-price·aria-label 속성 + textContent를 **공백·개행 제거로
  //   조립**해 통화 패턴 매칭. 취소선 제외(_priceOriginal)는 컨테이너 단위 유지. 통화 미감지 시 빈 통화(추정 금지).
  function _composedPrice(el) {
    var cands = [
      el.getAttribute && el.getAttribute("content"),
      el.getAttribute && el.getAttribute("data-price"),
      el.getAttribute && el.getAttribute("aria-label"),
      (el.textContent || "").replace(/\s+/g, ""),   // span 분절 조립(공백·개행 제거)
    ];
    for (var i = 0; i < cands.length; i++) {
      var p = parsePriceStr(cands[i]);
      if (p && p.price) return p;
    }
    return null;
  }
  function _clsId(el) {
    return ((el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || "")) + " " + (el.id || ""));
  }
  // v70 STEP1: 아마존 정가(a-text-price) 배제 — 광고 위젯의 정가 32.99가 실판매가 29.99를 이기던 근원.
  function _isListPriceNode(el) { return /a-text-price/i.test(_clsId(el)); }
  // v70 STEP1: 어댑터 buybox 스코프 최우선 — 아마존 현재가 컨테이너(#apex_desktop·corePrice·priceToPay)에서만
  //   현재가를 읽는다. 스코프 안이라도 정가(a-text-price)·취소선은 배제. 스코프 성공 시 전역 휴리스틱·폰트크기 불요.
  function _buyboxPrice() {
    var scopeSel = "#apex_desktop,#corePrice_desktop,#corePriceDisplay_desktop_feature_div,#corePrice_feature_div,#corePriceDisplay_mobile_feature_div,#buybox,#price_inside_buybox,#priceblock_ourprice,#newAccordionRow,#qualifiedBuybox";
    var priceSel = ".priceToPay,.apexPriceToPay,[data-testid*=\"priceToPay\" i],span[data-a-color=\"price\"] .a-offscreen,.a-price:not(.a-text-price)";
    var scopes;
    try { scopes = document.querySelectorAll(scopeSel); } catch (e) { return null; }
    for (var s = 0; s < scopes.length; s++) {
      var sc = scopes[s];
      if (_nonProdRegion(sc)) continue;
      var pn;
      try { pn = sc.querySelectorAll(priceSel); } catch (e) { continue; }
      for (var i = 0; i < pn.length; i++) {
        var el = pn[i];
        if (_isListPriceNode(el) || _priceOriginal(el) || _nonPriceCtx(el)) continue;
        var p = _composedPrice(el); if (!p || !p.price) continue;
        var path = _nodePath(el);
        try { console.log("[고가수집기] (buybox)가격 채택: " + p.price + " " + p.currency + " [" + path + "]"); } catch (e) {}
        return { price: p.price, currency: p.currency, val: parseFloat(p.price) || 0, fs: 0, path: path, scope: true, src: "buybox" };
      }
    }
    return null;
  }
  function _domPrice() {
    // v70 STEP1: buybox 스코프 최우선 → 실패 시에만 전역 휴리스틱(폰트크기는 동률 보조로 강등).
    var bx = _buyboxPrice();
    if (bx) return bx;
    var nodes = [];
    try {
      nodes = Array.prototype.slice.call(document.querySelectorAll('[class*="price" i],[class*="Price"],[itemprop="price"],[data-price],[class*="amount" i],[aria-label*="price" i]'));
    } catch (e) { nodes = []; }
    var cands = [];
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (_nonProdRegion(el) || _priceOriginal(el) || _nonPriceCtx(el)) continue;
      if (_isListPriceNode(el)) continue;   // v70: 아마존 정가(a-text-price) 배제
      var p = _composedPrice(el); if (!p) continue;
      var fs = 0; try { fs = parseFloat(getComputedStyle(el).fontSize) || 0; } catch (e) {}
      cands.push({ price: p.price, currency: p.currency, val: parseFloat(p.price) || 0, fs: fs, ord: i, path: _nodePath(el), src: "dom" });
    }
    // v70 STEP1: 폰트크기 강등 — 문서 순서(현재가는 buybox라 상단) 우선, 폰트는 동률 보조.
    cands.sort(function (a, b) { return (a.ord - b.ord) || (b.fs - a.fs); });
    try {
      console.log("[고가수집기] (DOM)가격 후보(" + cands.length + "):",
        cands.slice(0, 6).map(function (c) { return c.price + " " + c.currency + " @" + c.fs + "px [" + c.path + "]"; }));
    } catch (e) {}
    return cands[0] || null;
  }
  // v51 Tier2: 갤러리 스코프 전용 제외(추천/연관/함께구매만 — 캐러셀/스와이퍼는 '갤러리 그 자체'라 제외 안 함).
  function _galleryExcluded(el) {
    var re = /(recommend|related|similar|also[-_ ]?bought|you[-_ ]?may|sponsored|advert|ranking|cross[-_ ]?sell|up[-_ ]?sell|footer|comment|qna|review[-_ ]?list)/i;
    var cur = el && el.parentElement, d = 0;
    while (cur && d < 10) {
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && re.test(tok)) return true;
      cur = cur.parentElement; d++;
    }
    return false;
  }
  // 이미지 요소의 최고해상도 후보(currentSrc·data-*·srcset 최대). naturalWidth 필터 미사용(URL·컨테이너로 판별).
  //   v57 STEP4: 롤오버/줌 data-* 변형(data-zoom-image·data-large·data-image-large·data-hires 등) 우선(고해상).
  function _bestImgSrc(im) {
    var src = im.getAttribute("data-zoom-image") || im.getAttribute("data-large") || im.getAttribute("data-large-image")
      || im.getAttribute("data-image-large") || im.getAttribute("data-hires") || im.getAttribute("data-old-hires")
      || im.getAttribute("data-zoom") || im.currentSrc || im.getAttribute("data-src")
      || im.getAttribute("data-original") || im.getAttribute("data-lazy") || im.getAttribute("data-image")
      || im.getAttribute("data-srcset") || im.src || "";
    try {
      // srcset(또는 data-srcset)에서 최대 해상도 후보 — data-*로 못 얻었을 때만 덮어씀.
      var ss = im.srcset || im.getAttribute("data-srcset") || "";
      if (ss && (!src || src === im.src)) {
        var best = "", bw = -1;
        ss.split(",").forEach(function (part) {
          var seg = part.trim().split(/\s+/); var u = seg[0];
          var w = seg[1] ? parseInt(seg[1], 10) || 0 : 0;
          if (u && w >= bw) { bw = w; best = u; }
        });
        if (best) src = best;
      }
    } catch (e) {}
    return src;
  }
  // v57 STEP4: 인라인 background-image:url(...) 스타일에서 이미지 URL 추출(div/ a 기반 갤러리 대응).
  function _bgImage(el) {
    try {
      var st = (el.getAttribute && el.getAttribute("style")) || "";
      var m = st.match(/background(?:-image)?\s*:\s*url\((['"]?)([^'")]+)\1\)/i);
      if (m && m[2]) return m[2].trim();
    } catch (e) {}
    return "";
  }
  // v70 STEP3: 아마존 갤러리 hi-res 승격 — data-a-dynamic-image(url→[w,h] JSON)에서 최대 해상도 URL.
  function _amazonDynMax(im) {
    try {
      var j = im.getAttribute && im.getAttribute("data-a-dynamic-image");
      if (!j) return "";
      var map = JSON.parse(j), best = "", ba = -1;
      for (var k in map) { if (!map.hasOwnProperty(k)) continue; var d = map[k] || []; var a = (d[0] || 0) * (d[1] || 0); if (a > ba) { ba = a; best = k; } }
      return best;
    } catch (e) { return ""; }
  }
  // v70 STEP3: 아마존 갤러리 스코프 — #altImages(썸네일 스트립) + #imgTagWrapper(메인)만. 관련상품·스프라이트·1px 배제,
  //   hiRes/data-old-hires/data-a-dynamic-image 고해상 승격. 브로드 제네릭 갤러리(추천 캐러셀 혼입=58장 근원)는 건너뜀.
  function _amazonGallery() {
    var out = [], seen = {};
    var aSel = "#altImages img, #imgTagWrapperId img, #imgTagWrapper img, #main-image-container img, #imageBlock img, #ivLargeImage img, #landingImage";
    try {
      var els = document.querySelectorAll(aSel);
      for (var i = 0; i < els.length; i++) {
        var im = els[i];
        if (_galleryExcluded(im)) continue;
        var src = _amazonDynMax(im) || _bestImgSrc(im);   // 고해상 우선
        if (!src) continue;
        // 로드된 실측 크기만으로 1px·초소형 아이콘 배제(깨진/미로드 이미지의 layout width=16 오판 방지 —
        //   미로드는 파일명 기반 NONPROD_IMG(sprite/icon)로 걸러짐).
        var nw = im.naturalWidth || 0, nh = im.naturalHeight || 0;
        if ((nw && nw < 40) || (nh && nh < 40)) continue;
        if (isProductImg(src)) uniqPush(out, seen, hiRes(src));
      }
    } catch (e) {}
    return out;
  }
  // v76 STEP3: 라쿠텐(楽天市場) 상세 어댑터 — 갤러리 1→전량. 초기 JSON이 가격+대표1장만 주면 needDom이 false라
  //   제네릭 DOM 갤러리가 안 돌아 '갤러리1'에 그친다. 호스트별로 독립 수집: 갤러리 컨테이너 + 라쿠텐 CDN(r10s.jp·
  //   image.rakuten.co.jp) 이미지 전량(추천/리뷰/상세 영역 제외) + 상세 본문(텍스트·이미지) 별도 버킷.
  var _RAKUTEN_CDN = /(^|\/\/|\.)(r10s\.jp|image\.rakuten\.co\.jp|thumbnail\.image\.rakuten\.co\.jp|r\.r10s\.jp)/i;
  function _inRakutenDetail(el) {
    var re = /(item[-_]?detail|item[-_]?desc|itemdesc|sale[-_]?desc|description|spec|レビュー|商品説明)/i;
    var cur = el, d = 0;
    while (cur && d < 8) {
      var tok = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || "")) + " " + (cur.id || "");
      if (tok && re.test(tok)) return true;
      cur = cur.parentElement; d++;
    }
    return false;
  }
  // v80 STEP3: 라쿠텐 이미지 URL의 디렉토리(파일명 제거) — 현 상품 폴더 스코프 키. 쿼리 제거 후 마지막 / 이후 절삭.
  function _rakutenFolder(u) { return String(u == null ? "" : u).split("?")[0].split("#")[0].replace(/\/[^\/]*$/, ""); }
  function _rakutenGallery() {
    var out = [], seen = {}, det = [], detSeen = {};
    // (a) 상세 본문 이미지 먼저(별도 버킷) — 갤러리 CDN 스윕에서 이 영역을 제외하기 위해 URL 마킹.
    var dSel = '[class*="item-detail" i] img,[id*="item_desc" i] img,[class*="itemDesc" i] img,'
      + '[class*="sale_desc" i] img,[class*="description" i] img,[id*="ratRanking" i] img';
    try {
      var dels = document.querySelectorAll(dSel);
      for (var d = 0; d < dels.length; d++) {
        var dm = dels[d]; if (_nonProdRegion(dm) || _galleryExcluded(dm)) continue;
        var ds = _bestImgSrc(dm); if (isProductImg(ds)) uniqPush(det, detSeen, hiRes(ds));
      }
    } catch (e) {}
    // (b) 갤러리 컨테이너 스코프(있으면 우선).
    var gSel = '[class*="image-gallery" i] img,[class*="ImageMain" i] img,[class*="ImageThumb" i] img,'
      + '[class*="item-image" i] img,[class*="itemImage" i] img,[id*="ImageBody" i] img,'
      + '[class*="sliderMain" i] img,[class*="thumbnail" i] img';
    try {
      var gels = document.querySelectorAll(gSel);
      for (var i = 0; i < gels.length; i++) {
        var im = gels[i]; if (_galleryExcluded(im) || _inRakutenDetail(im)) continue;
        var s = _bestImgSrc(im); if (isProductImg(s)) uniqPush(out, seen, hiRes(s));
      }
    } catch (e) {}
    // v80 STEP3: 현 상품 폴더 스코프 — 컨테이너(b, 현 상품) 이미지 + og:image(대표)의 **디렉토리**를 유효 폴더셋으로
    //   삼아, (c) CDN 스윕에서 그 폴더 밖(같은 shop의 타상품 추천 folder)을 제외. di가 상세영역 DOM 스코프로 깨끗한
    //   것과 동형(폴더 기준). 폴더셋이 비면 스코프 미적용(shop-slug 필터 v79 STEP4가 교차-shop만 커버).
    var folderSet = {};
    out.forEach(function (u) { var f = _rakutenFolder(u); if (f) folderSet[f] = 1; });
    try { var _og = _meta("og:image") || _meta("og:image:url"); if (_og && _RAKUTEN_CDN.test(_og)) { var _of = _rakutenFolder(hiRes(_og)); if (_of) folderSet[_of] = 1; } } catch (e) {}
    var _hasFolders = false; for (var _fk in folderSet) { _hasFolders = true; break; }
    // (c) 컨테이너로 부족하면 라쿠텐 CDN 이미지 전량(추천/리뷰/상세 영역 + 타상품 폴더 제외) → '전량' 보장.
    if (out.length < 3) {
      try {
        var all = document.querySelectorAll("img");
        for (var k = 0; k < all.length && out.length < 40; k++) {
          var im2 = all[k]; var s2 = _bestImgSrc(im2);
          if (!s2 || !_RAKUTEN_CDN.test(s2)) continue;
          if (_galleryExcluded(im2) || _nonProdRegion(im2) || _inRakutenDetail(im2)) continue;
          if (detSeen[hiRes(s2)]) continue;   // 상세 버킷에 이미 귀속된 것은 갤러리 제외
          if (_hasFolders && !folderSet[_rakutenFolder(hiRes(s2))]) continue;   // v80 STEP3: 현 상품 폴더 밖(타상품) 제외
          if (isProductImg(s2)) uniqPush(out, seen, hiRes(s2));
        }
      } catch (e) {}
    }
    return { images: out, detailImages: det };
  }
  function _domImages() {
    var out = [], seen = {}, det = [], detSeen = {};
    var og = _meta("og:image") || _meta("og:image:url"); if (isProductImg(og)) uniqPush(out, seen, hiRes(og));
    // v70 STEP3: 아마존은 갤러리 스코프를 #altImages+#imgTagWrapper로 한정(58장 혼입 방지) → 상세만 dSel로 추가.
    var _host = ""; try { _host = (location.hostname || "").toLowerCase(); } catch (e) {}
    if (/(^|\.)amazon\.[a-z.]+$/.test(_host)) {
      var ag = _amazonGallery();
      for (var ai = 0; ai < ag.length; ai++) uniqPush(out, seen, ag[ai]);
      try {
        var adels = document.querySelectorAll('#aplus img,#productDescription img,#feature-bullets img,#aplus_feature_div img');
        for (var adi = 0; adi < adels.length; adi++) {
          var adm = adels[adi]; if (_nonProdRegion(adm) || _galleryExcluded(adm)) continue;
          var adsrc = _amazonDynMax(adm) || _bestImgSrc(adm);
          if (isProductImg(adsrc)) uniqPush(det, detSeen, hiRes(adsrc));
        }
      } catch (e) {}
      return { images: out, detailImages: det };   // 브로드 제네릭 스코프 건너뜀(자기 상품만)
    }
    // 상품 갤러리 컨테이너(메인 캐러셀/스와이퍼/프리뷰)로 스코프 한정 — 페이지 전체 document.images 금지.
    var gSel = '[class*="gallery" i] img,[class*="product-image" i] img,[class*="main-image" i] img,#imgTagWrapperId img,'
      + '[class*="swiper" i] img,[class*="carousel" i] img,[class*="preview" i] img,[class*="mainImage" i] img,'
      + '[class*="bigImg" i] img,[class*="thumb" i] img,[data-testid*="gallery" i] img,[aria-roledescription="carousel"] img,'
      + '[class*="image-view" i] img';   // v83 STEP2: 알리 갤러리 컨테이너(image-view--previewWrap)
    // v71 STEP3: 테무 상세 컨테이너 보강(goods-desc·decoration·richtext·longimage·productDesc).
    var dSel = '#productDescription img,#feature-bullets img,[class*="detail" i] img,[class*="description" i] img,#aplus img,'
      + '[class*="goods-desc" i] img,[class*="goodsDesc" i] img,[class*="decoration" i] img,[class*="richtext" i] img,'
      + '[class*="rich-text" i] img,[class*="longimage" i] img,[class*="productDesc" i] img,[class*="pdd" i] img';
    // 갤러리: naturalWidth 필터 없이 — 추천/연관 섹션만 제외(캐러셀은 갤러리라 허용).
    try {
      var gels = document.querySelectorAll(gSel);
      for (var gi = 0; gi < gels.length; gi++) {
        var im = gels[gi];
        if (_galleryExcluded(im)) continue;
        var src = _bestImgSrc(im);
        if (isProductImg(src)) uniqPush(out, seen, hiRes(src));
      }
    } catch (e) {}
    // v57 STEP4: 제네릭 갤러리 보강 — <picture><source srcset> + 인라인 background-image(div/a 갤러리).
    try {
      var gScope = '[class*="gallery" i],[class*="product-image" i],[class*="main-image" i],[class*="swiper" i],'
        + '[class*="carousel" i],[class*="preview" i],[class*="mainImage" i],[data-testid*="gallery" i]';
      var srcs = document.querySelectorAll(gScope + ' picture source,picture source');
      for (var si = 0; si < srcs.length; si++) {
        var so = srcs[si]; if (_galleryExcluded(so)) continue;
        var ssv = so.getAttribute("srcset") || so.getAttribute("data-srcset") || "";
        var u0 = ssv ? ssv.split(",")[0].trim().split(/\s+/)[0] : (so.getAttribute("src") || "");
        if (isProductImg(u0)) uniqPush(out, seen, hiRes(u0));
      }
      var bgs = document.querySelectorAll(gScope + ' [style*="background-image" i],[style*="background-image" i]');
      for (var bi = 0; bi < bgs.length && bi < 200; bi++) {
        var be = bgs[bi]; if (_galleryExcluded(be)) continue;
        var bu = _bgImage(be);
        if (isProductImg(bu)) uniqPush(out, seen, hiRes(bu));
      }
    } catch (e) {}
    // 상세 본문 이미지(별도 버킷) — 추천/리뷰/푸터 제외.
    try {
      var dels = document.querySelectorAll(dSel);
      for (var di = 0; di < dels.length; di++) {
        var dm = dels[di];
        if (_nonProdRegion(dm) || _galleryExcluded(dm)) continue;
        var dsrc = _bestImgSrc(dm);
        if (isProductImg(dsrc)) uniqPush(det, detSeen, hiRes(dsrc));
      }
    } catch (e) {}
    // 브리프(오너): 갤러리 컨테이너 스코프 실패 시 document.images 전체 폴백 금지 → 빈 배열(정직, Tier1이 채우거나 부분수집).
    return { images: out, detailImages: det };
  }
  // v57 STEP3: 상세영역에 '더보기'류 접힘 컨트롤이 있는지(펼치면 상세이미지가 더 나올 수 있음).
  // v71 STEP3: 테무·CJK 상세 펼침 라벨 보강(상품상세·전체·全部·查看更多·展开·상세정보).
  var FOLD_RE = /(더\s*보기|펼치기|전체\s*보기|자세히\s*보기|상품\s*상세|상세\s*보기|상세\s*정보|see\s*more|view\s*more|read\s*more|show\s*more|see\s*all|view\s*all|product\s*details|expand|全部|查看更多|展开|もっと見る|続きを読む)/i;
  function _foldButtons() {
    var out = [];
    try {
      var cands = document.querySelectorAll(
        '[class*="detail" i] button,[class*="detail" i] a,[class*="detail" i] [role="button"],' +
        '[class*="description" i] button,[class*="description" i] a,[class*="desc" i] [role="button"],' +
        // v71 STEP3: 테무식 이미지/div 기반 펼침(button/a 아님) — expand/more/unfold 클래스.
        '[class*="expand" i],[class*="viewmore" i],[class*="view-more" i],[class*="unfold" i],[class*="showmore" i],[class*="more-btn" i],' +
        'button,a[role="button"],[role="button"]');
      for (var i = 0; i < cands.length && out.length < 6; i++) {
        var el = cands[i];
        var t = (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim();
        if (t && t.length <= 20 && FOLD_RE.test(t)) out.push(el);
      }
    } catch (e) {}
    return out;
  }
  function _hasDetailFold() { return _foldButtons().length > 0; }
  // v76 STEP4: 일본어 축명(요시다카반 등) 추가 — カラー/サイズ/色/タイプ/スタイル 인식.
  var OPT_LABEL = /(색상|색깔|컬러|사이즈|크기|규격|수량|종류|옵션|타입|스타일|모델|용량|カラー|サイズ|タイプ|スタイル|色|color|colour|size|variant|option|type|style|qty|quantity|model|capacity)/i;
  // 축명 정규화(일본어/영문 → 한글 통일). 값이 아닌 '옵션명' 표기 일관.
  var _AXIS_NORM = { "カラー": "색상", "色": "색상", "color": "색상", "colour": "색상",
                     "サイズ": "사이즈", "size": "사이즈", "タイプ": "타입", "type": "타입",
                     "スタイル": "스타일", "style": "스타일" };
  function _normAxis(name) { var k = String(name || "").trim(); return _AXIS_NORM[k] || _AXIS_NORM[k.toLowerCase()] || name; }
  // v70 STEP2: 수량 셀렉터는 옵션(변형)이 아님 — 라벨/ID/이름이 수량류면 명시 제외(색상·사이즈 변형만 수집).
  var QTY_RE = /(수량|개수|갯수|数量|数量|qty|quantity|amount|count)/i;
  // 값이 순수 1..N 정수열(수량 드롭다운)이면 옵션 아님 — 라벨이 없어도 배제.
  function _looksLikeQty(vals) {
    if (!vals || vals.length < 2) return false;
    var nums = [];
    for (var i = 0; i < vals.length; i++) {
      var t = String(vals[i]).replace(/\s+/g, "");
      if (!/^\d{1,3}$/.test(t)) return false;   // 정수 아니면 수량 아님(색상/사이즈 텍스트)
      nums.push(parseInt(t, 10));
    }
    // 1 또는 0에서 시작하는 오름차순 연속열 → 수량.
    if (nums[0] > 2) return false;
    for (var j = 1; j < nums.length; j++) { if (nums[j] !== nums[j - 1] + 1) return false; }
    return true;
  }
  function _domOptions() {
    var out = [], seen = {};
    function _push(name, vals) {
      if (_isBadOptAxis(name)) return;   // v80 STEP4: 스펙 축(원산지·브랜드·품번…)은 옵션 아님
      var uniq = [], s2 = {};
      // v79 STEP3: 알리식 값에 축명 접두 중복('색상: 1pcs') → 접두 제거(축명과 동일 라벨만).
      var _pre = name ? new RegExp("^" + String(name).replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*[:：]\\s*", "i") : null;
      vals.forEach(function (v) { v = (v || "").replace(/\s+/g, " ").trim(); if (_pre) v = v.replace(_pre, "").trim(); if (v && v.length <= 40 && !_isBadOptValue(v) && !s2[v]) { s2[v] = 1; uniq.push(v); } });   // v79 STEP3: 오염값 배제
      if (uniq.length < 2) return;
      var key = name + "|" + uniq.join(",");
      if (seen[key]) return; seen[key] = 1;
      out.push({ name: name, values: uniq.slice(0, 50) });
    }
    try {
      var sels = document.querySelectorAll("select");
      for (var i = 0; i < sels.length; i++) {
        var sel = sels[i]; if (_nonProdRegion(sel)) continue;
        var vals = Array.prototype.slice.call(sel.options || []).map(function (o) { return (o.textContent || "").trim(); })
          .filter(function (t) { return t && !/^(선택|선택하세요|choose|select|please)/i.test(t); });
        var lbl = sel.getAttribute("aria-label") || (sel.labels && sel.labels[0] && sel.labels[0].textContent) || "";
        // v70 STEP2: 수량 드롭다운 제외 — 라벨/id/name이 수량류이거나 값이 순수 1..N 정수열이면 옵션 아님.
        var selId = (sel.id || "") + " " + ((sel.getAttribute && sel.getAttribute("name")) || "");
        if (QTY_RE.test(lbl) || QTY_RE.test(selId) || _looksLikeQty(vals)) continue;
        var m = String(lbl).match(OPT_LABEL); _push(m ? m[0] : "옵션", vals);
      }
    } catch (e) {}
    // v62 STEP3: 아마존 트위스터 — 축 이름 정확 매핑(색상/사이즈). 값은 v58 스와치 경로가 이미 잡지만
    //   이름이 '옵션'으로 뭉개짐 → 행 id(inline-twister-row-color_name) / .a-form-label('Color:')로 축명 복원.
    try {
      var _TW_ID = { color: "색상", size: "사이즈", style: "스타일", pattern: "패턴", flavor: "종류", model: "모델", material: "소재", edition: "에디션" };
      // v70 STEP2: 트위스터 값 정제 — 스와치 라벨은 img[alt]/aria-label 우선, 'Click to select X'류 접두 제거.
      var _twClean = function (s) {
        s = String(s || "").replace(/\s+/g, " ").trim();
        var m = s.match(/^(?:click to select|select|choose|선택[:：]?)\s*(.+)$/i);
        if (m && m[1]) s = m[1].trim();
        return s.replace(/\.\s*$/, "").trim();
      };
      var _twVal = function (el) {
        var im = el.querySelector && el.querySelector("img[alt]");
        var v = (im && im.getAttribute && im.getAttribute("alt")) || "";
        if (!v) v = (el.getAttribute && el.getAttribute("aria-label")) || "";
        if (!v) v = (el.getAttribute && el.getAttribute("title")) || "";
        if (!v) v = el.innerText || el.textContent || "";
        return _twClean(v);
      };
      // v70 STEP2: 신형 인라인 트위스터(inline-twister-row-) + 구형 variation_ 컨테이너 둘 다.
      var trows = document.querySelectorAll('[id^="inline-twister-row-"],[id^="variation_"],#twister [class*="twisterTextDiv" i]');
      for (var t2 = 0; t2 < trows.length; t2++) {
        var row = trows[t2];
        if (_nonProdRegion(row)) continue;
        // 축명: 행 id의 표준 축(color/size…)을 한글로 우선 매핑, 없으면 .a-form-label 텍스트.
        var rid = (row.id || "").replace(/^(inline-twister-row-|variation_)/, "").split("_")[0].toLowerCase();
        var nm = _TW_ID[rid] || "";
        if (!nm) {
          var flbl = row.querySelector(".a-form-label,label");
          if (flbl) {
            var ft = String(flbl.innerText || flbl.textContent || "").replace(/[:：]\s*$/, "").replace(/\s+/g, " ").trim();
            var fm = ft.match(OPT_LABEL); if (fm) nm = fm[0];
          }
        }
        // 값: 스와치 li·버튼·라디오(+img[alt]). 신형은 li[id^=color_name_]/구형은 ul li.
        var tv = [], sw = row.querySelectorAll('li[id],li[data-asin],.swatches li,[class*="swatch" i] li,ul.a-button-list li,ul li,[role="radio"],button[data-asin],.a-button-toggle');
        for (var s3 = 0; s3 < sw.length && tv.length < 60; s3++) {
          var st = _twVal(sw[s3]);
          if (st && st.length <= 40 && !QTY_RE.test(st) && !/^(선택|choose|select|please|담기|구매|장바구니|add to|buy)/i.test(st)) tv.push(st);
        }
        _push(nm || "옵션", tv);
      }
    } catch (e) {}
    // v58 STEP2: 라디오·버튼 그룹(구매박스 인근 색상/사이즈 스와치) — select 없는 SPA(테무 등) 대응.
    //   role=radiogroup / [class*=sku i] / [class*=option i] / [class*=variant i] / [class*=spec i] 컨테이너에서
    //   버튼·라디오·라벨의 텍스트를 옵션 값으로. 추천/리뷰 영역 제외. 값 2+일 때만(확신 없으면 미수집=정직).
    try {
      var groups = document.querySelectorAll('[role="radiogroup"],[class*="sku" i],[class*="option" i],[class*="variant" i],[class*="spec" i],[class*="swatch" i]');
      for (var g = 0; g < groups.length; g++) {
        var grp = groups[g];
        if (_nonProdRegion(grp) || _galleryExcluded(grp)) continue;
        if (grp.closest && grp.closest('[id^="inline-twister-row-"],[id^="variation_"]')) continue;   // v62/v70: 트위스터는 위에서 축명 매핑(중복 방지)
        // v79 STEP3: 미디어 캐러셀(#altImages·썸네일)·스펙표(table/dl/spec/attribute)는 옵션 아님 — 제외.
        //   아마존 '←/1/→·Product Image' 캐러셀 컨트롤, 라쿠텐 스펙표(브랜드·품번·원산지) 뭉침 박멸.
        //   스펙표는 _domSpecs가 별도 수집(정직). 테무 등 실옵션은 JSON(axisMap) 경로라 무영향.
        if (grp.closest && grp.closest('#altImages,[class*="thumbnail" i],[class*="imageThumb" i],[class*="a-carousel" i],[aria-roledescription="carousel"],table,dl,[class*="spec" i],[class*="attribute" i],[class*="product-info" i],[class*="itemInfo" i]')) continue;
        if (grp.querySelector("select")) continue;       // select은 위에서 처리(중복 방지)
        // 그룹 라벨: aria-label / [class*=label] / 첫 텍스트 노드 중 OPT_LABEL 매칭.
        var glbl = grp.getAttribute("aria-label") || "";
        if (!glbl) { var le = grp.querySelector('[class*="label" i],[class*="title" i],dt,.name'); if (le) glbl = (le.innerText || le.textContent || ""); }
        // v76 STEP4: 라벨이 그룹(예: ul.color-swatch) 밖 형제/부모에 있으면(요시다 .item-color-select>span.label)
        //   부모 컨테이너에서 라벨 보완 — 스와치 옵션명('색상') 복원.
        if (!glbl && grp.parentElement) {
          var ple = grp.parentElement.querySelector('[class*="label" i],[class*="title" i],dt,legend,.name,span');
          if (ple && !(grp.contains && grp.contains(ple))) glbl = (ple.innerText || ple.textContent || "");
        }
        // v70 STEP2: 수량 그룹 제외.
        if (QTY_RE.test(glbl) || QTY_RE.test(grp.id || "")) continue;
        var gm = String(glbl).match(OPT_LABEL);
        // 값 후보: 버튼·라디오·옵션 라벨·스와치(+ v76 STEP4: data-color/data-option 앵커·li).
        var cands = grp.querySelectorAll('button,[role="radio"],label,[class*="value" i],[class*="item" i],'
          + 'a[data-value],[data-value],a[data-color],[data-color],[data-option],[data-name],li a,li[data-color]');
        var vv = [];
        for (var c = 0; c < cands.length && vv.length < 60; c++) {
          var el = cands[c];
          if (el.querySelector && el.querySelector("button,[role=radio],select")) continue;   // 중첩 컨테이너 스킵
          // v76 STEP4: 스와치 값은 data-color/option/name·aria·title 우선, 없으면 자식 img[alt], 마지막 텍스트.
          var t = (el.getAttribute && (el.getAttribute("aria-label") || el.getAttribute("data-value")
            || el.getAttribute("data-color") || el.getAttribute("data-option") || el.getAttribute("data-name")
            || el.getAttribute("title"))) || "";
          if (!t) { var _im = el.querySelector && el.querySelector("img[alt]"); if (_im) t = _im.getAttribute("alt") || ""; }
          if (!t) t = el.innerText || el.textContent || "";
          t = String(t).replace(/\s+/g, " ").trim();
          if (t && t.length >= 1 && t.length <= 40 && !/^(선택|choose|select|please|담기|구매|장바구니|add to|buy)/i.test(t)) vv.push(t);
        }
        // 라벨 텍스트가 값에 섞이면 제외(라벨=그룹명).
        if (gm) vv = vv.filter(function (v) { return v.replace(/\s/g, "") !== gm[0].replace(/\s/g, ""); });
        if (_looksLikeQty(vv)) continue;   // v70 STEP2: 순수 1..N 정수열(수량) 제외
        _push(gm ? _normAxis(gm[0]) : "옵션", vv);
      }
    } catch (e) {}
    return out;
  }
  // ── v83 STEP3: 상세 스펙·설명 위생 ────────────────────────────────────
  //   증거(라쿠텐 tsumugi): detail_specs에 JCB 프로모 배너("…까지! ポイント3倍")·공유링크 UI 텍스트가 흡입되고,
  //   desc에 raw HTML 주석과 깨진 속성(`</div ="" ="">`)이 남았다. 스펙은 **상품 속성 표**만, 설명은 **본문**만.
  var _SPEC_BAD_K = /(까지!|까지\s*!|ポイント\d*倍|포인트\s*(증정|적립|\d*배)|캠페인|キャンペーン|エントリー|쿠폰|クーポン|공유\s*링크|공유하기|シェア|share\s*link|sns|트위터|twitter|facebook|line で送る|즐겨찾기|お気に入り|랭킹|ランキング|배너|banner|\d{1,2}\/\d{1,2}\s*\(|\d{4}[年.\-\/]\d{1,2}[月.\-\/]\d{1,2})/i;
  var _SPEC_BAD_V = /(\{[^}]*(?:font-size|color|margin|padding|background|border|width|display)\s*:[^}]*\}|^\s*[.#][a-z0-9_-]+\s*\{|@media|<\/?[a-z]+[\s>])/i;
  function _cleanSpecs(specs) {
    var out = [];
    (specs || []).forEach(function (s) {
      if (!s) return;
      var k = String(s.k == null ? "" : s.k).replace(/\s+/g, " ").trim();
      var v = String(s.v == null ? "" : s.v).replace(/\s+/g, " ").trim();
      if (!k || !v) return;
      if (_SPEC_BAD_K.test(k) || _SPEC_BAD_K.test(v)) return;   // 프로모·날짜·공유 UI 문구는 상품 속성이 아님
      if (_SPEC_BAD_V.test(v)) return;                          // CSS 조각·마크업 잔재
      if (k.length > 60 || v.length > 200) { k = k.slice(0, 60); v = v.slice(0, 200); }
      out.push({ k: k, v: v });
    });
    return out;
  }
  // 설명 본문에서 raw HTML 주석·깨진 태그 잔재 제거(사용자에게 마크업 노출 금지).
  function _stripHtmlNoise(s) {
    var t = String(s == null ? "" : s);
    t = t.replace(/<!--[\s\S]*?-->/g, " ");            // HTML 주석
    t = t.replace(/<!--[\s\S]*$/g, " ");               // 닫히지 않은 주석 잔재
    t = t.replace(/<\/?[a-z][^>]*>/gi, " ");           // 남은 태그(정상·깨진 것 모두)
    t = t.replace(/<\/?[a-z][^<>]*$/gi, " ");          // `</div ="" ="">` 류 잘린 태그
    t = t.replace(/[ \t]{2,}/g, " ").replace(/\n{3,}/g, "\n\n");
    return t.trim();
  }
  function _domSpecs() {
    // 속성 표(스펙): table tr / dl / [class*=spec|attribute|param] li
    var specs = [], seen = {};
    try {
      var rows = document.querySelectorAll('table tr,[class*="spec" i] li,[class*="attribute" i] li,[class*="param" i] li,dl');
      for (var i = 0; i < rows.length && specs.length < 60; i++) {
        var row = rows[i]; if (_nonProdRegion(row)) continue;
        var cells = row.querySelectorAll("th,td,dt,dd");
        if (cells.length >= 2) {
          var k = (cells[0].textContent || "").trim().slice(0, 60), v = (cells[1].textContent || "").trim().slice(0, 200);
          if (k && v && !seen[k]) { seen[k] = 1; specs.push({ k: k, v: v }); }
        } else {
          var txt = (row.textContent || "").trim();
          var mm = txt.match(/^([^:：]{1,40})[:：]\s*(.+)$/);
          if (mm && !seen[mm[1]]) { seen[mm[1]] = 1; specs.push({ k: mm[1].trim(), v: mm[2].trim().slice(0, 200) }); }
        }
      }
    } catch (e) {}
    return _cleanSpecs(specs);   // v83 STEP3: 프로모 배너·공유 UI·CSS 조각 제거
  }
  // ── v83 STEP2: 알리익스프레스 옵션 어댑터(DOM sku-item) ────────────────
  //   증거: ko.aliexpress.com 상세에 sku-item 16개·"색상:" 라벨이 실존하는데 options/skus 0으로 수집됐다.
  //   제네릭 그룹 스캐너는 알리의 해시 클래스(sku-item--image--3XxXxXx) 구조에서 축명을 못 잡는다 → 전용 어댑터.
  //   호스트 게이트(*.aliexpress.*)라 타 사이트 영향 0. 값이 하나도 없으면 빈 배열(가짜 옵션 금지).
  function _aliHost(h) {
    try { h = String(h || (location.hostname || "")).toLowerCase(); } catch (e) { h = String(h || "").toLowerCase(); }
    return /(^|\.)aliexpress\.[a-z]{2,3}(\.[a-z]{2,3})?$/.test(h);
  }
  function _aliOptions() {
    if (!_aliHost()) return [];
    var out = [], axSeen = {};
    try {
      var titles = document.querySelectorAll('[class*="sku-item--title" i],[class*="sku-title" i],[class*="sku-property-name" i]');
      for (var i = 0; i < titles.length && out.length < 8; i++) {
        var tEl = titles[i];
        if (_nonProdRegion(tEl)) continue;
        // 축명: "색상: White" / "Color:" → 콜론 앞부분. 선택값(selectedText)은 축명이 아니다.
        var rawT = String(tEl.innerText || tEl.textContent || "").replace(/\s+/g, " ").trim();
        var sel = tEl.querySelector('[class*="selectedText" i],[class*="sku-item--selected" i]');
        if (sel) rawT = rawT.replace(String(sel.innerText || sel.textContent || "").trim(), "").trim();
        var axis = _normAxis(rawT.split(/[:：]/)[0].replace(/\s+/g, " ").trim());
        if (!axis || axis.length > 20) continue;
        // 값 컨테이너: 제목의 형제/부모 안 sku 값 노드들.
        var box = tEl.parentElement || tEl;
        var nodes = box.querySelectorAll('[class*="sku-item--image" i] img[alt],[class*="sku-item--text" i],[class*="sku-item--box" i],'
          + '[class*="sku-property-image" i] img[alt],[class*="sku-property-text" i] span,li[title],[data-sku-col]');
        var vals = [], vSeen = {};
        for (var n = 0; n < nodes.length && vals.length < 60; n++) {
          var el = nodes[n];
          var v = "";
          if ((el.tagName || "").toLowerCase() === "img") v = el.getAttribute("alt") || "";
          if (!v && el.getAttribute) v = el.getAttribute("title") || el.getAttribute("data-value") || "";
          if (!v) { var im = el.querySelector && el.querySelector("img[alt]"); if (im) v = im.getAttribute("alt") || ""; }
          if (!v) v = String(el.innerText || el.textContent || "");
          v = String(v).replace(/\s+/g, " ").trim();
          if (!v || v.length > 40) continue;
          if (_isBadOptValue(v) || _isBadOptFallbackValue(v)) continue;
          if (v === axis || v.replace(/[:：]\s*$/, "") === axis) continue;
          if (vSeen[v]) continue;
          vSeen[v] = 1; vals.push(v);
        }
        if (!vals.length || axSeen[axis]) continue;
        axSeen[axis] = 1;
        out.push({ name: axis, values: vals.slice(0, 50) });
      }
    } catch (e) {}
    return out;
  }
  // v83 STEP2: 판매자/스토어 블록은 상세설명이 아니다(알리 desc가 '판매자 블록 쪼가리'로 저장되던 근원).
  var _SELLER_BLOCK_RE = /(판매자|거래\s*업체|스토어|store\b|seller\b|shop\s*now|팔로우|follow|긍정적\s*피드백|positive\s*feedback|매장\s*방문)/i;
  function _isSellerBlock(el) {
    try {
      var meta = String((el.id || "") + " " + ((el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className) || "")).toLowerCase();
      if (/(store|seller|shop-?info|vendor|merchant)/.test(meta)) return true;
      var t = String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
      if (t.length < 300 && _SELLER_BLOCK_RE.test(t)) return true;
    } catch (e) {}
    return false;
  }
  // v83 STEP4: 평점 DOM 폴백 — 리뷰는 잡혔는데 rating이 공란인 실기기 증상(초기 JSON에 aggregateRating 없음).
  //   페이지에 이미 렌더된 **집계 평점 표기**만 읽는다(계산·추정 금지: 리뷰 평균을 지어내지 않는다).
  function _domRating() {
    var sels = ['[data-hook="rating-out-of-text"]', '#acrPopover', 'span[data-hook="rating-out-of-text"]',
      '[itemprop="ratingValue"]', '[class*="rating-value" i]', '[class*="ratingValue" i]',
      '[class*="average-star" i]', '[class*="averageStar" i]', '[class*="review-average" i]', 'i.a-icon-star span.a-icon-alt'];
    for (var i = 0; i < sels.length; i++) {
      try {
        // 평점 표기는 본래 리뷰 영역 안에 있다 → _nonProdRegion(리뷰 제외 규칙)을 적용하지 않는다.
        var el = document.querySelector(sels[i]);
        if (!el || _isInjectedUI(el)) continue;
        var raw = String((el.getAttribute && (el.getAttribute("title") || el.getAttribute("content"))) || el.innerText || el.textContent || "");
        var m = raw.match(/(\d(?:[.,]\d)?)\s*(?:out of|\/)\s*5/i) || raw.match(/^\s*(\d(?:[.,]\d)?)\s*$/);
        if (m) { var v = parseFloat(String(m[1]).replace(",", ".")); if (v > 1 && v <= 5) return String(m[1]).replace(",", "."); }
      } catch (e) {}
    }
    return "";
  }
  // v76 STEP6: DOM 리뷰 폴백 — 초기 JSON에 리뷰가 없어도 **페이지에 이미 렌더된** 리뷰 섹션 상위 텍스트를 읽는다.
  //   추가 네트워크 요청 0(존재분만). 아마존([data-hook=review]) + 제네릭 리뷰 항목. 리뷰 영역은 정상(제외 안 함).
  function _domReviews() {
    var out = [], seenTxt = {};
    function _clean(el) { return el ? String(el.innerText || el.textContent || "").replace(/\s+/g, " ").trim() : ""; }
    // v79 STEP5: 본문 셀렉터 = 구체적인 리뷰 본문만(저자 노드 .a-profile-* 배제). 넓은 [class*=content]·p는
    //   저자 프로필(.a-profile-content)을 먼저 잡아 text=author 복제를 만들었다 → 순차 구체 셀렉터 + 저자 배제.
    var BODY_SELS = ['[data-hook="review-body"]', '[itemprop="reviewBody"]', '[class*="review-text" i]',
      '[class*="reviewText" i]', '[class*="review-content" i]', '[class*="comment-text" i]', '[class*="comment-content" i]'];
    var AUTH_SEL = '.a-profile-name,.a-profile-content,[class*="author" i],[itemprop="author"],[class*="reviewer" i],[class*="user-name" i]';
    try {
      var items = document.querySelectorAll('[data-hook="review"],[id^="customer_review"],[class*="review-item" i],'
        + '[class*="reviewItem" i],[itemprop="review"],[class*="comment-item" i],li[class*="review" i]');
      for (var i = 0; i < items.length && out.length < REVIEW_MAX; i++) {
        var it = items[i];
        // 저자 먼저 확정(본문 후보에서 배제 기준).
        var aEl = it.querySelector('.a-profile-name,[class*="author" i],[itemprop="author"],[class*="reviewer" i],[class*="user-name" i]');
        var author = _clean(aEl);
        // 본문: 구체 셀렉터 순차 → 저자 노드/저자 텍스트가 아닌 첫 후보.
        var body = "";
        for (var s = 0; s < BODY_SELS.length; s++) {
          var be = it.querySelector(BODY_SELS[s]);
          if (!be) continue;
          if (be.closest && be.closest(AUTH_SEL)) continue;          // 저자 프로필 하위면 스킵
          var t = _clean(be);
          if (t && t.length >= 3 && t !== author) { body = t; break; }   // v79 STEP5: text≠author 봉인
        }
        if (!body) continue;                                          // 본문 못 찾으면 저자 복제 저장 금지(스킵)
        var kk = body.slice(0, 40);
        if (seenTxt[kk]) continue; seenTxt[kk] = 1;
        // 평점: 'X out of 5 stars'(a-icon-alt) 우선 → X/5. class a-star-N 폴백. 1.0~5.0만.
        var rating = "";
        var rEl = it.querySelector('[data-hook="review-star-rating"] .a-icon-alt,[data-hook="cmps-review-star-rating"] .a-icon-alt,'
          + '[class*="a-icon-alt" i],[itemprop="ratingValue"]');
        if (rEl) {
          var rraw = String((rEl.getAttribute && rEl.getAttribute("content")) || rEl.innerText || rEl.textContent || "");
          var rm = rraw.match(/(\d(?:\.\d)?)\s*(?:out of|\/)\s*5/i) || rraw.match(/(\d(?:\.\d)?)/);
          if (rm) { var rv2 = parseFloat(rm[1]); if (rv2 >= 1 && rv2 <= 5) rating = rm[1]; }   // 원본 형식 보존('5.0')
        }
        if (!rating) {   // class 기반(a-star-4 / rating-4) 폴백.
          try {
            var sc = it.querySelector('[class*="a-star-" i],[class*="star-rating" i]');
            var cm = sc ? String((sc.className && sc.className.baseVal !== undefined ? sc.className.baseVal : sc.className) || "").match(/(?:a-star-|rating-)(\d(?:[._]\d)?)/i) : null;
            if (cm) { var rv3 = parseFloat(cm[1].replace("_", ".")); if (rv3 >= 1 && rv3 <= 5) rating = String(rv3); }
          } catch (e) {}
        }
        out.push({ author: author.slice(0, 60), rating: rating, text: body.slice(0, 500) });
      }
    } catch (e) {}
    return out;
  }
  // v78 STEP3: 상세설명 소스 사다리 — **어댑터 상세(DOM)** 전용(meta 폴백 분리). 아마존 feature-bullets+A+,
  //   테무 상세영역, productDescription/detail 컨테이너 본문. meta SEO 문구('Buy …')는 여기서 반환 안 함.
  function _adapterDetailText() {
    // 아마존: About this item(#feature-bullets) 불릿 + productDescription + A+(#aplus) 본문.
    try {
      var fb = document.querySelector("#feature-bullets");
      if (fb && !_nonProdRegion(fb)) {
        var bl = [];
        fb.querySelectorAll("li span.a-list-item, li").forEach(function (li) {
          var t = (li.innerText || li.textContent || "").replace(/\s+/g, " ").trim();
          if (t && t.length > 2 && !/^about this item$/i.test(t) && bl.indexOf("· " + t) < 0) bl.push("· " + t);
        });
        var pd = document.querySelector("#productDescription");
        var pdt = pd ? (pd.innerText || "").replace(/\n{3,}/g, "\n\n").trim() : "";
        var apl = document.querySelector("#aplus, #aplus_feature_div, #aplusBrandStory_feature_div");
        var aplt = (apl && !_nonProdRegion(apl)) ? (apl.innerText || "").replace(/\n{3,}/g, "\n\n").trim() : "";
        var out = [bl.join("\n"), pdt, aplt].filter(Boolean).join("\n\n").trim();
        if (out.length > 20) return out.slice(0, 4000);
      }
    } catch (e) {}
    // 테무·제네릭 상세영역 + productDescription/detail 컨테이너(추천/리뷰 제외).
    // v83 STEP2: 알리 상세 모듈(detailmodule_·description--wrap)을 사다리 앞에 두고, **판매자/스토어 블록은 제외**
    //   (desc가 '판매자 …' 쪼가리로 저장되던 근원). 후보를 하나 실패해도 다음 후보로 계속 내려간다.
    var sel = ['[class*="detailmodule" i]', '[class*="description--wrap" i]', '#product-description',
      '#productDescription', '[class*="goods-desc" i]', '[class*="goodsDesc" i]', '[class*="productDesc" i]',
      '[class*="detail-desc" i]', '[class*="item-desc" i]', '[class*="description" i]', '[class*="detail" i]'];
    for (var i = 0; i < sel.length; i++) {
      try {
        var els = document.querySelectorAll(sel[i]);
        for (var e2 = 0; e2 < els.length && e2 < 5; e2++) {
          var el = els[e2];
          if (!el || _nonProdRegion(el) || _galleryExcluded(el) || _isSellerBlock(el)) continue;
          var t = _stripHtmlNoise(String(el.innerText || el.textContent || "").replace(/\n{3,}/g, "\n\n").trim());
          if (t.length > 20) return t.slice(0, 4000);
        }
      } catch (e) {}
    }
    return "";
  }
  function _metaDescription() { return _meta("og:description") || _meta("description") || ""; }
  // v79 STEP6: SEO/필러 상세 판정(서버 _FILLER_DESC_RE 미러) — Tier1(state) / meta 후보가 '{사이트}에서 이
  //   …을 확인하세요'·'Buy … online'·'쇼핑하여 절약을 시작' 등 마켓 자동 필러면 desc_text로 저장 금지(정직 —
  //   빈 상세 + 편집 AI 초안). 어댑터 상세(실 DOM)는 신뢰(필터 안 함). 계약: desc_text 접두 'Temu에서'/'Buy ' 금지.
  function _isFillerDesc(s) {
    s = String(s == null ? "" : s).replace(/\s+/g, " ").trim();
    if (!s) return true;
    if (/^Buy\s/i.test(s)) return true;                                                   // 아마존 SEO 'Buy X online…'
    if (/[A-Za-z가-힣]+에서\s*이\s*.{0,80}?[을를]\s*확인하세요/.test(s)) return true;       // '{사이트}에서 이 …을 확인하세요'
    if (/(제품|상품)도\s*좋아할\s*수\s*있습니다/.test(s)) return true;                       // 추천 꼬리
    if (/(쇼핑하여|구매하여)\s*절약을?\s*시작/.test(s)) return true;                          // 테무 '쇼핑하여 절약을 시작'
    if (/shop\b.{0,40}\band save\b/i.test(s) || /start saving/i.test(s)) return true;      // Shop … and save
    if (/^Temu\b/i.test(s) || /^Temu에서/.test(s)) return true;                            // 'Temu…' 접두
    return false;
  }
  // 하위호환(v60): _domDescription = 어댑터 상세 우선, 없으면 meta 폴백.
  function _domDescription() { return _adapterDetailText() || _metaDescription(); }
  // v60 STEP1: 우리 확장이 주입한 DOM(kgp-*) 또는 사이드패널/챗/네비 등 페이지 크롬 안에 있는 요소인지.
  //   → 제목/키워드 추출에서 제외(아마존 'Chat history' 등 삽입 UI h1 오염 차단).
  function _isInjectedUI(el) {
    var re = /(^|\s|-)(kgp-|assistant|copilot|rufus|chat[-_ ]?history|chat[-_ ]?panel|side[-_ ]?panel|sidebar|drawer|overlay|extension|widget|toolbar|popover|modal)($|\s|-)/i;
    var cur = el, d = 0;
    while (cur && d < 12) {
      var id = cur.id || "";
      var cls = (cur.className && cur.className.baseVal !== undefined ? cur.className.baseVal : (cur.className || ""));
      if (/^kgp-/.test(id) || /(^|\s)kgp-/.test(cls) || (cur.getAttribute && cur.getAttribute("data-kgp-outline"))) return true;
      var tg = (cur.tagName || "").toLowerCase();
      if (tg === "nav" || tg === "aside" || tg === "header") return true;
      var role = cur.getAttribute && (cur.getAttribute("role") || "");
      if (/(complementary|navigation|dialog|banner)/i.test(role || "")) return true;
      if (re.test(id + " " + cls)) return true;
      cur = cur.parentElement; d++;
    }
    return false;
  }
  // v60 STEP1: 디폴트 소싱처 어댑터별 상품명 셀렉터(하드매핑) — 삽입 UI h1 오염을 원천 우회.
  function _adapterTitle() {
    var host = (location.hostname || "").toLowerCase();
    var MAP = [
      { re: /(^|\.)amazon\.[a-z.]+$/, sels: ["#productTitle", "#title #productTitle", "h1#title span"] },
      { re: /(^|\.)temu\.[a-z.]+$/, sels: ['[class*="goods-name" i]', '[class*="productTitle" i]', 'h1[class*="title" i]'] },
      { re: /(^|\.)(aliexpress|ae01)\.[a-z.]+$/, sels: ['h1[data-pl="product-title"]', '[class*="title--wrap" i] h1', "h1"] },
      { re: /(^|\.)(taobao|tmall)\.[a-z.]+$/, sels: ['[class*="mainTitle" i]', '[class*="ItemTitle" i]', "h1"] },
    ];
    for (var i = 0; i < MAP.length; i++) {
      if (!MAP[i].re.test(host)) continue;
      for (var s = 0; s < MAP[i].sels.length; s++) {
        try {
          var el = document.querySelector(MAP[i].sels[s]);
          if (el && !_isInjectedUI(el)) {
            var t = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
            if (t && t.length >= 2) return t.slice(0, 300);
          }
        } catch (e) {}
      }
      break;
    }
    return "";
  }
  // v60 STEP1: 본문 최상위 h1 — 우리 UI·삽입 패널 제외, 제일 긴(상품명일 가능성 높은) 것.
  function _cleanH1() {
    try {
      var h1s = document.querySelectorAll("h1");
      var best = "";
      for (var i = 0; i < h1s.length; i++) {
        var el = h1s[i];
        if (_isInjectedUI(el) || _nonProdRegion(el)) continue;
        var t = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
        if (t && t.length > best.length) best = t;
      }
      return best.slice(0, 300);
    } catch (e) { return ""; }
  }

  // v65 STEP1: 순수 사이트/브랜드명 판별(상품명 아님) — 제목이 'Temu'·'Amazon' 등으로 저장되는 것 차단.
  //   상품명이면 사이트명 뒤에 상품 정보가 붙거나(예 '무선 이어폰 | Temu') 길이가 길다. 바로 그 사이트명만/짧은 것만 배제.
  function _isBareSiteName(t) {
    var s = String(t || "").trim();
    if (!s) return true;
    if (s.length <= 2) return true;
    if (/^(temu|amazon|aliexpress|taobao|tmall|1688|rakuten|mercari|shopee|ebay|yahoo|paypaymall)!?(\.[a-z.]+)?\s*(shopping|쇼핑|ショッピング|재팬|japan)?[\s\-–|:·!]*$/i.test(s)) return true;
    return false;
  }
  // v76 STEP1: 제목 새니타이저(전 마켓 공통) — 사이트명 접두/접미 제거. 어댑터별 알려진 패턴 + 제네릭(구분자
  //   |·:·- 뒤 세그먼트가 도메인 브랜드명과 일치하면 제거). 계약: 제목에 사이트명 0. 상품명 본문은 보존.
  var _SITE_BRAND_RE = /(amazon(\.[a-z.]+)?|aliexpress|rakuten|楽天市場|楽天|temu|qoo10|mercari|メルカリ|메루카리|ヤフーショッピング|yahoo!?\s*(shopping|쇼핑)?|paypaymall|吉田カバン|요시다카반|요시다|yoshida(kaban)?|iherb|dhgate|tmall|taobao|1688|shopee|ebay)/i;
  function _brandFromHost(url) {
    try {
      var h = (new URL(url).hostname || "").replace(/^www\./, "");
      var parts = h.split(".");
      // 메인 라벨(SLD) — co.jp/com 등 앞. 4자 이상만(오탐 방지).
      var sld = parts.length >= 2 ? parts[parts.length - 2] : (parts[0] || "");
      if (sld && (sld === "co" || sld === "com") && parts.length >= 3) sld = parts[parts.length - 3];
      return sld.length >= 4 ? sld.toLowerCase() : "";
    } catch (e) { return ""; }
  }
  // v83 STEP3: 아마존 카테고리 꼬리(' : Home & Kitchen') — 상품명이 아니라 브레드크럼 카테고리다. 사전에 있는
  //   카테고리명일 때만 절단(임의 ':' 뒤 절단 금지 — 상품명에 콜론이 흔하다).
  var _AMZ_CAT_TAIL_RE = new RegExp("\\s*[:：]\\s*(" + [
    "Home\\s*&\\s*Kitchen", "Kitchen\\s*&\\s*Dining", "Electronics", "Beauty\\s*&\\s*Personal\\s*Care",
    "Health\\s*&\\s*Household", "Clothing,?\\s*Shoes\\s*&\\s*Jewelry", "Sports\\s*&\\s*Outdoors",
    "Toys\\s*&\\s*Games", "Tools\\s*&\\s*Home\\s*Improvement", "Office\\s*Products", "Pet\\s*Supplies",
    "Grocery\\s*&\\s*Gourmet\\s*Food", "Baby", "Automotive", "Industrial\\s*&\\s*Scientific",
    "Musical\\s*Instruments", "Video\\s*Games", "Books", "Garden\\s*&\\s*Outdoor",
    "Patio,?\\s*Lawn\\s*&\\s*Garden", "Cell\\s*Phones\\s*&\\s*Accessories", "Computers\\s*&\\s*Accessories",
    "Arts,?\\s*Crafts\\s*&\\s*Sewing", "Appliances", "Everything\\s*Else",
  ].join("|") + ")\\s*$", "i");
  function _sanitizeTitle(t, url) {
    var s = String(t == null ? "" : t).replace(/\s+/g, " ").trim();
    if (!s) return "";
    for (var _ci = 0; _ci < 2; _ci++) { var _b = s; s = s.replace(_AMZ_CAT_TAIL_RE, "").trim(); if (s === _b) break; }
    // 접두: 【楽天市場】… / 【…市場/store/shop…】
    s = s.replace(/^【\s*[^】]{0,24}(楽天|市場|store|shop|mall|ストア)[^】]{0,24}】\s*/i, "");
    // 접두: 사이트명 + 구분자(: | - – ·). 예 "Amazon.com: ", "楽天市場｜"
    s = s.replace(/^(amazon(\.[a-z.]+)?|楽天市場|rakuten|aliexpress|temu|qoo10)\s*[:：|｜\-–·]\s*/i, "");
    // 접미: 구분자 + 사이트/브랜드명 (여러 개 연속 제거)
    for (var i = 0; i < 3; i++) {
      var before = s;
      s = s.replace(new RegExp("\\s*[|｜:：\\-–·]\\s*" + _SITE_BRAND_RE.source + "\\s*$", "i"), "");
      if (s === before) break;
    }
    // 제네릭: 구분자 뒤 마지막 세그먼트가 도메인 브랜드명과 (영숫자 기준) 일치하면 제거.
    var brand = _brandFromHost(url);
    if (brand) {
      var segs = s.split(/\s*[|｜·]\s*/);
      if (segs.length >= 2) {
        var last = segs[segs.length - 1].replace(/[^a-z0-9]/gi, "").toLowerCase();
        if (last && (last === brand || last.indexOf(brand) === 0 || brand.indexOf(last) === 0)) {
          segs.pop(); s = segs.join(" | ");
        }
      }
    }
    return s.replace(/\s+/g, " ").trim();
  }

  // ── 가격 sanity 게이트 ─────────────────────────────────────
  // ── v83 STEP1: 통화 판정 재설계(돈 직결) ────────────────────────────────
  // 사다리: ①tier1 명시 통화 필드 → ②**어댑터 도메인 고정 테이블** → ③표시 기호 → ④html lang 로케일(최후).
  //   근원: 구글 번역이 <html lang>을 ko로 바꿔(class="translated-ltr") 로케일 사다리가 7,480円 상품을 KRW로
  //   오판(tsumugi). 도메인은 번역이 못 바꾸는 근거라 로케일보다 위, 다만 tier1 명시 필드보다는 아래.
  //
  // 등재 원칙: **단일 통화 도메인만**(추측 금지). 다통화 표시 도메인(알리 ko/es/ru…)은 미등재 → tier1/기호 위임.
  function _domainCurrency(host, path) {
    try {
      host = String(host || (location.hostname || "")).toLowerCase();
      path = String(path == null ? (location.pathname || "") : path).toLowerCase();
    } catch (e) { host = String(host || "").toLowerCase(); path = String(path || "").toLowerCase(); }
    if (!host) return "";
    if (/(^|\.)rakuten\.(co\.jp|com)$/.test(host)) return "JPY";           // item.rakuten.co.jp·www·books
    if (/(^|\.)yoshidakaban\.com$/.test(host)) return "JPY";
    if (/yahoo\.co\.jp$/.test(host)) return "JPY";
    if (/(^|\.)amazon\.co\.jp$/.test(host)) return "JPY";
    if (/(^|\.)amazon\.co\.uk$/.test(host)) return "GBP";
    if (/(^|\.)amazon\.(de|fr|it|es|nl|be|se|pl)$/.test(host)) return "EUR";
    if (/(^|\.)amazon\.com$/.test(host)) return "USD";
    if (/(^|\.)amazon\.ca$/.test(host)) return "CAD";
    if (/(^|\.)amazon\.com\.au$/.test(host)) return "AUD";
    if (/(^|\.)(taobao|tmall|1688)\.com$/.test(host)) return "CNY";
    // 테무는 다국가 단일 도메인 — **국가 경로(/kr)** 가 명시된 경우만 확정(그 외는 미확정 → 기호/로케일).
    if (/(^|\.)temu\.com$/.test(host)) return /^\/kr(\/|$)/.test(path) ? "KRW" : "";
    return "";
  }
  // v83 STEP1: 구글 번역이 DOM을 바꿔치기한 상태인지(html class="translated-ltr|translated-rtl" · 번역 뱃지).
  //   true면 html lang은 **번역 언어**라 원문 로케일 근거로 못 쓴다 → 로케일 사다리에서 lang 무효화.
  function _translatedDom() {
    try {
      var de = document.documentElement;
      if (!de) return false;
      var cls = String((de.className && de.className.baseVal !== undefined ? de.className.baseVal : de.className) || "");
      if (/(^|\s)translated-(ltr|rtl)(\s|$)/.test(cls)) return true;
      if (de.classList && (de.classList.contains("translated-ltr") || de.classList.contains("translated-rtl"))) return true;
      if (document.querySelector && document.querySelector(".goog-te-banner-frame,#goog-gt-tt,html[class*='translated-']")) return true;
    } catch (e) {}
    return false;
  }
  // v71 STEP1: 통화 로케일 추론 — 위 단계가 모두 비었을 때 로케일 기본값으로 채운다(무근거 추정
  //   금지: 명시 로케일 힌트(html lang·경로 /kr·/jp)와 도메인 TLD만 근거로 인정). 못 정하면 빈 통화 유지.
  //   v83 STEP1: opts.ignoreLang=true(번역된 DOM)면 html lang 근거를 **완전 무효화**(경로·TLD만 인정).
  function _localeCurrency(opts) {
    var host = "", path = "", lang = "";
    try { host = (location.hostname || "").toLowerCase(); path = (location.pathname || "").toLowerCase(); } catch (e) {}
    try { lang = ((document.documentElement && document.documentElement.lang) || "").toLowerCase(); } catch (e) {}
    if (opts && opts.ignoreLang) lang = "";
    var hint = lang + " " + path + " " + host;
    // 명시 로케일 힌트(언어/경로) 최우선.
    if (/(^|[^a-z])ko(-|[^a-z]|$)|\/kr(\/|$|-)|(^|\.)kr\./.test(hint)) return "KRW";
    if (/(^|[^a-z])ja(-|[^a-z]|$)|\/jp(\/|$|-)|(^|\.)jp\./.test(hint)) return "JPY";
    if (/(^|[^a-z])zh(-|[^a-z]|$)|(^|\.)cn\./.test(hint)) return "CNY";
    // 도메인 TLD/레지스트리 기본값.
    if (/(^|\.)(taobao|tmall|1688)\.com$/.test(host)) return "CNY";
    if (/(^|\.)amazon\.co\.jp$/.test(host) || /(^|\.)rakuten\.(co\.jp|com)$/.test(host)
        || /(^|\.)yoshidakaban\.com$/.test(host) || /yahoo\.co\.jp$/.test(host)) return "JPY";
    if (/(^|\.)amazon\.co\.uk$/.test(host)) return "GBP";
    if (/(^|\.)amazon\.(de|fr|it|es|nl)$/.test(host)) return "EUR";
    if (/(^|\.)amazon\.[a-z.]+$/.test(host)) return "USD";   // amazon.com 등 기본 USD
    return "";
  }
  function _priceSanity(price, currency) {
    var warnings = [], status = "";
    var v = parseFloat(String(price || "").replace(/,/g, ""));
    if (!(v > 0)) return { price: "", currency: currency || "", status: "needs_check", warnings: ["가격을 확실히 읽지 못했어요"] };
    if (!currency) { status = "needs_check"; warnings.push("통화를 확인하지 못했어요"); }
    // 비상식 하한: 통화별 최소 상식가. 재고/리뷰 숫자 오인(예: 9 KRW) 저장 거부.
    var MIN = { KRW: 100, JPY: 10, CNY: 1, USD: 0.5, EUR: 0.5, GBP: 0.5 };
    if (currency && MIN[currency] != null && v < MIN[currency]) {
      status = "needs_check"; warnings.push("가격이 비상식적으로 낮아요(" + currency + " " + v + ") — 재고/쿠폰 숫자 오인 가능");
    }
    return { price: String(price), currency: currency || "", status: status, warnings: warnings };
  }

  // ── 오케스트레이션 ────────────────────────────────────────
  function kgpExtractProduct() {
    var warnings = [], source = "json";
    var j = {};
    try { j = _fromJson(); } catch (e) { j = { ok: false, images: [], detailImages: [], options: [], skus: [], specs: [], reviews: [] }; }

    // v60 STEP1: 타이틀 우선순위 = 어댑터 지정 셀렉터 → ld+json/state name(Tier1) → 본문 h1(우리 UI·패널 제외)
    //   → og:title → document.title(최후). 삽입 UI h1('Chat history' 등) 오염 차단.
    var at = _adapterTitle();
    var h1t = _cleanH1();
    var ogt = _meta("og:title");
    // v65 STEP1: 순수 사이트/브랜드명("Temu" 등)은 상품명이 아니다 — 후보에서 배제(제목 'Temu' 재발 금지).
    var _cands = [{ v: at, s: "adapter" }, { v: j.title, s: "tier1" }, { v: h1t, s: "tier2" },
      { v: ogt, s: "tier3" }, { v: (document.title || ""), s: "tier3" }];
    var title = "", titleSrc = "none";
    for (var _ti = 0; _ti < _cands.length; _ti++) {
      var _c = String(_cands[_ti].v || "").replace(/\s+/g, " ").trim();
      if (_c && !_isBareSiteName(_c)) { title = _c; titleSrc = _cands[_ti].s; break; }
    }
    title = _sanitizeTitle(title, location.href);   // v76 STEP1: 사이트명 접두/접미 제거(전 마켓 공통)
    var price = j.price || "", currency = j.currency || "";
    // v83 STEP1: 통화 근거(tier1 명시 필드 / symbol 표시 기호) — 사다리 판정에 쓴다.
    var currencySrc = currency ? (j.currencySrc || "symbol") : "";
    // v78 STEP4: 가격 출처(어댑터 패리티) — tier1(state JSON)·buybox(어댑터 스코프)·tier2(제네릭 휴리스틱)·none.
    //   실기기 아마존은 state JSON 미캡처(tier1 빈값)라 buybox 어댑터가 현재가를 읽는데, 예전엔 그 provenance를
    //   버리고 fieldSources가 무조건 'tier2'로 라벨 → '어댑터 매치인데 tier2' 모순. 여기서 실제 출처를 보존한다.
    var priceSrc = j.price ? "tier1" : "";
    var images = (j.images || []).slice(), detailImages = (j.detailImages || []).slice();
    var options = (j.options || []).slice(), skus = (j.skus || []).slice(), specs = _cleanSpecs(j.specs || []);
    var reviews = (j.reviews || []).slice(), rating = j.rating || "", reviewCount = j.reviewCount || "";
    // v83 STEP2: 알리 옵션 소생 — tier1(state)이 비면 DOM sku-item 어댑터로. 값이 있으면 그 값 각각을 sku로도
    //   등록한다(스와치=실제 선택 가능한 변형. 가격은 미상이라 빈값 — 가짜 가격 금지).
    if (_aliHost() && !options.length) {
      var _ao = [];
      try { _ao = _aliOptions(); } catch (e) { _ao = []; }
      if (_ao.length) {
        options = _ao;
        if (!skus.length) {
          _ao.forEach(function (o) { (o.values || []).forEach(function (v) { skus.push({ spec: [v], price: "", currency: "" }); }); });
        }
      }
    }
    var description = "", descSource = "";   // v78 STEP3: 소스 사다리로 채움(어댑터>ldjson>meta)

    var needDom = !price || images.length === 0;
    if (needDom) {
      source = j.ok ? "json+dom" : "dom";
      try {
        if (!price) { var dp = _domPrice(); if (dp) { price = dp.price; currency = dp.currency; if (currency) currencySrc = "symbol"; priceSrc = (dp.scope || dp.src === "buybox") ? "buybox" : "tier2"; } }
        if (images.length === 0) { var di = _domImages(); images = di.images; if (!detailImages.length) detailImages = di.detailImages; }
        if (!options.length) options = _domOptions();
        if (!specs.length) specs = _domSpecs();
      } catch (e) { warnings.push("DOM 폴백 중 일부 실패"); }
    }

    // v57 STEP3: 상세이미지는 **갤러리와 독립** 수집 — Tier1이 갤러리를 채웠어도 상세(더보기 접힘)는
    //   비어 있을 수 있다. 숨김 컨테이너(display:none 포함 — querySelectorAll은 포함)의 data-src까지 긁는다.
    var detailFold = _hasDetailFold();
    if (detailImages.length === 0) {
      try { var di2 = _domImages(); if (di2.detailImages && di2.detailImages.length) detailImages = di2.detailImages; } catch (e) {}
    }
    if (!options.length) { try { options = _domOptions(); } catch (e) {} }
    if (!options.length && _aliHost()) { try { options = _aliOptions(); } catch (e) {} }
    if (!specs.length) { try { specs = _domSpecs(); } catch (e) {} }
    options = _dropNumericColorValues(options);   // v83 STEP3: 색상 축의 순수 숫자값('1') 제거(tier1·tier2 공통)
    // v78 STEP3: 상세설명 소스 사다리(재배선) — ① 어댑터 상세(DOM: feature-bullets+A+·테무 상세영역) →
    //   ② ld+json/state description(Tier1) → ③ **meta description은 최후 폴백**(SEO 'Buy …') + desc_source=meta
    //   표기(품질 낮음 신호). '가격/이미지와 독립' 수집(Tier1이 채워도 상세는 빌 수 있음).
    try {
      var _ad = _adapterDetailText();
      if (_ad && _ad.length > 20) { description = _ad; descSource = "adapter"; }
    } catch (e) {}
    // v79 STEP6: Tier1(state)·meta 후보가 마켓 SEO/필러면 거부(빈 상세 + 편집 AI 초안, 정직). 어댑터는 신뢰.
    if (!description && j.description && !_isFillerDesc(j.description)) { description = _stripHtmlNoise(j.description); descSource = j.ok ? "tier1" : "ldjson"; }
    if (!description) { try { var _m = _metaDescription(); if (_m && !_isFillerDesc(_m)) { description = _stripHtmlNoise(_m); descSource = "meta"; } } catch (e) {} }
    // v78 STEP3: detail_specs(스펙 표)가 있으면 desc_text에 병합(사용자가 상세에서 스펙까지 한눈에).
    if (specs.length) {
      try {
        var _specTxt = specs.slice(0, 40).map(function (s) { return "· " + s.k + ": " + s.v; }).join("\n");
        if (_specTxt && (!description || description.indexOf(_specTxt.split("\n")[0]) < 0)) {
          description = (description ? description + "\n\n" : "") + _specTxt;
          if (!descSource) descSource = "specs";
        }
      } catch (e) {}
    }
    // v76 STEP6: 리뷰도 **초기 JSON과 독립** 수집 — 아마존 등 리뷰가 JSON-LD/state에 없고 DOM에만 렌더될 때,
    //   페이지에 이미 있는 리뷰 섹션 상위 텍스트를 읽는다(추가 요청 0·존재분만). JSON 리뷰가 부족하면 병합·중복제거.
    if (reviews.length < 3) {
      try {
        var _seenR = {}; reviews.forEach(function (r) { if (r && r.text) _seenR[String(r.text).slice(0, 40)] = 1; });
        var dr = _domReviews();
        for (var _di = 0; _di < dr.length && reviews.length < REVIEW_MAX; _di++) {
          var _k = String(dr[_di].text || "").slice(0, 40);
          if (_k && !_seenR[_k]) { _seenR[_k] = 1; reviews.push(dr[_di]); }
        }
      } catch (e) {}
    }
    // 정직: 더보기 접힘이 남아 있고 상세이미지가 여전히 비었으면 '일부만' 경고(무음 실패 금지).
    if (detailFold && detailImages.length === 0) warnings.push("상세이미지 일부만(더보기 펼침 필요할 수 있어요)");

    // ③ 둘 다 실패 → 부분 수집(가짜 성공 금지)
    var partial = !price && images.length === 0;
    if (partial) { source = "partial"; warnings.push("초기 JSON·DOM 모두에서 핵심 정보를 못 읽어 부분 수집입니다"); }

    // ── v83 STEP1: 통화 사다리 확정 ──────────────────────────────────────
    //   ①tier1 명시 통화 필드(그대로 확정) → ②도메인 고정 테이블 → ③표시 기호 → ④로케일(최후).
    //   기호와 도메인이 **충돌**하면(예: amazon.com에 ₩ 표시) 도메인을 택하되 needs_check로 올려 사람이 확인한다
    //   (임의 확정 = 10배 오등록 위험. 정직 데이터 원칙).
    var translatedDom = false;
    try { translatedDom = _translatedDom(); } catch (e) {}
    var currencySource = currencySrc === "tier1" ? "tier1" : (currency ? "symbol" : "none");
    var currencyConflict = false;
    var domCur = "";
    try { domCur = _domainCurrency(); } catch (e) {}
    if (currencySrc !== "tier1" && domCur) {
      if (!currency) { currency = domCur; currencySource = "domain"; }
      else if (currency === domCur) { currencySource = "domain+symbol"; }
      else {
        var _symCur = currency;
        currency = domCur; currencySource = "domain";
        if (translatedDom) {
          warnings.push("번역된 페이지라 표시 통화(" + _symCur + ") 대신 원문 기준 " + domCur + "으로 저장했어요");
        } else {
          currencyConflict = true;
          warnings.push("표시 통화(" + _symCur + ")와 사이트 기준 통화(" + domCur + ")가 달라요 — 가격을 확인해 주세요");
        }
      }
    }
    if (price && !currency) {
      var lc = ""; try { lc = _localeCurrency({ ignoreLang: translatedDom }); } catch (e) {}
      if (lc) { currency = lc; currencySource = "locale"; }
    }
    if (translatedDom && currencySource === "locale") {
      warnings.push("번역된 페이지예요 — 통화를 확인해 주세요");
    }
    // v74 STEP4: 가격 숫자 정규화(공통) — 후행 점·천단위 제거해 항상 \d+(\.\d+)?. sanity 이전에 봉인.
    price = _normNum(price);
    // 가격 sanity
    var sane = _priceSanity(price, currency);
    var price_status = sane.status || (currencyConflict ? "needs_check" : "");
    price = sane.status === "needs_check" && !sane.price ? "" : sane.price;
    currency = sane.currency;
    warnings = warnings.concat(sane.warnings);

    // v76 STEP3: 라쿠텐은 초기 JSON이 가격+대표1장만 줘 needDom=false여도 갤러리가 1장에 그친다 → 호스트가
    //   라쿠텐이면 DOM 갤러리를 **독립 수집·병합**(갤러리 1→전량) + 상세 본문 이미지 분리. (아마존식 독립 경로.)
    try {
      var _rh = ""; try { _rh = (location.hostname || "").toLowerCase(); } catch (e) {}
      if (/(^|\.)rakuten\.(co\.jp|com)$/.test(_rh)) {
        var rg = _rakutenGallery();
        if (rg.images.length) { rg.images.forEach(function (u) { images.push(u); }); source = (source === "json" ? "json+dom" : source); }
        if (!detailImages.length && rg.detailImages.length) detailImages = rg.detailImages;
      }
    } catch (e) {}

    // 이미지 원본해상도 + 순서 보존 + 중복 제거(이미 uniqPush로 됨). 1번=썸네일.
    var seen = {}, gallery = [];
    images.forEach(function (u) { uniqPush(gallery, seen, u); });
    gallery = _galleryScopeHost(gallery);   // v79 STEP4: 호스트별 갤러리 오염 필터(테무 배너·라쿠텐 타상품)
    // v83 STEP3: 원본 승격 실패(저해상 토큰 잔존) 이미지는 갤러리·상세 양쪽에서 제외 + 정직 경고.
    (function () {
      var _g0 = gallery.length, _d0 = detailImages.length;
      gallery = gallery.filter(function (u) { return !_isLowResImg(u); });
      detailImages = detailImages.filter(function (u) { return !_isLowResImg(u); });
      var _dropped = (_g0 - gallery.length) + (_d0 - detailImages.length);
      if (_dropped > 0) warnings.push("저해상 이미지 " + _dropped + "장 제외(원본 해상도 승격 실패)");
    })();

    // v78 STEP2: 리뷰 메타 정직화 — rating은 (1,5]만(0·1 더미 금지), 아니면 '없음'(빈값). review_count는 실제
    //   추출 리뷰 수 이상(count<reviews면 스테일 '0' 등 → 최소 reviews.length 보정). 가짜 평점/카운트 저장 방지.
    // v83 STEP4: rating 공란인데 리뷰가 있으면 DOM 집계 평점으로 보완(없으면 그대로 공란 — 날조 금지).
    if (!rating && reviews.length) { try { rating = _domRating(); } catch (e) {} }
    (function () {
      var _raw = String(rating == null ? "" : rating).trim();
      var _rn = parseFloat(_raw);
      if (!(_rn > 1 && _rn <= 5)) rating = "";     // 0·1·범위밖 → 없음(정직)
      else rating = _raw;
      var _cn = parseInt(String(reviewCount == null ? "" : reviewCount).replace(/[^\d]/g, ""), 10);
      if (!(_cn > 0)) _cn = 0;
      if (_cn < reviews.length) _cn = reviews.length;   // count ≥ 실제 추출 리뷰 수(불일치 스테일 보정)
      reviewCount = _cn ? String(_cn) : "";
    })();

    try {
      console.log("[고가수집기] 추출 소스=" + source, "| 가격=" + price + " " + currency + "(" + currencySource + ")" + (translatedDom ? "(translated)" : "") + " [" + (priceSrc || "none") + "] (" + (price_status || "ok") + ")",
        "| 갤러리=" + gallery.length + " 상세이미지=" + detailImages.length + " 옵션=" + options.length + " 스펙=" + specs.length + " 리뷰=" + reviews.length + " 평점=" + (rating || "없음") + " 리뷰수=" + (reviewCount || "없음"),
        warnings.length ? "| 경고:" + warnings.join(" / ") : "");
    } catch (e) {}

    // v51: 필드별 추출 Tier — Tier1(캡처 API/초기상태 JSON)·Tier2(렌더 DOM 갤러리·h1)·Tier3(og/meta)·none.
    //   서버 수집 로그에 '어느 Tier가 어느 필드를 줬는지' 표기. 값 없으면 none(가짜 소스 날조 금지).
    var fieldSources = {
      title: titleSrc,
      price: priceSrc ? priceSrc : (price ? "tier2" : "none"),   // v78 STEP4: buybox 어댑터 매치 시 'buybox'(모순 해소)
      images: (j.images && j.images.length) ? "tier1" : (gallery.length ? "tier2" : "none"),
      options: (j.options && j.options.length) ? "tier1" : (options.length ? "tier2" : "none"),
      description: j.description ? "tier1" : (description ? "tier2" : "none"),
      detail_images: (j.detailImages && j.detailImages.length) ? "tier1" : (detailImages.length ? "tier2" : "none"),
      reviews: ((j.reviews && j.reviews.length) || j.rating || j.reviewCount) ? "tier1" : (reviews.length ? "tier2" : "none")   // v76 STEP6: DOM 리뷰=tier2
    };

    var out = {
      url: location.href,
      title: String(title || "").slice(0, 300),
      price: price, currency: currency, price_status: price_status,
      // v83 STEP1: 통화 근거(tier1|domain|domain+symbol|symbol|locale|none)와 번역 DOM 여부 — 진단·수집 카드 안내용.
      currency_source: currencySource, translated_dom: translatedDom,
      image: gallery[0] || "",
      images: gallery, gallery_images: gallery, detail_images: detailImages,
      detail_fold: detailFold,          // v57 STEP3: 상세 '더보기' 접힘 잔존 여부(정직 표기용)
      thumbnail: gallery[0] || "",
      options: options, skus: skus,
      description: description, detail_specs: specs,
      desc_text: description, desc_images: detailImages,   // v60 STEP2: 상세 텍스트/이미지 명시 분리(브리프 명명)
      desc_source: descSource,   // v78 STEP3: 상세설명 출처(adapter>tier1/ldjson>meta>specs) — meta면 품질 낮음 신호
      reviews: reviews, rating: rating, review_count: reviewCount,
      source: source, partial: partial, warnings: warnings,
      field_sources: fieldSources,
      // v54 STEP2: 자가발견 채택 응답 URL 패턴(sources=tier1:{URL}) — Tier1이 실제 기여했을 때만.
      tier1_source: (j.ok && fieldSources.price === "tier1") ? (global.__kgpTier1Url || "") : "",
      jsonld: _jsonLd(),
      collected_at: new Date().toISOString()
    };
    return out;
  }

  // v57 STEP3: 상세 '더보기' 접힘을 프로그램적으로 펼친다 — 클릭 → MutationObserver로 새 img 대기(최대 3s).
  //   상세이미지가 fold 뒤에 lazy-mount되는 테무 대응. 접힘 없으면 즉시 콜백(정상 페이지 지연 0).
  //   추가 네트워크 요청 없음(페이지 자체 로더가 이미지 채움). cb는 상세이미지 증가 여부와 무관하게 1회 호출.
  function kgpRevealDetailFolds(cb) {
    var done = false;
    function finish() { if (done) return; done = true; try { cb && cb(); } catch (e) {} }
    var btns;
    try { btns = _foldButtons(); } catch (e) { btns = []; }
    if (!btns || !btns.length) { finish(); return; }
    var scope = null;
    try { scope = document.querySelector('[class*="detail" i],[class*="description" i],[class*="goods-desc" i],[class*="goodsDesc" i],[class*="decoration" i],[class*="richtext" i],[class*="rich-text" i]') || document.body; } catch (e) { scope = document.body; }
    var before = 0;
    try { before = scope.querySelectorAll("img").length; } catch (e) {}
    var mo = null, timer = null;
    function stop() { try { if (mo) mo.disconnect(); } catch (e) {} if (timer) clearTimeout(timer); finish(); }
    try {
      mo = new MutationObserver(function () {
        var now = 0; try { now = scope.querySelectorAll("img").length; } catch (e) {}
        if (now > before) stop();               // 새 이미지 mount 확인 → 조기 종료
      });
      mo.observe(scope, { childList: true, subtree: true, attributes: true, attributeFilter: ["src", "data-src"] });
    } catch (e) {}
    // 접힘 버튼 클릭(최대 3개 — 여러 섹션 대응). 스크롤 유발 lazy도 커버.
    for (var i = 0; i < btns.length && i < 3; i++) {
      try { btns[i].scrollIntoView({ block: "center" }); } catch (e) {}
      try { btns[i].click(); } catch (e) {}
    }
    timer = setTimeout(stop, 3000);              // 최대 3초 후 강제 종료(무한 대기 금지)
  }

  // v65 STEP1: 렌더 완료 대기 — 정본 경로(렌더된 DOM 추출)의 게이트. 가격 패턴 텍스트 + 메인 이미지(≥200px)
  //   로드를 감지하면 준비 완료. 최대 maxMs(기본 8초) 초과 시 '부분'(있는 것만)으로 진행. 셀렉터 의존 최소.
  function _renderReady() {
    var priceOk = false, imgOk = false;
    try { var p = _domPrice(); priceOk = !!(p && p.price); } catch (e) {}
    try {
      var imgs = document.querySelectorAll("img");
      for (var i = 0; i < imgs.length; i++) {
        var im = imgs[i];
        if (((im.naturalWidth || im.width || 0) >= 200) && ((im.naturalHeight || im.height || 0) >= 200)) { imgOk = true; break; }
      }
    } catch (e) {}
    return { priceOk: priceOk, imgOk: imgOk, ready: priceOk && imgOk };
  }
  // 준비될 때까지 폴링(250ms). ready면 partial=false, maxMs 초과면 partial=true로 cb 호출(무한대기 금지).
  function kgpWaitRendered(cb, maxMs) {
    var intervalMs = 250;
    var maxTicks = Math.max(1, Math.ceil(((typeof maxMs === "number" ? maxMs : 8000)) / intervalMs));
    var ticks = 0, done = false;
    function finish(partial) { if (done) return; done = true; try { cb && cb({ partial: !!partial, ready: !partial }); } catch (e) {} }
    function tick() {
      if (done) return;
      var r;
      try { r = _renderReady(); } catch (e) { r = { ready: false }; }
      if (r.ready) { finish(false); return; }
      ticks++;
      if (ticks >= maxTicks) { finish(true); return; }   // 8초 초과 → 부분 표기
      setTimeout(tick, intervalMs);
    }
    tick();
  }

  global.kgpExtractProduct = kgpExtractProduct;
  global.kgpRevealDetailFolds = kgpRevealDetailFolds;
  global.kgpWaitRendered = kgpWaitRendered;
  global._kgpRenderReady = _renderReady;   // 테스트/진단용
  if (typeof module !== "undefined" && module.exports) module.exports = { kgpExtractProduct: kgpExtractProduct, kgpRevealDetailFolds: kgpRevealDetailFolds, kgpWaitRendered: kgpWaitRendered,
    // v82: 순수 헬퍼(DOM 무의존) 하네스 노출 — 계약 검증용(브라우저 경로 불변).
    _test: { hiRes: hiRes, skusToOptions: _skusToOptions, collectSkuSpecs: _collectSkuSpecs, isBadOptValue: _isBadOptValue, isBadOptAxis: _isBadOptAxis, isBadOptFallbackValue: _isBadOptFallbackValue,
      // v83: 통화 사다리·이미지 승격·스펙 위생 계약 검증용.
      domainCurrency: _domainCurrency, translatedDom: _translatedDom, localeCurrency: _localeCurrency, parsePriceStr: parsePriceStr,
      isLowResImg: _isLowResImg, cleanSpecs: _cleanSpecs, stripHtmlNoise: _stripHtmlNoise, aliOptions: _aliOptions,
      dropNumericColorValues: _dropNumericColorValues, domRating: _domRating } };
})(typeof window !== "undefined" ? window : this);
