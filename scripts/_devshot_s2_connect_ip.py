"""개발용 스크린샷 — S2-b: 마켓 연동 화면의 '허용 목록에 등록할 IP' 안내.

BEFORE는 **모든 마켓에 Render 아웃바운드 목록**을 뭉뚱그려 보여줬다. 그게 재발 지뢰다 —
Render는 공유 대역이라 값이 바뀌고, 등록한 IP가 며칠 뒤 무효가 된다.
AFTER는 발신 경로로 갈라 안내한다: 게이트 마켓은 릴레이 고정 IP 하나, 11번가는 직발이라 전부.

BEFORE는 옛 템플릿 조각을 그대로 렌더해 만든다(그림 합성 아님 — 실제 렌더 결과).
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["SERVER_OUTBOUND_IP"] = "74.220.49.7, 74.220.52.223"
os.environ["MARKET_RELAY_IP"] = "203.0.113.9"          # 예시 — 실값은 오너 Render 설정에서

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/s2"
SIZE = (1280, 420)

BEFORE_HTML = """
<div class="alert alert-warning d-flex flex-wrap gap-2 align-items-center mb-3" role="note">
  <i class="bi bi-hdd-network"></i>
  <span class="small mb-0">쿠팡 · 네이버 · 11번가는 <strong>서버 IP를 허용 목록에 등록</strong>해야 연결돼요:</span>
  <code class="ms-1">74.220.49.7</code>
  <button type="button" class="btn btn-gold btn-sm py-0">복사</button>
  <div class="small text-muted w-100 mt-2">등록해야 할 IP 전체:
    <code class="me-2">74.220.49.7</code><code class="me-2">74.220.52.223</code>
  </div>
</div>
"""


def _shell(inner: str) -> str:
    css = ""
    if os.path.exists(BOOTSTRAP):
        css += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    css += "<style>" + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            css += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>" + css +
            "</head><body style='background:var(--bg);padding:24px'>"
            "<div style='max-width:1100px'>" + inner + "</div></body></html>")


def _after_fragment() -> str:
    """실제 뷰 컨텍스트로 실제 템플릿의 IP 안내 블록만 렌더한다(합성 0)."""
    from flask import render_template_string

    from src.order_webhook import app
    from src.seller_console import views

    tpl = open("src/seller_console/templates/markets_connect.html", encoding="utf-8").read()
    start = tpl.index("{# S2-b:")
    end = tpl.index("{# server_ip / server_ips")
    with app.test_request_context("/seller/markets/connect"):
        return render_template_string(tpl[start:end], **views._connect_ip_ctx())


def main():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT_DIR, exist_ok=True)
    from src.seller_console import views
    ctx = views._connect_ip_ctx()
    print("=== S2-b 실측 ===")
    for market in ("coupang", "smartstore", "elevenst", "woocommerce"):
        row = ctx["allowlist_ips"][market]
        print(f"  {market:<12} source={row['source']:<7} ips={row['ips']} complete={row['complete']}")

    shots = [("before", _shell(BEFORE_HTML)), ("after", _shell(_after_fragment()))]
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, html in shots:
            path = f"/tmp/_s2_{label}.html"
            open(path, "w", encoding="utf-8").write(html)
            pg = br.new_page(viewport={"width": SIZE[0], "height": SIZE[1]})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(500)
            pg.screenshot(path=f"{OUT_DIR}/connect-ip-{label}.png", full_page=True)
            pg.close()
        br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
