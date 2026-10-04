"""Z4(오너 2026-10-04) — 아마존 상품 주소가 **실제로 있나**(AI가 만든 링크 대비).

판정은 셋:
  · `not_found` — 아마존이 **404**로 답함(「존재하지 않는 상품」)
  · `exists`    — 200 + 상품 페이지(로봇 확인 화면 아님)
  · `unknown`   — 로봇 확인(captcha)·503·네트워크 실패 등 — 「확인 불가」(있다/없다 단정 안 함)
"""
from __future__ import annotations

import os
import re

_ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/124.0 Safari/537.36")
_WALL = re.compile(r"validateCaptcha|Robot Check|api-services-support@amazon|Type the characters you see", re.I)


def is_amazon(url: str) -> bool:
    return bool(re.search(r"(^|//|\.)amazon\.[a-z.]+/", str(url or ""), re.I))


def asin(url: str) -> str:
    m = _ASIN.search(str(url or ""))
    return m.group(1).upper() if m else ""


def check(url: str, *, get=None) -> dict:
    """`{state, status, asin, why}`. `get(url, headers, timeout)`를 주입할 수 있다(테스트)."""
    a = asin(url)
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1" and get is None:
        return {"state": "unknown", "status": None, "asin": a, "why": "dry-run — 확인 안 함"}
    if get is None:
        import requests
        get = lambda u, headers, timeout: requests.get(u, headers=headers, timeout=timeout, allow_redirects=True)  # noqa: E731
    try:
        r = get(url, {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}, 15)
    except Exception as exc:                                  # noqa: BLE001
        return {"state": "unknown", "status": None, "asin": a, "why": f"{type(exc).__name__}"}
    st = int(getattr(r, "status_code", 0) or 0)
    body = str(getattr(r, "text", "") or "")[:200000]
    if st == 404:
        return {"state": "not_found", "status": 404, "asin": a, "why": "아마존 404 — 존재하지 않는 상품"}
    if st == 200 and not _WALL.search(body):
        return {"state": "exists", "status": 200, "asin": a, "why": ""}
    why = "로봇 확인 화면" if _WALL.search(body) else f"HTTP {st}"
    return {"state": "unknown", "status": st or None, "asin": a, "why": f"확인 불가 — {why}"}
