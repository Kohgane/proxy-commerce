import json, re, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]   # 사용: python3 scripts/_devshot_raf_cards.py <출력폴더> 다음 scripts/_devshot_raf_shoot.py <출력폴더>
SP = Path(sys.argv[1])
css = (R / "src/static/app.css").read_text(encoding="utf-8")
m5 = (R / "src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
pv = (R / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
m5_style = m5[m5.index("<style>"):m5.index("</style>") + 8]
m5_js = m5[m5.index("  function catLine(r) {"):m5.index("  function pvRender() {")]
pv_js = pv[pv.index("function renderActionLink(url, label) {"):pv.index("  el.innerHTML = html;", pv.index("function renderPrevalidateResults"))]

HOLD = {"market": "coupang:woojoo", "market_label": "쿠팡 · 우주대행", "ok": False, "hold": False, "error_code": "ad_claim_risk",
        "message": "할인율·기간·순위 같은 표시광고 위험 문구가 있어요 — 고친 뒤 등록해 주세요.",
        "hint": "이름은 편집 화면(쿠팡은 「쿠팡 상품명」)에서 고칠 수 있어요.",
        "details": ["상품명에 표시광고 위험 문구 「최저가」 — 빼고 등록해 주세요", "옵션 값에 표시광고 위험 문구 「50% 할인」 — 빼고 등록해 주세요"],
        "fixes": [], "cautions": [], "category": {}}
OK = {"market": "coupang:woojoo", "market_label": "쿠팡 · 우주대행", "ok": True, "hold": False, "error_code": None,
      "message": "사전검증 통과", "hint": "",
      "details": [],
      "fixes": [], "cautions": [], "category": {}}
FIX = {"status": "done", "undone": False, "changes": [
    {"label": "쿠팡 상품명", "before": "무선 충전기 최저가 거치대", "after": "무선 충전기 거치대"},
    {"label": "옵션 「색상」", "before": "블랙 50% 할인", "after": "블랙"}]}
cases = {"before": ([HOLD], None), "after": ([OK], FIX), "applied": ([OK], {**FIX, "status": "applied"}),
         "fail": ([HOLD], {"status": "failed", "error": "고친 값이 우리 판정을 못 넘었어요 — 상품명에 표시광고 문구가 남았어요 「최저가」", "changes": [], "reasons": [1]})}

for name, (rows, fix) in cases.items():
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{css}</style>{m5_style}
<style>body{{background:var(--bg,#fff);padding:16px;width:420px}}</style></head><body>
<div id="root" data-item="item1"><div id="checks"></div></div>
<script>
var root=document.getElementById('root'), itemId='item1';
function esc(s){{return String(s==null?'':s).replace(/[&<>"']/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];}});}}
var OVERRIDES={{}}; var pvRows={{}};
{m5_js}
var rows={json.dumps(rows, ensure_ascii=False)}, fix={json.dumps(fix, ensure_ascii=False)};
var h=''; if (fix) h+=autoFixHtml(fix);
rows.forEach(function(r){{pvRows[r.market]=r; h+=pvRowHtml(r.market);}});
document.getElementById('checks').innerHTML=h;
</script></body></html>"""
    (SP / f"m5_{name}.html").write_text(html, encoding="utf-8")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{css}</style>
<style>body{{background:var(--bg,#fff);padding:16px;width:760px}} .list-group-item{{border:1px solid var(--border);padding:10px;border-radius:8px}}</style></head><body>
<input id="uploadMarginPct" value="27" data-default="27" type="hidden"><button id="btnConfirmUpload" style="display:none"></button>
<div id="prevalidateResults"></div>
<script>
function kgpEscapeForHtml(s){{return String(s==null?'':s).replace(/[&<>"']/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];}});}}
var _validatedMarkets=[], _ITEM_ID='item1';
{pv_js}
  el.innerHTML = html; }}
renderPrevalidateResults({json.dumps(rows, ensure_ascii=False)}, [], 'done', '', {json.dumps(fix, ensure_ascii=False)});
</script></body></html>"""
    (SP / f"pv_{name}.html").write_text(html, encoding="utf-8")
print("ok")
