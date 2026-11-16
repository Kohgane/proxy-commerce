"""감독 11-16 — #1021 호출자 계수 24h: extra_json째 목록의 범인 = 확장 폴링 `/api/v1/collect/enrich/pending`
(271회·14,092행 — 나머지는 lean 8회뿐). 대기 판정·응답에 쓰는 칸만 끈다.

계약: ① 그 목록은 `extra_keys`로(ENRICH_AXES_KEYS + title · uncollected) ② 응답은 전체 행으로 읽었을 때와 같다
③ 뷰의 `_ENRICH_KEYS`와 같은 정본 한 곳.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app as flask_app
    flask_app.config["TESTING"] = True
    from src.api import extension_api as E
    monkeypatch.setattr(E, "_require_token", lambda **kw: {"user_id": "u-ep", "scopes": ["collect.write"]})
    from src.seller_console import collect_history_store as S
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    monkeypatch.setattr(S, "_in_memory", [])
    return flask_app.test_client()


def _seed():
    from src.seller_console import collect_history_store as S
    big = [{"idx": i, "boxes": ["x" * 200] * 40} for i in range(6)]
    S.append(source="share", url="https://item.taobao.com/item.htm?id=1", title="링크만", seller_id="u-ep",
             extra={"mode": "simple", "enrich_state": "pending", "enrich_attempts": 1, "uncollected": ["images", "price"],
                    "images": ["https://img/a.jpg"], "images_ko": big, "title": "링크만"})
    S.append(source="share", url="https://item.taobao.com/item.htm?id=2", title="다 됨", seller_id="u-ep",
             extra={"mode": "full", "enrich_state": "done", "enriched": True, "images": ["a", "b", "c"], "price": "9"})
    S.append(source="share", url="https://item.taobao.com/item.htm?id=3", title="상한", seller_id="u-ep",
             extra={"mode": "simple", "enrich_state": "pending", "enrich_attempts": 99})


def test_pending_poll_reads_only_its_keys_and_answers_the_same(client, monkeypatch):
    from src.seller_console import collect_history_store as S
    _seed()
    real = S.list_items
    seen = []

    def spy(**kw):
        seen.append(kw.get("extra_keys"))
        return real(**kw)
    monkeypatch.setattr(S, "list_items", spy)
    lean = client.get("/api/v1/collect/enrich/pending").get_json()

    monkeypatch.setattr(S, "list_items", lambda **kw: real(**{k: v for k, v in kw.items() if k != "extra_keys"}))
    full = client.get("/api/v1/collect/enrich/pending").get_json()

    assert lean == full and lean["ok"] and [i["title"] for i in lean["items"]] == ["링크만"]
    assert lean["items"][0]["uncollected"] == ["images", "price"] and lean["items"][0]["images_count"] == 1
    from src.collectors.collect_status import ENRICH_AXES_KEYS
    assert seen and set(seen[0]) == set(ENRICH_AXES_KEYS) | {"title", "uncollected"}
    assert "images_ko" not in seen[0] and "images" not in seen[0]


def test_one_source_of_truth_for_enrich_keys():
    from src.collectors.collect_status import ENRICH_AXES_KEYS
    from src.seller_console import views as V
    assert V._ENRICH_KEYS is ENRICH_AXES_KEYS
