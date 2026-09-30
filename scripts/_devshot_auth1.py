"""AUTH-1 캡처 — 폰 폭 390px, 실제 폼 입력.

  signup : /auth/signup 입력 → 제출 직후 화면(before: 로그인 화면으로 돌아감 / after: 대시보드)
  login  : 같은 자격으로 /auth/login → 결과(before: 「이메일 또는 비밀번호가 올바르지 않습니다」)
  wrongpw: 틀린 비밀번호(after: 「비밀번호가 틀립니다」)
  noacct : 미등록 이메일(after: 「등록되지 않은 이메일」)
사용: python scripts/_devshot_auth1.py <before|after> <out_dir>
"""
import os
import sys
import threading

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "1"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
EMAIL, PW = "owner-test@example.test", "pass12345"


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    import src.seller_console.views as V
    V._AUTH_ENABLED = True
    from src.order_webhook import app
    import scripts._devshot_f51 as base

    srv = make_server("127.0.0.1", 5198, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    B = "http://127.0.0.1:5198"
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
            pg = ctx.new_page()

            def shot(key):
                pg.wait_for_timeout(500)
                if os.path.exists(base.BOOT):
                    pg.add_style_tag(content=open(base.BOOT).read())
                pg.wait_for_timeout(200)
                pg.screenshot(path=f"{OUT}/auth1-{key}-{TAG}.png", full_page=False)
                alert = pg.evaluate("() => [...document.querySelectorAll('.alert')].map(e => e.innerText.trim()).join(' / ')")
                print(f"[{TAG}/{key}] {pg.url.replace(B, '')} | {alert[:160]}")

            pg.goto(B + "/auth/signup")
            pg.fill("input[name=email]", EMAIL)
            pg.fill("input[name=password]", PW)
            pg.click("form[action='/auth/signup'] button[type=submit]")
            pg.wait_for_load_state("domcontentloaded")
            shot("signup")

            for key, email, pw_ in (("login", EMAIL, PW), ("wrongpw", EMAIL, "wrong-pass"),
                                    ("noacct", "nobody@example.test", PW)):
                pg.goto(B + "/auth/logout")
                pg.goto(B + "/auth/login")
                pg.fill("#login-email", email)
                pg.fill("#login-password", pw_)
                pg.click("#emailLoginForm button[type=submit]")
                pg.wait_for_load_state("domcontentloaded")
                shot(key)
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
