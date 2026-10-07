"""M5 후속(오너 2026-10-07, 실사용 1호): 「사진 좌우반전 의심(워터마크 거울상)」 — 원본과 우리가 보여 주는 사진을 픽셀로 비교.

판정: 두 장을 64×64 흑백으로 줄여 평균 차이를 잰다 — 그대로 비교(같음) vs 원본을 좌우로 뒤집어 비교(반전).
- 반전 쪽이 확연히 작고 충분히 작으면 「좌우반전」 · 그대로 쪽이 작으면 「같음」 · 둘 다 크면 「다름」(번역본·크롭 등).
- 원본 EXIF 방향(2·4·5·7 = 거울)도 함께 적는다 — 브라우저·Cloudinary가 EXIF를 따르면 그 자체로 거울상이 될 수 있다.
코드 전수 검색(2026-10-07): 파이프라인(Cloudinary 변환·Y7 크롭·텐센트 렌더)에 flip/mirror/transpose 0곳.
"""
from __future__ import annotations

import io
from typing import Any, Dict, Optional

SIZE = 64
SAME_MAX = 18.0          # 평균 차이(0~255) — 이 아래면 「같은 그림」
MIRROR_RATIO = 0.6       # 반전 비교가 그대로 비교의 60% 아래여야 「반전」
MIRROR_EXIF = {2, 4, 5, 7}


def _gray(raw: bytes):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    exif = None
    try:
        exif = int(im.getexif().get(274) or 0) or None
    except Exception:
        exif = None
    return im.convert("L").resize((SIZE, SIZE)), exif


def _diff(a, b) -> float:
    pa, pb = a.getdata(), b.getdata()
    return sum(abs(x - y) for x, y in zip(pa, pb)) / float(SIZE * SIZE)


def compare(original: bytes, shown: bytes) -> Dict[str, Any]:
    """`{verdict: 같음|좌우반전|다름, same, mirror, exif_orientation}` — 실패면 verdict=판정 못 함 + why."""
    try:
        from PIL import Image
        a, exif = _gray(original)
        b, _ = _gray(shown)
        same = _diff(a, b)
        mirror = _diff(a.transpose(Image.FLIP_LEFT_RIGHT), b)
    except Exception as exc:                                     # noqa: BLE001
        return {"verdict": "판정 못 함", "why": f"{type(exc).__name__}: {str(exc)[:120]}"}
    if mirror < SAME_MAX and mirror < same * MIRROR_RATIO:
        verdict = "좌우반전"
    elif same < SAME_MAX:
        verdict = "같음"
    else:
        verdict = "다름"
    return {"verdict": verdict, "same": round(same, 1), "mirror": round(mirror, 1),
            "exif_orientation": exif, "exif_mirror": bool(exif in MIRROR_EXIF)}


def check_pair(original_url: str, shown_url: str, fetch=None) -> Dict[str, Any]:
    """주소 두 개 → 비교. 우리 번역본 주소(내부)도 읽는다(`coupang_image_check._bytes_for`)."""
    if fetch is None:
        from src.services.coupang_image_check import _bytes_for as fetch
    ra, wa = fetch(original_url)
    if not ra:
        return {"verdict": "판정 못 함", "why": f"원본: {wa}"}
    if shown_url == original_url:
        out = compare(ra, ra)
        out["note"] = "보여 주는 사진이 원본 주소 그대로"
        return out
    rb, wb = fetch(shown_url)
    if not rb:
        return {"verdict": "판정 못 함", "why": f"보여 주는 사진: {wb}"}
    return compare(ra, rb)


def original_urls(extra: dict, onebound_raw: Optional[dict] = None) -> list:
    """원본 사진 주소 — 온바운드 보관본 `item.item_imgs`가 있으면 그것(정본), 없으면 수집 `images`."""
    imgs = []
    item = (onebound_raw or {}).get("item") if isinstance(onebound_raw, dict) else None
    for it in ((item or {}).get("item_imgs") or []):
        u = str((it or {}).get("url") or "") if isinstance(it, dict) else str(it or "")
        if u:
            imgs.append("https:" + u if u.startswith("//") else u)
    return imgs or [u for u in (extra.get("images") or []) if u]
