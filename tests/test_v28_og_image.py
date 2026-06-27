"""tests/test_v28_og_image.py — v28: 공유 카드 OG 이미지를 브릿지 카드로 교체(글러브 폐기)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_og_card_asset_is_1200x630():
    from PIL import Image
    p = Path("src/seller_console/static/og-card.png")
    assert p.exists(), "og-card.png 누락"
    im = Image.open(p)
    assert im.size == (1200, 630), im.size
    # 벤더 사본(소스 산출물)도 존재
    assert Path("assets/og/og-card-1200x630.png").exists()


def test_og_meta_points_to_bridge_card_not_glove(client):
    html = client.get("/").get_data(as_text=True)
    assert "og-card.png?v=2" in html              # og:image = 신규 브릿지 카드 + 캐시 bump
    assert 'property="og:image"' in html
    assert 'name="twitter:image"' in html
    # 옛 정사각 아이콘을 og:image로 쓰지 않음
    assert "/seller/static/icon-512.png" not in html


def test_og_card_served(client):
    r = client.get("/seller/static/og-card.png")
    assert r.status_code == 200
    assert r.mimetype in ("image/png", "application/octet-stream")


def test_glove_generator_scripts_removed():
    # 옛 글러브 생성 스크립트(잔재) 제거
    assert not Path("scripts/gen_favicon_glove.py").exists()
    assert not Path("scripts/gen_extension_icons.py").exists()
