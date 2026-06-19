"""tests/test_collect_receiver.py — 북마클릿 postMessage 수집(이미지/상세/리뷰 + 번역선택)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


_HTML = """<html><head>
<meta property="og:title" content="가죽 가방">
<meta property="og:image" content="https://img/og.jpg">
<script type="application/ld+json">{"@type":"Product","review":[{"@type":"Review","reviewBody":"정말 좋아요 튼튼합니다","reviewRating":{"ratingValue":5},"author":{"name":"홍길동"}}]}</script>
</head><body></body></html>"""


def test_receiver_page_renders(client):
    r = client.get("/seller/collect/receiver")
    assert r.status_code == 200
    assert "kgp" in r.get_data(as_text=True)  # postMessage handshake JS


def test_receive_collects_images_and_reviews(client):
    with patch("src.seller_console.views._translate_draft", side_effect=lambda d: d), \
         patch("src.seller_console.collect_history_store.append", return_value="rid1") as ap:
        r = client.post("/seller/collect/receive", json={
            "url": "https://shop.example/p/1", "title": "가죽 가방",
            "images": ["https://img/a.jpg", "https://img/og.jpg"],  # og.jpg 중복 → dedupe
            "html": _HTML, "translate": True,
        })
    d = r.get_json()
    assert d["ok"] is True and d["id"] == "rid1"
    assert d["image_count"] >= 2            # og + client, 중복 제거
    assert d["review_count"] == 1           # JSON-LD 리뷰 1개
    # 저장된 extra에 reviews 포함
    extra = ap.call_args.kwargs["extra"]
    assert extra["reviews"][0]["rating"] == 5
    assert ap.call_args.kwargs["source"] == "bookmarklet"


def test_receive_translate_false_keeps_original(client):
    """번역 off 선택 시 번역 함수 호출 안 함(원문 유지)."""
    with patch("src.seller_console.views._translate_draft") as tr, \
         patch("src.seller_console.collect_history_store.append", return_value="rid2"):
        r = client.post("/seller/collect/receive", json={
            "url": "https://shop.example/p/2", "title": "셔츠", "html": "", "translate": False,
        })
    assert r.get_json()["ok"] is True
    assert r.get_json()["translated"] is False
    tr.assert_not_called()


def test_receive_rejects_bad_url(client):
    r = client.post("/seller/collect/receive", json={"url": "nope"})
    assert r.status_code == 400


def test_receive_honest_when_no_data(client):
    """제목·이미지 둘 다 없으면 정직하게 실패(가짜 저장 금지)."""
    with patch("src.seller_console.collect_history_store.append") as ap:
        r = client.post("/seller/collect/receive", json={
            "url": "https://shop.example/p/3", "html": "", "title": "", "images": [],
        })
    assert r.get_json()["ok"] is False
    ap.assert_not_called()


def test_extract_reviews_jsonld():
    from src.seller_console.views import _extract_reviews
    revs = _extract_reviews(_HTML)
    assert len(revs) == 1
    assert "좋아요" in revs[0]["body"]


def test_extract_reviews_empty_on_no_reviews():
    from src.seller_console.views import _extract_reviews
    assert _extract_reviews("<html><body>no reviews here</body></html>") == []


def test_quick_now_shows_confirmation_not_redirect(client):
    """북마클릿 quick은 편집페이지로 redirect하지 않고 '수집됨' 확인만 표시."""
    draft = {"title_ko": "t", "title": "t", "images": ["https://i/1.jpg"],
             "price_original": "10", "currency": "USD", "source": "x"}
    with patch("src.seller_console.views._collect_real_draft", return_value=draft), \
         patch("src.seller_console.collect_history_store.append", return_value="qid"):
        r = client.get("/seller/collect/quick?u=https://shop.example/p/9", follow_redirects=False)
    assert r.status_code == 200          # redirect(302) 아님
    assert "수집 완료" in r.get_data(as_text=True)


def test_bulk_limit_raised_to_1000(client):
    """일괄 수집 상한이 1000으로 상향."""
    urls = "\n".join(f"https://x.com/p/{i}" for i in range(1100))
    with patch("src.seller_console.views._collect_real_draft", return_value=None):
        r = client.post("/seller/collect/bulk", json={"urls": urls})
    assert r.get_json()["total"] == 1000


def test_receiver_does_not_redirect_to_login_when_unauth(monkeypatch):
    """미로그인이어도 receiver는 로그인 페이지로 튕기지 않고 페이지 안에서 안내."""
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "1")
    import importlib
    from src.seller_console import views as v
    importlib.reload(v)  # _AUTH_ENABLED 재평가
    try:
        from src.order_webhook import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            r = c.get("/seller/collect/receiver")
        assert r.status_code == 200          # redirect(302) 아님
        assert "showLogin" in r.get_data(as_text=True)
    finally:
        # delenv가 아니라 "0"으로 복원해야 함 — 기본값이 ON이라 삭제 시 reload가
        # _AUTH_ENABLED를 켜버려 이후 테스트가 오염됨.
        monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
        importlib.reload(v)


def test_edit_page_has_image_thumbnails(client):
    """편집 페이지 이미지 행에 썸네일(사람이 보이게)."""
    with patch("src.seller_console.collect_history_store.get",
               return_value={"id": "x", "title": "t", "url": "https://u", "image_url": "https://i/1.jpg",
                             "price": "10", "currency": "USD", "extra_json": "{}"}):
        r = client.get("/seller/collect/preview/x")
    html = r.get_data(as_text=True)
    assert "img-thumb" in html
