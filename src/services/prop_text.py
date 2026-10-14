"""Y11-G(오너 2026-10-14) — 소품 글자는 글자가 아니다.

소품(책등·책 표지·스피커 로고·포장·배경 간판)에 찍힌 글자는 **어디서도 글자로 다루지 않는다** — 경고 없음 · 상자 없음 ·
번역 대상 아님. 상표 토큰이 걸려도 차단·주의가 아니라 위험 목록에 「참고: 소품(책 표지)에 'Zaha Hadid'」 한 줄뿐.

상자 하나가 소품 글자 = 면적 < 0.5% **그리고** (기울기 ≥ 20° 또는 OCR 확신 < 70 또는 사진 전체가 180°·90° 돌린 틀).
사진 전체 회전 판정이 180°/90°이면(글자가 거꾸로·옆으로 = 소품) 그 사진의 상자는 **전부** 소품이다.

⚠️ 오너 규칙의 「번역본에서 원본과 픽셀 차이가 상자 밖으로 안 번짐」은 **넣지 않았다** — 운영 실측(VRSUK 대표사진 쿠폰 ·
갤러리 3 책등)에서 상자 둘레의 차이가 쿠폰 2.6~28.9 · 책등 13.3~38.1(/255)로 갈리지 않았다. 넣으면 진짜 쿠폰 글자
(「이탈리아 브랜드」 0.44% · 둘레 2.6)가 소품으로 숨는다. 회전 틀 판정(box_frame)이 그 몫을 한다.

반례(오너): 상품 자체가 책·포스터·간판이면 그 글자는 소품이 아니다 — 카테고리가 도서·문구·인테리어 소품(액자·포스터)이면 규칙을 끈다.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

#: 상자 면적 상한(사진 대비) — 이보다 작아야 소품 후보
MAX_AREA = 0.005
#: 기울기(도) — 이 이상 기울었으면(거꾸로 포함) 소품 후보
MIN_TILT = 20.0
#: OCR 확신 — 이보다 낮으면 소품 후보
MIN_CONF = 70.0
ROTATED_FRAMES = ("rot180", "rot90a", "rot90b")

#: 상품 자체가 글자를 파는 물건 — 소품 규칙을 끈다(도서·문구·액자·포스터·간판). 「노트」는 「노트북 거치대」와 겹쳐 안 쓴다
_EXEMPT_RE = re.compile(r"도서|서적|그림책|만화책|소설책|화보집|포스터|액자|간판|사인보드|문구류|필기구|다이어리|"
                        r"\bbook\b|\bbooks\b|poster|picture frame|signage|stationery|图书|书籍|海报|画框|装饰画|招牌|文具")


def exempt(extra: Optional[dict] = None, *, title: str = "") -> bool:
    """이 상품은 소품 규칙을 끈다(상품이 곧 글자) — 정규화 카테고리 OFC(사무/문구) · 카테고리 경로·상품명에 도서·포스터·액자·간판·문구."""
    ex = extra or {}
    if str(ex.get("category_code") or "").upper() == "OFC":
        return True
    hay = " ".join(str(x or "") for x in (title, ex.get("title_ko"), ex.get("title"), ex.get("category"),
                                          ex.get("naver_category_name"), ex.get("coupang_category_name")))
    return bool(_EXEMPT_RE.search(hay))


def tilt_of(polygon) -> Optional[float]:
    """네 꼭짓점의 첫 변(왼위→오른위) 기울기(도, 0~180) — 거꾸로 놓인 글자는 180 근처. 모양이 아니면 None."""
    try:
        p0, p1 = polygon[0], polygon[1]
        dx, dy = float(p1.get("X")) - float(p0.get("X")), float(p1.get("Y")) - float(p0.get("Y"))
    except (TypeError, ValueError, AttributeError, IndexError, KeyError):
        return None
    if dx == 0 and dy == 0:
        return None
    return round(abs(math.degrees(math.atan2(dy, dx))), 1)


def is_prop(box: Dict, size, *, frame: str = "") -> bool:
    """상자 하나 — 소품 글자인가. `size` = 상자 좌표 공간(W, H) · `frame` = 사진 회전 틀(box_frame)."""
    W, H = (size or [0, 0])[:2]
    if frame in ROTATED_FRAMES:
        return True
    if not (W and H):
        return False
    if _watermark_word(str(box.get("src") or "")):
        return False                                             # Y11-D 반례 유지: 작은 워터마크·로고 낱말(www·tmall·official…)은 진짜 반려 사유
    area = max(0, int(box.get("w") or 0)) * max(0, int(box.get("h") or 0)) / float(W * H)
    if area >= MAX_AREA:
        return False
    tilt = box.get("tilt")
    if tilt is not None and min(float(tilt), 360 - float(tilt)) >= MIN_TILT:
        return True
    conf = box.get("conf")
    return conf is not None and float(conf) < MIN_CONF


def _watermark_word(text: str) -> str:
    """상품 사진·워터마크 낱말(사전) · 쿠팡 브랜드 목록에 있는 영숫자 3자 이상 낱말 — 상표 위험 토큰(risk_tokens)은 여기 넣지 않는다
    (오너 Y11-G: 소품에 찍힌 상표는 「참고」만)."""
    try:
        from src.services.coupang_image_check import _ALNUM_RUN, _known_words
        words = _known_words()
        return next((r for r in _ALNUM_RUN.findall(text or "") if r.lower() in words), "")
    except Exception:                                             # noqa: BLE001
        return ""


def mark(boxes: List[Dict], size, *, frame: str = "", off: bool = False) -> List[Dict]:
    """상자마다 `prop` 표시(제자리) — `off`(카테고리 반례)면 전부 False."""
    for b in boxes or []:
        b["prop"] = bool(not off and is_prop(b, size, frame=frame))
    return boxes


def split(boxes: List[Dict]):
    """`(글자 상자, 소품 상자)`."""
    return [b for b in boxes or [] if not b.get("prop")], [b for b in boxes or [] if b.get("prop")]


def note_line(name: str, where: str = "") -> str:
    """「참고: 소품(사진 4)에 'Zaha Hadid'」 — 차단·주의가 아니다(오너: 책 표지는 괜찮다)."""
    return f"참고: 소품({where or '책 표지'})에 '{name}'"
