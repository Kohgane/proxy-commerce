"""tests/test_media_process_image.py — 이미지 정제 엔드포인트 (Phase 249, v3 P1-5)."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _result(processed_url, **over):
    d = {"processed_url": processed_url, "cdn_uploaded": False,
         "watermark_removed": False, "success": True}
    d.update(over)
    return SimpleNamespace(to_dict=lambda: d)


def test_process_image_rejects_bad_url(client):
    r = client.post("/seller/media/process-image", json={"image_url": "notaurl"})
    assert r.status_code == 400


def test_process_image_cdn_success(client):
    with patch("src.media.image_pipeline.process_image",
               return_value=_result("https://cdn/x.webp", cdn_uploaded=True, watermark_removed=True)):
        r = client.post("/seller/media/process-image",
                        json={"image_url": "https://shop/img.jpg"})
    data = r.get_json()
    assert data["ok"] is True
    assert data["processed_url"] == "https://cdn/x.webp"
    assert data["cdn_uploaded"] is True
    assert data["watermark_removed"] is True


def test_process_image_no_cdn_keeps_original_with_message(client):
    """CDN 미설정/처리 미적용 → 원본 유지 + 정직 안내(가짜 호스팅 URL 금지)."""
    with patch("src.media.image_pipeline.process_image",
               return_value=_result("https://shop/img.jpg")):
        r = client.post("/seller/media/process-image",
                        json={"image_url": "https://shop/img.jpg"})
    data = r.get_json()
    assert data["ok"] is True
    assert data["processed_url"] == "https://shop/img.jpg"
    assert data["cdn_uploaded"] is False
    assert data["message"]  # 안내 메시지 존재


def test_edit_page_has_clean_button(client):
    from unittest.mock import patch as p
    draft = {"id": "p1", "title": "t", "title_ko": "t", "images": ["https://i/1.jpg"],
             "price": "10", "currency": "USD", "source": "x", "status": "ok"}
    with p("src.seller_console.collect_history_store.get", return_value=draft):
        html = client.get("/seller/collect/preview/p1").get_data(as_text=True)
    if "img-row" in html or "btn-clean-img" in html:
        assert "btn-clean-img" in html
        assert "/seller/media/process-image" in html
