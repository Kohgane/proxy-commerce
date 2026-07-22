"""tests/test_v81_core_fallback.py — v81 STEP1: 북마클릿 간이 폴백 정직화(되다안되다 종결).

run.js 로더 타임아웃 2.5s→6s + 성공 로드 시 localStorage 캐시(다음 클릭 즉시·백그라운드 갱신). 코어 폴백
발동 시 침묵 금지(토스트 '간이 수집') + 서버 저장 mode=core → 이력 '간이' 배지 + [다시 수집] 유도.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path("src")


def _bm():
    sys.path.insert(0, str(SRC))
    from seller_console.views import _bookmarklet_js
    return _bookmarklet_js("https://x.com", "TOK", True)


def test_timeout_6s_and_cache_source():
    js = _bm()
    # 타임아웃 6s(2.5s 아님).
    assert "setTimeout(function(){go(core(),true);},6000)" in js
    assert ",2500)" not in js
    # localStorage 캐시(다음 클릭 즉시) + 백그라운드 갱신.
    assert "localStorage.getItem('kgp_runjs')" in js
    assert "localStorage.setItem('kgp_runjs'" in js
    assert "function cacheRun()" in js and "if(fromCache){useRun('cache');cacheRun();}" in js


def test_core_fallback_honest_toast_and_mode():
    js = _bm()
    # 코어 폴백 = 침묵 금지 토스트 + data.mode='core'.
    assert "간이 수집(제목·이미지만) — 네트워크 지연으로 확장 수집기 미로드" in js
    assert "data.mode='core'" in js
    # 성공 응답 시에도 간이/풀 구분.
    assert "간이 수집 완료 — 제목·이미지만" in js


def test_bm_js_valid():
    """생성된 북마클릿 JS가 문법 유효(node --check)."""
    import shutil
    if not shutil.which("node"):
        return
    code = _bm()[len("javascript:"):]
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(code); f.close()
    try:
        r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
    finally:
        Path(f.name).unlink()


def test_server_stores_mode_and_history_badge():
    # 서버 저장에 mode 필드 + 이력 뷰가 is_core 플래그 + 템플릿 '간이' 배지.
    ext = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert '"mode": (str(payload.get("mode") or "").strip().lower() or "full")' in ext
    views = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert 'it["is_core"] = (str(ex.get("mode") or "").lower() == "core")' in views
    rows = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    assert "{% if it.is_core %}" in rows and "간이" in rows and "다시 수집" in rows
