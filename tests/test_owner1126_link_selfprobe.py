"""오너 11-26 감독 1 — 렌더 IP에서 짧은 링크를 편 실측을 서버가 스스로 남긴다. 계약.

빌드마다 첫 틱에 한 번 `a.co/d/00RG5ThB`를 편다 → `app_state link_selfprobe:last`에 홉·HTTP·사유 → `/health/deep` `link_probe` 한 줄.
같은 빌드에선 다시 재지 않는다 · 쿼리(추적값)는 적지 않는다 · 막혀도 거짓 성공 없이 사유 그대로.
"""
from __future__ import annotations

import pytest


class _Resp:
    def __init__(self, status, loc=""):
        self.status_code, self.headers = status, ({"Location": loc} if loc else {})

    def close(self):
        pass


@pytest.fixture
def store(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    monkeypatch.setenv("KGP_SHORT_LINK_RESOLVE", "1")
    return s


def test_probe_records_hops_and_item_without_query(store, monkeypatch):
    import requests
    from src.services import link_selfprobe as P
    calls = []

    def _get(url, **kw):
        calls.append(url)
        return _Resp(301, "https://www.amazon.com/dp/B0C38WV1F6?ref_=secret_tracking&th=1")
    monkeypatch.setattr(requests, "get", _get)
    assert P.due("abc123")
    rec = P.run("abc123")
    assert rec["ok"] and rec["item_id"] == "B0C38WV1F6" and rec["build"] == "abc123"
    assert rec["hops"] == [{"status": 301, "host": "a.co"}]
    assert "secret_tracking" not in str(store["link_selfprobe:last"])          # 추적값은 남기지 않는다
    assert not P.due("abc123") and P.due("def456")                            # 빌드마다 한 번
    line = P.health_line()
    assert line["measured"] and line["ok"] and "a.co 301" in line["line"] and "B0C38WV1F6" in line["line"]


def test_probe_blocked_is_recorded_honestly(store, monkeypatch):
    import requests
    from src.services import link_selfprobe as P
    monkeypatch.setattr(requests, "get", lambda url, **kw: _Resp(403))
    rec = P.run("b1")
    assert rec["ok"] is False and rec["reason"] and rec["hops"] == [{"status": 403, "host": "a.co"}]
    assert P.health_line()["ok"] is False and "못 폄" in P.health_line()["line"]


def test_probe_ignores_cached_success(store, monkeypatch):
    """10분 기억(같은 흐름용)이 아니라 지금 잰 값이어야 한다."""
    import requests
    from src.collectors import link_diag as L
    from src.services import link_selfprobe as P
    L._RESOLVED[P.SAMPLE] = (__import__("time").time(), {"ok": True, "item_id": "OLD", "hops": []})
    monkeypatch.setattr(requests, "get", lambda url, **kw: _Resp(403))
    assert P.run("b2")["ok"] is False


def test_health_line_before_any_probe(store):
    from src.services import link_selfprobe as P
    assert P.health_line() == {"measured": False}


def test_health_deep_carries_link_probe(store, monkeypatch):
    from src.order_webhook import app
    store["link_selfprobe:last"] = {"build": "x", "at": "2026-11-26T00:00:00+00:00", "url": "https://a.co/d/00RG5ThB", "ok": True,
                                    "canonical_url": "https://www.amazon.com/dp/B0C38WV1F6", "reason": "ok",
                                    "hops": [{"status": 301, "host": "a.co"}], "elapsed_ms": 120}
    d = app.test_client().get("/health/deep").get_json()
    assert d["link_probe"]["measured"] and "a.co 301" in d["link_probe"]["line"]


def test_tick_kicks_probe_only_when_build_changed(store, monkeypatch):
    from src.services import link_selfprobe as P
    from src.utils import bg_job
    started = []
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (started.append(name) or True, {}))
    monkeypatch.setattr("src.utils.build_info.get_build_sha", lambda: "build-9")
    from tests._ast_probe import importers_of
    assert "src/pricing/cron.py" in importers_of("link_selfprobe")          # 틱이 실측을 깨운다(배선 — AST로)
    assert P.due("build-9")
    store["link_selfprobe:last"] = {"build": "build-9"}
    assert not P.due("build-9")
