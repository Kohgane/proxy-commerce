"""tests/test_v66_amazon_enrich.py — v66 STEP3: 아마존 보강 판정 회수.

보강 시 상세의 고해상 갤러리를 **대표로** — 검색결과 저해상 썸네일을 대표로 쓰지 않음.
보강 판정(큐가 돌았는지/필드 채웠는지)은 서버 로그(changed)로 특정. 상세 셀렉터(hi-res·A+·불릿)는
공유 추출기에 이미 존재(계약 고정).
"""
from __future__ import annotations

import json
from pathlib import Path

EXT_API = Path("src/api/extension_api.py").read_text(encoding="utf-8")
EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")


def test_enrich_gallery_first_source_contract():
    # 갤러리를 앞에 두어 union → 대표 고해상. image_url도 교체. 판정 로그.
    assert "_union(gi, extra.get(\"images\"))" in EXT_API
    assert '_upd["image_url"] = rep' in EXT_API
    assert "[enrich] item=%s changed=%s status=%s rep=%s" in EXT_API


def test_shared_extractor_amazon_detail_contract():
    # 공유 추출기가 아마존 고해상·A+·feature-bullets를 다룸(보강 경로 실작동 근거).
    assert "data-old-hires" in EX
    assert "#aplus img" in EX or "#aplus" in EX
    assert "#feature-bullets" in EX and "#productDescription" in EX
    assert "function hiRes" in EX          # 크기 토큰 제거(hi-res 정규화)


def _seed(monkeypatch):
    from src.seller_console import collect_history_store as store
    monkeypatch.setattr(store, "pg_enabled", lambda: False, raising=False)
    if hasattr(store, "_in_memory"):
        store._in_memory.clear()
    item_id = store.append(
        source="bulk", seller_id="u-az", url="https://www.amazon.com/dp/B0AMZ00001",
        title="Amazon Item", price="20000", currency="KRW", image="lowres_thumb.jpg",
        extra={"images": ["lowres_thumb.jpg"], "price": "20000", "price_status": ""},
    )
    return item_id[0] if isinstance(item_id, tuple) else item_id


def test_enrich_hires_becomes_representative(flask_client, monkeypatch):
    from src.seller_console import collect_history_store as store
    import src.api.extension_api as ext
    item_id = _seed(monkeypatch)
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-az"})

    body = {
        "item_id": item_id,
        "gallery": ["hires_main.jpg", "hires_2.jpg", "hires_3.jpg"],
        "detail_images": ["aplus_1.jpg", "aplus_2.jpg"],
        "options": [{"name": "색상", "values": ["Black", "Silver"]}],
        "description": "고해상 상세 이미지와 A+ 콘텐츠를 포함한 상세 설명입니다. 조립 방법을 확인하세요.",
        "reviews": [{"text": "good"}], "rating": "4.7",
    }
    r = flask_client.post("/api/v1/collect/enrich", json=body)
    assert r.status_code == 200, r.data
    d = r.get_json()
    assert d["ok"] is True and d["status"] == "성공", d
    assert d["changed"].get("images")           # 갤러리 병합됨

    item = store.get(item_id, seller_ids={"u-az"})
    extra = json.loads(item.get("extra_json") or "{}")
    # 대표(images[0]) = 고해상(갤러리 first), 저해상 썸네일은 대표 아님.
    assert extra["images"][0] == "hires_main.jpg", extra["images"]
    assert "lowres_thumb.jpg" in extra["images"]   # 기존은 유지(뒤로)
    assert extra["images"].index("hires_main.jpg") < extra["images"].index("lowres_thumb.jpg")
    # 상세이미지·옵션·리뷰 채움.
    assert extra["detail_images"] and extra["options"] and extra["reviews"]
