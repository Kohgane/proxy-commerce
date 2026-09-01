"""tests/test_m1_mobile_collect.py — M1-1: 모바일 단건 수집 엔드포인트.

**왜 새 엔드포인트인가(실측 근거):** 기존 진입점 셋 중 어느 것도 단축어·봇을 받지 못한다.
  · `/seller/collect/quick`·`/collect/share` → **로그인 세션** 필요(단축어·봇엔 세션이 없다)
  · `/api/v1/collect/bulk` → 토큰은 되지만 **비동기**(job_id 폴링)
  · `/api/v1/collect/extension` → 확장이 만든 페이로드(제목·이미지·HTML) 전제
그래서 **토큰 + 동기 + 단건**이 필요했다. 수집 코어는 벌크와 공유한다(이중 구현 금지).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.api import extension_api as api


@pytest.fixture
def client():
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_store():
    from src.seller_console import collect_history_store as store
    store._in_memory.clear()
    yield
    store._in_memory.clear()


def _auth(monkeypatch, user_id="u1"):
    monkeypatch.setattr(api, "_require_token",
                        lambda scopes=None: {"user_id": user_id, "email": f"{user_id}@x.kr"})


class _Draft:
    title = "PopSockets 그립톡"
    images = ["https://x/a.jpg"]
    price = "19900"
    currency = "KRW"


def test_route_exists_and_requires_token(client):
    """토큰 없으면 401 — 세션 쿠키로는 열리지 않는다(봇·단축어 전용 경로)."""
    r = client.post("/api/v1/collect/one", json={"url": "https://x.com/dp/1"})
    assert r.status_code == 401
    assert r.get_json()["ok"] is False


@pytest.mark.parametrize("send", ["json", "form", "query"])
def test_accepts_url_from_any_shape(client, monkeypatch, send):
    """★ 단축어가 만들기 쉬운 형태를 다 받는다 — JSON · form · 쿼리."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    url = "https://www.amazon.com/dp/B0TEST0001"
    if send == "json":
        r = client.post("/api/v1/collect/one", json={"url": url})
    elif send == "form":
        r = client.post("/api/v1/collect/one", data={"url": url})
    else:
        r = client.post(f"/api/v1/collect/one?url={url}")
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] is True, d
    assert d["item_id"] and d["title"] == "PopSockets 그립톡"


def test_extracts_url_from_shared_text(client, monkeypatch):
    """공유 시트가 제목·본문만 줄 때 거기서 URL을 건져 낸다(기존 share와 동형)."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    r = client.post("/api/v1/collect/one",
                    json={"text": "이거 봐봐 https://item.rakuten.co.jp/shop/abc 괜찮네"})
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_rejects_non_url_honestly(client, monkeypatch):
    _auth(monkeypatch)
    r = client.post("/api/v1/collect/one", json={"url": "그냥 텍스트"})
    assert r.status_code == 400 and "URL" in r.get_json()["error"]


def test_failure_is_honest_not_fake_success(client, monkeypatch):
    """★ 수집 실패는 가짜 성공이 되지 않는다 — 사유를 담아 502."""
    _auth(monkeypatch)

    def _boom(u):
        raise RuntimeError("봇 차단(403)")
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: _boom)
    r = client.post("/api/v1/collect/one", json={"url": "https://x.com/dp/1"})
    d = r.get_json()
    assert r.status_code == 502 and d["ok"] is False
    assert "봇 차단" in d["error"]                    # 원문이 올라온다
    assert "확장" in d["message"]                     # 다음 행동을 알려준다


def test_duplicate_uses_existing_normalized_key(client, monkeypatch):
    """중복 방지는 **기존 정규화 키**(v42 1-3)를 쓴다 — 새 규칙을 만들지 않는다."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    url = "https://www.amazon.com/dp/B0TEST0002"
    first = client.post("/api/v1/collect/one", json={"url": url}).get_json()
    assert first["ok"] and not first["duplicate"]
    # 같은 상품, 트래킹 파라미터만 다른 URL → 같은 키로 잡힌다.
    again = client.post("/api/v1/collect/one",
                        json={"url": url + "?ref=sr_1_3&keywords=grip"}).get_json()
    assert again["ok"] is True and again["duplicate"] is True
    assert again["item_id"] == first["item_id"]


def test_collect_core_is_shared_with_bulk():
    """★ 이중 구현 금지 — 벌크와 단건이 **같은 코어**를 부른다.

    벌크 안에 있던 `process_url`을 모듈 레벨 `collect_one_url`로 끌어올렸고,
    벌크는 그걸 감싸기만 한다. 수집 로직이 두 벌 생기면 한쪽만 고쳐진다.
    """
    src = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert src.count("def collect_one_url") == 1
    assert "return collect_one_url(url, seller_id=seller_id_val" in src   # 벌크가 위임
    assert 'collect_one_url(url, seller_id=seller_id, source="mobile")' in src  # 단건이 위임
    # 벌크·단건 어느 쪽도 이력 저장을 **직접** 하지 않는다 — 코어만 한다.
    bulk = src.split("def _run_bulk_job")[1].split("@extension_bp")[0]
    one = src.split("def collect_one()")[1].split("@extension_bp")[0]
    for name, body in (("bulk", bulk), ("one", one)):
        assert "history_append" not in body, f"{name}이 이력 저장을 따로 한다"


def test_durable_gate_survived(client, monkeypatch):
    """영속 저장이 확인될 때만 ok — v38 P0 게이트가 새 경로에도 살아 있다."""
    _auth(monkeypatch)
    monkeypatch.setattr(api, "_dispatcher_collect", lambda: (lambda u: _Draft()))
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: ("id-1", False))      # 비영속
    r = client.post("/api/v1/collect/one", json={"url": "https://x.com/dp/9"})
    assert r.status_code == 502 and "영속" in r.get_json()["error"]
