"""Administrator-reviewed product regions, bound to exact source bytes.

This produces human review evidence, not an automatic product detector.
Snapshot reads never invoke OCR, upload, edit normalization or database writes.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import datetime, timezone

from itsdangerous import BadData, URLSafeSerializer, URLSafeTimedSerializer


def _secret():
    from flask import current_app, has_app_context
    if has_app_context():
        key = current_app.secret_key
    else:
        from src.order_webhook import app
        key = app.secret_key
    if not key:
        raise ValueError("검토 서명 키를 사용할 수 없어요")
    return key


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def _source(extra, idx):
    from src.services import image_edit as IE
    if type(idx) is not int or not 0 <= idx < len(extra.get("images") or []):
        raise ValueError("사진 번호를 확인해 주세요")
    entry = IE._entry(extra, "gallery", idx) or {}
    url = IE.base_url(extra, "gallery", idx)
    if not url:
        raise ValueError("사진 주소가 없어요")
    return {"url": url, "version": IE.current_key(entry)}


def _bytes(url):
    from src.services import image_edit as IE
    from src.collectors.image_norm import image_head
    # work_bytes can create a CDN copy; this read-only path must not call it.
    raw = IE._fetch(url)
    if not raw or len(raw) > 12 * 1024 * 1024:
        raise ValueError("사진을 받지 못했거나 용량이 너무 커요")
    fmt, w, h = image_head(raw)
    if fmt not in ("PNG", "JPEG") or not w or not h or max(w, h) > 2000:
        raise ValueError("검토는 긴 변 2,000px 이하 PNG·JPEG 사진에서 가능해요")
    return raw, [w, h], "image/png" if fmt == "PNG" else "image/jpeg"


def snapshot(extra, idx, *, item_id, reviewer):
    if not reviewer:
        raise ValueError("로그인이 필요합니다")
    source = _source(extra, idx)
    raw, size, mime = _bytes(source["url"])
    payload = dict(source, sha256=hashlib.sha256(raw).hexdigest(), size=size,
                   item_id=str(item_id), idx=idx, reviewer=str(reviewer), state=_digest(extra))
    token = URLSafeTimedSerializer(_secret(), salt="rep-review-challenge-v1").dumps(payload)
    return {"ok": True, "token": token, "size": size, "version": source["version"],
            "image": "data:" + mime + ";base64," + base64.b64encode(raw).decode(),
            "review_kind": "human", "expires_in": 900}


def sign(proof):
    return URLSafeSerializer(_secret(), salt="rep-protection-v1").dumps(proof)


def verified(proof):
    if not isinstance(proof, dict) or not proof.get("signature"):
        return False
    try:
        unsigned = {k: v for k, v in proof.items() if k != "signature"}
        return URLSafeSerializer(_secret(), salt="rep-protection-v1").loads(proof["signature"]) == unsigned
    except (BadData, ValueError, TypeError):
        return False


def accept(extra, idx, body, *, item_id, reviewer):
    if not isinstance(body, dict) or body.get("reviewed_complete") is not True:
        raise ValueError("상품 전체를 보호 영역에 포함했는지 확인해 주세요")
    try:
        p = URLSafeTimedSerializer(_secret(), salt="rep-review-challenge-v1").loads(
            body.get("token", ""), max_age=900)
    except (BadData, TypeError, ValueError):
        raise ValueError("검토 시간이 지났거나 잘못된 요청이에요 — 다시 열어 주세요") from None
    if (p.get("item_id") != str(item_id) or p.get("idx") != idx
            or p.get("reviewer") != str(reviewer) or not reviewer
            or p.get("state") != _digest(extra)
            or _source(extra, idx) != {k: p[k] for k in ("url", "version")}):
        raise ValueError("검토 중 상품이나 사진이 바뀌었어요 — 다시 열어 주세요")
    raw, size, _ = _bytes(p["url"])
    if p["sha256"] != hashlib.sha256(raw).hexdigest() or p["size"] != size:
        raise ValueError("검토 중 사진 내용이 바뀌었어요 — 다시 열어 주세요")
    from src.services.rep_clean_geometry import _rects
    regions = body.get("regions")
    if not isinstance(regions, list) or not 1 <= len(regions) <= 24:
        raise ValueError("상품 보호 영역을 1~24개 지정해 주세요")
    try:
        regions = [list(r) for r in _rects(regions, *size)]
    except ValueError:
        raise ValueError("상품 보호 영역이 사진 밖이거나 올바르지 않아요") from None
    proof = {k: p[k] for k in ("url", "version", "sha256", "size", "reviewer", "item_id", "idx")}
    proof.update(reviewed_complete=True, reviewed_at=datetime.now(timezone.utc).isoformat(),
                 review_kind="human", regions=regions)
    proof["signature"] = sign(proof)
    result = copy.deepcopy(extra)
    from src.services import image_edit as IE
    IE._entry(result, "gallery", idx, create=True)["rep_protection"] = proof
    return result
