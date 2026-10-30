import copy
import hashlib
import io

import pytest
from PIL import Image

from src.services import image_edit as IE
from src.services import rep_clean_edit as E
from src.services import rep_auto_clean as R


def png():
    out = io.BytesIO()
    Image.new("RGB", (600, 600), "white").save(out, "PNG")
    return out.getvalue()


def reviewed():
    raw = png()
    proof = {"reviewed_complete": True, "reviewer": "unit-test-review", "reviewed_at": "2026-10-30",
             "sha256": hashlib.sha256(raw).hexdigest(), "url": "https://cdn/translated.png",
             "version": "translated", "regions": [[100, 250, 500, 550]]}
    ex = {"images": ["https://cdn/original.png"], "detail_images": ["https://cdn/detail.png"],
          "images_ko": [{"idx": 0, "status": "done", "use": True, "url": proof["url"],
                         "translated_url": proof["url"], "rep_protection": proof}]}
    return ex, raw


def prepare(monkeypatch, ex, raw):
    monkeypatch.setattr(IE, "work_bytes", lambda url: (raw, ""))
    monkeypatch.setattr(IE, "plan", lambda *a, **kw: {
        "url": "https://cdn/translated.png", "current": "translated", "size": [1200, 1200],
        "boxes": [{"x": 20, "y": 20, "w": 600, "h": 100}]})
    return E.prepare(ex, 0)


def test_missing_review_never_fetches_or_renders(monkeypatch):
    ex, raw = reviewed()
    ex["images_ko"][0].pop("rep_protection")
    monkeypatch.setattr(IE, "work_bytes", lambda *_: pytest.fail("must not fetch"))
    monkeypatch.setattr(E, "render", lambda *_: pytest.fail("must not render"))
    saved = copy.deepcopy(ex)
    result = R.clean(ex, {0: 2})
    assert not result["ok"] and not result["tried"]
    assert "검토 기록" in result["why"]
    assert ex["images_ko"] == saved["images_ko"] and ex["images"] == saved["images"]


def test_prepare_scales_ocr_frame_without_mutating_source(monkeypatch):
    ex, raw = reviewed()
    saved = copy.deepcopy(ex)
    p = prepare(monkeypatch, ex, raw)
    assert p["ok"] and p["text_regions"] == [[10, 10, 310, 60]]
    assert p["protection"]["regions"] == [[100, 250, 500, 550]]
    assert ex == saved


@pytest.mark.parametrize("field,value", [("version", "original"), ("url", "https://cdn/stale.png"),
                                         ("sha256", "stale")])
def test_stale_review_is_rejected(monkeypatch, field, value):
    ex, raw = reviewed()
    ex["images_ko"][0]["rep_protection"][field] = value
    assert not prepare(monkeypatch, ex, raw)["ok"]


def publish_setup(monkeypatch):
    from src.media import image_pipeline as P
    ex, raw = reviewed()
    p = prepare(monkeypatch, ex, raw)
    result = {"ok": True, "bytes": raw, "boxes_after": 0, "requires_fresh_ocr": False,
              "source_sha256": p["protection"]["sha256"], "source_version": p["version"],
              "output_sha256": hashlib.sha256(raw).hexdigest(), "size": [600, 600], "method": "edge_crop"}
    monkeypatch.setattr(P, "upload_bytes", lambda data, **kw: {"ok": True, "secure_url": "https://cdn/clean.png"})
    monkeypatch.setattr(IE, "_fetch", lambda url: raw)
    return ex, p, result


def test_publish_preserves_other_market_selection_and_uses_new_ocr_frame(monkeypatch):
    ex, p, result = publish_setup(monkeypatch)
    saved = copy.deepcopy(ex)
    out = E.publish(ex, 0, p, result)
    assert out["ok"] and out["version"] == "edit:1"
    entry = ex["images_ko"][0]
    assert IE.current_key(entry) == "translated"
    assert all(entry[k] == v for k, v in saved["images_ko"][0].items())
    assert ex["images"] == saved["images"] and ex["detail_images"] == saved["detail_images"]
    assert entry["vboxes"]["edit:1"] == {"img": out["url"], "boxes": [], "size": [600, 600]}


def test_cdn_changed_bytes_cannot_be_accepted(monkeypatch):
    ex, p, result = publish_setup(monkeypatch)
    saved = copy.deepcopy(ex)
    monkeypatch.setattr(IE, "_fetch", lambda _: b"reencoded output")
    assert not E.publish(ex, 0, p, result)["ok"]
    assert ex == saved


def test_concurrent_source_change_is_not_overwritten(monkeypatch):
    from src.media import image_pipeline as P
    ex, p, result = publish_setup(monkeypatch)
    def upload(*a, **kw):
        ex["images_ko"][0]["use"] = False
        return {"ok": True, "secure_url": "https://cdn/clean.png"}
    monkeypatch.setattr(P, "upload_bytes", upload)
    assert not E.publish(ex, 0, p, result)["ok"]
    assert IE.current_key(ex["images_ko"][0]) == "original" and not ex["images_ko"][0].get("edits")


def test_invalid_counts_cannot_turn_into_zero_or_negative_candidates():
    assert R.pick_min({0: False, 1: -1, 2: None}) == -1


def test_renderer_failure_never_uploads_and_next_candidate_runs(monkeypatch):
    from src.db import image_translate_queue_pg as q
    ex, _ = reviewed()
    ex["images"].append("https://cdn/second.png")
    monkeypatch.setattr(q, "take_start", lambda *a: (True, 1))
    monkeypatch.setattr(E, "prepare", lambda extra, idx: {"ok": True, "idx": idx})
    seen = []
    def render(p):
        seen.append(p["idx"])
        return {"ok": False, "why": "edit_overlaps_product"}
    monkeypatch.setattr(E, "render", render)
    monkeypatch.setattr(E, "publish", lambda *a: pytest.fail("must not upload"))
    assert not R.clean(ex, {0: 2, 1: 3})["ok"]
    assert seen == [0, 1] and "rep_image" not in ex
    R.clean(ex, {0: 2, 1: 3})
    assert seen == [0, 1]
    ex["images_ko"][0]["rep_protection"]["reviewed_at"] = "2026-10-31"
    R.clean(ex, {0: 2, 1: 3})
    assert seen == [0, 1, 0]
