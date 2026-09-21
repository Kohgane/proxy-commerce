"""src/services/image_text_render.py — D3 **3단계: 지우고 다시 쓴다**.

## 어디에 놓이나

```
1단계  텐센트 TransDetails  →  「박스 + 원문」만 쓴다(렌더본은 버린다)
2단계  image_text_glossary  →  우리가 번역한다(브랜드 보존·관용 사전·영문 UI 유지)
3단계  ★여기★             →  원문 글자를 지우고, 그 자리에 한국어를 그린다
```

**골든 샘플 5축을 통과하기 전에는 파이프라인에 연결하지 않는다** — 지금 도는 텐센트 경로는 그대로다.

## 두 가지 일을 한다

| | 무엇 | 어떻게 |
|---|---|---|
| **지우기** | 원문 글자를 배경으로 메운다 | `cv2.inpaint` — TELEA(기본) 또는 NS |
| **쓰기** | 박스 **안에** 한국어를 앉힌다 | Noto Sans KR, **폭에 맞춰** 크기·줄바꿈 |

## ★★ 박스는 **원문** 문단의 자리다

텐센트 `BoundingBox`는 「段落文本框位置」 — **원문**이 있던 자리다. 한국어는 같은 뜻이라도
길이가 다르다(대개 짧고, 가끔 길다). 그래서 **박스를 넘기지 않는 것**이 3단계의 일이고,
넘길 것 같으면 **글자를 줄이거나 줄을 나눈다.** 박스를 늘리지 않는다 — 옆 글자를 덮기 때문이다.

> ★ **못 앉히면 그 줄은 그리지 않는다.** 삐져나온 글자는 상품 사진을 망친다 —
> 안 그린 자리는 (지운 뒤라) 깨끗하고, 그게 잘못 그린 것보다 낫다. 사유는 결과에 남는다.

## 원본을 훼손하지 않는다

입력 바이트는 건드리지 않고 **새 바이트**를 낸다. 실패하면 **원본 바이트 그대로** 돌려준다
(빈 이미지나 반쯤 그린 것을 내지 않는다).
"""
from __future__ import annotations

import io
import logging
from typing import Dict, List, Optional, Tuple

from src.services.image_render_font import load as load_font

logger = logging.getLogger(__name__)

# 지우기 방식 — 둘 다 cv2가 주는 것이고, 우리가 고른다.
#   TELEA: 경계에서 안쪽으로 빠르게 메운다(글자처럼 얇은 자국에 강하다)
#   NS   : 유체 흐름을 흉내 낸다(넓은 면·그라데이션 배경에 낫다)
INPAINT_METHODS = ("telea", "ns")

_MIN_FONT_PX = 11          # 이보다 작으면 사람이 못 읽는다 — 그리느니 안 그린다
_BOX_PAD_RATIO = 0.06      # 박스 안쪽 여백(글자가 테두리에 붙지 않게)


def _load_cv2():
    """`(cv2, numpy, 사유)` — F43과 같은 규율. 없으면 **사유가 남는다.**"""
    try:
        import cv2
        import numpy as np
        return cv2, np, ""
    except ImportError as exc:
        return None, None, f"OpenCV(cv2) 미설치 — 지우기를 할 수 없습니다 ({exc})"


def _norm_box(box: Dict, w: int, h: int) -> Optional[Tuple[int, int, int, int]]:
    """`{x,y,w,h}` → 이미지 안으로 잘라 낸 `(x1,y1,x2,y2)`. 못 쓰면 None.

    좌표가 이미지 밖으로 나가는 일은 실제로 있다(회전·여백). **조용히 넘기지 않고**
    잘라 내되, 잘라서 남는 게 없으면 None이다.
    """
    if not box:
        return None
    try:
        x, y = int(box.get("x") or 0), int(box.get("y") or 0)
        bw, bh = int(box.get("w") or 0), int(box.get("h") or 0)
    except (TypeError, ValueError):
        return None
    if bw <= 0 or bh <= 0:
        return None
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(w, x + bw), min(h, y + bh)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return x1, y1, x2, y2


def erase_boxes(image_bytes: bytes, boxes: List[Dict], *, method: str = "telea",
                dilate_px: int = 2) -> tuple:
    """박스 안 글자를 **지운다** — `(바이트, 지운 개수, 사유)`.

    `dilate_px`로 마스크를 약간 부풀린다 — 글자의 안티앨리어싱 가장자리가 남으면
    그 위에 새 글자를 얹었을 때 **옛 글자의 유령**이 보인다.

    실패하면 **원본 바이트 그대로**. 반쯤 지운 이미지를 내지 않는다.
    """
    cv2, np, why = _load_cv2()
    if why:
        return image_bytes, 0, why
    if not boxes:
        return image_bytes, 0, "지울 박스가 없습니다"
    try:
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes, 0, "이미지를 디코드하지 못했습니다"
        h, w = img.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        used = 0
        for b in boxes:
            rect = _norm_box(b, w, h)
            if rect is None:
                continue
            x1, y1, x2, y2 = rect
            mask[y1:y2, x1:x2] = 255
            used += 1
        if not used:
            return image_bytes, 0, "쓸 수 있는 박스가 없습니다(좌표가 이미지 밖이거나 0 크기)"
        if dilate_px > 0:
            k = np.ones((dilate_px * 2 + 1, dilate_px * 2 + 1), np.uint8)
            mask = cv2.dilate(mask, k, iterations=1)
        flag = cv2.INPAINT_NS if str(method).lower() == "ns" else cv2.INPAINT_TELEA
        out = cv2.inpaint(img, mask, 3, flag)
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            return image_bytes, 0, "결과를 인코드하지 못했습니다"
        return buf.tobytes(), used, ""
    except Exception as exc:
        logger.warning("[D3 렌더] 지우기 실패(원본 유지): %s", exc)
        return image_bytes, 0, f"지우기 오류: {type(exc).__name__}"


def fit_text(text: str, box_w: int, box_h: int, *, weight: str = "regular",
             max_px: int = 0) -> Optional[Dict]:
    """박스 **안에** 들어가는 `(크기, 줄들)`을 찾는다. 못 찾으면 None.

    큰 크기부터 줄여 가며, 각 크기에서 **단어 단위로 줄을 나눠** 폭과 높이를 둘 다 본다.
    한국어는 띄어쓰기가 드물어 단어가 길 수 있으므로, 한 낱말이 폭을 넘으면 **글자 단위**로 나눈다.

    `_MIN_FONT_PX`까지 줄여도 안 들어가면 **None** — 호출부는 그 줄을 그리지 않는다.
    """
    text = str(text or "").strip()
    if not text or box_w <= 0 or box_h <= 0:
        return None
    pad = max(1, int(min(box_w, box_h) * _BOX_PAD_RATIO))
    inner_w, inner_h = box_w - pad * 2, box_h - pad * 2
    if inner_w < 4 or inner_h < _MIN_FONT_PX:
        return None

    start = max_px or min(inner_h, max(_MIN_FONT_PX, int(box_h * 0.9)))
    for size in range(int(start), _MIN_FONT_PX - 1, -1):
        font = load_font(size, weight)
        if font is None:
            return None
        lines = _wrap(text, font, inner_w)
        if lines is None:
            continue
        line_h = int(size * 1.25)                     # 한글은 행간이 넉넉해야 읽힌다
        if line_h * len(lines) <= inner_h:
            return {"size": size, "lines": lines, "line_h": line_h, "pad": pad}
    return None


def _wrap(text: str, font, max_w: int) -> Optional[List[str]]:
    """폭 안에서 줄을 나눈다. 한 글자도 안 들어가면 None."""
    def _w(s: str) -> int:
        box = font.getbbox(s)
        return int(box[2] - box[0])

    words, lines, cur = str(text).split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if _w(trial) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        if _w(word) <= max_w:
            cur = word
            continue
        # 낱말 하나가 폭을 넘는다 — 글자 단위로 자른다(한국어에서 흔하다).
        piece = ""
        for ch in word:
            if _w(piece + ch) <= max_w:
                piece += ch
            else:
                if not piece:
                    return None                # 한 글자도 안 들어간다
                lines.append(piece)
                piece = ch
        cur = piece
    if cur:
        lines.append(cur)
    return lines or None


def draw_lines(image_bytes: bytes, lines: List[Dict], *, weight: str = "regular",
               color: Tuple[int, int, int] = (26, 23, 20)) -> tuple:
    """지워진 이미지 위에 한국어를 **앉힌다** — `(바이트, 그린 수, 건너뛴 것들)`.

    `lines` = `[{render_text, box}]`(2단계 산출). 각 줄은 자기 박스 안에서 가운데 정렬된다.
    **못 앉힌 줄은 그리지 않고** `skipped`에 사유와 함께 남는다 — 조용히 빠뜨리지 않는다.

    기본 색은 먹(#1A1714)이다. 배경이 어두우면 읽히지 않으므로, 호출부가 필요하면 바꾼다
    (배경 밝기 판정은 이 함수의 일이 아니다 — 골든 샘플로 확인한 뒤 붙인다).
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        return image_bytes, 0, [{"reason": f"Pillow 미설치 ({exc})"}]

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        return image_bytes, 0, [{"reason": f"이미지를 열지 못했습니다: {type(exc).__name__}"}]

    draw = ImageDraw.Draw(img)
    drawn, skipped = 0, []
    for ln in lines or []:
        text = str(ln.get("render_text") or "").strip()
        rect = _norm_box(ln.get("box") or {}, img.width, img.height)
        if not text:
            skipped.append({"text": text, "reason": "그릴 글자가 없습니다"})
            continue
        if rect is None:
            skipped.append({"text": text, "reason": "박스를 쓸 수 없습니다"})
            continue
        x1, y1, x2, y2 = rect
        plan = fit_text(text, x2 - x1, y2 - y1, weight=weight)
        if plan is None:
            # ★ 억지로 그리지 않는다 — 삐져나온 글자는 상품 사진을 망친다.
            skipped.append({"text": text, "reason": f"박스에 안 들어갑니다({x2 - x1}×{y2 - y1}px)"})
            continue
        font = load_font(plan["size"], weight)
        if font is None:
            skipped.append({"text": text, "reason": "폰트를 불러오지 못했습니다"})
            continue
        total_h = plan["line_h"] * len(plan["lines"])
        cy = y1 + ((y2 - y1) - total_h) // 2
        for i, line in enumerate(plan["lines"]):
            bbox = font.getbbox(line)
            lw = bbox[2] - bbox[0]
            cx = x1 + ((x2 - x1) - lw) // 2
            draw.text((cx, cy + i * plan["line_h"]), line, font=font, fill=color)
        drawn += 1

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), drawn, skipped


def render(image_bytes: bytes, lines: List[Dict], *, method: str = "telea",
           weight: str = "regular") -> Dict:
    """3단계 전체 — 지우고 쓴다. `{ok, image_bytes, erased, drawn, skipped, error}`.

    **그릴 게 하나도 없으면 지우지도 않는다** — 멀쩡한 원본을 괜히 뭉개지 않기 위해서다.
    실패는 언제나 **원본 바이트**로 끝난다.
    """
    paintable = [ln for ln in (lines or [])
                 if str(ln.get("render_text") or "").strip() and ln.get("box")]
    if not paintable:
        return {"ok": False, "image_bytes": image_bytes, "erased": 0, "drawn": 0,
                "skipped": [], "error": "그릴 줄이 없습니다(원본 그대로)"}

    erased_bytes, erased, why = erase_boxes(
        image_bytes, [ln["box"] for ln in paintable], method=method)
    if why:
        return {"ok": False, "image_bytes": image_bytes, "erased": 0, "drawn": 0,
                "skipped": [], "error": why}

    out, drawn, skipped = draw_lines(erased_bytes, paintable, weight=weight)
    return {
        "ok": drawn > 0,
        "image_bytes": out,
        "erased": erased,
        "drawn": drawn,
        "skipped": skipped,
        "error": "" if drawn else "한 줄도 앉히지 못했습니다",
    }
