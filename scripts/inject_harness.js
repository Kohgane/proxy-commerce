#!/usr/bin/env node
/* scripts/inject_harness.js — v84 STEP1: UI 주입 사활(死活) 하네스.
 *
 * 추출(extract_harness.js)은 "값이 맞나"를 보지만, 오너가 실제로 겪은 사고는 **버튼이 아예 안 뜨는 것**이었다.
 * 값 계약이 전부 그린인데 화면엔 아무것도 없는 상태가 통과해 버린다 — 그 구멍을 막는 하네스다.
 *
 * 하는 일: manifest content_scripts(ISOLATED) 순서대로 실제 스크립트를 jsdom 문서에 물리고, chrome API를
 * 최소 스텁으로 채운 뒤 **주입 결과**를 검사한다:
 *   (a) 스타일 주입 — #kgp-style (kgpEnsureStyles 호출 시)
 *   (b) 상세 페이지: FAB 존재 + 인라인 position === 'fixed'  ← all:initial 격리가 위치를 삼키면 여기서 잡힌다
 *   (c) 목록 페이지: 벌크바 존재 + 타일 버튼 CSS 적용
 * 실패는 사유와 함께 종료코드 1. CI 게이트는 tests/test_v84_injection_harness.py.
 *
 * 사용: npm i -D jsdom && node scripts/inject_harness.js
 */
"use strict";
const fs = require("fs");
const path = require("path");

let JSDOM;
try { JSDOM = require("jsdom").JSDOM; }
catch (e) {
  console.log("[주입하네스] jsdom 미설치 — `npm i -D jsdom`. CI 게이트는 pytest(test_v84_injection_harness.py).");
  process.exit(0);
}

const ROOT = path.resolve(__dirname, "..");
const EXT = path.join(ROOT, "extensions/chrome-collector");
const MANIFEST = JSON.parse(fs.readFileSync(path.join(EXT, "manifest.json"), "utf-8"));

// manifest가 선언한 ISOLATED 월드 스크립트 순서 그대로(하드코딩 금지 — manifest가 단일 소스).
function isolatedScripts() {
  const out = [];
  (MANIFEST.content_scripts || []).forEach((cs) => {
    if ((cs.world || "ISOLATED") !== "ISOLATED") return;
    (cs.js || []).forEach((j) => out.push(j));
  });
  return out;
}

// 최소 chrome 스텁 — content_script가 실제로 쓰는 표면만. 실패를 숨기지 않도록 조용히 삼키지 않는다.
function makeChrome(win, store) {
  const listeners = [];
  return {
    runtime: {
      id: "kgp-harness-ext",
      lastError: null,
      getManifest: () => MANIFEST,
      getURL: (p) => "chrome-extension://kgp-harness-ext/" + p,
      sendMessage: (msg, cb) => {
        // 수집·설정 조회는 하네스에서 호출되지 않는 게 정상. 호출되면 빈 응답으로 진행(무한대기 방지).
        if (typeof cb === "function") setTimeout(() => cb({ ok: false }), 0);
      },
      onMessage: { addListener: () => {} },
    },
    storage: {
      local: {
        get: (keys, cb) => {
          const out = {};
          const list = Array.isArray(keys) ? keys : (typeof keys === "string" ? [keys] : Object.keys(keys || {}));
          list.forEach((k) => { if (k in store) out[k] = store[k]; });
          if (typeof cb === "function") cb(out);
        },
        set: (obj, cb) => { Object.assign(store, obj); if (typeof cb === "function") cb(); },
      },
      sync: { get: (k, cb) => { if (typeof cb === "function") cb({}); } },
      onChanged: { addListener: (fn) => listeners.push(fn) },
    },
    _fireChange: (changes) => listeners.forEach((fn) => { try { fn(changes, "local"); } catch (e) {} }),
  };
}

function run(name, html, url, opts) {
  opts = opts || {};
  const dom = new JSDOM(html, { url, runScripts: "outside-only", pretendToBeVisual: true });
  const win = dom.window;
  const store = opts.store || {};
  win.chrome = makeChrome(win, store);
  // jsdom엔 matchMedia가 없다 → 실브라우저 기본(모션 허용)으로 스텁. reduced-motion 케이스는 opts.rm로.
  win.matchMedia = win.matchMedia || ((q) => ({ matches: !!opts.rm && /reduce/.test(q), media: q, addListener() {}, removeListener() {} }));

  const errors = [];
  win.addEventListener("error", (e) => errors.push(String(e.message || e)));

  for (const rel of isolatedScripts()) {
    const code = fs.readFileSync(path.join(EXT, rel), "utf-8");
    try {
      win.eval(code);
    } catch (e) {
      errors.push(rel + ": " + (e && e.message));
      // 로드 실패는 치명 — 이후 스크립트는 어차피 의미 없다.
      break;
    }
  }
  return { win, doc: win.document, errors, store };
}

// 인라인 스타일에서 실제 적용된 값을 읽는다(모듈 격리 all:initial이 삼켰는지 판정).
function inlineProp(el, prop) {
  if (!el) return "";
  try { return el.style.getPropertyValue(prop) || ""; } catch (e) { return ""; }
}

const DETAIL_HTML = `<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>테스트 상세</title></head>
<body><h1 class="item_name">테스트 상품</h1><div class="item_price">3,980円</div>
<div class="item_gallery"><img src="https://tshop.r10s.jp/x/a.jpg" width="500" height="500" alt="1"></div></body></html>`;

// 상품 타일 12개(제목+이미지+가격+상세 URL) — 목록 감지·벌크바 주입 검사용.
const LIST_TILES = Array.from({ length: 12 }, (_, i) => `
  <li class="searchresultitem">
    <a href="https://item.rakuten.co.jp/shop${i}/item-${i}/"><img src="https://tshop.r10s.jp/shop${i}/thumb.jpg" width="200" height="200" alt="상품 ${i} 이름"></a>
    <div class="title"><a href="https://item.rakuten.co.jp/shop${i}/item-${i}/">상품 ${i} 이름 길게</a></div>
    <div class="price">${1000 + i}円</div>
  </li>`).join("");
const LIST_HTML = `<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>검색 결과</title></head>
<body><div class="searchresultitems"><ul>${LIST_TILES}</ul></div></body></html>`;

const CASES = [
  {
    name: "상세(라쿠텐) — FAB 주입",
    html: DETAIL_HTML,
    url: "https://item.rakuten.co.jp/tsumugi/bag-ai-01/",
    check: (r) => {
      const fails = [];
      const fab = r.doc.getElementById("kgp-collect-fab");
      if (!fab) { fails.push("FAB 미주입(#kgp-collect-fab 없음)"); return fails; }
      const pos = inlineProp(fab, "position");
      if (pos !== "fixed") fails.push("FAB position=" + (pos || "(빈값)") + " != fixed — all:initial 격리가 위치를 삼킴");
      if (!inlineProp(fab, "z-index")) fails.push("FAB z-index 미설정");
      if (!inlineProp(fab, "top") && !inlineProp(fab, "bottom")) fails.push("FAB 세로 앵커 미설정");
      return fails;
    },
  },
  {
    name: "상세 — 스타일 주입(kgpEnsureStyles)",
    html: DETAIL_HTML,
    url: "https://item.rakuten.co.jp/tsumugi/bag-ai-01/",
    check: (r) => {
      const fails = [];
      try { r.win.eval("kgpEnsureStyles()"); } catch (e) { fails.push("kgpEnsureStyles 호출 실패: " + e.message); return fails; }
      if (!r.doc.getElementById("kgp-style")) fails.push("#kgp-style 미주입");
      return fails;
    },
  },
  {
    name: "목록(라쿠텐 검색) — 벌크바 주입",
    html: LIST_HTML,
    url: "https://search.rakuten.co.jp/search/mall/craighill/",
    check: (r) => {
      const fails = [];
      const bar = r.doc.getElementById("kgp-collect-bar");
      if (!bar) { fails.push("벌크바 미주입(#kgp-collect-bar 없음)"); return fails; }
      const pos = inlineProp(bar, "position");
      if (pos !== "fixed") fails.push("벌크바 position=" + (pos || "(빈값)") + " != fixed");
      const badges = r.doc.querySelectorAll(".kgp-card-badge, .kgp-card-quick");
      if (!badges.length) fails.push("타일 버튼 0개(카드 감지 실패)");
      return fails;
    },
  },
];

let bad = 0;
CASES.forEach((c) => {
  let r;
  try { r = run(c.name, c.html, c.url, c.opts); }
  catch (e) { bad++; console.log("✗ " + c.name + " — 실행 실패: " + (e && e.message)); return; }
  const fails = (r.errors.length ? ["스크립트 오류: " + r.errors.join(" | ")] : []).concat(c.check(r) || []);
  if (fails.length) { bad++; console.log("✗ " + c.name + "\n    " + fails.join("\n    ")); }
  else console.log("✓ " + c.name);
});
console.log(bad ? ("[주입하네스] " + bad + "건 실패 — 화면에 안 뜨는 상태") : "[주입하네스] 전 케이스 그린");
process.exit(bad ? 1 : 0);
