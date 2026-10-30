"""Verified H-rep2 crop candidate boundary. No upload or product mutation.

Protection evidence is server-side reviewed data, not a client assertion. It
must cover all merchandise and refer to the exact bytes sent to the worker.
This module does not invent that evidence or silently fall back to erasing.
"""
from __future__ import annotations

import hashlib


def crop_candidate(raw, text_regions, protection, *, version, ocr, worker=None):
    """Return a candidate only after evidence, child rendering and fresh OCR.

    `ocr(png_bytes)` returns an integer box count or None. Integration must use
    the real OCR service; callbacks in unit tests are only contract doubles.
    A crop has a new frame and must never inherit old edit/OCR coordinates.
    """
    fail = lambda why: {"ok": False, "why": why}
    if not isinstance(raw, bytes) or not raw or not isinstance(version, str) or not version:
        return fail("missing_image_identity")
    if not isinstance(protection, dict) or protection.get("reviewed_complete") is not True:
        return fail("product_protection_unverified")
    if (protection.get("version") != version
            or protection.get("sha256") != hashlib.sha256(raw).hexdigest()):
        return fail("product_protection_stale")
    if not isinstance(protection.get("regions"), (list, tuple)) or not protection["regions"]:
        return fail("product_protection_missing")
    if not callable(ocr):
        return fail("ocr_unavailable")
    from src.services.rep_clean_geometry import render_edge_crop
    if worker is None:
        from src.utils.render_worker import run
        worker = run
    try:
        rendered = worker(render_edge_crop, raw, text_regions, protection["regions"],
                          _name="rep_crop_candidate", _timeout=30.0)
    except Exception:
        return fail("crop_worker_failed")
    if not isinstance(rendered, dict) or rendered.get("ok") is not True:
        return fail((rendered or {}).get("why", "crop_failed") if isinstance(rendered, dict) else "crop_failed")
    output = rendered.get("bytes")
    if not isinstance(output, bytes) or not output:
        return fail("crop_output_missing")
    try:
        count = ocr(output)
    except Exception:
        return fail("fresh_ocr_failed")
    # False, 0.0, string '0' and negative sentinels are not measured zero.
    if type(count) is not int or count < 0:
        return fail("fresh_ocr_unmeasured")
    if count:
        return {"ok": False, "why": "text_remains", "boxes_after": count}
    return dict(rendered, boxes_after=0, requires_fresh_ocr=False,
                source_sha256=protection["sha256"], source_version=version,
                output_sha256=hashlib.sha256(output).hexdigest(),
                coordinate_frame="cropped", reuse_source_boxes=False)
