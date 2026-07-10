"""tests/test_v51_instant_nav.py — v51 STEP2: 0.5초 내비(풀 기본 ON + 드로어 왕복 1회 + 즉시 skeleton).

DNS 싱가포르 전환 전제(오너 진행). dbq 계측으로 3페이지 쿼리 ≤3 확인. 상시 풀 기본 ON. 드로어 마켓
연결상태 5회 왕복 → 1회. hover prefetch + 진행바(기존) + 클릭 즉시 skeleton. 정적 immutable 캐시.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

PG = Path("src/db/pg.py").read_text(encoding="utf-8")
BASE = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
OWH = Path("src/order_webhook.py").read_text(encoding="utf-8")


def test_pool_default_on():
    assert 'os.getenv("PG_PERSISTENT_POOL", "1")' in PG   # 기본 ON
    assert "if not db_url():" in PG                        # DB 없으면 폴백(무회귀)


def test_connected_markets_single_load():
    # 5개 마켓 연결여부를 _load_all 1회로 판정(왕복 절감).
    from src.seller_console import market_credentials as mc
    calls = {"n": 0}
    def _fake_load(sid):
        calls["n"] += 1
        return {"coupang": {"COUPANG_ACCESS_KEY": "x", "COUPANG_SECRET_KEY": "y", "COUPANG_VENDOR_ID": "z"}}
    with patch.object(mc, "_load_all", _fake_load):
        res = mc.connected_markets("u1", ("shopify", "coupang", "smartstore", "elevenst", "woocommerce"))
    assert calls["n"] == 1, "connected_markets는 _load_all 1회만 호출해야"
    assert isinstance(res, dict) and set(res.keys()) == {"shopify", "coupang", "smartstore", "elevenst", "woocommerce"}


def test_drawer_uses_batched_connected_markets():
    assert "mc.connected_markets(" in VIEWS               # 드로어가 배치 호출 사용
    assert "market_connected[m] = bool(mc.is_connected" not in VIEWS   # 옛 5회 루프 제거


def test_instant_skeleton_and_prefetch():
    # 클릭 즉시 skeleton + hover/touch prefetch + 진행바(기존).
    assert "kgp-nav-skeleton" in BASE and "showSkeleton" in BASE
    assert "rel = 'prefetch'" in BASE or "l.rel = 'prefetch'" in BASE
    assert "kgp-progress" in BASE                          # 진행바 유지
    # 내부 링크만·새탭 제외
    assert "location.origin" in BASE


def test_static_immutable_cache_present():
    assert "max-age=31536000" in OWH and "immutable" in OWH   # 버전드 정적 1년 immutable
