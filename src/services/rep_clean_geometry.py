"""H-rep2 crop/quality primitives; deliberately not wired to automatic cleaning yet.

Coordinates must describe the decoded current image, not an earlier edit/OCR
frame. Protected regions are caller-supplied evidence, never inferred from the
absence of text. Unknown protection or quality means rejection. Invoke pixel
work only in render_worker; module import has no Pillow/numpy/cv2 imports.
"""
from __future__ import annotations

import math
from numbers import Real

MAX_SIDE = 2000
MIN_RETAINED_SIDE = 500
EDGE_FRACTION = 0.30
VARIANCE_RATIO_LIMIT = 1.5


def _rects(values, width, height):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("missing_regions")
    result = []
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            raise ValueError("invalid_region")
        if any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in value):
            raise ValueError("invalid_region")
        x0, y0, x1, y1 = value
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError("region_outside_frame")
        result.append((math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)))
    return result


def crop_plan(size, text_regions, protected_regions, *, margin=4):
    """Plan a lossless edge crop, requiring explicit product-protection evidence.

    Output includes the crop and translation into a white square canvas. No
    enlargement: a <500px retained long side cannot pass by adding padding.
    Rectangles use half-open pixel bounds. Top and bottom bands may coexist.
    """
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(type(v) is not int or v <= 0 or v > MAX_SIDE for v in size)):
        return {"ok": False, "why": "invalid_size"}
    if type(margin) is not int or margin < 0 or margin > 20:
        return {"ok": False, "why": "invalid_margin"}
    width, height = size
    try:
        texts = _rects(text_regions, width, height)
        protected = _rects(protected_regions, width, height)
    except ValueError as exc:
        return {"ok": False, "why": str(exc)}
    top, bottom = 0, height
    for _x0, y0, _x1, y1 in texts:
        if y1 + margin <= height * EDGE_FRACTION:
            top = max(top, y1 + margin)
        elif y0 - margin >= height * (1 - EDGE_FRACTION):
            bottom = min(bottom, y0 - margin)
        else:
            return {"ok": False, "why": "text_outside_edge_band"}
    if top >= bottom:
        return {"ok": False, "why": "empty_crop"}
    if any(y0 < top or y1 > bottom for _x0, y0, _x1, y1 in protected):
        return {"ok": False, "why": "crop_overlaps_product"}
    retained_height = bottom - top
    side = max(width, retained_height)
    if side < MIN_RETAINED_SIDE:
        return {"ok": False, "why": "retained_image_too_small"}
    left_pad, top_pad = (side - width) // 2, (side - retained_height) // 2
    return {"ok": True, "crop": [0, top, width, bottom], "size": [side, side],
            "offset": [left_pad, top_pad - top], "padding": [left_pad, top_pad],
            "protected_regions": [list(r) for r in protected],
            "text_regions": [list(r) for r in texts], "method": "edge_crop"}


def variance_check(before, after):
    """Symmetric ratio: reject both flattened smears and added texture/noise.

    Zero/unknown/nonfinite variance is not evidence of preserved texture.
    Return measured values with a nullable ratio; never silently coerce to 0.
    """
    if any(isinstance(v, bool) or not isinstance(v, Real)
           or not math.isfinite(v) or v <= 0 for v in (before, after)):
        return {"ok": False, "ratio": None, "why": "variance_unmeasurable"}
    ratio = max(before, after) / min(before, after)
    return {"ok": ratio < VARIANCE_RATIO_LIMIT, "ratio": ratio,
            "before": float(before), "after": float(after),
            "why": "" if ratio < VARIANCE_RATIO_LIMIT else "texture_changed"}


def render_edge_crop(raw, text_regions, protected_regions, *, margin=4):
    """Worker-only PNG render; input coordinates must match this exact image.

    EXIF orientation is deliberately not auto-transposed: an unoriented frame
    is rejected so OCR/protection coordinates cannot silently drift. No upload,
    DB access, OCR call, model call or output selection occurs here.
    """
    from io import BytesIO
    from PIL import Image

    try:
        with Image.open(BytesIO(raw)) as source:
            if source.getexif().get(274, 1) != 1:
                return {"ok": False, "why": "orientation_requires_new_coordinates"}
            if getattr(source, "n_frames", 1) != 1:
                return {"ok": False, "why": "animated_image"}
            if source.mode != "RGB":
                return {"ok": False, "why": "unsupported_color_mode"}
            plan = crop_plan(source.size, text_regions, protected_regions, margin=margin)
            if not plan["ok"]:
                return plan
            # Size was checked from the header before decoding the raster.
            source.load()
            cropped = source.crop(tuple(plan["crop"]))
            canvas = Image.new("RGB", tuple(plan["size"]), "white")
            canvas.paste(cropped, tuple(plan["padding"]))
            output = BytesIO()
            canvas.save(output, format="PNG")
            return dict(plan, bytes=output.getvalue(), coordinate_frame="cropped",
                        requires_fresh_ocr=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        return {"ok": False, "why": "invalid_image"}
