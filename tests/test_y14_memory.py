"""Y14-2(오너 2026-10-20 「413MB 상시 점유」) — 지연 임포트 · 일 끝난 자리에서 malloc_trim.

로컬 실측(같은 스크립트, main 44e7f802 → 이 브랜치): 앱 import 111 → 99MB(gspread 부팅 체인 제거) ·
8스레드 큰 사진 작업 뒤 워커 회차 끝 722MB → 200MB(`record_run` → `rss.release`).
"""
import subprocess
import sys


def test_sheets_does_not_load_gspread_at_import():
    code = ("import sys; import src.utils.sheets as S; print('gspread' in sys.modules, 'oauth2client' in sys.modules);"
            "S.gspread.exceptions; print('gspread' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert out == ["False", "False", "True"]                       # 처음 쓸 때 실린다


def test_app_boot_does_not_load_heavy_modules():
    code = ("import os, sys; os.environ['SELLER_CONSOLE_AUTH']='0'; from src.order_webhook import app;"
            "print([m for m in ('gspread','anthropic','cv2','numpy','pypinyin') if m in sys.modules])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    assert out == "[]"


def test_worker_round_end_releases_heap(monkeypatch):
    from src.services import workers as W
    from src.utils import rss
    calls = []
    monkeypatch.setattr(rss, "release", lambda reason="": calls.append(reason) or (0, 0))
    monkeypatch.setattr(W, "_state", lambda: type("S", (), {"state_get": staticmethod(lambda k: {}),
                                                             "state_set": staticmethod(lambda k, v: None)}))
    W.record_run("imgko-auto", 3)
    W.record_run("reject-watch", 0)                                # 한 일이 없으면 부르지 않는다
    assert calls == ["worker:imgko-auto"]


def test_release_trims_and_reports(monkeypatch):
    from src.utils import rss, render_worker
    seq = iter([500, 180])
    monkeypatch.setattr(rss, "read_mb", lambda: (next(seq), 0))
    trimmed = []
    monkeypatch.setattr(render_worker, "trim", lambda: trimmed.append(1) or True)
    assert rss.release("t") == (500, 180) and trimmed == [1]


def test_heavy_request_releases_after(monkeypatch):
    from src.utils import rss
    calls = []
    monkeypatch.setattr(rss, "release", lambda reason="": calls.append(reason) or (0, 0))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="u-mem", user_email="u-mem@example.com", user_role="seller")
    c.post("/seller/collect/upload", json={"product": {}, "markets": []})
    c.get("/seller/")
    assert calls == ["collect_upload"]                             # 등록 요청 뒤에만(대시보드는 아님)
