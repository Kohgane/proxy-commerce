"""Z3-2(오너 2026-10-04) — 유료 이미지 번역 **전에** 서버 로컬 OCR(무료)로 「이 사진에 한자가 있나」.

엔진: RapidOCR(PaddleOCR PP-OCR 검출+인식 모델을 onnxruntime으로 — CPU, 모델 동봉, 키·네트워크 0).
판정: 인식 글자에 한자(CJK 통합)가 한 글자라도 있으면 「있음」. 확신 점수 0.5 미만 조각은 버린다.

돌려주는 값은 셋 — `True`(한자 있음 → 텐센트로) · `False`(없음 → 원본 유지, 텐센트 안 부름) · `None`(모름 →
**예전처럼 텐센트로**: 엔진 미설치·이미지 못 읽음·오류). 모를 때 「없음」으로 치면 한자가 남은 사진이 그대로 나간다.

`IMAGE_OCR_PRECHECK=0`이면 끈다(전부 None).
"""
from __future__ import annotations

import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

_HAN = re.compile("[㐀-䶿一-鿿]")
_ENGINE = {"obj": None, "tried": False, "lock": threading.Lock(), "err": ""}
MIN_SCORE = 0.5


def enabled() -> bool:
    return str(os.getenv("IMAGE_OCR_PRECHECK", "1")).strip() != "0"


def engine():
    """RapidOCR 한 벌(프로세스당) — 없으면 None(이유는 `engine_error()`)."""
    with _ENGINE["lock"]:
        if not _ENGINE["tried"]:
            _ENGINE["tried"] = True
            try:
                from rapidocr_onnxruntime import RapidOCR
                _ENGINE["obj"] = RapidOCR()
            except Exception as exc:                       # noqa: BLE001 — 미설치·모델 로드 실패
                _ENGINE["err"] = f"{type(exc).__name__}: {str(exc)[:120]}"
                logger.warning("[OCR 사전판정] 엔진 없음 — 텐센트로 그대로 보냅니다(%s)", _ENGINE["err"])
        return _ENGINE["obj"]


def engine_error() -> str:
    return _ENGINE["err"]


def han_text(raw: bytes) -> tuple:
    """`(판정, 읽은 글자 앞 40자)` — 판정은 True/False/None."""
    if not enabled() or not raw:
        return None, ""
    eng = engine()
    if eng is None:
        return None, ""
    try:
        res, _ = eng(raw)
    except Exception as exc:                               # noqa: BLE001
        logger.warning("[OCR 사전판정] 읽기 실패 — 텐센트로(%s: %s)", type(exc).__name__, str(exc)[:80])
        return None, ""
    txt = "".join(str(r[1]) for r in (res or []) if len(r) > 2 and float(r[2] or 0) >= MIN_SCORE)
    return bool(_HAN.search(txt)), txt[:40]


def has_han(raw: bytes):
    return han_text(raw)[0]


def all_text(raw: bytes) -> tuple:
    """Y7: `(글자 있음?, 읽은 글자 앞 40자)` — 한자만이 아니라 **아무 글자**(영문 워터마크 「INTERSTELLAR」 포함).

    확신 0.5 이상 조각을 이어 공백 빼고 두 글자 이상이면 「있음」. 엔진 없음·못 읽음·꺼짐이면 `(None, "")`.
    `IMAGE_OCR_PRECHECK=0`(텐센트 사전판정 끄기)과는 따로 켠다 — 대표 사진 판정은 `COUPANG_IMAGE_CHECK`가 쥔다.
    """
    if not raw:
        return None, ""
    eng = engine()
    if eng is None:
        return None, ""
    try:
        res, _ = eng(raw)
    except Exception as exc:                               # noqa: BLE001
        logger.warning("[OCR 글자 판정] 읽기 실패: %s: %s", type(exc).__name__, str(exc)[:80])
        return None, ""
    txt = " ".join(str(r[1]) for r in (res or []) if len(r) > 2 and float(r[2] or 0) >= MIN_SCORE)
    return len(re.sub(r"\s+", "", txt)) >= 2, txt[:40]
