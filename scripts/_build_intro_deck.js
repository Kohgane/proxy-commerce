/**
 * scripts/_build_intro_deck.py 대응 노드 스크립트 — K1a 카카오 연동대행사 신청 소개서.
 *
 * 디자인 v3 토큰 승계(app.css :root): 먹 #1A1714 · 한지 #F5EFE3 · 종이 #FBF8F1 ·
 * 금 #C9A24B · 청록 #119A8E · 주황 #F5821F(강조 1점) · 라인 #E6DECB.
 * "디지털 한지 위의 금속활자" — 어두운 표지·마무리, 밝은 본문(샌드위치).
 *
 * 사실만 담는다. 없는 수치는 [오너 기입]. 발명 0.
 */
const pptx = require("pptxgenjs");
const fs = require("fs");

// ★ 콘텐츠 단일 소스 — PDF 생성기(build_intro_deck.py)와 **같은 JSON**을 읽는다.
//   문구를 두 곳에 두면 한쪽만 고쳐진다(이번 세션 최다 결함).
const C = JSON.parse(fs.readFileSync("docs/apply/intro_content.json", "utf-8"));

const INK = "1A1714", INK2 = "2A241E", HANJI = "F5EFE3", PAPER = "FBF8F1";
const GOLD = "C9A24B", GOLDSOFT = "E0C588", TEAL = "119A8E", ORANGE = "F5821F";
const LINE = "E6DECB", MUTED = "8A8275", INKSOFT = "3A352E";
const SERIF = "Cambria", SANS = "Calibri";

const p = new pptx();
p.layout = "LAYOUT_WIDE";                 // 13.3 x 7.5
const W = 13.3, H = 7.5, M = 0.75;

const notes = (s, t) => s.addNotes(t);

/** 어두운 슬라이드 공통 바탕(표지·마무리). */
function darkSlide() {
  const s = p.addSlide();
  s.background = { color: INK };
  return s;
}
/** 밝은 본문 슬라이드 + 제목. */
function lightSlide(kicker, title) {
  const s = p.addSlide();
  s.background = { color: PAPER };
  s.addText(kicker, {
    x: M, y: 0.45, w: 8, h: 0.3, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 11, bold: true, charSpacing: 2, color: GOLD,
  });
  s.addText(title, {
    x: M, y: 0.8, w: W - M * 2, h: 0.8, isTextBox: true, margin: 0,
    fontFace: SERIF, fontSize: 34, bold: true, color: INK,
  });
  return s;
}
/** 카드 — 배경 톤 + 그림자. 테두리 줄무늬 금지. */
function card(s, x, y, w, h, fill) {
  s.addShape(p.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08,
    fill: { color: fill || "FFFFFF" }, line: { color: LINE, width: 0.75 },
    shadow: { type: "outer", angle: 90, blur: 12, offset: 2, opacity: 0.08, color: INK },
  });
}
/** 번호 원형 배지 — 다리를 건너는 순서(시그니처). */
function stepDot(s, x, y, n, color) {
  s.addShape(p.ShapeType.ellipse, { x, y, w: 0.42, h: 0.42, fill: { color: color || INK } });
  s.addText(String(n), {
    x, y, w: 0.42, h: 0.42, isTextBox: true, margin: 0, align: "center", valign: "middle",
    fontFace: SERIF, fontSize: 15, bold: true, color: "FFFFFF",
  });
}

/* ── 1. 표지 ───────────────────────────────────────────────────────────── */
{
  const s = darkSlide();
  s.addText(C.cover.kicker, {
    x: M, y: 1.5, w: 10, h: 0.35, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12, bold: true, charSpacing: 3, color: GOLD,
  });
  s.addText(C.cover.brand, {
    x: M, y: 1.95, w: 11, h: 1.3, isTextBox: true, margin: 0,
    fontFace: SERIF, fontSize: 60, bold: true, color: HANJI,
  });
  s.addText(C.cover.tagline, {
    x: M, y: 3.25, w: 11, h: 0.5, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 20, color: GOLDSOFT,
  });
  s.addShape(p.ShapeType.rect, { x: M, y: 4.15, w: 2.2, h: 0.02, fill: { color: GOLD } });

  const rows = C.cover.rows;
  rows.forEach(([k, v], i) => {
    const y = 4.6 + i * 0.42;
    s.addText(k, {
      x: M, y, w: 1.9, h: 0.35, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12, color: MUTED,
    });
    s.addText(v, {
      x: M + 2.0, y, w: 7, h: 0.35, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 14, color: HANJI,
    });
  });
  notes(s, "신청 명의는 고가네(개인사업자). alaz ltd·우주대행 명의는 사용하지 않는다.");
}

/* ── 2. 서비스 개요 ────────────────────────────────────────────────────── */
{
  const s = lightSlide(C.overview.kicker, C.overview.title);
  const steps = C.overview.steps;
  const cw = 1.85, gap = 0.16;
  steps.forEach(([t, d], i) => {
    const x = M + i * (cw + gap);
    card(s, x, 2.05, cw, 2.15, "FFFFFF");
    stepDot(s, x + 0.2, 2.25, i + 1, i === steps.length - 1 ? ORANGE : INK);
    s.addText(t, {
      x: x + 0.2, y: 2.82, w: cw - 0.4, h: 0.35, isTextBox: true, margin: 0,
      fontFace: SERIF, fontSize: 15, bold: true, color: INK,
    });
    s.addText(d, {
      x: x + 0.2, y: 3.2, w: cw - 0.4, h: 0.85, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10, color: INKSOFT, lineSpacing: 14,
    });
  });
  s.addText(C.overview.note, {
    x: M, y: 4.45, w: W - M * 2, h: 0.4, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 14, color: INKSOFT,
  });
  s.addImage({
    path: C.overview.shot,
    x: M, y: 5.0, w: 11.8, h: 1.95, sizing: { type: "crop", w: 11.8, h: 1.95, x: 0, y: 0 },
  });
  s.addText(C.overview.shot_caption, {
    x: M, y: 6.98, w: 5, h: 0.28, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 10, color: MUTED,
  });
  notes(s, "화면은 실제 운영 화면 캡처. 목업 아님.");
}

/* ── 3. 연동 현황 ──────────────────────────────────────────────────────── */
{
  const s = lightSlide(C.markets.kicker, C.markets.title);
  const items = C.markets.rows;
  const DOTC = { teal: TEAL, gold: GOLD, orange: ORANGE };   // JSON은 색 이름, pptx는 hex
  items.forEach(([name, api, state, dotKey], i) => {
    const dot = DOTC[dotKey] || TEAL;
    const y = 2.05 + i * 1.02;
    card(s, M, y, 11.8, 0.88, "FFFFFF");
    s.addShape(p.ShapeType.ellipse, { x: M + 0.35, y: y + 0.33, w: 0.22, h: 0.22,
                                      fill: { color: dot } });
    s.addText(name, {
      x: M + 0.75, y: y + 0.16, w: 2.4, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SERIF, fontSize: 17, bold: true, color: INK,
    });
    s.addText(api, {
      x: M + 0.75, y: y + 0.48, w: 2.4, h: 0.28, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11, color: MUTED,
    });
    s.addText(state, {
      x: M + 3.4, y: y + 0.28, w: 8.0, h: 0.35, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 14, color: INKSOFT,
    });
  });
  s.addText(C.markets.note, {
    x: M, y: 6.35, w: W - M * 2, h: 0.35, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12, italic: true, color: MUTED,
  });
}

/* ── 4. 보안·개인정보 ─────────────────────────────────────────────────── */
{
  const s = lightSlide(C.security.kicker, C.security.title);
  const items = C.security.items;
  items.forEach(([t, d], i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = M + col * 6.05, y = 2.05 + row * 1.42;
    const w = i === 4 ? 11.8 : 5.75;
    card(s, x, y, w, 1.22, "FFFFFF");
    s.addShape(p.ShapeType.ellipse, { x: x + 0.28, y: y + 0.28, w: 0.34, h: 0.34,
                                      fill: { color: HANJI } });
    s.addShape(p.ShapeType.ellipse, { x: x + 0.38, y: y + 0.38, w: 0.14, h: 0.14,
                                      fill: { color: TEAL } });
    s.addText(t, {
      x: x + 0.78, y: y + 0.2, w: w - 1.05, h: 0.32, isTextBox: true, margin: 0,
      fontFace: SERIF, fontSize: 15, bold: true, color: INK,
    });
    s.addText(d, {
      x: x + 0.78, y: y + 0.54, w: w - 1.05, h: 0.6, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 11, color: INKSOFT, lineSpacing: 15,
    });
  });
  notes(s, "여기 적은 다섯 가지는 전부 코드에 구현돼 있는 것. 없는 기능은 쓰지 않는다.");
}

/* ── 5. 카카오쇼핑 연동 계획 ──────────────────────────────────────────── */
{
  const s = lightSlide(C.plan.kicker, C.plan.title);
  card(s, M, 2.0, 5.75, 2.5, "FFFFFF");
  s.addText("매핑 모델", {
    x: M + 0.35, y: 2.22, w: 5, h: 0.32, isTextBox: true, margin: 0,
    fontFace: SERIF, fontSize: 17, bold: true, color: INK,
  });
  C.plan.model
    .forEach(([t, d], i) => {
      const y = 2.68 + i * 0.6;
      s.addText(t, {
        x: M + 0.35, y, w: 5.05, h: 0.26, isTextBox: true, margin: 0,
        fontFace: SANS, fontSize: 12, bold: true, color: TEAL,
      });
      s.addText(d, {
        x: M + 0.35, y: y + 0.26, w: 5.05, h: 0.3, isTextBox: true, margin: 0,
        fontFace: SANS, fontSize: 10, color: INKSOFT,
      });
    });

  card(s, M + 6.05, 2.0, 5.75, 2.5, "FFFFFF");
  s.addText("연동 범위", {
    x: M + 6.4, y: 2.22, w: 5, h: 0.32, isTextBox: true, margin: 0,
    fontFace: SERIF, fontSize: 17, bold: true, color: INK,
  });
  C.plan.scope
    .forEach(([t, d], i) => {
      const y = 2.68 + i * 0.6;
      s.addText(t, {
        x: M + 6.4, y, w: 5.05, h: 0.26, isTextBox: true, margin: 0,
        fontFace: SANS, fontSize: 12, bold: true, color: TEAL,
      });
      s.addText(d, {
        x: M + 6.4, y: y + 0.26, w: 5.05, h: 0.3, isTextBox: true, margin: 0,
        fontFace: SANS, fontSize: 10, color: INKSOFT,
      });
    });

  card(s, M, 4.7, 11.8, 1.35, HANJI);
  C.plan.facts
    .forEach(([k, v], i) => {
      const x = M + 0.4 + i * 3.85;
      s.addText(k, {
        x, y: 4.92, w: 3.6, h: 0.28, isTextBox: true, margin: 0,
        fontFace: SANS, fontSize: 11, bold: true, charSpacing: 1, color: GOLD,
      });
      s.addText(v, {
        x, y: 5.22, w: 3.6, h: 0.6, isTextBox: true, margin: 0,
        fontFace: SANS, fontSize: 13, color: INK,
      });
    });
  s.addText(C.plan.note, {
    x: M, y: 6.25, w: W - M * 2, h: 0.35, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12, italic: true, color: MUTED,
  });
}

/* ── 6. 판매자 현황 ───────────────────────────────────────────────────── */
{
  const s = lightSlide(C.sellers.kicker, C.sellers.title);
  const stats = C.sellers.stats;
  stats.forEach(([n, k, d], i) => {
    const x = M + i * 4.0;
    card(s, x, 2.05, 3.75, 1.9, "FFFFFF");
    s.addText(n, {
      x: x + 0.35, y: 2.2, w: 3.0, h: 0.95, isTextBox: true, margin: 0,
      fontFace: SERIF, fontSize: 54, bold: true, color: i === 0 ? ORANGE : INK,
    });
    s.addText(k, {
      x: x + 0.35, y: 3.15, w: 3.0, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 13, bold: true, color: INK,
    });
    s.addText(d, {
      x: x + 0.35, y: 3.45, w: 3.0, h: 0.3, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 10, color: MUTED,
    });
  });
  card(s, M, 4.2, 11.8, 0.85, HANJI);
  s.addText(C.sellers.headline, {
    x: M + 0.4, y: 4.42, w: 11.0, h: 0.42, isTextBox: true, margin: 0,
    fontFace: SERIF, fontSize: 17, bold: true, color: INK,
  });
  s.addText(C.sellers.goal, {
    x: M, y: 5.25, w: 6, h: 0.35, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 13, color: INKSOFT,
  });
  s.addImage({
    path: C.sellers.shot,
    x: M, y: 5.7, w: 11.8, h: 1.3, sizing: { type: "crop", w: 11.8, h: 1.3, x: 0, y: 0 },
  });
  s.addText(C.sellers.shot_caption, {
    x: M, y: 7.02, w: 5, h: 0.28, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 10, color: MUTED,
  });
  notes(s, "수치는 사실만. 목표는 오너가 채운다 — 부풀리지 않는다.");
}

/* ── 7. 연락처 ────────────────────────────────────────────────────────── */
{
  const s = darkSlide();
  s.addText(C.contact.kicker, {
    x: M, y: 1.6, w: 8, h: 0.35, isTextBox: true, margin: 0,
    fontFace: SANS, fontSize: 12, bold: true, charSpacing: 3, color: GOLD,
  });
  s.addText(C.contact.title, {
    x: M, y: 2.05, w: 11, h: 1.0, isTextBox: true, margin: 0,
    fontFace: SERIF, fontSize: 44, bold: true, color: HANJI,
  });
  s.addShape(p.ShapeType.rect, { x: M, y: 3.25, w: 2.2, h: 0.02, fill: { color: GOLD } });
  const rows = C.contact.rows;
  rows.forEach(([k, v], i) => {
    const y = 3.7 + i * 0.5;
    s.addText(k, {
      x: M, y, w: 2.2, h: 0.38, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 12, color: MUTED,
    });
    s.addText(v, {
      x: M + 2.3, y, w: 8, h: 0.38, isTextBox: true, margin: 0,
      fontFace: SANS, fontSize: 16, color: HANJI,
    });
  });
  s.addText("고가브릿지", {
    x: W - 4.2, y: 6.4, w: 3.5, h: 0.5, isTextBox: true, margin: 0, align: "right",
    fontFace: SERIF, fontSize: 22, bold: true, color: GOLDSOFT,
  });
}

p.writeFile({ fileName: "docs/apply/gogabridj_intro_kakao_v1.pptx" })
  .then((f) => console.log("saved", f));
