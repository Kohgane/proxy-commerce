"""Z7(오너 2026-10-08) — 글자 판정 OCR = **텐센트 OCR API**(`GeneralBasicOCR`, ocr 2018-11-19).

왜: 서버 로컬 OCR(RapidOCR = PP-OCR 모델 + onnxruntime)이 **요청 프로세스 안에서** 모델을 올리고 원본 해상도로 돌았다.
실측(워커 1개, 이 컨테이너): 앱 로드 81MB → 대표 사진 1장 판정 뒤 피크 **582MB**(1500px) · 312MB(800px).
RapidOCR 단독: 모델 로드 115MB, 추론 피크 232MB(800px)·315MB(1024px)·498MB(1500px)·677MB(1920px).
Render 512MB에서 「Ran out of memory」로 인스턴스가 죽고 사전검증은 502 — 2026-10-08 13:30·13:33·15:19 KST.

이제 로컬 ML 모델을 프로세스에 올리지 않는다. 이미지 번역에 이미 쓰는 텐센트 계정·키(`TENCENT_SECRET_ID/KEY`,
`TENCENT_REGION`)를 재사용한다. 새 SDK 패키지는 들이지 않는다 — 공통 SDK의 `CommonClient`로 부른다.

입력: 긴 변 1024px로 줄인 JPEG(base64). 응답 `TextDetections[].DetectedText/Confidence(0~100)`.
실패(키 없음·네트워크·공급사 오류)는 `{"ok": False, "code": "ocr_unavailable", "why": …}` — 판정을 **건너뛴다**(막지 않는다).
"""
from __future__ import annotations

import base64
import io
import logging
import os
import time
from typing import Dict

logger = logging.getLogger(__name__)

SERVICE, VERSION, ACTION = "ocr", "2018-11-19", "GeneralBasicOCR"
#: 문서 권장 도메인(가까운 지역으로 자동 연결). `TENCENT_OCR_ENDPOINT`로 바꿀 수 있다.
DEFAULT_ENDPOINT = "ocr.tencentcloudapi.com"
MAX_SIDE = 1024
#: 확신(0~100) 이 값 미만 조각은 버린다 — 예전 로컬 판정 0.5와 같은 선.
MIN_CONFIDENCE = 50
CODE_UNAVAILABLE = "ocr_unavailable"


def endpoint() -> str:
    return os.getenv("TENCENT_OCR_ENDPOINT", "").strip() or DEFAULT_ENDPOINT


def timeout_sec() -> int:
    try:
        return max(1, int(os.getenv("TENCENT_OCR_TIMEOUT_SEC", "8") or 8))
    except ValueError:
        return 8


def is_configured() -> bool:
    from src.services.image_translate_tencent import is_configured as _ok
    return _ok()


def shrink(raw: bytes, max_side: int = MAX_SIDE) -> bytes:
    """긴 변 `max_side`px JPEG로 — 보내는 바이트·디코딩 메모리를 줄인다. 못 열면 예외."""
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
        im.draft("RGB", (max_side, max_side))            # JPEG는 디코딩 단계에서 미리 줄인다(메모리 절약)
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85)
    return out.getvalue()


def _unavailable(why: str) -> Dict:
    return {"ok": False, "code": CODE_UNAVAILABLE, "why": why, "lines": [], "text": ""}


def _call(b64: str) -> dict:
    """공급사 호출 한 번 — 응답 `Response` 본문(dict). 테스트는 이 함수를 바꿔 끼운다."""
    from tencentcloud.common import credential
    from tencentcloud.common.common_client import CommonClient
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from src.services.image_translate_tencent import _secret, region
    sid, skey = _secret()
    prof = ClientProfile(httpProfile=HttpProfile(endpoint=endpoint(), reqTimeout=timeout_sec()))
    client = CommonClient(SERVICE, VERSION, credential.Credential(sid, skey), region(), profile=prof)
    resp = client.call_json(ACTION, {"ImageBase64": b64, "LanguageType": "auto"})
    return (resp or {}).get("Response") or {}


def read(raw: bytes) -> Dict:
    """이미지 바이트 → `{ok, lines: [(글자, 확신)], text, code, why}`. 확신 50 미만 조각은 뺀다."""
    if not raw:
        return _unavailable("이미지 바이트 없음")
    if not is_configured():
        return _unavailable("텐센트 키 미설정")
    try:
        small = shrink(raw)
    except Exception as exc:                                # noqa: BLE001 — 깨진 바이트
        return _unavailable(f"이미지를 열지 못했어요({type(exc).__name__})")
    t0 = time.monotonic()
    try:
        body = _call(base64.b64encode(small).decode("ascii"))
    except Exception as exc:                                # noqa: BLE001 — 키·네트워크·공급사 오류 전부 「확인 못 함」
        code = getattr(exc, "code", "") or type(exc).__name__
        msg = str(getattr(exc, "message", "") or exc)[:80]
        logger.warning("[텐센트 OCR] 호출 실패 %s: %s (%dms)", code, msg, int((time.monotonic() - t0) * 1000))
        return _unavailable(f"텐센트 OCR 실패({code})")
    lines = []
    for d in body.get("TextDetections") or []:
        txt = str((d or {}).get("DetectedText") or "").strip()
        try:
            conf = float((d or {}).get("Confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if txt and conf >= MIN_CONFIDENCE:
            lines.append((txt, conf))
    logger.info("[텐센트 OCR] %d조각 %dms req=%s", len(lines), int((time.monotonic() - t0) * 1000),
                str(body.get("RequestId") or "")[:36])
    return {"ok": True, "code": "", "why": "", "lines": lines, "text": " ".join(t for t, _ in lines)}
