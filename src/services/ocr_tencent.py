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
import threading
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


# Y11-B(오너 2026-10-14 실측): `FailedOperation.UnOpenError` = 텐센트 계정에 **OCR(文字识别) 서비스가 미개통**.
#   키·네트워크는 멀쩡하다(이미지 번역은 같은 키로 된다) — 고칠 곳은 텐센트 콘솔이다. 사람 말로 그렇게 말하고,
#   개통 전에는 매 장 다시 부르지 않는다(UNOPEN_HOLD_SEC 동안 「미개통」으로 기억 — 헛호출·로그 소음 0).
UNOPEN_CODE = "FailedOperation.UnOpenError"
UNOPEN_WHY = "글자 상자 읽기(OCR) 서비스가 텐센트 계정에 아직 개통되지 않았어요 — 텐센트 콘솔 「文字识别(OCR)」에서 개통이 필요해요"
UNOPEN_HOLD_SEC = 3600
_UNOPEN_AT = [0.0]


def unopened() -> bool:
    """최근 한 시간 안에 「미개통」 답을 받았나 — 그동안은 부르지 않는다."""
    return bool(_UNOPEN_AT[0]) and time.monotonic() - _UNOPEN_AT[0] < UNOPEN_HOLD_SEC


#: Y11-G(오너 2026-10-14): 「글자를 못 찾았다」는 실패가 아니라 **글자 없음**이다 — 화면에 코드 원문을 안 보인다.
NO_TEXT_CODES = ("FailedOperation.ImageNoText",)
NO_TEXT_LABEL = "글자 없음(OCR)"


def no_text(exc) -> bool:
    return str(getattr(exc, "code", "") or "") in NO_TEXT_CODES


def _fail_why(exc) -> str:
    code = getattr(exc, "code", "") or type(exc).__name__
    if str(code) in NO_TEXT_CODES:
        return NO_TEXT_LABEL
    if str(code) == UNOPEN_CODE:
        _UNOPEN_AT[0] = time.monotonic()
        return UNOPEN_WHY
    return f"텐센트 OCR 실패({code})"


#: 공급사가 그대로 받는 원본 한도 — 긴 변(문서: 20~10,000px) · base64 7MB.
RAW_MAX_SIDE = 10000
RAW_MAX_B64 = 7 * 1024 * 1024


#: Y11-H: `read(max_side=AS_IS)` — JPEG·PNG가 공급사 한도(긴 변 10,000 · base64 7MB) 안이면 **풀지도 줄이지도 않고 그대로**.
AS_IS = -1
#: 한도 밖이라 풀어야 할 때의 긴 변 — 3000×3000 RGB ≈ 27MB(Render 512MB 안).
AS_IS_FALLBACK_SIDE = 3000


def _fits_as_is(raw: bytes) -> bool:
    from src.collectors.image_norm import image_head
    fmt, w, h = image_head(raw)[:3]
    return fmt in ("JPEG", "PNG") and bool(w and h) and max(w, h) <= RAW_MAX_SIDE and len(raw) * 4 / 3 <= RAW_MAX_B64


def shrink(raw: bytes, max_side: int = MAX_SIDE) -> bytes:
    """긴 변 `max_side`px JPEG로 — 보내는 바이트·디코딩 메모리를 줄인다. 못 열면 예외.

    Z10-B(오너 2026-10-11 02:24): 예전엔 `draft`(JPEG 전용) 뒤 `convert("RGB")`를 **원본 크기에서** 했다 — PNG는 draft가
    안 먹어 원본 화소 그대로 풀고 RGB 사본까지 한 벌 더. 이제 `image_norm.open_small`(줄이기 먼저 · 한 장씩)이고,
    서버가 풀면 안 되는 큰 PNG는 **풀지 않고 원본 바이트를 그대로** 보낸다(공급사가 PNG를 받는다 · 한도 안일 때만)."""
    from src.collectors.image_norm import image_head, open_small
    _f, _w, _h = image_head(raw)[:3]
    if _w and _h and min(_w, _h) < 20:
        # Y13-A(피샹리 상세 24번 s.gif 1×1): 공급사 최소 20px — 보내면 `InvalidParameterValue.Data`(그릴 것도 읽을 것도 없다)
        raise ValueError(f"너무 작은 사진({_w}×{_h} — 공급사 최소 20px)")
    if max_side == AS_IS:
        if _fits_as_is(raw):
            return bytes(raw)
        max_side = AS_IS_FALLBACK_SIDE                       # 한도 밖(webp·초대형) — 그래도 1024보다 훨씬 크게
    im, _fmt, w, h, why = open_small(raw, max_side)
    if im is None:
        if w and h and max(w, h) <= RAW_MAX_SIDE and len(raw) * 4 / 3 <= RAW_MAX_B64:
            logger.info("[텐센트 OCR] 원본 그대로 보냄(%s) — %s", f"{w}×{h}", why)
            return bytes(raw)
        raise ValueError(why or "이미지를 열지 못했어요")
    try:
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85)
        return out.getvalue()
    finally:
        im.close()


def _unavailable(why: str) -> Dict:
    return {"ok": False, "code": CODE_UNAVAILABLE, "why": why, "lines": [], "text": ""}


#: 이번 호출의 인식 언어(`LanguageType`) — 스레드마다. 기본 auto(아무 글자 · 대표 사진 판정), 한자 사전검사는 zh(중영 혼합).
_LANG = threading.local()


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
    try:
        resp = client.call_json(ACTION, {"ImageBase64": b64, "LanguageType": getattr(_LANG, "value", None) or "auto"})
    finally:
        from src.services.image_translate_tencent import close_client
        close_client(client)                                       # Y15: 호출마다 새 Session — 다 쓰면 닫는다
    return (resp or {}).get("Response") or {}


def read(raw: bytes, *, max_side: int = 0, lang: str = "") -> Dict:
    """이미지 바이트 → `{ok, lines: [(글자, 확신)], text, code, why}`. 확신 50 미만 조각은 뺀다.
    `max_side`(보낼 긴 변, 기본 MAX_SIDE · `AS_IS`=한도 안이면 원본 그대로) · `lang`(LanguageType, 기본 auto)."""
    if not raw:
        return _unavailable("이미지 바이트 없음")
    if not is_configured():
        return _unavailable("텐센트 키 미설정")
    if unopened():
        return _unavailable(UNOPEN_WHY)
    try:
        small = shrink(raw, max_side or MAX_SIDE)
    except Exception as exc:                                # noqa: BLE001 — 깨진 바이트
        if str(exc).startswith("너무 작은 사진"):
            return _unavailable(str(exc))
        return _unavailable(f"이미지를 열지 못했어요({type(exc).__name__})")
    t0 = time.monotonic()
    _LANG.value = lang or ""
    try:
        body = _call(base64.b64encode(small).decode("ascii"))
    except Exception as exc:                                # noqa: BLE001 — 키·네트워크·공급사 오류 전부 「확인 못 함」
        if no_text(exc):                                     # Y11-G: 글자 없음 — 실패 아님
            return {"ok": True, "code": "", "why": "", "lines": [], "text": ""}
        code = getattr(exc, "code", "") or type(exc).__name__
        msg = str(getattr(exc, "message", "") or exc)[:80]
        logger.warning("[텐센트 OCR] 호출 실패 %s: %s (%dms)", code, msg, int((time.monotonic() - t0) * 1000))
        return _unavailable(_fail_why(exc))
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


def read_boxes(raw: bytes) -> Dict:
    """Y11(오너 2026-10-14) — 글자 상자까지. `{ok, boxes:[{x,y,w,h,src}], size:[W,H], why}` — 좌표는 **원본 크기** 기준
    (보낼 때 줄인 비율만큼 되돌린다). 사진 편집(지우기·글자 고치기)이 쓴다. 확신 50 미만 조각은 뺀다."""
    if not raw:
        return {"ok": False, "why": "이미지 바이트 없음", "boxes": [], "size": [0, 0]}
    if not is_configured():
        return {"ok": False, "why": "텐센트 키 미설정", "boxes": [], "size": [0, 0]}
    if unopened():
        return {"ok": False, "why": UNOPEN_WHY, "code": "ocr_unopened", "boxes": [], "size": [0, 0]}
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as im0:
            W, H = im0.size                                # 헤더만 — 풀지 않는다
        small = shrink(raw)
        with Image.open(io.BytesIO(small)) as im1:
            sw, sh = im1.size
    except Exception as exc:                                # noqa: BLE001
        return {"ok": False, "why": f"이미지를 열지 못했어요({type(exc).__name__})", "boxes": [], "size": [0, 0]}
    kx, ky = (W / sw if sw else 1.0), (H / sh if sh else 1.0)
    try:
        body = _call(base64.b64encode(small).decode("ascii"))
    except Exception as exc:                                # noqa: BLE001
        if no_text(exc):                                     # Y11-G: 글자 없음 — 실패 아님(상자 0)
            return {"ok": True, "why": "", "boxes": [], "size": [W, H], "angle": 0.0}
        why = _fail_why(exc)
        return {"ok": False, "why": why, "code": "ocr_unopened" if why == UNOPEN_WHY else "ocr_failed", "boxes": [], "size": [W, H]}
    # Y11-E(오너 2026-10-14): 텐센트는 기울거나 뒤집힌 글자를 **돌려 세운 그림 기준**으로 줄 수 있다(이미지 번역 실측: 180°).
    #   네 꼭짓점(`Polygon`)이 있으면 그것의 외접 사각형을 쓰고, 없으면 `ItemPolygon`은 그림 각도가 0일 때만 쓴다
    #   (각도가 있는데 꼭짓점이 없으면 그 상자는 버린다 — 빈 벽에 상자를 그리지 않는다).
    angle = _angle_of(body)
    boxes = []
    for d in body.get("TextDetections") or []:
        d = d or {}
        txt = str(d.get("DetectedText") or "").strip()
        try:
            conf = float(d.get("Confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if not txt or conf < MIN_CONFIDENCE:
            continue
        rect = _polygon_rect(d.get("Polygon")) or (_item_rect(d.get("ItemPolygon")) if abs(angle) < 1.0 else None)
        if not rect:
            continue
        x, y, w, h = rect
        bx = {"x": int(x * kx), "y": int(y * ky), "w": int(w * kx), "h": int(h * ky),
              "src": txt[:120], "tgt": "", "conf": round(conf, 1)}
        from src.services.prop_text import tilt_of
        t = tilt_of(d.get("Polygon"))                        # Y11-G: 소품 판정용 기울기(거꾸로 = 180 근처)
        if t is not None:
            bx["tilt"] = t
        boxes.append(bx)
    return {"ok": True, "why": "", "boxes": boxes[:40], "size": [W, H], "angle": angle}


def _angle_of(body: dict) -> float:
    """응답 그림 각도 — 이 API는 `Angel`(원문 철자)로 주기도 한다. 없으면 0."""
    for k in ("Angle", "Angel"):
        try:
            v = float(body.get(k))
        except (TypeError, ValueError):
            continue
        v = v % 360
        return v - 360 if v > 180 else v
    return 0.0


def _polygon_rect(pts):
    """`[{X,Y}×4]` → `(x, y, w, h)` 외접 사각형. 모양이 아니면 None."""
    try:
        xs = [float(p.get("X")) for p in pts]
        ys = [float(p.get("Y")) for p in pts]
    except (TypeError, ValueError, AttributeError):
        return None
    if len(xs) < 3:
        return None
    x0, y0 = max(0.0, min(xs)), max(0.0, min(ys))
    return (x0, y0, max(1.0, max(xs) - x0), max(1.0, max(ys) - y0))


def _item_rect(p):
    if not isinstance(p, dict):
        return None
    try:
        return (float(p.get("X") or 0), float(p.get("Y") or 0), float(p.get("Width") or 0), float(p.get("Height") or 0))
    except (TypeError, ValueError):
        return None
