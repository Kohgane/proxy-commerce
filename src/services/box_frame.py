"""Y11-E(오너 2026-10-14) — 글자 상자의 좌표 틀(frame) 확인.

실측(VRSUK 갤러리 3, 운영 10-14): 텐센트 이미지 번역은 거꾸로 놓인 책등 글자(「Zaha Hadid」·「IS THAT YUO」)를
**제대로 번역해 책 위에 그렸는데**, 줄 상자(`TransDetails[].BoundingBox`)는 **180° 돌린 그림 기준**으로 돌려줬다
(SDK 설명: 응답 `Angle` = 「逆时针图片角度，取值范围为0-359」). 그 상자를 그대로 그리니 왼쪽 위 **빈 벽**에 상자가 떴고,
오너가 그 자리를 지우게 됐다(지울 글자가 없는 벽을 지움).

판정은 각도 숫자만 믿지 않는다 — **그림으로 잰다**: 원본과 번역본은 글자가 바뀐 자리에서만 다르다.
후보 틀(그대로 · 180° · 90° 양쪽)마다 상자 안의 원본↔번역본 차이를 재서, 가장 크게 다른 틀을 고른다.
어느 틀도 뚜렷하지 않으면 「확인 못 함」 — 상자를 **보여 주지 않는다**(빈 벽에 상자 금지).
"""
from __future__ import annotations

import io
from typing import Dict, List, Optional, Tuple

#: 상자 안 평균 밝기 차이(0~255)가 이 값 이상이어야 「글자가 바뀐 자리」로 본다.
MIN_DIFF = 4.0
#: 돌린 틀이 그대로 틀보다 이 배수 이상 커야 돌린 틀을 고른다(애매하면 그대로).
WIN_RATIO = 2.0
SMALL_SIDE = 320

FRAMES = ("identity", "rot180", "rot90a", "rot90b")


def to_original(box: Dict, W: int, H: int, frame: str) -> Dict:
    """상자 하나를 `frame` 기준 좌표 → 원본 그림 좌표로. `W,H` = 원본 그림 크기."""
    x, y, w, h = (int(box.get(k) or 0) for k in ("x", "y", "w", "h"))
    if frame == "rot180":
        nx, ny, nw, nh = W - x - w, H - y - h, w, h
    elif frame == "rot90a":                                   # 원본을 반시계 90° 돌린 틀(크기 H×W)
        nx, ny, nw, nh = W - (y + h), x, h, w
    elif frame == "rot90b":                                   # 원본을 시계 90° 돌린 틀(크기 H×W)
        nx, ny, nw, nh = y, H - (x + w), h, w
    else:
        nx, ny, nw, nh = x, y, w, h
    out = dict(box)
    out.update(x=max(0, nx), y=max(0, ny), w=max(1, nw), h=max(1, nh))
    return out


def _gray_small(raw: bytes, size: Optional[Tuple[int, int]] = None):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    W, H = im.size
    im.draft("L", (SMALL_SIDE, SMALL_SIDE))
    g = im.convert("L")
    sw = SMALL_SIDE if W >= H else max(1, int(SMALL_SIDE * W / H))
    sh = SMALL_SIDE if H > W else max(1, int(SMALL_SIDE * H / W))
    g = g.resize(size or (sw, sh))
    return g, (W, H)


def _diff_in(a, b, box: Dict, W: int, H: int) -> Tuple[float, int]:
    """상자 안 평균 차이와 화소 수(작은 그림 공간)."""
    sw, sh = a.size
    x0, y0 = int(box["x"] * sw / W), int(box["y"] * sh / H)
    x1 = min(sw, max(x0 + 1, int((box["x"] + box["w"]) * sw / W)))
    y1 = min(sh, max(y0 + 1, int((box["y"] + box["h"]) * sh / H)))
    if x0 >= sw or y0 >= sh:
        return 0.0, 0
    pa, pb = a.load(), b.load()
    tot = n = 0
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            tot += abs(pa[xx, yy] - pb[xx, yy])
            n += 1
    return (tot / n if n else 0.0), n


def score(orig_raw: bytes, trans_raw: bytes, boxes: List[Dict], frames=FRAMES) -> Dict:
    """틀마다 상자 안 원본↔번역본 차이(화소 가중 평균). `{frame: diff}` + `size`. 못 열면 `{}`."""
    try:
        a, (W, H) = _gray_small(orig_raw)
        b, (W2, H2) = _gray_small(trans_raw, size=a.size)
    except Exception:                                          # noqa: BLE001
        return {}
    out = {"size": [W, H]}
    for f in frames:
        tot = n = 0.0
        for bx in boxes:
            ob = to_original(bx, W, H, f)
            d, k = _diff_in(a, b, ob, W, H)
            tot += d * k
            n += k
        out[f] = round(tot / n, 2) if n else 0.0
    return out


def pick(orig_raw: bytes, trans_raw: bytes, boxes: List[Dict], angle=None) -> Dict:
    """`{frame, boxes(원본 좌표), scores, why}` — frame: identity|rot180|rot90a|rot90b|unknown.

    고르는 법: 그대로 틀이 뚜렷하면(≥ MIN_DIFF) 그대로. 아니면 돌린 틀 중 가장 큰 것이 뚜렷하고 그대로의 `WIN_RATIO`배 이상이면 그것.
    둘 다 아니면 `unknown` — 상자를 쓰지 않는다(빈 벽에 상자 금지)."""
    boxes = [b for b in boxes or [] if isinstance(b, dict) and int(b.get("w") or 0) > 0 and int(b.get("h") or 0) > 0]
    if not boxes:
        return {"frame": "identity", "boxes": [], "scores": {}, "why": ""}
    sc = score(orig_raw, trans_raw, boxes)
    if not sc:
        return {"frame": "unknown", "boxes": [], "scores": {}, "why": "원본·번역본을 열지 못해 상자 자리를 확인 못 함"}
    W, H = sc["size"]
    ident = sc.get("identity", 0.0)
    best = max((f for f in FRAMES if f != "identity"), key=lambda f: sc.get(f, 0.0))
    if sc[best] >= MIN_DIFF and sc[best] >= WIN_RATIO * max(ident, 0.5):
        frame = best
    elif ident >= MIN_DIFF:
        frame = "identity"
    else:
        return {"frame": "unknown", "boxes": [], "scores": sc,
                "why": "상자 자리에서 번역 전후 차이를 못 찾음 — 상자 위치를 믿을 수 없어 보여 주지 않아요"}
    return {"frame": frame, "boxes": [to_original(b, W, H, frame) for b in boxes], "scores": sc, "why": ""}
