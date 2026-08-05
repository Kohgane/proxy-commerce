"""v86-G 판정 캡처 — 목록 타일 수집 항목의 '간이' 뱃지 before/after.

before = 종전 동작(타일 수집이 mode:'full'로 저장 → 뱃지 없음, 상세페이지 수집분과 구별 불가)
after  = 이번 수정(mode:'simple' 강등 → '간이' 뱃지 + 타일 전용 안내 문구)

실제 템플릿(collect_history_rows.html)을 그대로 렌더한다 — 목업 HTML을 따로 짜면
"화면이 이렇게 나올 것"이라는 추측 캡처가 되므로 금지(정직 데이터 원칙).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "screens" / "v86" / "g-simple-badge.png"

_ITEMS = [
    # (라벨, mode, is_core)
    ("상세페이지 수집 (full)", "full", False),
    ("목록 타일 수집", "simple", True),
    ("북마클릿 폴백 (core)", "core", True),
]


def _item(idx, label, mode, is_core):
    return {
        "id": f"it{idx}",
        "url": "https://www.amazon.com/dp/B0HOME0001",
        "domain": "amazon.com",
        "title": label,
        "title_display": label,
        "title_is_original": False,
        "price": "24.99",
        "currency": "USD",
        "source": "extension",
        "status": "ok",
        "collected_at": "2026-08-06 14:20",
        "thumbs": [],
        "uploaded_markets": [],
        "collect_status": {},
        "enrich_status": "",
        "is_core": is_core,
        "collect_mode": mode,
    }


def _render(after: bool) -> str:
    """after=False면 '간이' 판정을 끈 상태(=종전 동작)로 렌더."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(ROOT / "src" / "seller_console" / "templates")),
        autoescape=select_autoescape(["html"]),
    )
    tpl = env.get_template("collect_history_rows.html")
    items = [_item(i, lbl, mode, core) for i, (lbl, mode, core) in enumerate(_ITEMS)]
    if not after:
        # 종전: 타일 수집이 full로 저장돼 간이 판정이 안 붙었다(core만 뱃지).
        for it in items:
            if it["collect_mode"] == "simple":
                it["collect_mode"], it["is_core"] = "full", False
    return tpl.render(items=items)


_SHELL = """<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
<style>
  :root{--warn:#f5821f;--success:#2f9e44;--teal:#119a8e}
  body{background:#f5efe3;font-family:Pretendard,-apple-system,sans-serif;padding:20px;width:980px}
  h2{font-size:15px;letter-spacing:.08em;text-transform:uppercase;color:#8a7f70;margin:18px 0 8px}
  table{background:#fff;border-radius:8px;overflow:hidden}
</style>
<h2>BEFORE — 타일 수집이 full로 저장(간이 표시 없음)</h2>
<table class="table table-sm align-middle"><tbody>__BEFORE__</tbody></table>
<h2>AFTER — 타일 수집 = mode:simple 강등 → '간이' 뱃지</h2>
<table class="table table-sm align-middle"><tbody>__AFTER__</tbody></table>
"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    html = _SHELL.replace("__BEFORE__", _render(False)).replace("__AFTER__", _render(True))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1000, "height": 700}).new_page()
        page.set_content(html)
        page.wait_for_timeout(1200)   # CDN CSS/아이콘 폰트 로드
        page.screenshot(path=str(OUT), full_page=True)
        browser.close()
    print(f"saved: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
