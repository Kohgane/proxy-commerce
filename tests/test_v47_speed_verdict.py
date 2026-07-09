"""tests/test_v47_speed_verdict.py — v47 STEP1: Server-Timing 서버시간 분해(db/render/app/total).

오너가 배포 실서버 네트워크 탭에서 TTFB의 서버시간 성분(db/렌더/앱)을 바로 판정 → Render 승급 게이트.
app = total - db - render. 판정 프레임워크는 docs/screens/v47/step1-speed-verdict.md.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _mem():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    yield


def test_server_timing_has_app_and_total_buckets():
    from src.order_webhook import app
    with app.test_client() as c:
        r = c.get("/seller/collect")
        st = r.headers.get("Server-Timing", "")
        assert "app;dur=" in st, st          # 앱(=total-db-render) 서버시간 명시
        assert "total;dur=" in st, st        # 총 서버시간(TTFB 서버성분)


def test_app_bucket_is_nonnegative():
    # app = max(0, total - db - render) → 음수 방지(측정 순서 오차로도 음수 안 나옴)
    from src.order_webhook import app
    with app.test_client() as c:
        r = c.get("/seller/collect")
        st = r.headers.get("Server-Timing", "")
        val = None
        for part in st.split(","):
            part = part.strip()
            if part.startswith("app;dur="):
                val = float(part.split("=", 1)[1])
        assert val is not None and val >= 0.0, st


def test_verdict_doc_has_gate_framework():
    doc = Path("docs/screens/v47/step1-speed-verdict.md").read_text(encoding="utf-8")
    assert "≥ 50%" in doc and "Render Standard 승급 권고" in doc   # 승급 게이트 기준
    assert "오너 캡처" in doc                                       # 배포 실측=오너 몫(정직)
    assert "app;dur" in doc                                          # 측정도구 명시
