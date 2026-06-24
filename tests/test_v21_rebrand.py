"""tests/test_v21_rebrand.py — v21: 고가브릿지(Goga Bridj) 일괄 리브랜딩 + 게이트웨이(B) 아이콘 가드.

원칙: 사용자 노출 표기는 고가브릿지/Goga Bridj/고가수집기, 코고가네/KOHgogane/퍼센티/Proxy Commerce 0.
내부 식별자(percenty 채널·proxy_commerce 네임스페이스·service json·Render 서비스명·github URL·실도메인)는 보존.
"""
from __future__ import annotations

import json
from pathlib import Path


def test_branding_defaults_are_goga_bridj():
    from src.utils.branding import get_brand_name, get_brand_name_ko
    assert get_brand_name() == "Goga Bridj"
    assert get_brand_name_ko() == "고가브릿지"


def test_pwa_manifest_rebranded():
    for name in ("manifest.json", "manifest.webmanifest"):
        m = json.loads(Path(f"src/seller_console/static/{name}").read_text(encoding="utf-8"))
        assert m["name"] == "Goga Bridj"
        assert m["short_name"] == "고가브릿지"
        assert "코고가네" not in json.dumps(m, ensure_ascii=False)
        assert "KOHgogane" not in json.dumps(m, ensure_ascii=False)


def test_favicon_is_gateway_mark():
    # 공식 게이트웨이(B): 금 아치 + 청록 다리(span) + 주황 키스톤
    low = Path("src/seller_console/static/favicon.svg").read_text(encoding="utf-8").lower()
    assert "gateway" in low
    assert "#f5821f" in low            # 주황 키스톤
    assert "#119a8e" in low            # 청록 다리
    assert "globe" not in low


def test_official_brand_assets_vendored():
    # 공식 자산 단일소스(재현 가능) — 직접 그린 게 아니라 오너 제공 자산
    src = Path("assets/brand-icons")
    assert (src / "gogabridge_icon_B_gateway.svg").exists()
    for px in ("16", "32", "48", "128", "180", "192", "512", "1024"):
        assert (src / f"icon-{px}.png").exists(), f"공식 icon-{px}.png 누락"


def test_gateway_icon_generator_exists():
    txt = Path("scripts/gen_gateway_icons.py").read_text(encoding="utf-8")
    assert "게이트웨이" in txt
    assert "favicon.ico" in txt and "icon-1024.png" in txt   # 스토어 사이즈 포함


def test_store_and_extension_icon_assets_exist():
    base = Path("src/seller_console/static")
    for n in ("favicon.ico", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-1024.png"):
        assert (base / n).exists(), f"{n} 누락"
    ext = Path("extensions/chrome-collector/icons")
    for px in ("16", "32", "48", "128"):
        assert (ext / f"{px}.png").exists(), f"확장 {px}.png 누락"


def test_extension_manifest_rebranded_and_bumped():
    mf = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
    # 수집기 명칭 = 고가수집기/Goga Collector
    blob = (mf.get("name", "") + mf.get("description", ""))
    assert "고가" in blob
    assert "코고가네" not in blob and "퍼센티" not in blob
    # 버전 bump (>= 1.5.9)
    parts = [int(x) for x in mf["version"].split(".")]
    assert parts >= [1, 5, 9], mf["version"]


def test_no_old_brand_in_user_facing_templates():
    targets = [
        "src/seller_console/templates/_base.html",
        "src/seller_console/templates/about.html",
        "src/seller_console/templates/mobile_home.html",
        "src/seller_console/templates/manual_collect.html",
        "src/templates/landing.html",
        "src/templates/_base_app.html",
    ]
    for p in targets:
        # 렌더되는 본문만(주석 제외) — Jinja {# #}, HTML <!-- -->, CSS /* */ 안의 브리프 참조는 허용
        text = Path(p).read_text(encoding="utf-8")
        for bad in ("코고가네", "코코가네", "KOHgogane", "퍼센티", "Percenty"):
            # 주석 안의 브리프/Phase 참조는 사용자에게 안 보이므로 라인 단위로 주석 제거 후 검사
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("{#") or stripped.startswith("<!--") or stripped.startswith("/*") or stripped.startswith("*"):
                    continue
                assert bad not in line, f"{p}: 사용자 노출 라인에 {bad} 잔존 → {line.strip()[:80]}"


def test_extension_content_script_no_percenty_or_kohgogane():
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "코고가네" not in cs
    assert "퍼센티" not in cs
    # FAB 마크 = 게이트웨이(주황 키스톤). 청록 글러브 제거.
    assert "#f5821f" in cs


def test_internal_identifiers_preserved():
    # percenty 채널 모듈은 실연동 — 보존
    assert Path("src/channels/percenty.py").exists()
    # service json 필드(내부) 보존
    assert '"service": "proxy-commerce"' in Path("src/order_webhook.py").read_text(encoding="utf-8")
    # shopify metafield 네임스페이스(내부) 보존
    assert "'namespace': 'proxy_commerce'" in Path("src/channels/shopify_markets.py").read_text(encoding="utf-8")
