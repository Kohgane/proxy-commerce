"""tests/test_lane_gate_v18.py — v18 PART A: 수입/수출 양방향 게이트."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---- 레인 단위 로직 ----
def test_lane_defaults_by_language():
    from src.lane import default_lane_for, get_lane
    assert default_lane_for("ko-KR,ko") == "import"      # 한국=수입
    assert default_lane_for("en-US,en") == "export"      # 외국=수출
    assert default_lane_for("") == "import"
    assert get_lane("export", "ko-KR") == "export"       # 쿠키 명시 우선


def test_lane_info_real_context():
    from src.lane import lane_info
    imp, exp = lane_info("import"), lane_info("export")
    assert imp["lang"] == "ko" and imp["currency"] == "KRW"
    assert "coupang" in imp["target_markets"] and imp["sourcing"] == "overseas"
    assert exp["lang"] == "en" and exp["currency"] == "USD"
    assert "shopify" in exp["target_markets"] and exp["sourcing"] == "domestic"


# ---- 게이트 + set 라우트 ----
@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_gate_renders_two_cards(client):
    html = client.get("/lane").get_data(as_text=True)
    assert "수입형" in html and "수출형" in html
    assert "운영할 방식을 선택하세요" in html
    assert "/lane/set?lane=import" in html and "/lane/set?lane=export" in html


def test_gate_suggests_export_for_foreign(client):
    html = client.get("/lane", headers={"Accept-Language": "en-US,en"}).get_data(as_text=True)
    # 외국 방문자에게 수출 레인 '추천' 강조
    idx = html.find("수출형")
    assert "추천" in html and idx > 0


def test_set_lane_switches_currency_not_language(client):
    # 한/영 자동전환 금지(오너): 레인은 통화 맥락만 구성하고 **언어는 바꾸지 않는다.**
    #   (예전엔 수출형 선택이 kgp_lang=en으로 UI를 제멋대로 EN 전환시켰다.)
    r = client.get("/lane/set?lane=export&next=/seller/", follow_redirects=False)
    assert r.status_code == 302
    cookies = " ".join(r.headers.getlist("Set-Cookie"))
    assert "kgp_lane=export" in cookies
    assert "kgp_lang=" not in cookies         # 언어는 건드리지 않음(명시 토글만)
    assert "kgp_currency=USD" in cookies      # 통화만 레인 맥락으로 구성
    r2 = client.get("/lane/set?lane=import", follow_redirects=False)
    c2 = " ".join(r2.headers.getlist("Set-Cookie"))
    assert "kgp_lang=" not in c2 and "kgp_currency=KRW" in c2


def test_topbar_lane_switcher(client, monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert 'href="/lane"' in html            # 운영 방식 전환 진입
