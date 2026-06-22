from __future__ import annotations

import json
from pathlib import Path


def test_seller_icon_assets_exist():
    base = Path("src/seller_console/static")
    for name in [
        "favicon.svg",
        "favicon.ico",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "manifest.webmanifest",
    ]:
        assert (base / name).exists()


def test_base_templates_include_favicon_links():
    targets = [
        Path("src/seller_console/templates/_base.html"),
        Path("src/templates/_base_app.html"),
        Path("src/dashboard/templates/base.html"),
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert 'rel="icon"' in text
        assert "favicon.svg" in text
        assert "favicon.ico" in text
        assert 'rel="apple-touch-icon"' in text
        assert "manifest.webmanifest" in text
        assert ("?v=173" in text) or ("v='173'" in text)
        # 테마 색상은 라이트/다크 리비전마다 달라질 수 있으므로(예: Phase 189 라이트 복구)
        # 특정 색상값이 아니라 theme-color 메타 존재만 검증한다.
        assert 'name="theme-color"' in text


def test_favicon_svg_uses_glove_brand_mark():
    text = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8")
    # v13: 브랜드 마크 = 글러브 모노그램(먹/금/청록). 지구본 폐기.
    assert "#1a1714" in text          # 먹 배경
    assert "#c9a24b" in text          # 금 글러브
    assert "#119a8e" in text          # 청록 소맷동/궤도
    assert "글러브" in text            # 마크 설명
    # 옛 지구본 잔재 없음(지구본/순흑/별 그라데이션 폐기)
    assert "#020010" not in text
    assert 'linearGradient id="bg"' not in text
    assert ">K<" not in text


def test_manifest_icon_files_are_served():
    from src.order_webhook import app

    with app.test_client() as client:
        manifest_resp = client.get("/seller/static/manifest.webmanifest")
        assert manifest_resp.status_code == 200
        manifest = json.loads(manifest_resp.data)
        for icon in manifest.get("icons", []):
            icon_resp = client.get(icon["src"])
            assert icon_resp.status_code == 200


def test_favicon_generation_script_exists():
    text = Path("scripts/gen_favicon_assets.py").read_text(encoding="utf-8")
    assert "cairosvg" in text
    assert "favicon.svg" in text


def test_public_templates_use_cache_busted_favicon_links():
    targets = [
        Path("src/auth/templates/auth/login.html"),
        Path("src/auth/templates/auth/signup.html"),
        Path("src/auth/templates/auth/magic_link_fallback.html"),
        Path("src/auth/templates/auth/magic_link_request.html"),
        Path("src/auth/templates/auth/diagnostic_token_issued.html"),
        Path("src/auth/templates/auth/reset.html"),
        Path("src/onboarding/templates/onboarding.html"),
        Path("src/legal/templates/legal/privacy.html"),
        Path("src/legal/templates/legal/terms.html"),
        Path("src/shop/templates/shop/base.html"),
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "favicon.svg?v=173" in text
        assert "favicon.ico?v=173" in text
        assert "apple-touch-icon.png?v=173" in text
        assert "manifest.webmanifest?v=173" in text
        # 다크 테마 컬러 — 순흑 #020010 폐기(KOHgogane 브리프 §2.2) → 따뜻한 먹(#1a1714)도 허용.
        assert ('content="#020010"' in text) or ('content="#1a1714"' in text)
