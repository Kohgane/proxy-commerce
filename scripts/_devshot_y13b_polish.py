"""Y13-A 7·8(오너 2026-10-18 16:37·16:41 피샹리) — 사진 편집 패널 「다듬기」 줄: 판촉 상자 · 브랜드 로고 상자.

같은 입력(피샹리 대표 사진 상자 3개 — 菲尚丽家 · FEISHANGLIJIA · 分期免息 买贵退差)을
before = main의 행(다듬기가 판촉을 번역하고 로고를 음차) + main 템플릿,
after  = 이 브랜치의 `guard_row`를 지난 행 + 이 브랜치 템플릿으로 그린다(편집기 GET은 Playwright가 가로채 응답).
사용: python scripts/_devshot_y13b_polish.py before|after [OUT]
"""
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())
TAG = sys.argv[1] if len(sys.argv) > 1 else "after"
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y13b", TAG)
os.makedirs(OUT, exist_ok=True)

# 다듬기 AI가 낸 행(운영 피샹리 대표 사진 모양) — main은 이대로 나간다
ROWS = [{"id": "t0", "src": "菲尚丽家", "tgt": "피샹리가", "ko": "피샹리가", "ai": "피샹리가", "from": "polish"},
        {"id": "t1", "src": "FEISHANGLIJIA", "tgt": "페이샹리자", "ko": "페이샹리자", "ai": "페이샹리자", "from": "polish"},
        {"id": "t2", "src": "分期免息 买贵退差", "tgt": "무이자 할부 차액 환불", "ko": "무이자 할부·차액 환불",
         "ai": "무이자 할부·차액 환불", "from": "polish"}]
if TAG == "after":
    from src.services.image_edit import logo_names
    from src.services.image_polish import guard_row
    ex = {"brand": "", "title": "菲尚丽家单人沙发椅设计师客厅阳台休闲懒人沙发可睡可躺舒适单椅"}
    logos = logo_names(ex, [r["src"] for r in ROWS])
    for r in ROWS:
        guard_row(r, logos, True, True)                      # 대표 사진(gallery 0) · 원본 되살릴 수 있음
    tpl = open("src/seller_console/templates/_image_edit.html", encoding="utf-8").read()
else:
    tpl = subprocess.run(["git", "show", "origin/main:src/seller_console/templates/_image_edit.html"],
                         capture_output=True, text=True, check=True).stdout
css = open("src/static/app.css", encoding="utf-8").read()
PIC = "file://" + os.path.abspath("src/seller_console/static/icon-1024.png")
PLAN = {"ok": True, "url": PIC, "size": [750, 1000], "current": "translated", "today": 3, "cap": 30,
        "versions": [{"key": "original", "label": "수집 원본"}, {"key": "translated", "label": "번역본"}],
        "boxes": [{"id": "t0", "x": 60, "y": 40, "w": 260, "h": 60, "cls": "brand", "cls_label": "브랜드 로고", "text": "菲尚丽家"},
                  {"id": "t1", "x": 60, "y": 110, "w": 300, "h": 36, "cls": "brand", "cls_label": "브랜드 로고", "text": "FEISHANGLIJIA"},
                  {"id": "t2", "x": 60, "y": 860, "w": 520, "h": 70, "cls": "promo", "cls_label": "판촉", "text": "分期免息 买贵退差"}],
        "polish": {"rows": ROWS, "why": ""}, "cost": {"credits": 1}}
html = ("<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        f"<style>{css}</style></head><body>{tpl}</body></html>")
page_path = os.path.join(OUT, "_page.html")
with open(page_path, "w", encoding="utf-8") as f:
    f.write(html)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=exe)
    for wname, vw in (("desktop", {"width": 1280, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
        pg = b.new_page(viewport=vw)
        pg.route("**/image-edit/**", lambda route: route.fulfill(status=200, content_type="application/json",
                                                                  body=json.dumps(PLAN, ensure_ascii=False)))
        pg.goto("file://" + os.path.abspath(page_path))
        pg.evaluate("window.fetch = (u, o) => Promise.resolve(new Response(JSON.stringify(%s)))" % json.dumps(PLAN, ensure_ascii=False))
        pg.evaluate("window.kgpImageEdit.open('fish', 'gallery', 0)")
        pg.wait_for_timeout(500)
        tgt = pg.locator("[data-role=kie-polish]").first
        tgt.screenshot(path=os.path.join(OUT, f"{TAG}-polish-rows-{wname}.png"))
        with open(os.path.join(OUT, f"{TAG}-polish-rows-{wname}.txt"), "w", encoding="utf-8") as f:
            f.write(tgt.inner_text() + "\n")
        print(wname, "|", tgt.inner_text().replace("\n", " / "))
        pg.close()
    b.close()
os.remove(page_path)
