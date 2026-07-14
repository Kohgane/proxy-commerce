#!/usr/bin/env node
/* scripts/extract_harness.js — v70 STEP5: 실페이지 추출 하네스(오너 로컬 · jsdom).
 *
 * fixtures/realpages/<name>.html 에 라이브 kgp-extractor.js를 물려 kgpExtractProduct()를 실행하고
 * <name>.expected.json 스냅샷과 비교한다. CI 게이트는 Playwright(tests/test_v70_realpage_harness.py)이며,
 * 이 스크립트는 오너가 로컬에서 jsdom으로 빠르게 돌려보는 도구다(오너 채팅 하네스와 동형).
 *
 * 사용:  npm i -D jsdom  &&  node scripts/extract_harness.js
 * jsdom 미설치 시 정직하게 안내하고 종료(가짜 통과 금지).
 */
"use strict";
const fs = require("fs");
const path = require("path");

let JSDOM;
try { JSDOM = require("jsdom").JSDOM; }
catch (e) {
  console.log("[하네스] jsdom 미설치 — 로컬 실행하려면 `npm i -D jsdom`.");
  console.log("[하네스] CI 게이트는 Playwright: `pytest tests/test_v70_realpage_harness.py`.");
  process.exit(0);
}

const ROOT = path.resolve(__dirname, "..");
const EX = fs.readFileSync(path.join(ROOT, "extensions/chrome-collector/kgp-extractor.js"), "utf-8");
const FIX = path.join(ROOT, "fixtures/realpages");

function loadFixtures() {
  return fs.readdirSync(FIX).filter((f) => f.endsWith(".expected.json"))
    .map((f) => f.replace(".expected.json", ""));
}

function run(name) {
  const spec = JSON.parse(fs.readFileSync(path.join(FIX, name + ".expected.json"), "utf-8"));
  const html = fs.readFileSync(path.join(FIX, name + ".html"), "utf-8");
  const dom = new JSDOM(html, { url: spec.url, runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  // kgp-extractor.js를 이 window 컨텍스트에서 실행(global=window).
  const fn = new w.Function("global", EX + "\n;return window.kgpExtractProduct;");
  const extract = fn(w);
  const r = extract();
  return check(name, spec, r);
}

function check(name, spec, r) {
  const fails = [];
  const opts = {};
  (r.options || []).forEach((o) => { opts[o.name] = o.values; });
  if (spec.title_contains && String(r.title || "").indexOf(spec.title_contains) < 0) fails.push("title !~ " + spec.title_contains + " (" + r.title + ")");
  if (spec.price != null && String(r.price || "") !== spec.price) fails.push("price " + r.price + " != " + spec.price);
  if (spec.currency != null && String(r.currency || "") !== spec.currency) fails.push("currency " + r.currency + " != " + spec.currency);
  Object.keys(spec.options || {}).forEach((k) => {
    if (JSON.stringify(opts[k]) !== JSON.stringify(spec.options[k])) fails.push("option[" + k + "] " + JSON.stringify(opts[k]) + " != " + JSON.stringify(spec.options[k]));
  });
  (spec.no_option_names || []).forEach((k) => { if (opts[k]) fails.push("option[" + k + "] 존재하면 안 됨"); });
  const imgs = r.images || [];
  if (spec.images_min != null && imgs.length < spec.images_min) fails.push("images " + imgs.length + " < " + spec.images_min);
  if (spec.images_max != null && imgs.length > spec.images_max) fails.push("images " + imgs.length + " > " + spec.images_max);
  (spec.images_exclude_substr || []).forEach((s) => { if (imgs.some((u) => u.indexOf(s) >= 0)) fails.push("images 혼입 " + s); });
  if (spec.description_contains && String(r.description || "").indexOf(spec.description_contains) < 0) fails.push("desc !~ " + spec.description_contains);
  return fails;
}

let bad = 0;
loadFixtures().forEach((name) => {
  try {
    const fails = run(name);
    if (fails.length) { bad++; console.log("✗ " + name + "\n    " + fails.join("\n    ")); }
    else console.log("✓ " + name);
  } catch (e) { bad++; console.log("✗ " + name + " — " + (e && e.message)); }
});
console.log(bad ? ("[하네스] " + bad + "개 픽스처 불일치") : "[하네스] 전 픽스처 그린");
process.exit(bad ? 1 : 0);
