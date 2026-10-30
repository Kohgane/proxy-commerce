"""H-rep2 bridge to existing edit storage, with no outbound selection changes.

``rep_protection`` is reviewed server-side evidence on an image entry. It must
identify the exact selected URL, version and work-bytes SHA256, plus complete
product rectangles in that byte frame. This module never creates that review.
The review producer is a separate integration requirement; this metadata alone
must not be presented as an automatic product detector.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone


def identity(extra, idx):
    from src.services import image_edit as IE
    entry = IE._entry(extra, "gallery", idx) or {}
    proof = entry.get("rep_protection")
    return {"url": IE.base_url(extra, "gallery", idx), "version": IE.current_key(entry),
            "proof": copy.deepcopy(proof)}


def attempt_key(extra, idx):
    value = identity(extra, idx)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prepare(extra, idx):
    """Resolve current boxes on a private copy, so failed candidates change no selection."""
    from src.services import image_edit as IE
    from src.collectors.image_norm import image_head
    current = identity(extra, idx)
    proof = current["proof"]
    if (not isinstance(proof, dict) or proof.get("reviewed_complete") is not True
            or not proof.get("reviewer") or not proof.get("reviewed_at")):
        return {"ok": False, "why": "상품 보호 영역 검토 기록이 없어요"}
    if proof.get("version") != current["version"] or proof.get("url") != current["url"]:
        return {"ok": False, "why": "상품 보호 영역이 현재 사진 버전과 달라요"}
    raw, why = IE.work_bytes(current["url"])
    if not raw:
        return {"ok": False, "why": why or "사진을 받지 못했어요"}
    if proof.get("sha256") != hashlib.sha256(raw).hexdigest():
        return {"ok": False, "why": "검토 후 사진 바이트가 바뀌었어요"}
    _, width, height = image_head(raw)
    if not width or not height or max(width, height) > 2000:
        return {"ok": False, "why": "사진 크기를 확인하지 못했어요"}
    p = IE.plan(copy.deepcopy(extra), "gallery", idx, fetch=False)
    if p.get("ok") is False or p.get("url") != current["url"] or p.get("current") != current["version"]:
        return {"ok": False, "why": "글자 상자가 다른 사진 버전이에요"}
    size = p.get("size") or []
    if len(size) != 2 or any(type(n) is not int or n <= 0 for n in size):
        return {"ok": False, "why": "글자 상자의 좌표계를 확인하지 못했어요"}
    sx, sy = width / size[0], height / size[1]
    regions = []
    for box in p.get("boxes") or []:
        x, y, w, h = (box.get(k) for k in ("x", "y", "w", "h"))
        if any(type(v) is not int for v in (x, y, w, h)) or w <= 0 or h <= 0:
            return {"ok": False, "why": "글자 상자 좌표가 올바르지 않아요"}
        regions.append([x * sx, y * sy, (x + w) * sx, (y + h) * sy])
    if not regions:
        return {"ok": False, "why": "지울 글자 상자를 못 찾았어요"}
    from src.services.rep_clean_geometry import _rects
    try:
        _rects(regions, width, height)
        _rects(proof.get("regions"), width, height)
    except ValueError:
        return {"ok": False, "why": "글자 또는 상품 보호 영역이 사진 밖이에요"}
    return {"ok": True, "raw": raw, "text_regions": regions, "protection": proof,
            "version": current["version"], "identity": current}


def render(prepared):
    from src.services.rep_clean_candidate import clean_candidate
    return clean_candidate(prepared["raw"], prepared["text_regions"], prepared["protection"],
                           version=prepared["version"])


def publish(extra, idx, prepared, result):
    """Upload only a validated candidate, verify CDN bytes, append a separate version.

    Caller persists extra. No database write here. If upload/re-download or
    source identity fails, no version or selection is changed.
    """
    from src.services import image_edit as IE
    from src.media.image_pipeline import upload_bytes
    if identity(extra, idx) != prepared["identity"]:
        return {"ok": False, "why": "처리 중 사진 버전이 바뀌었어요"}
    raw = result.get("bytes")
    if (result.get("ok") is not True or type(result.get("boxes_after")) is not int
            or result["boxes_after"] != 0 or not isinstance(raw, bytes) or not raw
            or result.get("requires_fresh_ocr") is not False
            or result.get("source_sha256") != prepared["protection"]["sha256"]
            or result.get("source_version") != prepared["version"]
            or result.get("output_sha256") != hashlib.sha256(raw).hexdigest()):
        return {"ok": False, "why": "검증을 마친 정리본이 아니에요"}
    up = upload_bytes(raw, folder="edit", timeout=IE.step_timeout_sec())
    url = str(up.get("secure_url") or "") if up.get("ok") else ""
    if not url:
        return {"ok": False, "why": "정리본 업로드에 실패했어요"}
    stored = IE._fetch(url)
    if not stored or hashlib.sha256(stored).hexdigest() != result["output_sha256"]:
        return {"ok": False, "why": "업로드된 사진이 검증한 바이트와 달라요"}
    if identity(extra, idx) != prepared["identity"]:
        return {"ok": False, "why": "처리 중 사진 버전이 바뀌었어요"}
    entry = IE._entry(extra, "gallery", idx, create=True)
    versions = IE.edits(entry)
    n = max([int(e.get("n") or 0) for e in versions] + [0]) + 1
    key = f"edit:{n}"
    versions.append({"n": n, "url": url, "base": prepared["identity"]["url"],
                     "base_key": prepared["version"], "at": datetime.now(timezone.utc).isoformat(),
                     "by": "rep_auto", "ready": True, "render": "hrep2", "credits": 0,
                     "method": result.get("method"), "size": result.get("size"),
                     "measurements": result.get("measurements", []),
                     "source_sha256": prepared["protection"]["sha256"],
                     "output_sha256": result["output_sha256"]})
    entry["edits"] = versions
    # New frame: never copy original OCR coordinates or alter url/use/status.
    entry.setdefault("vboxes", {})[key] = {"img": url, "boxes": [], "size": result["size"]}
    return {"ok": True, "url": url, "version": key, "method": result.get("method")}
