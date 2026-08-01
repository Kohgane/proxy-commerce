"""tests/test_v64_bulk_enrich.py — v64 STEP1: 벌크 2단 수집(상세 보강).

목록 데이터 저장 후 확장이 백그라운드 탭으로 상세를 읽어 서버 /enrich로 병합(fill-only).
서버측 직접 크롤 없음 — 확장이 브라우저 컨텍스트에서 읽어 보낸 값만. 상태 배지 부분→성공.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
EXT_API = Path("src/api/extension_api.py").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.134"


def test_enrich_endpoint_source_contract():
    assert '@extension_bp.post("/enrich")' in EXT_API
    assert "def collect_enrich" in EXT_API
    assert "fill-only" in EXT_API
    # 상태 배지 재계산 + fill-only(제목/가격은 안 건드림).
    assert "compute_collect_status" in EXT_API


def test_background_enrich_queue_contract():
    assert "handleEnrichStart" in BG and "_kgpEnrichLoop" in BG
    assert 'msg.action === "enrichStart"' in BG
    assert 'msg.action === "enrichPause"' in BG and 'msg.action === "enrichStop"' in BG
    assert "enrichTargets" in BG                      # 벌크가 보강 대상 회신
    assert "chrome.tabs.create" in BG                 # 백그라운드 탭 방문
    assert "_kgpEnrichDelayMs" in BG                  # 3~6초 간격


# ── 서버 enrich 엔드포인트 동작(pytest) ──


def _seed_item(monkeypatch):
    """collect_history_store에 목록 수준 항목 1건(옵션·상세·리뷰 비어 있음)을 심고 id 반환."""
    from src.seller_console import collect_history_store as store
    # 인메모리 경로로 강제(테스트 격리).
    monkeypatch.setattr(store, "pg_enabled", lambda: False, raising=False)
    if hasattr(store, "_in_memory"):
        store._in_memory.clear()
    item_id = store.append(
        source="extension", seller_id="u-enrich", url="https://www.amazon.com/dp/B0ENRICH01",
        title="Test Product", price="12000", currency="KRW", image="a.jpg",
        extra={"images": ["a.jpg"], "price": "12000", "price_status": ""},
    )
    if isinstance(item_id, tuple):
        item_id = item_id[0]
    return item_id


def test_enrich_fills_and_recomputes_status(flask_client, monkeypatch):
    from src.seller_console import collect_history_store as store
    item_id = _seed_item(monkeypatch)

    # /enrich 인증을 통과하도록 _require_token을 우리 유저로 모킹.
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-enrich"})

    body = {
        "item_id": item_id,
        "options": [{"name": "색상", "values": ["Black", "White"]}],
        "description": "이 제품은 원목으로 만든 튼튼한 책상입니다. 조립이 간편합니다.",
        "detail_images": ["d1.jpg", "d2.jpg"],
        "gallery": ["a.jpg", "b.jpg", "c.jpg"],
        "reviews": [{"text": "좋아요"}],
        "rating": "4.5",
    }
    r = flask_client.post("/api/v1/collect/enrich", json=body)
    assert r.status_code == 200, r.data
    d = r.get_json()
    assert d["ok"] is True and d["item_id"] == item_id
    # 옵션·상세·상세이미지·갤러리·리뷰가 채워짐.
    assert d["changed"].get("options") == 1
    assert d["changed"].get("description") == 1
    assert d["changed"].get("detail_images") == 2
    # 상태 배지 성공(부분→성공): price·images·options·detail·reviews 전부 present.
    assert d["status"] == "성공", d

    # 저장 확인 + 목록 수준 제목/가격은 보존(fill-only).
    item = store.get(item_id, seller_ids={"u-enrich"})
    extra = json.loads(item.get("extra_json") or "{}")
    assert extra["enriched"] is True
    assert extra["options"] and extra["detail_images"]
    assert item.get("title") == "Test Product"       # 제목 미변경(fill-only)


def test_enrich_missing_item_404(flask_client, monkeypatch):
    import src.api.extension_api as ext
    from src.seller_console import collect_history_store as store
    monkeypatch.setattr(store, "pg_enabled", lambda: False, raising=False)
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-enrich"})
    r = flask_client.post("/api/v1/collect/enrich", json={"item_id": "nonexistent-zzz"})
    assert r.status_code == 404


def test_enrich_requires_auth(flask_client, monkeypatch):
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: None)
    r = flask_client.post("/api/v1/collect/enrich", json={"item_id": "x"})
    assert r.status_code == 401


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_enrich_delay_and_retry_node():
    delay = re.search(r"function _kgpEnrichDelayMs\(rng\) \{.*?\n\}", BG, re.S).group(0)
    harness = (
        delay + "\n"
        "var out={};\n"
        "out.min=_kgpEnrichDelayMs(function(){return 0;});\n"      # 3000
        "out.max=_kgpEnrichDelayMs(function(){return 0.999;});\n"  # ~5999
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["min"] == 3000                     # 최소 3초
    assert 5900 <= out["max"] <= 6000              # 최대 ~6초(3~6초 랜덤)
