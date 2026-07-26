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
  (spec.title_excludes || []).forEach((s) => { if (String(r.title || "").indexOf(s) >= 0) fails.push("title 오염 " + s + " (" + r.title + ")"); });
  if (spec.price != null && String(r.price || "") !== spec.price) fails.push("price " + r.price + " != " + spec.price);
  if (spec.currency != null && String(r.currency || "") !== spec.currency) fails.push("currency " + r.currency + " != " + spec.currency);
  // v83 STEP1: 통화 근거(사다리 단계)·번역 DOM 플래그 계약.
  if (spec.currency_source != null && String(r.currency_source || "") !== spec.currency_source) fails.push("currency_source " + r.currency_source + " != " + spec.currency_source);
  if (spec.translated_dom != null && !!r.translated_dom !== !!spec.translated_dom) fails.push("translated_dom " + !!r.translated_dom + " != " + spec.translated_dom);
  Object.keys(spec.options || {}).forEach((k) => {
    if (JSON.stringify(opts[k]) !== JSON.stringify(spec.options[k])) fails.push("option[" + k + "] " + JSON.stringify(opts[k]) + " != " + JSON.stringify(spec.options[k]));
  });
  (spec.no_option_names || []).forEach((k) => { if (opts[k]) fails.push("option[" + k + "] 존재하면 안 됨"); });
  // v83 STEP2/3: 옵션 최소 개수 · sku 최소 개수 · 어떤 축에도 있으면 안 되는 값(색상 '1' 등).
  if (spec.options_min != null && (r.options || []).length < spec.options_min) fails.push("options " + (r.options || []).length + " < " + spec.options_min);
  if (spec.skus_min != null && (r.skus || []).length < spec.skus_min) fails.push("skus " + (r.skus || []).length + " < " + spec.skus_min);
  (spec.option_values_exclude || []).forEach((bad) => {
    (r.options || []).forEach((o) => { if ((o.values || []).indexOf(bad) >= 0) fails.push("option[" + o.name + "]에 금지값 '" + bad + "'"); });
  });
  const imgs = r.images || [];
  if (spec.images_min != null && imgs.length < spec.images_min) fails.push("images " + imgs.length + " < " + spec.images_min);
  if (spec.images_max != null && imgs.length > spec.images_max) fails.push("images " + imgs.length + " > " + spec.images_max);
  (spec.images_exclude_substr || []).forEach((s) => { if (imgs.some((u) => u.indexOf(s) >= 0)) fails.push("images 혼입 " + s); });
  const det = r.detail_images || [];
  if (spec.detail_images_min != null && det.length < spec.detail_images_min) fails.push("detail_images " + det.length + " < " + spec.detail_images_min);
  (spec.detail_images_exclude_substr || []).forEach((s) => { if (det.some((u) => u.indexOf(s) >= 0)) fails.push("detail_images 혼입 " + s); });
  if (spec.description_contains && String(r.description || "").indexOf(spec.description_contains) < 0) fails.push("desc !~ " + spec.description_contains);
  // v83 STEP2/3: 상세설명에 있으면 안 되는 것(판매자 블록·HTML 주석·CSS 조각) + 스펙 위생.
  (spec.desc_excludes || []).forEach((s) => { if (String(r.desc_text || r.description || "").indexOf(s) >= 0) fails.push("desc 오염 " + s); });
  (spec.desc_text_contains || []).forEach((s) => { if (String(r.desc_text || r.description || "").indexOf(s) < 0) fails.push("desc !~ " + s); });
  (spec.specs_exclude_substr || []).forEach((s) => {
    if ((r.detail_specs || []).some((sp) => String(sp.k || "").indexOf(s) >= 0 || String(sp.v || "").indexOf(s) >= 0)) fails.push("detail_specs 오염 " + s);
  });
  if (spec.rating != null && String(r.rating || "") !== spec.rating) fails.push("rating " + r.rating + " != " + spec.rating);
  // v84.1 STEP A: 재고 상태 + 가격에 절대 들어오면 안 되는 값(장바구니 합계 오염).
  if (spec.stock_status != null && String(r.stock_status || "") !== spec.stock_status) fails.push("stock_status " + r.stock_status + " != " + spec.stock_status);
  (spec.price_excludes || []).forEach((bad) => { if (String(r.price || "").indexOf(bad) >= 0) fails.push("price 오염 " + bad); });
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
