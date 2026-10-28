"""V42-2(오너 2026-10-28 20:33 「수정되었다는겨 머여. 딱히 뭐 없는디」) — app.css 링크에 빌드 버전이 없어 폰이 7일 캐시(정적 max-age=604800)를 들고 있었다.
console.css는 이미 ?v=build_sha, app.css만 빠져 있었다. 모든 app.css 링크에 ?v=."""
import glob
import os


def test_every_app_css_link_is_versioned():
    bad = []
    for p in glob.glob("src/**/templates/**/*.html", recursive=True) + glob.glob("src/templates/*.html"):
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            if "filename='app.css')" in line and "v={{ build_sha }}" not in line:
                bad.append(f"{p}:{i}")
    assert not bad, bad


def test_rendered_console_links_carry_version():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    html = app.test_client().get("/seller/dashboard").get_data(as_text=True)
    import re
    links = re.findall(r'href="([^"]*app\.css[^"]*)"', html)
    assert links and all("?v=" in l for l in links), links
