"""Verified H-rep2 crop candidate boundary. No upload or product mutation.

Protection evidence is server-side reviewed data, not a client assertion. It
must cover all merchandise and refer to the exact bytes sent to the worker.
This module does not invent that evidence or silently fall back to erasing.
"""
from __future__ import annotations

import hashlib


def fresh_text_count(raw):
    """Read exact rendered bytes; missing/malformed OCR is never measured zero.

    Unlike read_boxes, do not discard detections without polygon coordinates
    or low-confidence text. Neither is proof of a text-free representative.
    Reuse the configured Tencent client, bounded request timeout and cleanup.
    No image decode, resize, upload, cache or database write here.
    """
    if not isinstance(raw, bytes) or not raw:
        return None
    from src.services import ocr_tencent as provider
    import base64
    try:
        if not provider.is_configured() or provider.unopened() or not provider._fits_as_is(raw):
            return None
        previous_language = getattr(provider._LANG, "value", "")
        provider._LANG.value = "auto"
        try:
            body = provider._call(base64.b64encode(raw).decode("ascii"))
        except Exception as exc:
            return 0 if provider.no_text(exc) else None
        finally:
            provider._LANG.value = previous_language
        if not isinstance(body, dict) or body.get("Error"):
            return None
        detections = body.get("TextDetections")
        if not isinstance(detections, list):
            return None
        # Even an ambiguous detection prevents accepting this candidate.
        return len(detections)
    except Exception:
        return None


def crop_candidate(raw, text_regions, protection, *, version, ocr=fresh_text_count, worker=None):
    return _candidate(raw, text_regions, protection, version=version, ocr=ocr, worker=worker, inpaint=False)


def clean_candidate(raw, text_regions, protection, *, version, ocr=fresh_text_count, worker=None):
    """Crop first; inpaint only when edge geometry cannot preserve the product."""
    result = crop_candidate(raw, text_regions, protection, version=version, ocr=ocr, worker=worker)
    if result.get("why") not in ("text_outside_edge_band", "crop_overlaps_product"):
        return result
    return _candidate(raw, text_regions, protection, version=version, ocr=ocr, worker=worker, inpaint=True)


def _candidate(raw, text_regions, protection, *, version, ocr, worker, inpaint):
    """Return a candidate only after evidence, child rendering and fresh OCR.

    `ocr(png_bytes)` returns an integer box count or None. Integration must use
    the real OCR service; callbacks in unit tests are only contract doubles.
    A crop has a new frame and must never inherit old edit/OCR coordinates.
    """
    def fail(why):
        return {"ok": False, "why": why}
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
    from src.services.rep_clean_geometry import render_edge_crop, render_guarded_inpaint
    if worker is None:
        from src.utils.render_worker import run
        worker = run
    try:
        rendered = worker(render_guarded_inpaint if inpaint else render_edge_crop,
                          raw, text_regions, protection["regions"],
                          _name="rep_inpaint_candidate" if inpaint else "rep_crop_candidate", _timeout=30.0)
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
                coordinate_frame="unchanged" if inpaint else "cropped", reuse_source_boxes=False)
