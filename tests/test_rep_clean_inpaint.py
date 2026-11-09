import hashlib
import io

import numpy as np
from PIL import Image

from src.services.rep_clean_candidate import clean_candidate
from src.services.rep_clean_geometry import render_guarded_inpaint


def image_bytes():
    yy, xx = np.indices((600, 600))
    pixels = np.stack([(xx % 100) + 80, (yy % 100) + 80, ((xx + yy) % 100) + 80], axis=-1).astype('uint8')
    out = io.BytesIO()
    Image.fromarray(pixels).save(out, "PNG")
    return out.getvalue()


def test_inpaint_preserves_product_and_outside_pixels():
    raw = image_bytes()
    result = render_guarded_inpaint(raw, [[280, 280, 284, 284]], [[50, 350, 550, 580]])
    assert result["ok"] and result["method"] == "inpaint"
    assert result["protected_changed_pixels"] == result["outside_changed_pixels"] == 0
    assert result["requires_fresh_ocr"] is True
    assert all(m["ratio"] < 1.5 for m in result["measurements"])


def test_inpaint_rejects_product_marking_even_when_small():
    result = render_guarded_inpaint(image_bytes(), [[280, 280, 284, 284]], [[200, 200, 400, 400]])
    assert not result["ok"] and result["why"] == "edit_overlaps_product"
    assert "bytes" not in result


def test_real_fallback_requires_fresh_ocr_after_pixel_checks():
    raw = image_bytes()
    proof = {"sha256": hashlib.sha256(raw).hexdigest(), "version": "original",
             "reviewed_complete": True, "regions": [[50, 350, 550, 580]]}
    called = []
    def worker(fn, *args, **kwargs):
        called.append(fn.__name__)
        return fn(*args)
    out = clean_candidate(raw, [[280, 280, 284, 284]], proof, version="original",
                          worker=worker, ocr=lambda raw: None)
    assert called == ["render_edge_crop", "render_guarded_inpaint"]
    assert out == {"ok": False, "why": "fresh_ocr_unmeasured"}


def test_crop_ocr_failure_does_not_trigger_another_pixel_edit():
    raw = image_bytes()
    proof = {"sha256": hashlib.sha256(raw).hexdigest(), "version": "original",
             "reviewed_complete": True, "regions": [[50, 350, 550, 580]]}
    called = []
    def worker(fn, *args, **kwargs):
        called.append(fn.__name__)
        return fn(*args)
    out = clean_candidate(raw, [[20, 20, 300, 50]], proof, version="original",
                          worker=worker, ocr=lambda raw: 1)
    assert called == ["render_edge_crop"] and out["why"] == "text_remains"
