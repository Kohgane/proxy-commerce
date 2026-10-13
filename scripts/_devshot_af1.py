"""AF1 캡처 — 사전검증 「반려 사유 자동 수정」: 데스크톱 등록 모달 · 폰 카드, before(main) / after.

마켓 판정은 캡처용 디스패처 — **실 규칙 `ban_hits` 그대로**(이름에 판촉어가 있으면 ad_claim_risk, 없으면 통과).
Claude는 **캡처용 가짜 답**(실호출 아님 — 키는 Render에만 있다. 실측은 /admin/diagnostics 「Claude 연결 확인」).
사용: BSDL=<bootstrap npm 설치 폴더> python scripts/_devshot_af1.py <before|after> <out_dir> [port]
"""
import os
import sys
import threading

TAG, OUT = sys.argv[1], sys.argv[2]
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 5231
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
os.environ["ANTHROPIC_API_KEY"] = "capture-only"          # 가짜 답을 쓰므로 실호출 0
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
NM = os.environ.get("BSDL", "") + "/node_modules"
CDN = {"bootstrap.min.css": NM + "/bootstrap/dist/css/bootstrap.min.css",
       "bootstrap.bundle.min.js": NM + "/bootstrap/dist/js/bootstrap.bundle.min.js",
       "bootstrap-icons.min.css": NM + "/bootstrap-icons/font/bootstrap-icons.min.css",
       "bootstrap-icons.css": NM + "/bootstrap-icons/font/bootstrap-icons.min.css",
       "bootstrap-icons.woff2": NM + "/bootstrap-icons/font/fonts/bootstrap-icons.woff2",
       "bootstrap-icons.woff": NM + "/bootstrap-icons/font/fonts/bootstrap-icons.woff"}
BAD = "원목 라운지 체어 오일 가죽 55% 할인 9.28-10.05 최저가"
UID = "u-af1-shot"


class _Row:
    def __init__(self, m, ok=True, **kw):
        from src.seller_console.upload_dispatcher import MARKET_LABELS
        self.market, self.ok, self.market_label = m, ok, MARKET_LABELS.get(m, m)
        self.error_code = kw.get("error_code", "")
        self.message = kw.get("message", "통과")
        self.hint = kw.get("hint", "")
        self.reach_ok = self.reach_ms = None
        self.reach_detail = ""
        self.details = kw.get("details", [])
        self.action_url = ""
        self.hold = False
        self.fixes = []


class _Disp:
    def prevalidate(self, product, markets):
        from src.collectors.ko_polish import ban_hits
        out = []
        for m in markets:
            name = str(product.get("title_ko") or product.get("title") or "")
            hits = ban_hits(name)
            out.append(_Row(m, ok=False, error_code="ad_claim_risk",
                            message="할인율·기간·순위 같은 표시광고 위험 문구가 있어요 — 고친 뒤 등록해 주세요.",
                            hint="이름은 편집 화면(쿠팡은 「쿠팡 상품명」)에서 고칠 수 있어요.",
                            details=[f"상품명에 표시광고 위험 문구 「{h}」 — 빼고 등록해 주세요" for h in hits])
                       if hits else _Row(m))
        return out


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    import src.seller_console.views as V
    from src.order_webhook import app
    V._get_upload_dispatcher = lambda: _Disp()
    V._outbound_images = lambda pd, iid: (pd, [], None)
    V._account_codes_forbidden = lambda m: None
    try:
        from src.ai import claude_client as cc

        def fake(system, user, schema, **kw):
            # 받은 재료 그대로에서 판촉어만 뺀 답(정답 모양) — 실 Claude 아님
            import json as _j
            import re as _re
            from src.collectors.ko_polish import ban_hits
            ask = _j.loads(user.split("\n", 2)[-1])
            t = next(v for k, v in ask.items() if k.startswith("고칠 상품명"))
            for h in ban_hits(t):
                t = t.replace(h, " ")
            t = _re.sub(r"\s+", " ", t).strip()
            return ({"title_ko": t, "coupang_name": "", "title_en": "", "values": [], "translations": []},
                    {"model": "claude-sonnet-5-5", "ms": 1840, "in_tok": 1130, "out_tok": 74, "cost_usd": 0.003,
                     "stop_reason": "end_turn"})
        cc.messages_json = fake
        from src.ai import budget as B
        B.AISpendSheets.month_to_date = lambda self: __import__("decimal").Decimal("0")
        B.AISpendSheets.append = lambda self, rec: None
    except ImportError:
        print("claude_client 없음(before) — 자동 수정 없는 화면")

    @app.before_request
    def _as_user():
        from flask import session
        session["user_id"] = UID

    from src.seller_console import collect_history_store as S

    def item(n):
        iid = S.append(source="extension", url=f"https://detail.tmall.com/item.htm?id=af1{n}", title=BAD, price="1290",
                       currency="CNY", seller_id=UID,
                       extra={"title": BAD, "title_ko": BAD, "price": "1290", "currency": "CNY",
                              "images": ["/seller/static/icon-512.png"]})
        return iid[0] if isinstance(iid, tuple) else iid

    iid_desk, iid_phone = item(1), item(2)
    srv = make_server("127.0.0.1", PORT, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    base = f"http://127.0.0.1:{PORT}"

    def route(r):
        u = r.request.url
        if u.startswith(base):
            return r.continue_()
        name = u.split("?")[0].rsplit("/", 1)[-1]
        if name in CDN and os.path.exists(CDN[name]):
            ct = "text/css" if name.endswith(".css") else ("font/woff2" if name.endswith("woff2") else
                                                           ("font/woff" if name.endswith("woff") else "application/javascript"))
            return r.fulfill(status=200, body=open(CDN[name], "rb").read(), headers={"content-type": ct})
        return r.abort()

    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            # 1) 데스크톱 등록 모달
            ctx = br.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
            ctx.route("**/*", route)
            pg = ctx.new_page()
            pg.goto(base + f"/seller/collect/preview/{iid_desk}")
            pg.wait_for_timeout(800)
            pg.evaluate("() => openUploadModal()")
            pg.wait_for_timeout(500)
            pg.evaluate("""() => document.querySelectorAll('.market-upload-check').forEach(el => {
                el.checked = ['woocommerce', 'elevenst'].includes(el.value); })""")
            pg.click("#btnPrevalidate")
            pg.wait_for_function("() => document.getElementById('btnPrevalidate').textContent.includes('사전검증 →') "
                                 "&& document.querySelectorAll('#prevalidateResults .list-group-item').length >= 2", timeout=60000)
            pg.wait_for_timeout(400)
            dlg = pg.locator("#uploadModal .modal-content")
            dlg.screenshot(path=f"{OUT}/af1-desktop-modal-{TAG}.png")
            print(f"[{TAG}/desktop]", pg.inner_text("#prevalidateResults").replace("\n", " | ")[:600])
            if TAG == "after":
                pg.click("[data-role=pv-autofix-undo]")
                pg.wait_for_selector("[data-role=pv-autofix-off]", timeout=60000)
                pg.wait_for_function("() => document.getElementById('btnPrevalidate').textContent.includes('사전검증 →')", timeout=60000)
                pg.wait_for_timeout(400)
                dlg.screenshot(path=f"{OUT}/af1-desktop-modal-after-undo.png")
                print("[after/undo]", pg.inner_text("#prevalidateResults").replace("\n", " | ")[:600])
            ctx.close()
            # 2) 폰 카드
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            ctx.route("**/*", route)
            pg = ctx.new_page()
            pg.goto(base + f"/seller/m/item/{iid_phone}")
            pg.wait_for_timeout(800)
            pg.evaluate("""() => document.querySelectorAll('input[name=m5-market]').forEach(el => {
                el.checked = ['woocommerce', 'elevenst'].includes(el.value); })""")
            pg.click("[data-role=m5-check]")
            pg.wait_for_function("() => { const c = document.querySelector('[data-role=m5-checks]'); return c && c.querySelectorAll('.m5-res').length >= 2 "
                                 "&& !c.querySelector('[data-role=m5-check-progress]') && !c.querySelector('[data-role=m5-pending]'); }", timeout=60000)
            pg.wait_for_timeout(400)
            el = pg.locator("[data-role=m5-checks]")
            el.scroll_into_view_if_needed()
            pg.screenshot(path=f"{OUT}/af1-phone-card-{TAG}.png", full_page=True)
            sw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            print(f"[{TAG}/phone] hscroll={'있음' if sw[0] > sw[1] else '없음'} ·", el.inner_text().replace("\n", " | ")[:500])
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
