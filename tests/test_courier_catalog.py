"""tests/test_courier_catalog.py — 통합 택배사 카탈로그 테스트."""
from __future__ import annotations

import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_catalog_contains_required_aliases():
    from src.seller_console.orders.courier_catalog import get_courier_catalog

    catalog = get_courier_catalog(include_dynamic=False)
    by_name = {row["name"]: row for row in catalog}
    assert "CJ대한통운" in by_name
    assert "한진택배" in by_name
    assert "롯데택배" in by_name
    assert "우체국택배" in by_name
    assert "로젠택배" in by_name
    assert "씨제이" in by_name["CJ대한통운"]["aliases"]
    assert "cj-korea" in by_name["CJ대한통운"]["search_terms"]


def test_alias_lookup_ko_and_en():
    from src.seller_console.orders.courier_catalog import lookup_trackingmore_code

    assert lookup_trackingmore_code("CJ") == "cj-korea"
    assert lookup_trackingmore_code("씨제이") == "cj-korea"
    assert lookup_trackingmore_code("cj-korea") == "cj-korea"
    assert lookup_trackingmore_code("한진") == "hanjin"
    assert lookup_trackingmore_code("hanjin") == "hanjin"
    assert lookup_trackingmore_code("롯데") == "lotte"
    assert lookup_trackingmore_code("lotte") == "lotte"
    assert lookup_trackingmore_code("우체국") == "korea-post"
    assert lookup_trackingmore_code("korea-post") == "korea-post"
    assert lookup_trackingmore_code("로젠") == "logen"
    assert lookup_trackingmore_code("logen") == "logen"


def test_find_couriers_by_alias():
    from src.seller_console.orders.courier_catalog import find_couriers

    results = find_couriers("hanjin")
    assert any(row["name"] == "한진택배" for row in results)


def test_dynamic_catalog_fallback_when_api_unavailable(monkeypatch):
    monkeypatch.setenv("TRACKINGMORE_API_KEY", "tm_test")

    class FailResp:
        def raise_for_status(self):
            raise RuntimeError("offline")

    with mock.patch("requests.get", return_value=FailResp()):
        from src.seller_console.orders import courier_catalog

        courier_catalog._fetch_trackingmore_catalog.cache_clear()
        rows = courier_catalog.get_courier_catalog(include_dynamic=True)
        assert rows
        assert any(row["name"] == "CJ대한통운" for row in rows)


def test_dynamic_catalog_expands_when_api_available(monkeypatch):
    monkeypatch.setenv("TRACKINGMORE_API_KEY", "tm_test")

    class OkResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "courier_code": "custom-courier",
                        "courier_name": "Custom Courier",
                        "courier_name_kr": "커스텀택배",
                    }
                ]
            }

    with mock.patch("requests.get", return_value=OkResp()):
        from src.seller_console.orders import courier_catalog

        courier_catalog._fetch_trackingmore_catalog.cache_clear()
        rows = courier_catalog.get_courier_catalog(include_dynamic=True)
        assert any(row["trackingmore_code"] == "custom-courier" for row in rows)
