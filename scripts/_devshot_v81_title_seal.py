"""개발용 스크린샷 — v81 STEP5 제목 새니타이저 서버 봉인(코어 폴백 포함).

실 sanitize_title 출력으로 before/after 표를 렌더(정직: 실제 함수값).
"""
import glob, os, html
from pathlib import Path
import sys
sys.path.insert(0, os.getcwd())
from src.collectors.collect_sanitize import sanitize_title

CASES = [
    ("PORTER STROLL 2WAY BAG | YOSHIDA & Co.", "https://www.yoshidakaban.com/product/12345.html", "코어 폴백(북마클릿)"),
    ("PORTER TANKER | YOSHIDA & Co., LTD.", "https://www.yoshidakaban.com/p", "법인 접미"),
    ("ある製品 ｜ 楽天市場", "https://item.rakuten.co.jp/s/1", "라쿠텐 접미"),
    ("Amazon.com: Cool Gadget", "https://www.amazon.com/dp/x", "아마존 접두"),
    ("【楽天市場】名品バッグ", "https://item.rakuten.co.jp/s/1", "마켓 브래킷"),
    ("普通の商品タイトル", "https://example.com/p", "브랜드 없음(불변)"),
]

rows = ""
for raw, url, tag in CASES:
    out = sanitize_title(raw, url)
    changed = out != raw
    rows += (
        "<tr><td class=tag>" + html.escape(tag) + "</td>"
        "<td class=before>" + html.escape(raw) + "</td>"
        "<td class=arr>→</td>"
        "<td class=after " + ("changed" if changed else "same") + ">" + html.escape(out) + "</td></tr>"
    )

PAGE = """<!doctype html><html lang=ko><head><meta charset=utf-8><style>
body{font-family:Pretendard,'Noto Sans KR',sans-serif;background:#F5EFE3;color:#1A1714;margin:0;padding:24px}
h1{font-family:'Noto Serif KR',serif;font-size:19px;margin:0 0 4px;color:#1A1714}
.sub{font-size:12px;color:#7a6a58;margin:0 0 18px}
table{border-collapse:collapse;width:760px;background:#fff;border:1px solid #ded2bd;border-radius:10px;overflow:hidden}
td{padding:10px 12px;font-size:13px;border-top:1px solid #efe6d5;vertical-align:top}
.tag{color:#C9A24B;font-weight:700;white-space:nowrap;width:120px}
.before{color:#9a6a5a;text-decoration:line-through;text-decoration-color:#d3b3a8}
.arr{color:#119A8E;font-weight:700;width:20px;text-align:center}
.after{font-weight:600}
.after.changed{color:#0d7a6f}
.after.same{color:#7a6a58}
</style></head><body>
<h1>제목 새니타이저 서버 봉인 (v81 STEP5)</h1>
<p class=sub>collect_sanitize.sanitize_payload 단일 지점 — 코어 폴백(북마클릿 og-meta)도 브랜드+법인 접미(| YOSHIDA & Co.) 제거 · 브랜드 없는 제목 불변</p>
<table>ROWS</table></body></html>""".replace("ROWS", rows)

tmp = "/tmp/_v81_title.html"
open(tmp, "w", encoding="utf-8").write(PAGE)
exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=exe)
    p = b.new_context(viewport={"width": 820, "height": 380}).new_page()
    p.goto("file://" + tmp); p.wait_for_timeout(300)
    p.screenshot(path="/tmp/shot_v81_title.png", full_page=True)
    b.close()
print("캡처: /tmp/shot_v81_title.png")
