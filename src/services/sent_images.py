"""Y11X(오너 2026-10-17) — 마켓에 **보낸 사진 주소 목록**(해시+URL)을 등록 기록·상세 갱신 기록에 남긴다.

Y11W-2: 쿠팡 상세 14번(다듬은 「이수에」 버전)이 쿠팡에 들어갔는지 DB로 확인할 길이 없었다 — 상세 갱신 기록은 장 수(17)만,
네이버 응답 원문은 2,000자에서 잘렸다. 쿠팡·네이버가 같은 꼴로 남긴다:
`{"hash": 주소 목록 해시, "n": 장 수, "images": [{"k": 종류, "h": 주소 해시, "url": 주소}, …]}` (장 수 상한 `CAP`).
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, List, Tuple

CAP = 80
_IMG_SRC = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.I)


def _h(url: str) -> str:
    return hashlib.sha1(str(url or "").encode("utf-8")).hexdigest()[:12]


def summarize(pairs: Iterable[Tuple[str, str]]) -> Dict:
    """`(종류, 주소)` 순서 그대로 → `{hash, n, images}`. 빈 주소는 뺀다."""
    rows = [{"k": k, "h": _h(u), "url": u} for k, u in pairs if u]
    whole = hashlib.sha1("\n".join(f"{r['k']}|{r['url']}" for r in rows).encode("utf-8")).hexdigest()[:16]
    return {"hash": whole, "n": len(rows), "images": rows[:CAP]}


def from_html(html: str, kind: str = "detail") -> Dict:
    """네이버 상세 본문(보낸 그대로) → 사진 주소 목록."""
    return summarize((kind, u) for u in _IMG_SRC.findall(str(html or "")))


def from_coupang(body: Dict) -> Dict:
    """쿠팡 등록·수정 몸통(보낸 그대로) → 옵션 대표·기타 사진(품목마다 · 같은 주소는 한 번) + 상세 이미지 블록·본문 <img>."""
    pairs: List[Tuple[str, str]] = []
    seen = set()
    items = [it for it in (body or {}).get("items") or [] if isinstance(it, dict)]
    for it in items:
        for x in it.get("images") or []:
            if not isinstance(x, dict):
                continue
            u = str(x.get("vendorPath") or x.get("cdnPath") or "")
            k = "sku" if str(x.get("imageType") or "").upper() == "REPRESENTATION" else "sku_other"
            if u and (k, u) not in seen:
                seen.add((k, u))
                pairs.append((k, u))
    for c in (items[0].get("contents") if items else None) or []:
        for d in (c or {}).get("contentDetails") or []:
            if not isinstance(d, dict):
                continue
            if str(d.get("detailType") or "").upper() == "IMAGE":
                pairs.append(("detail", str(d.get("content") or "")))
            else:
                pairs += [("detail", u) for u in _IMG_SRC.findall(str(d.get("content") or ""))]
    return summarize(pairs)


def has(record: Dict, url: str) -> bool:
    """이 주소가 보낸 목록에 있나(주소 해시로 — 잘린 목록이면 n > len(images)라 「모름」은 호출자가 본다)."""
    h = _h(url)
    return any(r.get("h") == h for r in (record or {}).get("images") or [])
