"""#886 후속 캡처 — Claude 답이 상표 이름을 새로 들였을 때 카드: before(main) = 그대로 실림 / after = 버림 + 사유.

카드 기록은 **실함수**로 만든다: `reject_autofix.run`(그 트리의 판정) → `views._pv_autofix_public`. Claude 답만 캡처용 고정값
(「임스」를 덧붙인 답 — 실호출 아님). 카드 HTML은 실제 템플릿 함수(`_m5_flow` autoFixHtml·pvRowHtml / `collect_preview`
renderPrevalidateResults)를 그대로 잘라 실행한다(`_devshot_raf_cards.py`와 같은 방식 — app.css만, 부트스트랩 없음).
사용(그 트리 루트에서): python scripts/_devshot_raf_tm.py <before|after> <out_dir>
"""
import json
import os
import sys
from pathlib import Path

TAG, OUT = sys.argv[1], Path(sys.argv[2])
R = Path.cwd()
sys.path.insert(0, str(R))
os.environ["ANTHROPIC_API_KEY"] = "capture-only"
OUT.mkdir(parents=True, exist_ok=True)

PD = {"title_ko": "라운지 체어 오일 가죽 판매 1위", "coupang_name": "라운지 체어 최저가",
      "price": 89000, "currency": "KRW", "images": ["https://example.com/chair.jpg"],
      "options": [{"name": "색상", "values": ["黑", "白"], "values_ko": ["블랙 50% 할인", "화이트"]}]}
ANSWER = {"fixable": True, "title": "임스 라운지 체어 오일 가죽", "coupang_name": "임스 라운지 체어",
          "options": [{"name": "색상", "values_ko": ["블랙", "화이트"]}], "why": "표시광고 문구 삭제"}


class _R:
    market, ok, error_code, hold, fixes = "coupang:woojoo", False, "ad_claim_risk", False, []
    details = ["상품명에 표시광고 위험 문구 「최저가」 — 빼고 등록해 주세요",
               "옵션 값에 표시광고 위험 문구 「50% 할인」 — 빼고 등록해 주세요"]


def main():
    from src.services import reject_autofix as RAF
    import src.seller_console.views as V
    RAF._call = lambda fields, reasons, timeout: (dict(ANSWER), {"provider": "anthropic", "model": "capture", "error": ""})
    rec = RAF.run(PD, RAF.collect(PD, [_R()], {}))
    card = V._pv_autofix_public(rec)
    print(f"[{TAG}] run → status={rec.get('status')} · changes={[(c.get('label'), c.get('after')) for c in rec.get('changes') or []]}"
          f" · error={str(rec.get('error') or '')[:160]}")
    hold = {"market": "coupang:woojoo", "market_label": "쿠팡 · 우주대행", "ok": False, "hold": False, "error_code": "ad_claim_risk",
            "message": "할인율·기간·순위 같은 표시광고 위험 문구가 있어요 — 고친 뒤 등록해 주세요.",
            "hint": "이름은 편집 화면(쿠팡은 「쿠팡 상품명」)에서 고칠 수 있어요.", "details": list(_R.details),
            "fixes": [], "cautions": [], "category": {}}
    ok = {"market": "coupang:woojoo", "market_label": "쿠팡 · 우주대행", "ok": True, "hold": False, "error_code": None,
          "message": "사전검증 통과", "hint": "", "details": [], "fixes": [], "cautions": [], "category": {}}
    rows = [hold]
    if rec.get("status") == "done":
        # 잡은 고친 글자로 그 마켓을 다시 잰다 — 같은 실함수(표시광고 → 재료 보류)로 그 줄을 만든다
        from src.seller_console.upload_dispatcher import UploadDispatcher, readiness_hint, readiness_message
        fixed = RAF.apply(dict(PD, title=PD["title_ko"]), rec)
        ad = UploadDispatcher._ad_claim_hits(fixed, "coupang")
        hs = UploadDispatcher.readiness_holds(fixed, "coupang")
        if ad:
            rows = [dict(hold, details=ad)]
        elif hs:
            rows = [dict(hold, hold=True, error_code="missing_field", message=readiness_message(hs), hint=readiness_hint(hs),
                         details=[h["line"] for h in hs], fixes=[h.get("fix") for h in hs if h.get("fix")])]
        else:
            rows = [ok]
        print(f"[{TAG}] 다시 잼 → {'통과' if rows == [ok] else rows[0]['message']} · {rows[0]['details']}")

    css = (R / "src/static/app.css").read_text(encoding="utf-8")
    m5 = (R / "src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    pv = (R / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    m5_style = m5[m5.index("<style>"):m5.index("</style>") + 8]
    m5_js = m5[m5.index("  function catLine(r) {"):m5.index("  function pvRender() {")]
    pv_js = pv[pv.index("function renderActionLink(url, label) {"):pv.index("  el.innerHTML = html;", pv.index("function renderPrevalidateResults"))]
    esc = ("function esc(s){return String(s==null?'':s).replace(/[&<>\"']/g,function(c){return "
           "{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c];});}")
    m5_html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style>{m5_style}"
               "<style>body{background:var(--bg);padding:16px;width:420px}</style></head><body>"
               "<div id='root' data-item='item1'><div id='checks'></div></div><script>"
               f"var root=document.getElementById('root'), itemId='item1'; {esc} var OVERRIDES={{}}; var pvRows={{}};\n{m5_js}\n"
               f"var rows={json.dumps(rows, ensure_ascii=False)}, fix={json.dumps(card, ensure_ascii=False)};"
               "var h=''; if (fix) h+=autoFixHtml(fix); rows.forEach(function(r){pvRows[r.market]=r; h+=pvRowHtml(r.market);});"
               "document.getElementById('checks').innerHTML=h;</script></body></html>")
    pv_html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style>"
               "<style>body{background:var(--bg);padding:16px;width:760px} .list-group-item{border:1px solid var(--border);padding:10px;border-radius:8px}</style>"
               "</head><body><input id='uploadMarginPct' value='27' data-default='27' type='hidden'><button id='btnConfirmUpload' style='display:none'></button>"
               "<div id='prevalidateResults'></div><script>"
               f"{esc.replace('function esc', 'function kgpEscapeForHtml')} var _validatedMarkets=[], _ITEM_ID='item1';\n{pv_js}\n  el.innerHTML = html; }}\n"
               f"renderPrevalidateResults({json.dumps(rows, ensure_ascii=False)}, [], 'done', '', {json.dumps(card, ensure_ascii=False)});"
               "</script></body></html>")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = p.chromium.launch(executable_path=exe if Path(exe).exists() else None)
        for name, html, w in (("m5", m5_html, 460), ("pv", pv_html, 800)):
            f = OUT / f"raf-tm-{name}-{TAG}.html"
            f.write_text(html, encoding="utf-8")
            pg = b.new_page(viewport={"width": w, "height": 300}, device_scale_factor=2)
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f.as_uri())
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(OUT / f"raf-tm-{name}-{TAG}.png"), full_page=True)
            print(f"[{TAG}/{name}] errors={errs} ·", pg.inner_text("body")[:260].replace("\n", " | "))
        b.close()


if __name__ == "__main__":
    main()
