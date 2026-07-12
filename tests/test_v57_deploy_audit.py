"""tests/test_v57_deploy_audit.py — v57 STEP0: v56 배포 감사 + 구버전 경고 배너."""
from __future__ import annotations
import os
from pathlib import Path
os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
TPL = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")


def test_loader_routes_present():
    assert "def bookmarklet_run_js" in VIEWS and "def bookmarklet_testpage" in VIEWS
    assert "seller/bookmarklet/run.js" in VIEWS   # 로더가 run.js 주입


def test_old_bookmarklet_warning_banner():
    # v58 STEP3: '설치 전 기존 고가수집 북마크 전부 삭제' 경고 + 구버전 무동작 명시.
    assert "전부 삭제" in TPL and "작동하지 않습니다" in TPL
    # 배너가 최상단(첫 카드/헤딩보다 앞)
    assert TPL.index("전부 삭제") < TPL.index("북마클릿 (고급)")


def test_run_js_and_testpage_live():
    from src.order_webhook import app
    with app.test_client() as c:
        assert "window.__kgpRun" in c.get("/seller/bookmarklet/run.js").get_data(as_text=True)
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        assert c.get("/seller/bookmarklet/testpage").status_code == 200
        assert c.get("/seller/bookmarklet").status_code == 200
