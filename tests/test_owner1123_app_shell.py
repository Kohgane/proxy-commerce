"""오너 11-23 「앱이 실제 앱처럼 작동해야 한다」 PR1 — 폰·앱 웹뷰 셸 하나 + 목록 썸네일.

계약:
- 앱 판정: `?app=1`(쿠키로 기억) · 쿠키 · UA `gogabridjApp` → html.kgp-app. 아니면 웹.
- 「데스크톱 →」·「홈 화면에 추가」·「BETA」·설치 버튼은 kgp-web-only(앱·standalone에서 숨김).
- /seller/* 의 _base_app 화면(M5 등록·공유 결과·설정)도 같은 셸, PC 상단 내비는 폰에서 숨김. 랜딩·/lane 은 셸 없음.
- /seller/m 최근 수집은 M5(/seller/m/item/<id>)로 — 3,330줄 서랍(collect/preview)로 안 간다 · 쓰는 칸만 읽는다.
- 썸네일 순서: 우리 저장본(Cloudinary 작은 판) → 원본 대표 → 갤러리 첫 장 · 빈 그림(naturalWidth ≤2)은 실패로.
"""
from __future__ import annotations

import json
import re

import pytest


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _clear():
    from src.seller_console import collect_history_store as chs
    chs._in_memory.clear()
    yield
    chs._in_memory.clear()


def _is_app(html: str) -> bool:
    return bool(re.search(r'<html[^>]*class="kgp-app"', html))


def test_app_detection_query_cookie_and_ua(client):
    r = client.get("/seller/m?app=1")
    assert _is_app(r.get_data(as_text=True)) and "kgp_app=1" in r.headers.get("Set-Cookie", "")
    assert _is_app(client.get("/seller/orders").get_data(as_text=True))           # 쿠키로 기억 — 다음 링크도 앱
    client.get("/seller/m?app=0")
    assert not _is_app(client.get("/seller/orders").get_data(as_text=True))
    ua = {"User-Agent": "Mozilla/5.0 (iPhone) AppleWebKit/605.1.15 gogabridjApp/1.0"}
    assert _is_app(client.get("/seller/collect/history", headers=ua).get_data(as_text=True))
    assert not _is_app(client.get("/seller/collect/history").get_data(as_text=True))


def test_web_only_hints_marked(client):
    home = client.get("/seller/m").get_data(as_text=True)
    assert 'class="m-beta kgp-web-only"' in home
    more = client.get("/seller/m?tab=more").get_data(as_text=True)
    for marker in ("데스크톱 전체 콘솔", "홈 화면에 추가", "고가브릿지 앱 설치"):
        assert re.search(r'class="[^"]*kgp-web-only[^"]*"[^>]*>(?:(?!</a>|</div>|</button>).){0,200}?' + re.escape(marker), more, re.S), marker
    base = client.get("/seller/dashboard").get_data(as_text=True)
    assert re.search(r'id="pwaInstallBtn"[^>]*kgp-web-only', base) and re.search(r'id="pwaIosHint"[^>]*kgp-web-only', base)
    css = open("src/static/m_shell.css", encoding="utf-8").read()
    assert "html.kgp-app .kgp-web-only { display: none !important; }" in css
    assert "@media (display-mode: standalone) { .kgp-web-only { display: none !important; } }" in css


def test_base_app_seller_pages_get_the_shell_landing_does_not(client):
    for path in ("/seller/guide/iphone", "/seller/m/item/none"):
        html = client.get(path).get_data(as_text=True)
        assert 'class="kgp-mtop"' in html and 'class="kgp-mtab"' in html, path
        assert '<div class="kgp-pc-only">' in html, path                         # PC 내비는 폰에서 숨는 상자 안
    for path in ("/", "/lane"):
        html = client.get(path).get_data(as_text=True)
        assert 'class="kgp-mtab"' not in html, path


def test_mobile_home_recent_opens_m5_not_drawer(client):
    from src.seller_console import collect_history_store as chs
    iid = chs.append(source="manual", url="https://x/1", title="가방A", price="100", currency="USD",
                     image="https://img.alicdn.com/a.jpg", seller_id="default",
                     extra={"images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"],
                            "images_stored": ["https://res.cloudinary.com/demo/image/upload/v1/p0.webp"]})
    html = client.get("/seller/m").get_data(as_text=True)
    assert f'href="/seller/m/item/{iid}"' in html and "/seller/collect/preview/" not in html
    assert 'src="https://res.cloudinary.com/demo/image/upload/c_fill,w_128,h_128,q_auto,f_auto/v1/p0.webp"' in html
    assert 'data-alts="https://img.alicdn.com/a.jpg"' in html


def test_thumb_candidates_order():
    from src.seller_console.views import thumb_candidates
    ex = {"images_stored": ["https://res.cloudinary.com/d/image/upload/v9/x.webp"], "images": ["https://cdn/g0.jpg", "https://cdn/g1.jpg"]}
    rep, alts = thumb_candidates("https://cdn/rep.jpg", ex)
    assert rep == "https://res.cloudinary.com/d/image/upload/c_fill,w_128,h_128,q_auto,f_auto/v9/x.webp"
    assert alts == ["https://cdn/rep.jpg", "https://cdn/g0.jpg"]
    assert thumb_candidates("", {"images": ["https://cdn/g0.jpg"]}) == ("https://cdn/g0.jpg", [])
    assert thumb_candidates("", {}) == ("", [])                                      # 없는 장은 지어내지 않는다
    already = "https://res.cloudinary.com/d/image/upload/c_fill,w_64/v1/y.jpg"
    assert thumb_candidates("", {"images_stored": [already]})[0] == already          # 이미 변환된 주소는 그대로


def test_list_rows_use_stored_copy_and_treat_blank_as_failure(client):
    from src.seller_console import collect_history_store as chs
    chs.append(source="manual", url="https://item.taobao.com/item.htm?id=9", title="BLACKHOLES", price="9", currency="CNY",
               image="https://img.alicdn.com/rep.jpg", seller_id="default",
               extra={"images": ["https://img.alicdn.com/rep.jpg"], "images_stored": ["https://res.cloudinary.com/d/image/upload/v1/s.webp"]})
    html = client.get("/seller/collect/history?days=365").get_data(as_text=True)
    img = re.search(r'<img [^>]*data-role="ch-thumb"[^>]*>', html, re.S).group(0)
    assert 'src="https://res.cloudinary.com/d/image/upload/c_fill,w_128,h_128,q_auto,f_auto/v1/s.webp"' in img
    assert 'data-alts="https://img.alicdn.com/rep.jpg"' in img
    assert "naturalWidth<=2" in img                                               # 오류 없이 오는 빈 그림도 실패로


def test_lean_list_carries_first_stored_copy():
    from src.db import collect_history_pg as C
    assert "'images_stored', CASE WHEN jsonb_typeof(extra_json->'images_stored')='array'" in C._LEAN_EXTRA
    assert "jsonb_build_array(extra_json->'images_stored'->0)" in C._LEAN_EXTRA


def test_shell_script_contract():
    js = open("src/seller_console/static/m_shell.js", encoding="utf-8").read()
    for needle in ("history.back()", "data-role=\"m-skeleton\"", "data-ptr", "location.reload()", "window.kgpJobLine",
                   "window.webkit && window.webkit.messageHandlers", "display-mode: standalone"):
        assert needle in js, needle


def test_list_tap_opens_m5_on_phone_and_skips_heavy_prewarm():
    html = open("src/seller_console/templates/collect_history.html", encoding="utf-8").read()
    assert "if (_chPhone()) { location.href = '/seller/m/item/' + encodeURIComponent(id); return; }" in html
    assert "if (!id || warmed[id] || inflight || _chPhone()) return;" in html


def test_ios_app_markers_mean_app_mode_and_native_refresh_wins():
    """아이폰 앱 v1.1은 `window.KG_APP`·`html.kg-app`을 붙이고 네이티브 당겨서 새로고침이 있다."""
    js = open("src/seller_console/static/m_shell.js", encoding="utf-8").read()
    assert "if (window.KG_APP) html.classList.add('kg-app');" in js
    assert "html.classList.contains('kg-app')) html.classList.add('kgp-app');" in js
    assert "!document.documentElement.classList.contains('kg-app')" in js     # 앱 안에선 웹 PTR 끔(두 번 돌지 않게)
