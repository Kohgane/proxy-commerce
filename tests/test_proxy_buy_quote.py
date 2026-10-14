from decimal import Decimal

from src.proxy_buy.musinsa import parse_musinsa
from src.proxy_buy.quote_core import build_quote, find_prohibited


def test_basic_quote_matches_formula():
    q = build_quote(75000, 0, 0, 1020)
    # 75000/1020=73.53 ; 마진 8.82 ; (82.35+0.30)/0.956
    assert q.ok
    assert q.margin_usd == Decimal("8.82")
    assert Decimal("86.0") < q.total_usd < Decimal("87.0")


def test_min_margin_six_dollars():
    q = build_quote(10000, 0, 0, 1000)  # 12% = $1.2 -> 최소 $6
    assert q.margin_usd == Decimal("6.00")


def test_pg_reserve_covers_paypal():
    q = build_quote(50000, 3000, 20, 1000)
    sub = q.item_usd + q.kr_ship_usd + q.margin_usd + q.intl_ship_usd
    net = q.total_usd * (1 - Decimal("0.044")) - Decimal("0.30")
    assert abs(net - sub) < Decimal("0.05")


def test_duty_is_separate_not_in_total():
    a = build_quote(75000, 0, 10, 1020)
    b = build_quote(75000, 0, 10, 1020, duty_rate="0.1")
    assert a.total_usd == b.total_usd
    assert b.duty_estimate_usd and b.duty_estimate_usd > 0


def test_no_forbidden_words_in_output():
    text = " ".join(build_quote(75000, 2500, 15, 1020, duty_rate="0.1").lines()).lower()
    for w in ("service fee", "수수료", "대행"):
        assert w not in text


def test_first_order_cap():
    assert build_quote(700000, 0, 30, 1020).over_cap
    assert not build_quote(75000, 0, 10, 1020).over_cap


def test_prohibited_categories():
    assert find_prohibited("프리미엄 비타민 영양제")
    assert find_prohibited("부탄가스 캠핑")
    assert not find_prohibited("오버핏 후드 자켓")
    assert not build_quote(30000, 0, 10, 1020, title="향수 스프레이").ok


def test_musinsa_next_data_parse():
    html = ('<html><script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"meta":{"x":1},"goods":{"goodsNm":"오버핏 후드","salePrice":75000}}}}'
            '</script></html>')
    r = parse_musinsa(html)
    assert r == {"title": "오버핏 후드", "price_krw": 75000, "kr_ship_krw": 0}


def test_musinsa_unparseable_returns_none():
    assert parse_musinsa("<html></html>") is None
    assert parse_musinsa('<script id="__NEXT_DATA__">{broken</script>') is None


def test_no_false_positive_on_chong_word():
    assert not find_prohibited("총총 레터링 티셔츠")


def test_musinsa_prefers_goods_node_over_generic():
    html = ('<script id="__NEXT_DATA__">{"a":{"name":"추천","price":1000},'
            '"goods":{"goodsNm":"진짜 상품","salePrice":59000}}</script>')
    assert parse_musinsa(html)["title"] == "진짜 상품"
