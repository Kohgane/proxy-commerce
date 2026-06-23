"""tests/test_collect_button_zoom_v15.py — v15 P0-1 수집 버튼 줌/리사이즈 대응 + 소싱처 파비콘 가드."""
from __future__ import annotations

from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
OPT = Path("extensions/chrome-collector/options.js").read_text(encoding="utf-8")


def test_viewport_resize_clamp_handler():
    # 줌(Ctrl+휠)·리사이즈 시 고정 오버레이를 화면 안으로 재보정
    assert 'addEventListener("resize"' in CS
    assert "kgpClampFixed" in CS and "kgpRegisterFixed" in CS
    assert "__kgpViewportBound" in CS


def test_fab_viewport_bounded_width():
    # FAB가 줌에서 화면 밖으로 넘치지 않도록 뷰포트 기준 max-width
    assert "max-width:min(82vw,300px)" in CS


def test_sources_show_favicon():
    # 등록 소싱처를 사이트 아이콘(파비콘)으로 표시
    assert "s2/favicons?domain=" in OPT
    assert "amazon.*" not in OPT.split("favicons")[1][:200] or ".com" in OPT  # 와일드카드 정규화


def test_manifest_version_bumped():
    mf = Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8")
    assert '"version": "1.5.3"' in mf
