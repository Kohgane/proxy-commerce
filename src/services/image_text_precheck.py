"""Z3-2(오너 2026-10-04) → Z7(2026-10-08): 「이 사진에 글자/한자가 있나」 판정.

엔진: **텐센트 OCR API**(`ocr_tencent` — 이미지 번역과 같은 계정·키). 예전엔 서버 로컬 RapidOCR(PP-OCR 모델 +
onnxruntime)이었는데, 요청 프로세스 안에서 모델을 올리고 원본 해상도로 돌아 Render 512MB를 넘겼다(Z7 실측은
`ocr_tencent` 머리말). 이제 어떤 경로도 프로세스 안에서 로컬 ML 모델을 올리지 않는다.

판정: 읽은 글자(확신 50 이상)에 한자(CJK 통합)가 한 글자라도 있으면 「있음」.

돌려주는 값은 셋 — `True`(한자 있음 → 이미지 번역으로) · `False`(없음 → 원본 유지) · `None`(모름 → **예전처럼
번역으로 보냄**: 키 없음·이미지 못 읽음·OCR 실패 = 사유코드 `ocr_unavailable`). 모를 때 「없음」으로 치면 한자가 남은
사진이 그대로 나간다.

`IMAGE_OCR_PRECHECK=0`이면 이미지 번역 사전판정을 끈다(전부 None).
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_HAN = re.compile("[㐀-䶿一-鿿]")
_LATIN = re.compile("[A-Za-z]")
#: Y11-H(오너 2026-10-14 VRSUK 상세 3·6·7): 한자 문장이 크게 있는데 「한자 0」 — 읽은 글자는 라틴만(「Disponibile Subito…」).
#   ① 사전검사는 **줄이지 않는다** — 상세 사진은 790×5000처럼 세로로 길어, 긴 변 1024(Z10-B 공통 축소)면 가로가 162px로
#   한자 획이 뭉개진다. 텐센트 번역에 보내는 바로 그 바이트(긴 변 ≤4096 · ≤4MB)를 그대로 OCR에 보낸다(풀지도 않음 — 메모리 0).
#   `IMAGE_OCR_PRECHECK_SIDE=1600` 같은 숫자를 주면 그 긴 변으로 줄인다(1600 미만은 받지 않음).
#   인식 언어 zh(중영 혼합 — auto는 라틴이 많은 사진을 라틴으로 읽을 수 있다).
#   ② 그래도 「한자 0」인데 라틴 글자가 있으면 **건너뛰지 않는다**(모름 → 번역으로) — PictureWithoutText 1건 값이 중국어
#   배너가 그대로 나가는 것보다 싸다. 「한자 0 그리고 라틴도 거의 없음」일 때만 건너뛴다.
PRECHECK_MIN_SIDE = 1600


def precheck_side() -> int:
    from src.services.ocr_tencent import AS_IS
    try:
        v = int(os.getenv("IMAGE_OCR_PRECHECK_SIDE", "") or 0)
    except ValueError:
        v = 0
    return max(v, PRECHECK_MIN_SIDE) if v > 0 else AS_IS



PRECHECK_LANG = os.getenv("IMAGE_OCR_PRECHECK_LANG", "zh") or "zh"
LATIN_MIN = int(os.getenv("IMAGE_OCR_PRECHECK_LATIN_MIN", "6") or 6)
_LAST = {"why": ""}


def enabled() -> bool:
    return str(os.getenv("IMAGE_OCR_PRECHECK", "1")).strip() != "0"


def engine():
    """판정 엔진을 쓸 수 있나(텐센트 키) — 진단 화면용. 없으면 None(이유는 `engine_error()`)."""
    from src.services import ocr_tencent
    return "tencent-ocr" if ocr_tencent.is_configured() else None


def engine_error() -> str:
    from src.services import ocr_tencent
    return "" if ocr_tencent.is_configured() else "텐센트 키 미설정(TENCENT_SECRET_ID/KEY)"


def last_unavailable() -> str:
    """마지막 「확인 못 함」 사유(진단·화면 한 줄용)."""
    return _LAST["why"]


def _read(raw: bytes, **kw):
    """`(조각 목록 | None, 사유)` — None이면 판정 못 함(ocr_unavailable)."""
    from src.services import ocr_tencent
    res = ocr_tencent.read(raw, **kw)
    if not res.get("ok"):
        _LAST["why"] = res.get("why") or ""
        return None, res.get("why") or ""
    return [t for t, _c in res.get("lines") or []], ""


def han_text(raw: bytes) -> tuple:
    """`(판정, 읽은 글자 앞 40자)` — 판정은 True/False/None."""
    if not enabled() or not raw:
        return None, ""
    parts, _why = _read(raw, max_side=precheck_side(), lang=PRECHECK_LANG)
    if parts is None:
        return None, ""
    txt = "".join(parts)
    if _HAN.search(txt):
        return True, txt[:40]
    if len(_LATIN.findall(txt)) >= LATIN_MIN:
        return None, txt[:40]                       # Y11-H: 라틴 글자가 있다 — 한자를 놓쳤을 수 있어 「모름」(번역으로 보냄)
    return False, txt[:40]


def has_han(raw: bytes):
    return han_text(raw)[0]


def all_text(raw: bytes) -> tuple:
    """Y7: `(글자 있음?, 읽은 글자 앞 40자)` — 한자만이 아니라 **아무 글자**(영문 워터마크 「INTERSTELLAR」 포함).

    조각을 이어 공백 빼고 두 글자 이상이면 「있음」. 못 읽음·OCR 실패면 `(None, "")`(= ocr_unavailable).
    `IMAGE_OCR_PRECHECK=0`(이미지 번역 사전판정 끄기)과는 따로 켠다 — 대표 사진 판정은 `COUPANG_IMAGE_CHECK`가 쥔다.
    """
    if not raw:
        return None, ""
    parts, _why = _read(raw)
    if parts is None:
        return None, ""
    txt = " ".join(parts)
    return len(re.sub(r"\s+", "", txt)) >= 2, txt[:40]
