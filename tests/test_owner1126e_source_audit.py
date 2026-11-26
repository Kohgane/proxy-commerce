"""오너 11-26 저녁 ② — 소싱처별 수집 상태(운영 읽기 전용 진단) 계약.

쓸 만한 사진 비율은 주소 크기 토큰으로 판정할 수 있는 장만 센다(모르면 따로) · 옵션 있는데 SKU 0 · 짧은 링크 · 관리자만 · 쓰기 0.
"""
from __future__ import annotations

import json

import pytest


def _row(url, **ex):
    return {"id": url[-6:], "url": url, "domain": "", "extra_json": json.dumps(ex)}


ROWS = [
    _row("https://www.amazon.com/dp/B0C38WV1F6", images=["https://m.media-amazon.com/images/I/a._AC_US40_.jpg",
                                                         "https://m.media-amazon.com/images/I/a._AC_SL1500_.jpg"],
         options=[{"name": "색상", "values": ["A", "B"]}], skus=[]),
    _row("https://a.co/d/abc123", images=[]),
    _row("https://www.aliexpress.com/item/1005001.html", images=["https://ae01.alicdn.com/kf/S1.jpg_480x480q75.jpg_.avif"],
         options=[{"name": "Color", "values": ["Red", "Blue"]}], skus=[{"spec": ["Red"], "price": "1"}]),
    _row("https://item.rakuten.co.jp/shop/x/", images=["https://image.rakuten.co.jp/shop/cabinet/x.jpg"]),
]


def test_audit_counts_without_guessing():
    from src.services import source_audit as SA
    d = SA.audit(ROWS)
    by = {a["source"]: a for a in d["sources"]}
    amz = by["amazon"]
    assert amz["rows"] == 2 and amz["usable"] == 1 and amz["small"] == 1 and amz["usable_pct"] == 50.0
    assert amz["opt_no_sku"] == 1 and amz["short"] == 1 and amz["no_images"] == 1
    assert by["aliexpress"]["small"] == 1 and by["aliexpress"]["opt_no_sku"] == 0
    rak = by["rakuten"]
    assert rak["unknown"] == 1 and rak["usable_pct"] is None                              # 주소로 모르면 판정하지 않는다
    v = SA.verdict(d)
    assert "아마존: 쓸 만한 사진 50.0% · 옵션 있는데 SKU 0 1건 · 짧은 링크 1건" in v and "라쿠텐" not in v


def test_measure_sample_reads_real_sizes():
    from src.services import source_audit as SA
    d = SA.audit(ROWS, measure=2, size_of=lambda u: {"long_side": 270 if "rakuten" in u else 1500})
    by = {a["source"]: a for a in d["sources"]}
    assert by["rakuten"]["measured"] == {"n": 1, "read": 1, "under": 1, "min": 270, "max": 270}
    assert "라쿠텐: 잰 첫 사진 1장 중 1장 500px 미만" in SA.verdict(d)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


def test_route_admin_only_and_renders_korean(client, monkeypatch):
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_is_admin_user", lambda: False)
    assert client.get("/seller/admin/diag/sources").status_code == 403
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    from src.seller_console import collect_history_store as S
    S.append(source="share", url="https://www.amazon.com/dp/B0C38WV1F6", title="OKNIFE", price="1", currency="KRW", image="",
             seller_id="default", extra={"images": ["https://m.media-amazon.com/images/I/a._AC_US40_.jpg"]})
    h = client.get("/seller/admin/diag/sources", headers={"Accept": "text/html"}).get_data(as_text=True)
    assert 'data-mode="sources"' in h and "소싱처별 수집 상태" in h and 'data-source="amazon"' in h and "읽기 전용" in h
    j = client.get("/seller/admin/diag/sources?raw=1").get_json()
    assert j["ok"] and j["days"] == 90 and any(a["source"] == "amazon" for a in j["sources"])
