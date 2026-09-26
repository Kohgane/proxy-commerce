"""F49-T 2부 — 타오바오·티몰 초안의 통화는 **도메인이 곧 통화**(CNY). 가격은 여전히 지어내지 않는다.

오너 실측(2026-09-26): 붙여넣기 초안이 「통화 미상」 — URL에 `price=`가 있을 때만 CNY를 적었다.
확장 공유 추출기는 같은 도메인 규칙으로 이미 CNY를 보낸다(`kgp-extractor.js`) — 두 입구를 같은 규칙으로.
"""
import re
from pathlib import Path

import pytest

from src.collectors.share_text import site_currency


@pytest.mark.parametrize("url,cur", [
    ("https://item.taobao.com/item.htm?id=1", "CNY"),
    ("https://detail.tmall.com/item.htm?id=617129397971", "CNY"),
    ("https://m.intl.taobao.com/detail/detail.html?id=1", "CNY"),
    ("https://e.tb.cn/h.8IcTrtZuTU19ieN", "CNY"),
    ("https://www.amazon.com/dp/B0X", ""),
    ("https://detail.1688.com/offer/1.html", ""),     # 1688은 이 규칙 밖(측정 전)
    ("", ""),
])
def test_site_currency_is_a_domain_rule(url, cur):
    assert site_currency(url) == cur


def test_the_extension_uses_the_same_domain_rule():
    """확장 쪽 규칙(taobao·tmall → CNY)과 서버 쪽 규칙이 같은 도메인을 가리킨다."""
    js = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
    assert re.search(r"\(taobao\|tmall\|1688\)\\\.com\$/\.test\(host\)\) return \"CNY\"", js)


def test_a_pasted_tmall_url_without_price_is_cny_but_price_stays_empty(monkeypatch):
    from src.collectors.share_collect import collect_input
    saved = {}
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: saved.update(kw) or ("i1", True))
    r = collect_input("https://detail.tmall.com/item.htm?id=617129397971", seller_id="u", source="preview",
                      translate=False)
    assert r["ok"] and saved["currency"] == "CNY" and saved["price"] == ""
    assert "price" in saved["extra"]["uncollected"]


def test_the_preview_route_no_longer_says_currency_unknown():
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-f49t2"
        d = c.post("/seller/collect/preview", json={"url": "https://detail.tmall.com/item.htm?id=617129397971",
                                                    "translate": False}).get_json()
    assert d["draft"]["currency"] == "CNY" and d["draft"]["price"] == ""
