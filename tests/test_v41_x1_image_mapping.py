"""tests/test_v41_x1_image_mapping.py — v41 X-1: 이미지↔상품 매핑(엉뚱한 이미지) 수리.

증상: 목록에서 상품 A에 상품 B의 이미지가 붙음 / 어떤 상품은 대표 이미지 없음.
원인·수리 두 갈래:
 (1) 확장 리스팅 카드가 lazy-load placeholder(공용 src)를 써서 여러 상품이 같은 이미지를 공유
     → _kgpBestImg(data-src/srcset 우선)로 상품별 자기 이미지 귀속.
 (2) 서버 저장이 상품 ID(행)에 이미지를 귀속 → 다른 항목/전역 이미지 재사용 0, 없으면 빈값(정직).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


# ── (1) 확장 카드 이미지: placeholder 공유 방지 ──
def test_best_img_helper_used_in_card_functions():
    assert "function _kgpBestImg" in CS
    # 아마존/제네릭 카드 두 경로 모두 _kgpBestImg 사용(raw img.src 직결 제거)
    assert CS.count("_kgpBestImg(img)") >= 2
    # 카드 이미지가 없으면 빈 배열(가짜 대표 이미지 0)
    assert "images: bimg ? [bimg] : []" in CS


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_cards_do_not_share_placeholder_image():
    """서로 다른 두 카드가 lazy placeholder를 공유하지 않고 각자 data-src로 귀속."""
    start = CS.index("function _kgpBestImg")
    end = CS.index("\n}\n", start) + 2
    fn = CS[start:end]
    script = fn + r"""
    const mk = (o) => ({currentSrc:o.currentSrc||'', src:o.src||'', getAttribute:(k)=>o[k]||null});
    const out = [];
    out.push(_kgpBestImg(mk({src:'https://cdn/lazyload-placeholder.png','data-src':'https://cdn/A.jpg'})));
    out.push(_kgpBestImg(mk({src:'https://cdn/spacer.gif','data-src':'https://cdn/B.jpg'})));
    out.push(_kgpBestImg(mk({src:'data:image/gif;base64,AAAA',srcset:'https://cdn/s.jpg 200w, https://cdn/big.jpg 800w'})));
    console.log(JSON.stringify(out));
    """
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    import json
    a, b, c = json.loads(res.stdout.strip())
    assert a == "https://cdn/A.jpg"           # placeholder 대신 실제 A
    assert b == "https://cdn/B.jpg"           # 다른 카드는 B — 공유 0
    assert a != b
    assert c == "https://cdn/big.jpg"         # data:uri면 srcset 최대해상도


# ── (2) 서버 저장: 상품 ID 귀속, 항목 간 이미지 누출 0 ──
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]})
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def _clear():
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()


def test_images_bound_to_own_item_no_bleed(client):
    """A(이미지 있음) → B(이미지 없음) 수집 시 B가 A 이미지를 물려받지 않는다."""
    _clear()
    ra = client.post("/api/v1/collect/extension", json={
        "url": "https://temu.com/p/aaa", "title": "가방 A",
        "image": "https://cdn/A.jpg", "images": ["https://cdn/A.jpg"],
        "price": "10", "currency": "USD"})
    assert ra.status_code == 200 and ra.get_json()["ok"] is True
    rb = client.post("/api/v1/collect/extension", json={
        "url": "https://temu.com/p/bbb", "title": "지갑 B",
        "images": [], "price": "5", "currency": "USD"})
    assert rb.status_code == 200 and rb.get_json()["ok"] is True

    from src.seller_console import collect_history_store as ch
    rows = {r["title"]: r for r in ch.list_items(seller_ids={"u1"})}
    assert rows["가방 A"].get("image_url") == "https://cdn/A.jpg"
    # B는 자기 이미지가 없으므로 빈값(정직) — A 이미지 재사용 0.
    assert (rows["지갑 B"].get("image_url") or "") == ""
    import json
    ex_b = json.loads(rows["지갑 B"].get("extra_json") or "{}")
    assert ex_b.get("images") in ([], None)
