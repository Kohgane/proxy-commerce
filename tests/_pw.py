"""tests/_pw.py — Playwright chromium 탐지 단일 소스 (v86 STEP2).

왜 필요한가: 확장 UI 계약은 **실브라우저에서만** 재현된다(jsdom은 all:initial 계열을 못 흉내낸다).
그런데 각 테스트가 `glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")`로 **CI 리눅스 경로만**
확인하고 있어서, 개발 머신(윈도우/맥)에서는 브라우저가 설치돼 있어도 전부 **조용히 skip**됐다.
그 결과 "로컬 그린"이 실제로는 계약을 하나도 돌리지 않은 공허한 그린이었고, 회귀는 CI에서야 드러났다.

여기서 CI 경로 + playwright가 관리하는 기본 설치 위치(OS별·PLAYWRIGHT_BROWSERS_PATH 포함)를 함께 본다.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

_CI_GLOB = "/opt/pw-browsers/chromium-*/chrome-linux*/chrome"
_cached: list[str] | None = None


def chromium_hits() -> list[str]:
    """실행 가능한 chromium 경로 목록. 비어 있으면 미설치.

    반환값을 그대로 `bool(...)`(스킵 판정)에도, `[0]`(executable_path)에도 쓸 수 있게 리스트로 준다.
    """
    global _cached
    if _cached is not None:
        return _cached
    hits = glob.glob(_CI_GLOB)
    if not hits:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                exe = pw.chromium.executable_path
            if exe and Path(exe).exists():
                hits = [exe]
        except Exception:
            hits = []
    _cached = hits
    return hits


def launch_opts() -> dict:
    """pw.chromium.launch(**opts) 인자 — 실행 경로 + (있으면) 프록시."""
    hits = chromium_hits()
    opts: dict = {"executable_path": hits[0]} if hits else {}
    proxy = os.environ.get("HTTPS_PROXY")
    if proxy:
        opts["proxy"] = {"server": proxy, "bypass": "127.0.0.1,localhost"}
    return opts
