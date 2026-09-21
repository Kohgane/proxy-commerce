"""src/services/image_render_font.py — D3 3단계가 쓸 **한국어 렌더 폰트**.

## 왜 파일로 들고 있나

3단계는 박스를 지우고(inpaint) 그 자리에 **한국어를 그린다**. 그리려면 한글 글리프가
든 폰트가 **런타임 이미지 안에** 있어야 한다. 빌드할 때 인터넷에서 받아 오면
네트워크가 흔들리는 날 배포가 깨지고, 시스템 폰트에 기대면 base 이미지가 바뀌는 날
**글자가 두부(□□□)로 나간다.** 그래서 레포에 박아 두고 이미지로 COPY한다.

## 무엇을 들고 있나 (실측 2026-09-20)

| 것 | 값 |
|---|---|
| 파일 | `assets/fonts/NotoSansKR-VF.ttf` — 10,414,588 바이트 |
| 출처 | google/fonts `ofl/notosanskr/NotoSansKR[wght].ttf` (OFL, `assets/fonts/OFL.txt`) |
| 굵기 | 가변축 `wght` 100–900 — 이름 인스턴스 9종(Thin…Black) |
| 서브셋 | **아님.** 한글 음절 전부(`뷁`·`힣` 포함) + 라틴 |

> 오너 지시는 「Regular·Bold 2웨이트」였다. **정적 2파일은 더 이상 배포되지 않는다**
> (google/fonts에서 `static/NotoSansKR-Regular.ttf` → **404 실측**). 그래서 가변 폰트
> 한 장에서 **그 두 인스턴스를 꺼내 쓴다** — 받는 굵기는 같고, 파일은 10MB 하나다.

## ★★ 기본 인스턴스가 Thin이다

`ImageFont.truetype()`만 하면 **Thin(100)**이 나온다 — 상품 사진에 실오라기 같은
글씨가 박힌다. 그래서 이 모듈은 **언제나 인스턴스를 지정**하고, 지정을 빠뜨릴 수 있는
경로를 아예 만들지 않는다(`load()`의 `weight` 인자에 기본값이 있고, 그 기본이 Regular다).

아직 파이프라인에 연결하지 않는다 — 골든 샘플 5축 통과 전에는 텐센트 경로가 그대로다.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 배포 이미지에선 `/app/assets/fonts`, 개발에선 레포 루트 기준. 둘 다 이 계산으로 맞는다.
_ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = Path(os.getenv("IMAGE_RENDER_FONT_DIR") or (_ROOT / "assets" / "fonts"))
FONT_FILE = "NotoSansKR-VF.ttf"

# 우리가 쓰는 두 굵기 — 본문/강조. 이름은 폰트의 **이름 인스턴스**와 글자까지 같아야 한다.
WEIGHTS = {"regular": b"Regular", "bold": b"Bold"}


def font_path() -> Path:
    """폰트 파일 경로. 존재 여부는 `available()`로 따로 묻는다."""
    return FONT_DIR / FONT_FILE


def available() -> tuple:
    """`(있나, 사유)` — 없으면 **사유가 남는다**.

    F43에서 배운 것: 없는 걸 조용히 넘기면 **기능이 죽어도 아무도 모른다.**
    """
    p = font_path()
    if not p.is_file():
        return False, f"렌더 폰트가 없습니다: {p}"
    return True, ""


def load(size: int, weight: str = "regular"):
    """`PIL.ImageFont` — **인스턴스를 반드시 지정해서** 돌려준다.

    지정하지 않으면 가변 폰트의 기본값인 **Thin**이 나온다(위 ★★).
    폰트가 없거나 Pillow가 없으면 `None`이고, 사유는 WARNING으로 남는다 —
    **조용히 다른 폰트로 대체하지 않는다.** 엉뚱한 폰트로 그리면 그건 다른 상품이다.
    """
    ok, why = available()
    if not ok:
        logger.warning("[D3 렌더] %s", why)
        return None
    key = str(weight or "regular").lower()
    if key not in WEIGHTS:
        raise ValueError(f"지원하지 않는 굵기입니다: {weight} (가능: {sorted(WEIGHTS)})")
    try:
        from PIL import ImageFont
    except ImportError as exc:
        logger.warning("[D3 렌더] Pillow 미설치 — 글자를 그릴 수 없습니다 (%s)", exc)
        return None
    f = ImageFont.truetype(str(font_path()), int(size))
    f.set_variation_by_name(WEIGHTS[key])
    return f


_PROBE_SIZE = 40
_PROBE_MISSING = ""      # 사설 사용 영역 — **어떤 폰트에도 없다**(두부 기준선)
_supported_cache: dict = {}


def _glyph_bits(ch: str, font) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("L", (_PROBE_SIZE + 24, _PROBE_SIZE + 24), 255)
    ImageDraw.Draw(img).text((8, 4), ch, font=font, fill=0)
    return img.tobytes()


def supported(text: str) -> str:
    """이 폰트가 **실제로 그릴 수 있는** 글자만 남긴다.

    ## 왜 필요한가 (실측 2026-09-21)

    `NotoSansKR-VF`엔 한글·라틴·상용 한자가 있지만 **간체자 일부가 없다** —
    `绝` · `轻` · `纳` · `线` · `电`은 **두부(□)**로 그려진다.

    그린 그림이 두부여도 `getbbox()`는 **멀쩡한 숫자**를 돌려준다. 그래서 폭·굵기를
    그걸로 재면 **두부를 글자로 재게 된다.** 픽셀로 확인한다.

    (렌더 자체는 한국어라 영향이 없다. 이 함수가 필요한 곳은 **원문 글자를 기준선으로
    그려 보는 자리**다 — D3-4 ③ `estimate_weight`.)
    """
    text = str(text or "")
    if not text:
        return ""
    if not available()[0]:
        return ""
    try:
        font = load(_PROBE_SIZE, "regular")
        if font is None:
            return ""
        if "\x00tofu" not in _supported_cache:
            _supported_cache["\x00tofu"] = _glyph_bits(_PROBE_MISSING, font)
        tofu = _supported_cache["\x00tofu"]
        out = []
        for ch in text:
            if ch not in _supported_cache:
                _supported_cache[ch] = _glyph_bits(ch, font)
            if _supported_cache[ch] != tofu:
                out.append(ch)
        return "".join(out)
    except Exception as exc:                                  # pragma: no cover
        logger.warning("[D3 렌더] 글자 지원 확인 실패: %s", exc)
        return ""


def text_width(text: str, size: int, weight: str = "regular") -> Optional[int]:
    """그 굵기·크기로 그렸을 때의 **가로 폭**(px). 폰트가 없으면 `None`.

    3단계의 「폭맞춤」이 이 값을 본다 — 박스보다 넓으면 크기를 줄이거나 줄을 나눈다.
    """
    f = load(size, weight)
    if f is None:
        return None
    box = f.getbbox(str(text or ""))
    return int(box[2] - box[0])
