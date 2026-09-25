"""D3-6 캡처 — 같은 스크립트를 수리 전 워크트리(before)와 수리 후(after)에서 돌린다.

① 렌더러: 합성 픽스처 두 장(cphvcw 모양·ebvllh 모양)을 **그 트리의 실코드**로 번역·지우기·그리기
② 벤치 카드: 라우트 그대로 렌더(실행 기록 조회만 목) → 실브라우저 스크린샷
사용: python _devshot_d36.py <before|after> <out_dir>
"""
import io
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOT = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"


def _font(px, w="bold"):
    from src.services.image_render_font import load
    return load(px, w)


def _ink_box(text, xy, px=40, pad=8):
    from PIL import Image, ImageDraw
    l, t, r, b = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox(xy, text, font=_font(px))
    return {"x": l - pad, "y": t - pad, "w": (r - l) + 2 * pad, "h": (b - t) + 2 * pad}


def _pages():
    from PIL import Image, ImageDraw
    # cphvcw 모양 — 워드마크 + 옆 라인명 + 관용구 줄 + 시계 화면 UI(전각)
    a = Image.new("RGB", (750, 1000), (240, 240, 236))
    d = ImageDraw.Draw(a)
    d.text((66, 44), "SPORTLINK", font=_font(40), fill=(20, 20, 20))
    d.text((346, 44), "随行盾", font=_font(40), fill=(20, 20, 20))
    d.text((66, 200), "三合一 多功能", font=_font(44), fill=(20, 20, 20))
    d.rounded_rectangle((250, 470, 500, 720), radius=40, fill=(24, 24, 28))
    d.text((300, 560), "Ａｌａｒｍ ６：４５ａｍ", font=_font(14, "regular"), fill=(230, 230, 230))
    la = [{"source": "SPORTLINK", "box": _ink_box("SPORTLINK", (66, 44))},
          {"source": "随行盾", "box": _ink_box("随行盾", (346, 44))},
          {"source": "三合一 多功能", "box": _ink_box("三合一 多功能", (66, 200), 44)},
          {"source": "Ａｌａｒｍ ６：４５ａｍ",
           "box": _ink_box("Ａｌａｒｍ ６：４５ａｍ", (300, 560), 14, 3)}]
    # ebvllh 모양 — 파란 알약 위 흰 글자(박스가 알약보다 큼) + 작은 글자
    b = Image.new("RGB", (750, 1000), (250, 250, 250))
    d = ImageDraw.Draw(b)
    d.rounded_rectangle((210, 612, 540, 688), radius=38, fill=(40, 110, 220))
    d.text((300, 628), "拒绝混乱", font=_font(40), fill=(255, 255, 255))
    d.text((330, 300), "闹钟", font=_font(11, "regular"), fill=(30, 30, 30))
    lb = [{"source": "拒绝混乱", "box": {"x": 190, "y": 596, "w": 370, "h": 108}},
          {"source": "闹钟", "box": {"x": 326, "y": 298, "w": 30, "h": 13}}]
    out = []
    for name, img, lines in (("cphvcw", a, la), ("ebvllh", b, lb)):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        out.append((name, buf.getvalue(), lines))
    return out


def _fake_translate(s):
    # 이 목은 **번역기가 하는 일**만 흉내 낸다: 한자 → 한국어(직역). 자리표시자는 그대로 둔다.
    table = {"随行盾": "수행방패", "三合一": "삼합일", "多功能": "다기능", "拒绝混乱": "혼란을 거부하세요",
             "闹钟": "알람", "Ａｌａｒｍ ６：４５ａｍ": "알람 6:45A"}
    for k, v in table.items():
        s = s.replace(k, v)
    return s


def render_shots():
    from PIL import Image, ImageDraw
    from src.services import image_text_glossary as G
    from src.services import image_text_render as R
    for name, raw, lines in _pages():
        rows = G.translate_lines(lines, _fake_translate)
        out = R.render(raw, rows, method="telea")
        res = Image.open(io.BytesIO(out.get("image_bytes") or raw)).convert("RGB")
        org = Image.open(io.BytesIO(raw)).convert("RGB")
        W, H = 375, 500
        sheet = Image.new("RGB", (W * 2 + 30, H + 60), (251, 248, 241))
        sheet.paste(org.resize((W, H)), (10, 50))
        sheet.paste(res.resize((W, H)), (W + 20, 50))
        d = ImageDraw.Draw(sheet)
        d.text((10, 12), "원본(합성 픽스처)", font=_font(18), fill=(26, 23, 20))
        d.text((W + 20, 12), f"D3·TELEA — {TAG}", font=_font(18), fill=(26, 23, 20))
        sheet.save(f"{OUT}/d36-render-{name}-{TAG}.png")
        print(f"[{TAG}] {name}: drawn={out.get('drawn')} erased={out.get('erased')} "
              f"skipped={[s.get('reason', '')[:30] for s in out.get('skipped') or []]}")
        for r in rows:
            print("   ", r.get("source"), "→", repr(r.get("render_text")), r.get("action"))


def card_shot():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    run = {"run_id": "bench-20260925-101500-m0-d3g", "scores": {}, "results": [{
        "item_no": "617129397971", "kind": "detail", "status": "done", "idx": 3, "ms": 2140,
        "original": "https://img.example/o.jpg",
        "url": "https://res.cloudinary.com/dzxkl9put/image/upload/v1/proxy-commerce/bench/"
               "bench-20260925-101500-m0-d3g_617129397971_p3_TENCENT.jpg",
        "lines": [{"source": "SPORTLINK", "box": {"x": 58, "y": 30, "w": 280, "h": 62}},
                  {"source": "随行盾", "box": {"x": 338, "y": 30, "w": 140, "h": 62}}],
        "source_text": "SPORTLINK 随行盾 使用前 使用后", "unboxed": ["使用前", "使用后"],
        "d3": {"url": "/seller/admin/image-translate-bench/image/617129397971/3?kind=d3",
               "erased": 1, "drawn": 0, "skipped": [], "axes": {}},
        "d3g": {"url": "https://res.cloudinary.com/dzxkl9put/image/upload/v1/proxy-commerce/bench/"
                       "bench-20260925-101500-m0-d3g_617129397971_p3_GEN_REMOVE.jpg",
                "erased": 1, "drawn": 0, "inpainter": "gen_remove", "cloud_tx": 51,
                "cloud_credits": 0.051, "axes": {"F": {"score": 1, "reason": ""}}},
        "pick": {"pick": "d3g", "reason": "공통 축 합 최고 — F로 결정", "scores": {}, "common": []}}]}
    runs = [{"run_id": "bench-20260925-111500-m0-d3g", "created_at": "2026-09-25T11:15:00",
             "pages": 4, "ok": 4, "scored": False},
            {"run_id": run["run_id"], "created_at": "2026-09-25T10:15:00", "pages": 4, "ok": 4,
             "scored": False}]
    with patch("src.db.image_translate_usage_pg.get_run", lambda rid: run), \
            patch("src.db.image_translate_usage_pg.list_runs", lambda n=20: runs), \
            patch("src.db.image_translate_usage_pg.daily_totals", lambda n=14: []), \
            patch("src.seller_console.views._is_admin_user", lambda: True):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "owner"
            html = c.get(f"/seller/admin/image-translate-bench?run={run['run_id']}").get_data(as_text=True)
    css = ("<style>" + open(BOOT).read() + "</style>") if os.path.exists(BOOT) else ""
    css += "<style>" + open("src/static/app.css").read() + "</style>"
    for e in ("src/seller_console/static/seller.css", "src/seller_console/static/console.css"):
        css += "<style>" + open(e).read() + "</style>"
    html = html.replace("</head>", css + "</head>", 1)
    # 결과 그림 자리 — 네트워크가 없으니 **같은 크기의 회색 판**으로 대신한다(표시 폭을 보려는 캡처).
    ph = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='750' height='1000'><rect width='750' height='1000' fill='%23d9d3c6'/><text x='40' y='520' font-size='60' fill='%23555'>750x1000</text></svg>"
    open(f"/tmp/_d36_card_{TAG}.html", "w").write(html)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        pg = br.new_page(viewport={"width": 1400, "height": 1000})
        pg.goto(f"file:///tmp/_d36_card_{TAG}.html")
        pg.evaluate("(ph) => document.querySelectorAll('.op-card img').forEach(i => i.src = ph)", ph)
        pg.wait_for_timeout(400)
        pg.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
        card = pg.locator(".op-card").filter(has=pg.locator("h2", has_text=run["run_id"])).first
        top = pg.locator(".container-fluid").first
        top.screenshot(path=f"{OUT}/d36-bench-page-{TAG}.png")
        card.screenshot(path=f"{OUT}/d36-bench-card-{TAG}.png")
        br.close()
    print(f"[{TAG}] card saved")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    render_shots()
    card_shot()
