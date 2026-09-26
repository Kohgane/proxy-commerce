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
from src.services.image_render_font import load_source as load_source_font
from src.services.image_render_font import supported as font_supported
from src.services.image_render_font import supported_source as source_font_supported

logger = logging.getLogger(__name__)

# 지우기 방식 — 둘 다 cv2가 주는 것이고, 우리가 고른다.
#   TELEA: 경계에서 안쪽으로 빠르게 메운다(글자처럼 얇은 자국에 강하다)
#   NS   : 유체 흐름을 흉내 낸다(넓은 면·그라데이션 배경에 낫다)
INPAINT_METHODS = ("telea", "ns")

_MIN_FONT_PX = 11          # 이보다 작으면 사람이 못 읽는다 — 그리느니 안 그린다
#: D3-6 ③(오너 2026-09-25) — 박스 높이가 **원본 높이의 1.5%** 미만이면 손대지 않는다
#: (750×1000이면 15px). 시계 화면 속 작은 글자를 지우고 다시 그리면 「워ㅇ이」가 된다.
SMALL_TEXT_RATIO = 0.015
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


def _glyph_mask(cv2, np, img, rect, dilate_px: int) -> tuple:
    """박스 안에서 **글자 픽셀만** 골라 마스크를 만든다 — `(mask, 사유)` (D3-4 ②).

    ## 왜 박스를 통째로 지우면 안 되나 (골든 샘플 C축 실패)

    텐센트 `BoundingBox`는 **문단 박스**다. 그 안에는 글자만 있는 게 아니라
    **알약·띠 같은 배경 도형**이 함께 있다. 박스를 통째로 마스크로 쓰면
    **도형이 날아가고** 그 자리가 뭉개진다 — 실측에서 그게 C축을 떨어뜨렸다.

    ## 어떻게 고르나

    박스 안의 **배경색을 먼저 추정**(테두리 픽셀의 중앙값)하고, 그 색에서 **충분히 먼**
    픽셀을 글자로 본다. 글자는 배경 위에 얹힌 고대비 획이기 때문이다.
    잡힌 비율이 **너무 크면**(박스 대부분) 그건 글자가 아니라 **도형을 잡은 것**이므로
    실패로 돌려보낸다 — 잘못 지우느니 **이 장은 공급사 렌더를 쓰는 편이 낫다**.
    """
    x1, y1, x2, y2 = rect
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return None, "박스가 비어 있습니다"

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    # 배경색 = 테두리 한 줄의 중앙값(글자는 보통 안쪽에 있다).
    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    bg = float(np.median(border))
    diff = np.abs(gray.astype(np.int16) - bg).astype(np.uint8)
    if int(diff.max()) < 30:
        # 배경과 구분되는 게 없다 = 글자가 없다. Otsu는 **잡음도 반으로 가르므로**
        #   이 문을 먼저 두지 않으면 빈 칸에서 가짜 마스크가 나온다.
        return None, "글자 픽셀을 못 찾았습니다(배경과 대비 없음)"
    # 임계는 **Otsu**로 정한다. 백분위 고정값은 글자 **색**에 따라 값이 흔들렸다
    #   (청록 글자가 먹 글자보다 얇게 측정 — 실측 2026-09-21). Otsu는 색과 무관하다.
    _t, mask_roi = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # ★ D3-5에서 찾은 구멍 — **박스 테두리에 닿는 덩어리는 글자가 아니라 배경 도형**이다.
    #   문단 박스가 알약에 딱 붙어 있으면 테두리 중앙값이 알약 색이 되고, 박스 네 귀퉁이에 걸친
    #   **페이지 바탕**이 「배경과 먼 픽셀」로 잡혔다. 그러면 마스크의 외접 사각형이 **박스 전체**가
    #   되어 gen_remove가 **알약을 통째로 새로 그린다**(오너가 막으라던 그 사고). telea도 귀퉁이를 칠했다.
    #   글자는 박스 안에 떠 있다 — 테두리에 닿는 덩어리를 뺀다. 다 빠지면(글자가 테두리에
    #   붙은 좁은 박스) **원래 마스크를 그대로 쓴다** — 없는 걸 지어내지 않는다.
    n, lab, stats, _c = cv2.connectedComponentsWithStats(mask_roi, 8)
    if n > 1:
        hh, ww = mask_roi.shape
        touching = [i for i in range(1, n)
                    if stats[i, cv2.CC_STAT_LEFT] == 0 or stats[i, cv2.CC_STAT_TOP] == 0
                    or stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] >= ww
                    or stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] >= hh]
        if touching:
            inner = mask_roi.copy()
            inner[np.isin(lab, touching)] = 0
            if float((inner > 0).sum()) / float(inner.size) >= 0.005:
                mask_roi = inner

    mask_roi = _peel_plate(cv2, np, mask_roi)

    ratio = float((mask_roi > 0).sum()) / float(mask_roi.size)
    if ratio < 0.005:
        return None, f"글자 픽셀을 못 찾았습니다(비율 {ratio:.3f})"
    if ratio > 0.60:
        # 박스 대부분이 잡혔다 = 배경 도형을 잡은 것이다. 지우면 도형이 날아간다.
        return None, f"글자가 아니라 도형을 잡았습니다(비율 {ratio:.2f})"

    if dilate_px > 0:
        k = np.ones((dilate_px * 2 + 1, dilate_px * 2 + 1), np.uint8)
        mask_roi = cv2.dilate(mask_roi, k, iterations=1)

    full = np.zeros(img.shape[:2], np.uint8)
    full[y1:y2, x1:x2] = mask_roi
    return full, ""


#: D3-6 ⑤ — 「판(알약·띠)」으로 볼 덩어리: 박스 면적의 이 비율 이상이고, 자기 외접 사각형을
#: 이만큼 이상 채운(속이 찬) 모양. 글자 한 획은 둘 다 못 넘는다.
PLATE_MIN_AREA = 0.20
PLATE_MIN_SOLIDITY = 0.55


def plate_rect(image_bytes: bytes, box: Dict) -> Optional[Dict]:
    """박스 안에 글자를 태운 **판**(알약·띠)이 있으면, 글자를 앉힐 **판 안쪽** `{x,y,w,h}` (D3-6 ⑤).

    텐센트 박스가 알약보다 크면, 박스 폭에 맞춰 그린 한국어가 **알약 밖으로 삐져나간다**
    (합성 ebvllh 캡처 · cphvcw 「부제 넘침」의 유력 원인). 판이 있으면 판 안쪽에 앉힌다 —
    둥근 끝(높이의 절반)은 빼고, 위아래도 조금 뺀다. 판이 없으면 None(박스 그대로).
    """
    cv2, np, why = _load_cv2()
    if why:
        return None
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    except Exception:                                          # pragma: no cover
        return None
    if img is None:
        return None
    h, w = img.shape[:2]
    rect = _norm_box(box or {}, w, h)
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    diff = np.abs(gray.astype(np.int16) - float(np.median(border))).astype(np.uint8)
    if int(diff.max()) < 30:
        return None
    _t, m = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    got = _find_plate(cv2, np, m)
    if got is None:
        return None
    px, py, pw, ph = got
    inset_x, inset_y = int(min(ph / 2.0, pw * 0.2)), int(ph * 0.12)
    if pw - 2 * inset_x < 8 or ph - 2 * inset_y < _MIN_FONT_PX:
        return None
    return {"x": x1 + px + inset_x, "y": y1 + py + inset_y,
            "w": pw - 2 * inset_x, "h": ph - 2 * inset_y}


def _plates(cv2, np, mask_roi) -> list:
    """마스크 안의 **판** 덩어리들 — `[(bbox(roi), comp, holes)]`. 판 판정 규칙은 **여기 하나**다.

    판 = 박스 면적의 `PLATE_MIN_AREA` 이상 · 자기 외접 사각형을 `PLATE_MIN_SOLIDITY` 이상 채움 ·
    **구멍(글자)을 품음**. 글자 한 획은 셋을 다 못 넘는다.
    """
    n, lab, stats, _c = cv2.connectedComponentsWithStats(mask_roi, 8)
    area_total = float(mask_roi.size)
    out = []
    for i in range(1, n):
        area = float(stats[i, cv2.CC_STAT_AREA])
        bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if area / area_total < PLATE_MIN_AREA or area / float(max(1, bw * bh)) < PLATE_MIN_SOLIDITY:
            continue
        comp = (lab == i).astype(np.uint8) * 255
        cnts, _h = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(comp)
        cv2.drawContours(filled, cnts, -1, 255, thickness=-1)
        holes = cv2.bitwise_and(filled, cv2.bitwise_not(comp))
        if float((holes > 0).sum()) / area_total < 0.003:
            continue
        bbox = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]), int(bw), int(bh))
        out.append((bbox, comp, holes))
    return out


def _plate_interior(cv2, np, img, rect) -> Optional["np.ndarray"]:
    """박스 안 **판(알약·띠) 내부** 전체 마스크(이미지 크기) — 판 픽셀 + 판이 품은 구멍(글자). 없으면 None.

    F축 링을 여기로 제한한다(D3-7). 판 판정은 `plate_rect`와 같은 문턱(테두리 중앙값 → Otsu → `_plates`).
    """
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    diff = np.abs(gray.astype(np.int16) - float(np.median(border))).astype(np.uint8)
    if int(diff.max()) < 30:
        return None
    _t, m = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    got = _plates(cv2, np, m)
    if not got:
        return None
    inner = np.zeros(m.shape, np.uint8)
    for _bbox, comp, holes in got:
        inner = cv2.bitwise_or(inner, cv2.bitwise_or(comp, holes))
    full = np.zeros(img.shape[:2], np.uint8)
    full[y1:y2, x1:x2] = inner
    return full


def _find_plate(cv2, np, mask_roi) -> Optional[tuple]:
    """가장 큰 판의 외접 사각형(roi 좌표). 없으면 None."""
    got = _plates(cv2, np, mask_roi)
    return max((g[0] for g in got), key=lambda b: b[2] * b[3]) if got else None


def _peel_plate(cv2, np, mask_roi):
    """글자를 태운 **판**(알약)을 마스크에서 걷어 내고, 판 안의 **구멍 = 글자**만 남긴다 (D3-6 ⑤).

    ## 왜 (오너 벤치 ebvllh 실측 2026-09-25 — 회색 유령 사각형 + 파란 번짐)

    텐센트 박스가 알약보다 **크면** 테두리 중앙값 = 페이지 바탕(흰색)이 되고, 파란 알약 전체가
    「바탕과 먼 픽셀」 = 글자로 잡힌다. 테두리에 안 닿으니 D3-5의 걸러내기도 통과한다.
    그 마스크로 지우면 **알약이 통째로 지워진다.**

    알약 위 글자는 알약 색과 다르다 — 그러니 알약 덩어리에서 **구멍**으로 나타난다.
    큰·속이 찬 덩어리를 판으로 보고, 판 외곽을 채운 영역에서 판 픽셀을 빼면 글자가 남는다.
    판 밖의 다른 덩어리(판 바깥 글자)는 그대로 둔다. 구멍이 없으면 **아무것도 안 바꾼다.**
    """
    got = _plates(cv2, np, mask_roi)
    if not got:
        return mask_roi
    out = mask_roi.copy()
    for _bbox, comp, holes in got:
        out[comp > 0] = 0            # 판은 지우지 않는다
        out = cv2.bitwise_or(out, holes)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# D3-4 ③ 타이포 상속 — 원본 줄의 **굵기·정렬·색**을 그대로 받는다
# ─────────────────────────────────────────────────────────────────────────────
_ALIGN_TOL = 0.08          # 좌우 여백 차가 박스 폭의 이만큼 넘으면 한쪽 정렬로 본다


def _stroke_ratio(cv2, np, mask) -> Optional[float]:
    """마스크에서 **획 두께 ÷ 글자 높이**. 못 재면 None."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None
    cnts, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    per = sum(cv2.arcLength(c, True) for c in cnts)
    gh = float(ys.max() - ys.min() + 1)
    if per <= 0 or gh <= 0:
        return None
    return (2.0 * float(len(ys)) / per) / gh


def _has_han(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" for ch in str(text or ""))


def _render_ref(cv2, np, text: str, size: int, weight: str):
    """그 글자를 **기준선 폰트**로 그려 보고 `(획비, 글자높이)`를 잰다. 못 그리면 `(None, 0)`.

    ★ D3-5 ④ — **한자가 있으면 원문 기준선 폰트(SC 서브셋)**, 없으면 한국어 렌더 폰트.
    두 폰트는 같은 설계(Source Han Sans)라 획 두께가 같은 자로 잰다.
    **이건 원문을 재려고 그려 보는 자리다 — 한국어를 그리는 자리가 아니다.**
    """
    loader = load_source_font if _has_han(text) else load_font
    font = loader(max(8, int(size)), weight)
    if font is None:
        return None, 0.0
    try:
        from PIL import Image, ImageDraw
    except ImportError:                                       # pragma: no cover
        return None, 0.0
    w = max(32, int(font.getbbox(text)[2] - font.getbbox(text)[0]) + 40)
    img = Image.new("RGB", (w, max(32, int(size * 2.2))), (255, 255, 255))
    ImageDraw.Draw(img).text((20, int(size * 0.5)), text, font=font, fill=(0, 0, 0))
    gray = np.array(img.convert("L"))
    _t, mask = cv2.threshold(255 - gray, 0, 255,
                             cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ys, _xs = np.nonzero(mask)
    if not len(ys):
        return None, 0.0
    return _stroke_ratio(cv2, np, mask), float(ys.max() - ys.min() + 1)


def estimate_weight(cv2, np, text: str, glyph_h: float, measured: float) -> tuple:
    """`(굵기, 사유)` — **그 글자를 우리 폰트로 그려 보고** 더 가까운 쪽을 고른다.

    ## 왜 고정 임계값을 버렸나 (실측 2026-09-21)

    처음엔 `획비 ≥ 0.115면 Bold`라는 **상수**를 뒀다. 그런데 이 값은 **글자마다 다르다** —
    획이 많은 글자는 같은 굵기라도 외곽이 길어 비가 낮게 나온다(실측, 16~90px):

    | 글자 | Regular | Bold |
    |---|---|---|
    | `拒凌乱` | 0.076 ~ 0.099 | **0.115** ~ 0.137 |
    | `12:30` | 0.103 ~ **0.119** | 0.153 ~ 0.182 |

    `12:30`의 **Regular(0.119)**가 `拒凌乱`의 **Bold(0.115)**보다 높다.
    어떤 상수를 골라도 둘 중 하나는 틀린다 — 그건 재는 게 아니라 찍는 것이다.

    ## 그래서

    **같은 글자를** 우리 폰트의 Regular·Bold로 그려 같은 자로 재고, 측정값이 **어느 쪽에
    가까운지** 본다. 글자 복잡도·크기가 양쪽에서 같이 상쇄된다.

    ⚠️ **정직한 한계:** 원본 이미지의 폰트는 우리 폰트가 아니다. 두 기준선 **사이**에
    떨어지면 가까운 쪽으로 가되, 우리가 고른 것은 「원본이 Bold였다」가 아니라
    「**우리 Bold가 더 닮았다**」이다. 그리고 우리가 그릴 수 있는 굵기는 그 둘뿐이다.
    """
    text = str(text or "").strip()
    if not text:
        return "regular", "원문 글자를 몰라 굵기를 못 쟀습니다"
    # ★ 기준선 폰트에 **없는 글자**는 두부(□)로 그려진다 — 두부를 기준선으로 삼으면
    #   글자가 아니라 네모를 재게 된다. 그릴 수 있는 글자만 남긴다.
    #   D3-5 ④: 한자는 SC 서브셋(GB2312 전체)으로 재므로 `绝`·`轻`·`纳`도 이제 잰다.
    drawable = source_font_supported(text) if _has_han(text) else font_supported(text)
    if not drawable:
        return "regular", "원문 글자가 우리 폰트에 없어 굵기를 못 쟀습니다"
    text = drawable
    size = max(8, int(round(glyph_h / 0.72)))                 # 한글·한자 대략 비율
    best = {}
    for w in ("regular", "bold"):
        r, gh = _render_ref(cv2, np, text, size, w)
        if r is None or gh <= 0:
            return "regular", "기준선을 그리지 못했습니다(폰트 없음)"
        # 글자 높이를 원본에 맞춰 한 번 보정한다 — 작은 글자는 안티앨리어싱 몫이 커진다.
        size2 = max(8, int(round(size * glyph_h / gh)))
        if abs(size2 - size) >= 2:
            r2, _ = _render_ref(cv2, np, text, size2, w)
            if r2 is not None:
                r = r2
        best[w] = r
    if abs(measured - best["bold"]) < abs(measured - best["regular"]):
        return "bold", ""
    return "regular", ""


def sample_typography(image_bytes: bytes, box: Dict, source: str = "") -> Dict:
    """원본 줄의 **굵기·정렬·색**을 잰다 — `{weight, align, color, stroke_ratio, reason}`.

    ## 왜 (오너 브리프 D3-4 ③)

    표지의 큰 제목은 **굵고 가운데** 있고, 스펙 줄은 **가늘고 왼쪽**에 있다. 전부 Regular
    가운데로 다시 그리면 **위계가 무너진다** — 골든 샘플 E축이 거기서 떨어졌다.

    ## 어떻게

    글자 픽셀(② 마스크)만 보고:

    | 것 | 재는 법 |
    |---|---|
    | 굵기 | 같은 글자를 **우리 폰트 두 굵기로 그려 보고** 가까운 쪽(`estimate_weight`) |
    | 정렬 | 박스 안 글자의 **좌·우 여백 비교** |
    | 색 | 글자 **속살**(배경과 가장 먼 픽셀)의 중앙값 — 가장자리 안티앨리어싱 제외 |

    못 재면 `reason`이 남고 값은 **기본값**(regular·center·먹)이다 —
    지어낸 값을 내지 않고, 무엇을 못 쟀는지 결과에 남긴다.
    """
    out = {"weight": "regular", "align": "center", "color": (26, 23, 20),
           "stroke_ratio": 0.0, "reason": ""}
    cv2, np, why = _load_cv2()
    if why:
        out["reason"] = why
        return out
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            out["reason"] = "이미지를 디코드하지 못했습니다"
            return out
        h, w = img.shape[:2]
        rect = _norm_box(box or {}, w, h)
        if rect is None:
            out["reason"] = "박스를 쓸 수 없습니다"
            return out
        mask, why = _glyph_mask(cv2, np, img, rect, 0)
        if mask is None:
            out["reason"] = why
            return out

        x1, y1, x2, y2 = rect
        roi, m = img[y1:y2, x1:x2], mask[y1:y2, x1:x2]
        ys, xs = np.nonzero(m)

        # 색 — 글자 **속살**만 본다. 가장자리는 배경과 섞여 있어 색을 흐린다.
        #   D3-6 ⑤: 기준은 박스 테두리가 아니라 **글자 바로 둘레**다. 알약 위 흰 글자는
        #   박스 테두리(페이지 흰색) 기준으론 「가장 먼 픽셀」이 알약 쪽 가장자리가 되어
        #   **파랑을 글자색으로** 재 버렸다(합성 ebvllh 캡처). 둘레 = 알약색이 기준이다.
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.int16)
        k_in, k_out = np.ones((3, 3), np.uint8), np.ones((9, 9), np.uint8)
        ring = cv2.dilate(m, k_out) & ~cv2.dilate(m, k_in)
        ref_px = gray[ring > 0]
        if ref_px.size == 0:
            ref_px = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
        d = np.abs(gray[ys, xs] - float(np.median(ref_px)))
        core = d >= np.percentile(d, 60)
        px = roi[ys[core], xs[core]]
        out["color"] = tuple(int(np.median(px[:, i])) for i in (2, 1, 0))   # BGR→RGB

        # 정렬 — 좌우 여백 비교. 여백이 한쪽으로 쏠려 있으면 그쪽 정렬이다.
        span = float(m.shape[1])
        left, right = float(xs.min()), span - 1 - float(xs.max())
        gap = (left - right) / span if span else 0.0
        out["align"] = ("left" if gap < -_ALIGN_TOL
                        else "right" if gap > _ALIGN_TOL else "center")

        # 굵기 — 같은 글자를 우리 폰트로 그려 보고 가까운 쪽(고정 임계값은 글자마다 틀렸다).
        ratio = _stroke_ratio(cv2, np, m)
        if ratio is None:
            out["reason"] = "획 두께를 재지 못했습니다"
            return out
        out["stroke_ratio"] = round(ratio, 4)
        gh = float(ys.max() - ys.min() + 1)
        out["weight"], why = estimate_weight(cv2, np, source, gh, ratio)
        if why:
            out["reason"] = why
        return out
    except Exception as exc:                                  # pragma: no cover
        logger.warning("[D3 렌더] 타이포 측정 실패(기본값 사용): %s", exc)
        out["reason"] = f"측정 오류: {type(exc).__name__}"
        return out


def glyph_regions(image_bytes: bytes, boxes: List[Dict], *, dilate_px: int = 3,
                  pad: int = 2) -> tuple:
    """박스마다 **글자 마스크의 외접 사각형**을 낸다 — `([(x,y,w,h)…], 사유들)` (D3-5 ①).

    오너 브리프: gen_remove의 영역은 **「글자 마스크 bbox」**다 — 텐센트 문단 박스가 아니다.
    문단 박스를 통째로 넘기면 그 안의 **알약·띠까지** 새로 그려 버린다(C축에서 본 그 사고).
    글자 픽셀만 둘러싼 사각형이면 새로 그리는 면적이 가장 작다.

    마스크를 못 뽑은 박스는 **빼고 사유를 남긴다**(telea와 같은 규율).
    """
    cv2, np, why = _load_cv2()
    if why:
        return [], [why]
    try:
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    except Exception as exc:                                   # pragma: no cover
        return [], [f"이미지를 디코드하지 못했습니다: {type(exc).__name__}"]
    if img is None:
        return [], ["이미지를 디코드하지 못했습니다"]
    h, w = img.shape[:2]
    rects, failures = [], []
    for b in boxes or []:
        rect = _norm_box(b, w, h)
        if rect is None:
            failures.append("박스를 쓸 수 없습니다")
            continue
        gm, why = _glyph_mask(cv2, np, img, rect, dilate_px)
        if gm is None:
            failures.append(why)
            continue
        ys, xs = np.nonzero(gm)
        x1, y1 = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
        x2, y2 = min(w, int(xs.max()) + 1 + pad), min(h, int(ys.max()) + 1 + pad)
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            rects.append((x1, y1, x2 - x1, y2 - y1))
    return rects, failures


# ─────────────────────────────────────────────────────────────────────────────
# D3-5 ② F축 「배경 복원」 — 지운 자리가 **주변과 닮았나**
# ─────────────────────────────────────────────────────────────────────────────
#
# 오너 정의: 「지운 영역 주변 16px 링과 내부의 색/텍스처 차이(평균색·분산 차)가 임계 이하면 1」.
#
# ## 어디를 재나 — **지운 픽셀 그 자체**
#
# 처음엔 박스 전체를 쟀다. 그러자 **telea·완벽 복원·아예 안 지운 것**이 같은 점수가 나왔다
# (실측): telea는 가는 획만 다시 칠하므로 박스의 75%가 원래 배경이고, 통계가 거기에 묻힌다.
# 그래서 「지운 영역」 = **원문 글자 마스크 픽셀**(지우기가 실제로 건드린 곳)로 잡고,
# 「주변 링」 = 그 마스크를 16px 부풀린 띠에서 마스크를 뺀 곳으로 잡는다.
#
# ## 어느 그림에서 재나 — **지운 결과**(한국어를 얹기 전)
#
# 얹은 한국어가 통계를 덮으면 복원이 아니라 글씨를 재게 된다. 그래서 D3만 잴 수 있다 —
# **텐센트는 지운 중간본을 주지 않는다**(F = 측정 불가, 사유 명시).
#
# ## 임계 — 합성 픽스처로 교정(2026-09-25)
#
# | 경우 | 평균색 차 | 결 비(지운 std ÷ 링 std) |
# |---|---|---|
# | 안 지움(글자 그대로) | **100 ~ 211** | 3 ~ 5 |
# | 완벽 복원(배경 그대로) | 0 ~ 10 | **0.84 ~ 1.13** |
# | telea — 굵은 획·사진 결 | 1 ~ 8 | **0.72 ~ 0.94** |
#
# 가는 획에선 telea도 결을 거의 지킨다(0.86~0.96) — **그땐 F가 telea를 떨어뜨리지 않는다.**
# 그게 맞다. F는 「telea면 0」이 아니라 「결을 잃었으면 0」이다.
#
# ⚠️ 교정은 **합성 이미지**로 했다. 실제 상품 사진에서 이 임계가 맞는지는 오너 벤치가 판정한다.
F_RING_PX = 16
F_MAX_MEAN_DIFF = 12.0
F_TEXTURED_RING_STD = 4.0          # 링이 이보다 거칠면 「결이 있는 배경」으로 본다
F_TEXTURE_RATIO = (0.82, 1.25)     # 지운 자리 결 ÷ 링 결 — 이 밖이면 결을 잃었거나 찌꺼기가 남았다
F_FLAT_MAX_STD = 4.0               # 민 배경인데 지운 자리가 이보다 거칠면 찌꺼기다
F_MIN_PIXELS = 30


def background_score(erased_bytes: bytes, source_bytes: bytes, boxes: List[Dict]) -> Dict:
    """F축 — `{score: 1|0|None, reason, hits:[박스별 수치]}` (D3-5 ②).

    `source_bytes`로 **원문 글자 마스크**(지운 자리)를 잡고, `erased_bytes`(한국어를 얹기 전)에서
    그 자리와 주변 링을 비교한다. 박스 하나라도 떨어지면 0 — 부분 통과를 통과로 읽지 않는다.
    """
    cv2, np, why = _load_cv2()
    if why:
        return {"score": None, "reason": why, "hits": []}
    try:
        src = cv2.imdecode(np.frombuffer(source_bytes, np.uint8), cv2.IMREAD_COLOR)
        out = cv2.imdecode(np.frombuffer(erased_bytes, np.uint8), cv2.IMREAD_COLOR)
    except Exception as exc:                                   # pragma: no cover
        return {"score": None, "reason": f"디코드 실패: {type(exc).__name__}", "hits": []}
    if src is None or out is None:
        return {"score": None, "reason": "이미지를 디코드하지 못했습니다", "hits": []}
    if src.shape[:2] != out.shape[:2]:
        # gen_remove가 크기를 바꿔 돌려주면(6140px 초과 시 축소·확대) 좌표가 어긋난다 — 재지 않는다.
        return {"score": None, "reason": (f"지운 결과 크기가 원본과 다릅니다 "
                                          f"{out.shape[1]}×{out.shape[0]} ≠ {src.shape[1]}×{src.shape[0]}"),
                "hits": []}
    h, w = src.shape[:2]
    outf = out.astype(np.float32)
    lum_w = np.array([0.114, 0.587, 0.299], np.float32)          # BGR 휘도
    k = np.ones((F_RING_PX * 2 + 1, F_RING_PX * 2 + 1), np.uint8)

    # D3-7(오너 2026-09-26): 알약 위 글자는 링 16px이 **알약 밖 흰 바탕**까지 걸쳐 F가 무효였다
    #   (잘 지워도·못 지워도 둘 다 0). 박스 안에 판(알약·띠)이 있으면 링을 **판 안쪽 중 지운 자리 밖**으로
    #   제한한다. 판이 없으면 종전 링 그대로(회귀 0). 판 판정은 `_plates` 한 자리(지우기와 같은 규칙).
    plates = [_plate_interior(cv2, np, src, _norm_box(b, w, h)) if _norm_box(b, w, h) else None
              for b in boxes or []]

    # 모든 지운 자리의 합집합 — 한 박스의 링이 **옆 박스의 지운 자리**를 먹지 않게.
    masks = []
    for b in boxes or []:
        rect = _norm_box(b, w, h)
        gm, _why = _glyph_mask(cv2, np, src, rect, 2) if rect else (None, "박스를 쓸 수 없습니다")
        masks.append(gm)
    union = np.zeros((h, w), np.uint8)
    for gm in masks:
        if gm is not None:
            union = cv2.bitwise_or(union, gm)

    hits, fails = [], []
    for b, gm, plate in zip(boxes or [], masks, plates):
        if gm is None:
            hits.append({"box": b, "score": None, "reason": "원문 글자 마스크를 못 뽑았습니다"})
            continue
        E = gm > 0
        ring = (cv2.dilate(gm, k) > 0) & (union == 0)
        ring_scope = "dilate"
        if plate is not None:
            ring = ring & (plate > 0)
            ring_scope = "plate"
        if int(E.sum()) < F_MIN_PIXELS or int(ring.sum()) < F_MIN_PIXELS:
            hits.append({"box": b, "score": None, "ring_scope": ring_scope,
                         "reason": "잴 픽셀이 너무 적습니다" + (" (판 안쪽 링)" if plate is not None else "")})
            continue
        e, r = outf[E], outf[ring]
        mean_d = float(np.linalg.norm(e.mean(0) - r.mean(0)))
        std_e, std_r = float((e @ lum_w).std()), float((r @ lum_w).std())
        textured = std_r >= F_TEXTURED_RING_STD
        ratio = std_e / std_r if std_r > 1e-6 else None
        ok = mean_d <= F_MAX_MEAN_DIFF and (
            (F_TEXTURE_RATIO[0] <= ratio <= F_TEXTURE_RATIO[1]) if textured
            else std_e <= F_FLAT_MAX_STD)
        why_box = ""
        if mean_d > F_MAX_MEAN_DIFF:
            why_box = f"색이 주변과 다릅니다(평균색 차 {mean_d:.1f} > {F_MAX_MEAN_DIFF:g})"
        elif textured and not (F_TEXTURE_RATIO[0] <= ratio <= F_TEXTURE_RATIO[1]):
            why_box = (f"결이 주변과 다릅니다(결 비 {ratio:.2f}, 허용 "
                       f"{F_TEXTURE_RATIO[0]:g}~{F_TEXTURE_RATIO[1]:g})")
        elif not textured and std_e > F_FLAT_MAX_STD:
            why_box = f"민 배경에 찌꺼기가 남았습니다(지운 자리 거칠기 {std_e:.1f})"
        hits.append({"box": b, "score": 1 if ok else 0, "reason": why_box, "ring_scope": ring_scope,
                     "mean_diff": round(mean_d, 2), "ratio": None if ratio is None else round(ratio, 3),
                     "ring_std": round(std_r, 2), "erased_std": round(std_e, 2)})
        if not ok:
            fails.append(why_box)

    measured = [x for x in hits if x["score"] in (0, 1)]
    if not measured:
        return {"score": None, "reason": "잴 수 있는 지운 자리가 없습니다", "hits": hits}
    if fails:
        return {"score": 0, "reason": fails[0], "hits": hits}
    return {"score": 1, "reason": "지운 자리가 주변과 닮았습니다", "hits": hits}


def erase_boxes(image_bytes: bytes, boxes: List[Dict], *, method: str = "telea",
                dilate_px: int = 2, glyph_only: bool = True) -> tuple:
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
        used, failures = 0, []
        for b in boxes:
            rect = _norm_box(b, w, h)
            if rect is None:
                continue
            if glyph_only:
                # ★ D3-4 ②: **글자 픽셀만** 지운다 — 박스를 통째로 지우면 배경 도형이 날아간다.
                gm, why = _glyph_mask(cv2, np, img, rect, dilate_px)
                if gm is None:
                    failures.append(why)
                    continue
                mask = cv2.bitwise_or(mask, gm)
            else:
                x1, y1, x2, y2 = rect
                mask[y1:y2, x1:x2] = 255
                if dilate_px > 0:
                    k = np.ones((dilate_px * 2 + 1, dilate_px * 2 + 1), np.uint8)
                    mask = cv2.dilate(mask, k, iterations=1)
            used += 1
        if not used:
            # ★★ 못 뽑으면 **이 장은 공급사 렌더를 쓴다** — 잘못 지우느니 안 건드린다.
            why = failures[0] if failures else "쓸 수 있는 박스가 없습니다(좌표가 이미지 밖이거나 0 크기)"
            return image_bytes, 0, f"글자 마스크 실패 → 이 장은 텐센트 렌더 사용: {why}"
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


def _overflows(plan: Dict, weight: str, box_w: int) -> bool:
    """이 배치로 그리면 **실제 잉크**가 박스 폭을 넘나 — 가장 넓은 줄을 가운데 놓고 잰다."""
    font = load_font(plan["size"], weight)
    if font is None:
        return False
    for line in plan["lines"]:
        l, _t, r, _b = font.getbbox(line)
        lw = r - l
        cx = (box_w - lw) // 2
        if cx + l < 0 or cx + r > box_w:
            return True
    return False


def draw_lines(image_bytes: bytes, lines: List[Dict], *, weight: str = "regular",
               color: Tuple[int, int, int] = (26, 23, 20)) -> tuple:
    """지워진 이미지 위에 한국어를 **앉힌다** — `(바이트, 그린 수, 건너뛴 것들)`.

    `lines` = `[{render_text, box}]`(2단계 산출).
    **못 앉힌 줄은 그리지 않고** `skipped`에 사유와 함께 남는다 — 조용히 빠뜨리지 않는다.

    ★ D3-4 ③ — 줄마다 `weight` · `color` · `align`이 있으면 **그걸 쓴다**(원본에서 잰 값).
    없으면 인자 기본값이다. 그래서 굵은 제목은 굵게, 왼쪽 스펙 줄은 왼쪽에 앉는다.
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
        # D3-6 ⑤ — 판이 있으면 판 안쪽(`draw_box`), 없으면 원문 박스.
        rect = _norm_box(ln.get("draw_box") or ln.get("box") or {}, img.width, img.height)
        if not text:
            skipped.append({"text": text, "reason": "그릴 글자가 없습니다"})
            continue
        if rect is None:
            skipped.append({"text": text, "reason": "박스를 쓸 수 없습니다"})
            continue
        x1, y1, x2, y2 = rect
        # ★ D3-4 ③ — 원본에서 잰 값이 있으면 그걸 쓴다.
        w_key = str(ln.get("weight") or weight).lower()
        if w_key not in ("regular", "bold"):
            w_key = weight
        fill = tuple(ln.get("color") or color)
        align = str(ln.get("align") or "center").lower()

        plan = fit_text(text, x2 - x1, y2 - y1, weight=w_key)
        # D3-6 ⑤(cphvcw 부제 넘침) — `fit_text`는 **글리프 폭**(bbox[2]-bbox[0])으로 재는데,
        #   실제로 그릴 땐 왼쪽 여백(bbox[0])까지 밀려 끝이 박스를 넘을 수 있다. 그리기 전에
        #   **그려질 자리 그대로** 재고, 넘으면 한 단계씩 줄인다. 줄였으면 가운데로 앉힌다.
        shrunk = False
        while plan is not None and _overflows(plan, w_key, x2 - x1):
            plan = fit_text(text, x2 - x1, y2 - y1, weight=w_key, max_px=plan["size"] - 1)
            shrunk = True
        if shrunk:
            align = "center"
        if plan is None:
            # ★ 억지로 그리지 않는다 — 삐져나온 글자는 상품 사진을 망친다.
            skipped.append({"text": text, "reason": f"박스에 안 들어갑니다({x2 - x1}×{y2 - y1}px)"})
            continue
        font = load_font(plan["size"], w_key)
        if font is None:
            skipped.append({"text": text, "reason": "폰트를 불러오지 못했습니다"})
            continue
        total_h = plan["line_h"] * len(plan["lines"])
        cy = y1 + ((y2 - y1) - total_h) // 2
        pad = plan["pad"]
        for i, line in enumerate(plan["lines"]):
            bbox = font.getbbox(line)
            lw = bbox[2] - bbox[0]
            room = (x2 - x1) - lw
            if align == "left":
                cx = x1 + min(pad, max(0, room))
            elif align == "right":
                cx = x1 + max(0, room - min(pad, max(0, room)))
            else:
                cx = x1 + room // 2
            draw.text((cx, cy + i * plan["line_h"]), line, font=font, fill=fill)
        drawn += 1

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), drawn, skipped


def small_text_reason(line: Dict, image_h: int) -> str:
    """박스가 **너무 작으면** 손대지 않는 사유 — 아니면 빈 문자열 (D3-6 ③)."""
    try:
        bh = float((line.get("box") or {}).get("h") or 0)
    except (TypeError, ValueError, AttributeError):
        return ""
    if image_h > 0 and 0 < bh < SMALL_TEXT_RATIO * image_h:
        return (f"소형 텍스트 — 박스 높이 {bh:.0f}px < 원본 높이의 1.5%"
                f"({SMALL_TEXT_RATIO * image_h:.0f}px): 손대지 않음")
    return ""


def _image_height(image_bytes: bytes) -> int:
    try:
        from PIL import Image
        return int(Image.open(io.BytesIO(image_bytes)).height)
    except Exception:
        return 0


def untouched_reason(line: Dict) -> str:
    """이 줄을 **건드리지 않는 이유** — 없으면 빈 문자열(= 칠한다). (D3-4 ①)

    ## 왜 필요했나 (골든 샘플 D축 실패, 오너 벤치 `bench-20260921-120314-m0-d3`)

    예전엔 `render_text`에 글자만 있으면 「그릴 게 있다」로 보고 **박스를 지운 뒤
    같은 글자를 우리 폰트로 다시 그렸다.** 시계 화면의 `12:30`이 우리 글꼴로 바뀌었다 —
    그건 번역이 아니라 **제품 사진을 고쳐 그린 것**이다.

    「미번역」은 세 가지 모양으로 온다. 셋 다 **건드리지 않는다**:

    | 모양 | 어디서 오나 |
    |---|---|
    | `action != "translate"` | 용어집 규칙 D(영문·숫자만) · 빈 줄 |
    | `translate_error` | 번역기 실패 → 원문을 남겼다 |
    | `render_text == source` | 번역기가 원문을 그대로 돌려줬다 |

    ★ 셋째가 없으면 첫째·둘째를 다 막아도 **같은 사고가 다시 난다** —
    「실패는 원문을 남긴다」가 곧 「그 줄은 원문 그대로 다시 그린다」가 되기 때문이다.
    """
    if not line.get("box"):
        return "박스가 없습니다"
    text = str(line.get("render_text") or "").strip()
    if not text:
        return "그릴 글자가 없습니다"
    if str(line.get("action") or "translate") != "translate":
        return str(line.get("rule_reason") or "") or "번역 대상이 아닙니다"
    if line.get("translate_error"):
        return f"번역 실패로 원문을 남겼습니다({line['translate_error']})"
    if text == str(line.get("source") or "").strip():
        return "번역 결과가 원문과 같습니다"
    return ""


def render(image_bytes: bytes, lines: List[Dict], *, method: str = "telea",
           weight: str = "regular", inherit_typography: bool = True) -> Dict:
    """3단계 전체 — 지우고 쓴다. `{ok, image_bytes, erased, drawn, skipped, error, …}`.

    **그릴 게 하나도 없으면 지우지도 않는다** — 멀쩡한 원본을 괜히 뭉개지 않기 위해서다.
    실패는 언제나 **원본 바이트**로 끝난다.

    ## `method="gen_remove"` (D3-5 ①) — 인페인터 2단

    1. 글자 마스크 외접 사각형을 **Cloudinary `e_gen_remove`**로 지운다(`image_gen_remove`).
    2. 안 되면 **telea로 폴백**하고, 그 사실을 `inpainter`·`inpaint_fallback`에 남긴다.

    ★ 폴백을 숨기면 「D3(gen_remove)」 칸에 **telea 결과가 gen_remove 이름으로** 올라간다 —
    그러면 F축 비교가 거짓이 된다. 그래서 결과는 **실제로 쓴 인페인터 이름**을 든다.
    청구(`cloud_tx`)도 폴백과 **따로** 적는다 — 지우기는 실패했어도 돈은 나갔을 수 있다.
    """
    paintable, untouched, drops = [], [], []
    image_h = _image_height(image_bytes)
    for ln in lines or []:
        # D3-6 ③ — 작은 글자는 **번역·지우기·그리기 전부** 안 한다(라인명 삭제도 포함).
        why = small_text_reason(ln, image_h)
        if why:
            untouched.append({"text": str(ln.get("source") or ""), "reason": why})
            continue
        if str(ln.get("action") or "") == "drop" and ln.get("box"):
            # D3-6 ①-b — **지우기만** 한다(그릴 글자 없음). 사유는 결과에 남긴다.
            drops.append(ln)
            untouched.append({"text": str(ln.get("source") or ""),
                              "reason": str(ln.get("rule_reason") or "지우기만 함")})
            continue
        why = untouched_reason(ln)
        if why:
            # ★ 조용히 빼지 않는다 — 안 건드린 줄도 **사유와 함께** 결과에 남는다.
            untouched.append({"text": str(ln.get("render_text") or ""), "reason": why})
        else:
            paintable.append(ln)

    if inherit_typography:
        # ★★ D3-4 ③ — **지우기 전에** 잰다. 지운 뒤엔 잴 글자가 없다.
        #    줄이 이미 값을 들고 있으면(호출부가 정했으면) 그걸 존중한다.
        measured = []
        for ln in paintable:
            row = dict(ln)
            if not (row.get("weight") and row.get("color") and row.get("align")):
                t = sample_typography(image_bytes, row.get("box") or {},
                                      str(row.get("source") or ""))
                row.setdefault("weight", t["weight"])
                row.setdefault("color", t["color"])
                row.setdefault("align", t["align"])
                row["typography"] = t
            measured.append(row)
        paintable = measured

    # D3-6 ⑤ — 판(알약) 위 글자는 **판 안쪽**에 앉힌다(지우기 박스는 그대로 원문 박스).
    placed = []
    for ln in paintable:
        row = dict(ln)
        if not row.get("draw_box"):
            pr = plate_rect(image_bytes, row.get("box") or {})
            if pr:
                row["draw_box"] = pr
        placed.append(row)
    paintable = placed

    if not paintable and not drops:
        return {"ok": False, "image_bytes": image_bytes, "erased": 0, "drawn": 0,
                "skipped": untouched, "error": "그릴 줄이 없습니다(원본 그대로)"}

    # 지우는 박스 = 그릴 줄 + 지우기만 할 줄(라인명). 그리는 건 `paintable`뿐이다.
    boxes = [ln["box"] for ln in paintable] + [ln["box"] for ln in drops]
    inpainter, fallback, cloud = str(method or "telea").lower(), "", {"tx": 0, "credits": 0.0}
    erased_bytes, erased, why = image_bytes, 0, ""

    if inpainter == "gen_remove":
        from src.services import image_gen_remove as G
        can, why_cfg = G.configured()
        rects, rect_fail = glyph_regions(image_bytes, boxes) if can else ([], [])
        if not can:
            fallback = why_cfg
        elif not rects:
            fallback = ("글자 마스크 영역이 없습니다: " +
                        (rect_fail[0] if rect_fail else "사유 불명"))
        else:
            g = G.gen_remove(image_bytes, rects)
            cloud = {"tx": g.get("tx"), "credits": g.get("credits")}
            if g.get("ok"):
                erased_bytes, erased = g["image_bytes"], len(rects)
            else:
                fallback = g.get("error") or "gen_remove 실패(사유 불명)"
        if fallback:
            # ★ 폴백 — 이름을 **바꿔서** 적는다. 숨기면 F축 비교가 거짓이 된다.
            logger.info("[D3 렌더] gen_remove → telea 폴백: %s", fallback)
            inpainter = "telea"

    if inpainter != "gen_remove":
        erased_bytes, erased, why = erase_boxes(
            image_bytes, boxes, method=("ns" if inpainter == "ns" else "telea"))
    if why:
        return {"ok": False, "image_bytes": image_bytes, "erased": 0, "drawn": 0,
                "skipped": untouched, "error": why, "inpainter": inpainter,
                "inpaint_fallback": fallback, "cloud_tx": cloud["tx"],
                "cloud_credits": cloud["credits"]}

    out, drawn, skipped = draw_lines(erased_bytes, paintable, weight=weight)
    return {
        # 라인명만 지운 장도 **결과가 있는 장**이다(그릴 줄이 0이어도 지운 것이 산출물).
        "ok": drawn > 0 or (bool(drops) and erased > 0),
        "dropped": len(drops),
        "image_bytes": out,
        "erased": erased,
        "drawn": drawn,
        "skipped": untouched + list(skipped),
        # ★ 잰 타이포를 결과에 남긴다 — 벤치 표가 「왜 굵게 그렸나」를 보여 줄 수 있어야 한다.
        "typography": [r.get("typography") for r in paintable if r.get("typography")],
        # D3-5 ① — **실제로 쓴** 인페인터와 폴백 사유, 그리고 청구(폴백과 따로).
        "inpainter": inpainter,
        "inpaint_fallback": fallback,
        "cloud_tx": cloud["tx"],
        "cloud_credits": cloud["credits"],
        # D3-5 ② F축은 **지운 자리**를 잰다 — 어느 박스를 지웠는지와 **지운 결과**를 넘긴다.
        #   ★ `erased_bytes`는 잰 뒤 버린다(벤치 저장소·실행 기록에 싣지 않는다).
        "painted_boxes": boxes,
        "erased_bytes": erased_bytes,
        "error": "" if (drawn or (drops and erased)) else "한 줄도 앉히지 못했습니다",
    }
