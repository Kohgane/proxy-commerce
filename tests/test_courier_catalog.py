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
    """별칭 검색어가 살아 있나 — **공급사가 갈려도 검색은 그대로여야 한다**(F44-b).

    ★ 옛 TrackingMore 코드(`cj-korea`·`hanjin`…)는 **검색어로 남긴다.** 코드 축은
    사라졌지만 사람이 그 글자로 찾던 습관은 남는다 — 검색에서 빼면 「내 택배사가 없다」가 된다.
    """
    from src.seller_console.orders.courier_catalog import find_couriers

    for term, name in (("CJ", "CJ대한통운"), ("씨제이", "CJ대한통운"),
                       ("cj-korea", "CJ대한통운"), ("한진", "한진택배"),
                       ("hanjin", "한진택배"), ("롯데", "롯데택배"),
                       ("lotte", "롯데택배"), ("우체국", "우체국택배"),
                       ("korea-post", "우체국택배"), ("로젠", "로젠택배"),
                       ("logen", "로젠택배")):
        assert any(r["name"] == name for r in find_couriers(term)), term


def test_find_couriers_by_alias():
    from src.seller_console.orders.courier_catalog import find_couriers

    results = find_couriers("hanjin")
    assert any(row["name"] == "한진택배" for row in results)


def test_the_catalog_does_not_call_a_guessed_vendor_url():
    """★★★ F44-b — 추적 공급사 목록 확장은 **지금 없다.**

    예전엔 TrackingMore `couriers/all`을 받아 카탈로그를 넓혔다. 그 공급사는
    **쿼터 소진으로 교체**됐고, 17TRACK 캐리어 목록 URL은 문서에 링크로만 있다.

    ★ **짐작한 주소를 박아 두면** 매 요청이 없는 곳을 두드리고, 실패는 조용한 빈 목록이
    된다 — 그건 「목록이 비었다」와 구분되지 않는다. 그래서 **부르지 않는다.**
    """
    from unittest import mock

    from src.seller_console.orders import courier_catalog

    with mock.patch("requests.get", side_effect=AssertionError("부르면 안 된다")), \
         mock.patch("requests.post", side_effect=AssertionError("부르면 안 된다")):
        rows = courier_catalog.get_courier_catalog(include_dynamic=True)
    assert rows and any(row["name"] == "CJ대한통운" for row in rows)
