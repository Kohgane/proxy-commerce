"""src/services/image_translate_tencent.py — 텐센트 이미지 번역 클라이언트 한 겹 (D1).

## 무엇을 하나

상품 이미지에 박힌 중국어(·일/영) 글자를 **한국어가 박힌 이미지**로 바꿔 받는다.
지우고 다시 얹는 일(인페인팅·재렌더)은 공급사가 한다 — 우리가 만들지 않는다(D0 원칙).

## 어디서 확인한 스펙인가 — **문서가 아니라 SDK 원문**

이 세션은 텐센트 문서 사이트에 못 닿는다(프록시 403). 그래서 파라미터·응답 필드·에러 코드를
**공식 SDK 소스**에서 읽었다(`tencentcloud-sdk-python-tmt` v3.1.129,
`tencentcloud/tmt/v20180321/{models.py, tmt_client.py, errorcodes.py}`).
스키마는 문서보다 정확하다 — 공급사가 실제로 그 필드로 통신한다.

| 확인한 것 | 값 |
|---|---|
| 액션 | `ImageTranslateLLM` (옛 `ImageTranslate`는 **현행 SDK에 없다**) |
| API 버전 | `2018-03-21` |
| 엔드포인트 | `tmt.tencentcloudapi.com`(중국판 패키지) / `tmt.intl.tencentcloudapi.com`(국제판) |
| 요청 | `Data`(base64, 인코딩 후 9MB 이하) \\| `Url`(10MB 미만) · `Target` · `Mode`(0=pro, 1=lite) |
| 응답 | `Data`(번역 이미지 base64 **JPG**) · `Source` · `Target` · `SourceText` · `TargetText` · `Angle` · `TransDetails` |

## 원본 언어(`Source`)는 **보내지 않는다**

요청 모델에 `Source` 필드가 **없다.** 자동 감지이고, 감지 결과가 응답 `Source`로 온다.
그래서 「Source=auto」는 파라미터가 아니라 **이 API의 동작 자체**다 —
없는 필드를 만들어 보내지 않는다(발명 0).

## 타임아웃 — 오너 요청과 SDK가 줄 수 있는 것이 다르다

오너 요청은 `(connect 3s, read 20s)`였다. 그런데 SDK가 노출하는 것은
`HttpProfile(reqTimeout=<초>)` **하나뿐**이다(초 단위 정수). 연결/읽기를 나눠 줄 수 없다.
그래서 **읽기 예산 하나**로 두고(기본 20초), 연결 시간도 그 안에 포함된다는 것을 여기 적는다.
`(3, 20)`을 받은 척하지 않는다.

## 재시도 0

오너 지시. 이미지 번역은 장당 과금이라 **조용한 재시도가 곧 조용한 청구**다.
실패는 실패로 올리고, 다시 할지는 사람이 정한다.
"""
from __future__ import annotations

import base64
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

VENDOR = "tencent"
ACTION = "ImageTranslateLLM"
API_VERSION = "2018-03-21"
TARGET_LANG = "ko"

# 둘 다 **SDK 패키지에서 확인한 값**이다(기억 아님).
#   intl  = tencentcloud-sdk-python-intl-en 의 TmtClient._endpoint
#   cn    = tencentcloud-sdk-python-tmt     의 TmtClient._endpoint
ENDPOINTS = {
    "intl": "tmt.intl.tencentcloudapi.com",
    "cn": "tmt.tencentcloudapi.com",
}
DEFAULT_ENDPOINT_KEY = "intl"     # 오너 계정은 국제 콘솔 가입분(한국 리전 카드 게이트 우회)

# 호출 예산(초). SDK는 단일 값만 받는다 — 위 독스트링 참고.
DEFAULT_TIMEOUT_SEC = int(os.getenv("TENCENT_TMT_TIMEOUT_SEC", "20"))

# 공급사가 돌려주는 에러 코드 → 사람이 읽는 한 줄.
#   **전부 SDK `errorcodes.py`에 실재하는 코드다.** 없는 코드를 지어 넣지 않는다.
#   원문 설명은 중국어라, 뜻을 바꾸지 않는 선에서 우리말로 옮겼다.
ERROR_HINTS = {
    "FailedOperation.DecodeErr": "이미지를 해독하지 못했습니다(형식·손상 확인).",
    "FailedOperation.DownloadErr": "이미지를 내려받지 못했습니다(URL 접근 가능 여부 확인).",
    "FailedOperation.ErrorUserArea": "계정 리전과 요청 리전이 다릅니다 — TENCENT_REGION을 계정 리전으로 맞추세요.",
    "FailedOperation.NoFreeAmount": "이번 달 무료 한도를 다 썼습니다(콘솔에서 유료 전환 필요).",
    "FailedOperation.ServiceIsolate": "미납으로 서비스가 정지됐습니다(계정 충전 필요).",
    "FailedOperation.StopUsing": "계정이 정지됐습니다.",
    "FailedOperation.UserNotRegistered": "기계번역 서비스가 미개통입니다(콘솔에서 개통 필요).",
    "InternalError": "공급사 내부 오류입니다.",
    "InternalError.BackendTimeout": "공급사 백엔드 시간 초과입니다 — 잠시 후 다시.",
    "InternalError.ErrorUnknown": "공급사 알 수 없는 오류입니다.",
    "InternalError.RequestFailed": "공급사 요청이 실패했습니다.",
    "InvalidParameter": "파라미터 오류입니다.",
    "InvalidParameter.MissingParameter": "필수 파라미터가 빠졌습니다.",
    "LimitExceeded": "호출 한도를 넘었습니다.",
    "MissingParameter": "필수 파라미터가 빠졌습니다.",
    "UnauthorizedOperation.ActionNotFound": "액션 이름이 올바르지 않습니다.",
    "UnsupportedOperation": "지원하지 않는 동작입니다.",
    "UnsupportedOperation.UnSupportedTargetLanguage": "지원하지 않는 대상 언어입니다.",
    "UnsupportedOperation.UnsupportedLanguage": "지원하지 않는 언어입니다.",
    "UnsupportedOperation.UnsupportedSourceLanguage": "지원하지 않는 원본 언어입니다.",
}


# ---------------------------------------------------------------------------
# 설정 — 없으면 **기능을 숨긴다**(오류가 아니라 「미연결」)
# ---------------------------------------------------------------------------

def _secret() -> tuple:
    return (os.getenv("TENCENT_SECRET_ID", "").strip(),
            os.getenv("TENCENT_SECRET_KEY", "").strip())


def endpoint() -> str:
    """쓸 엔드포인트. `TENCENT_TMT_ENDPOINT`로 바꿀 수 있고, 별칭 `intl`·`cn`도 받는다."""
    raw = os.getenv("TENCENT_TMT_ENDPOINT", "").strip()
    return ENDPOINTS.get(raw, raw) or ENDPOINTS[DEFAULT_ENDPOINT_KEY]


def region() -> str:
    """`TENCENT_REGION` 그대로. **기본값을 두지 않는다.**

    SDK에는 **리전 목록이 없다**(리전은 그냥 헤더로 실려 나가는 문자열이다).
    확인할 수 없는 값을 기본값으로 두면 그건 발명이다. 비어 있으면 비운 채 보내고,
    계정 리전과 어긋나면 공급사가 `FailedOperation.ErrorUserArea`로 알려 준다 —
    그 코드의 뜻을 위 표에 그대로 적어 두었다.

    오너 계정 실값(2026-09-14)은 **`ap-singapore`**(가입 리전 싱가포르)이고 Render env에 있다.
    그래도 여기에 기본값으로 박지 않는다 — **리전은 계정마다 다르다.** 박아 두면 다른 계정을
    쓰는 날 env가 비어도 조용히 싱가포르로 나가고, 그때는 어긋난 줄도 모른다.
    """
    return os.getenv("TENCENT_REGION", "").strip()


def is_configured() -> bool:
    sid, skey = _secret()
    return bool(sid and skey)


def status() -> dict:
    """화면이 「미연결」을 정직하게 그릴 수 있도록 — 왜 못 쓰는지까지."""
    sid, skey = _secret()
    missing = [n for n, v in (("TENCENT_SECRET_ID", sid), ("TENCENT_SECRET_KEY", skey)) if not v]
    try:
        import tencentcloud  # noqa: F401
        sdk = True
    except Exception:
        sdk = False
    if not sdk:
        missing.append("tencentcloud-sdk-python-tmt(미설치)")
    return {
        "vendor": VENDOR, "configured": not missing, "missing": missing,
        "endpoint": endpoint(), "region": region() or "(미설정)",
        "action": ACTION, "target": TARGET_LANG,
    }


# ---------------------------------------------------------------------------
# 호출
# ---------------------------------------------------------------------------

def _client(timeout_sec: int):
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.tmt.v20180321 import tmt_client

    sid, skey = _secret()
    http = HttpProfile(endpoint=endpoint(), reqTimeout=int(timeout_sec))
    prof = ClientProfile(httpProfile=http)
    return tmt_client.TmtClient(credential.Credential(sid, skey), region(), prof)


def translate_image(*, url: str = "", data: bytes = b"", mode: int = 0,
                    timeout_sec: Optional[int] = None) -> dict:
    """이미지 1장 → 한국어가 박힌 이미지.

    `url`이나 `data` 중 하나. 둘 다 오면 `url`을 쓴다(요청이 더 가볍다).

    반환(성공/실패 공통 키): `ok` · `ms` · `vendor` · `action` · `request_bytes`
    성공: `image_b64`(JPG) · `source_lang` · `target_lang` · `source_text` · `target_text`
          · `lines`[{source, target, box}] · `request_id`
    실패: `error_class`(예외 **클래스명 그대로**) · `error_code` · `error_message` · `hint`

    **재시도하지 않는다.** 장당 과금이라 조용한 재시도는 조용한 청구다.
    """
    t0 = time.perf_counter()
    out = {"ok": False, "vendor": VENDOR, "action": ACTION, "ms": 0,
           "request_bytes": len(data or b""), "used": "url" if url else "data"}

    if not is_configured():
        out.update({"error_class": "NotConfigured", "error_code": "",
                    "error_message": "공급사 미연결", "hint": "TENCENT_SECRET_ID/KEY 미설정"})
        out["ms"] = int((time.perf_counter() - t0) * 1000)
        return out
    if not (url or data):
        out.update({"error_class": "ValueError", "error_code": "",
                    "error_message": "이미지가 없습니다(url 또는 data 필요)", "hint": ""})
        out["ms"] = int((time.perf_counter() - t0) * 1000)
        return out

    try:
        from tencentcloud.tmt.v20180321 import models
        req = models.ImageTranslateLLMRequest()
        # 요청 모델에 `Source`가 없다 — 자동 감지다(위 독스트링).
        payload = {"Target": TARGET_LANG, "Mode": int(mode)}
        if url:
            payload["Url"] = url
            payload["Data"] = ""          # SDK 주석: Url을 쓰면 Data에 "" 를 넣는다
        else:
            payload["Data"] = base64.b64encode(data).decode("ascii")
        req.from_json_string(__import__("json").dumps(payload))

        resp = _client(timeout_sec or DEFAULT_TIMEOUT_SEC).ImageTranslateLLM(req)

        lines = []
        for d in (getattr(resp, "TransDetails", None) or []):
            box = getattr(d, "BoundingBox", None)
            lines.append({
                "source": getattr(d, "SourceLineText", "") or "",
                "target": getattr(d, "TargetLineText", "") or "",
                "box": ({"x": getattr(box, "X", None), "y": getattr(box, "Y", None),
                         "w": getattr(box, "Width", None), "h": getattr(box, "Height", None)}
                        if box is not None else None),
            })
        img_b64 = getattr(resp, "Data", "") or ""
        out.update({
            "ok": bool(img_b64),
            "image_b64": img_b64,
            "image_bytes": len(img_b64),
            "source_lang": getattr(resp, "Source", "") or "",
            "target_lang": getattr(resp, "Target", "") or "",
            "source_text": getattr(resp, "SourceText", "") or "",
            "target_text": getattr(resp, "TargetText", "") or "",
            "lines": lines,
            "angle": getattr(resp, "Angle", None),
            "request_id": getattr(resp, "RequestId", "") or "",
        })
        if not img_b64:
            # 200인데 이미지가 비었다 — 성공이라 부르지 않는다(가짜 성공 0).
            out.update({"error_class": "EmptyImage", "error_code": "",
                        "error_message": "응답에 번역 이미지가 없습니다", "hint": ""})
    except Exception as exc:
        code = str(getattr(exc, "code", "") or "")
        out.update({
            "error_class": type(exc).__name__,          # 예외 **클래스명 그대로**(발명 0)
            "error_code": code,
            "error_message": str(getattr(exc, "message", "") or exc)[:400],
            "request_id": str(getattr(exc, "requestId", "") or ""),
            "hint": ERROR_HINTS.get(code, ""),
        })
        logger.warning("[이미지번역] 실패 %s code=%s", type(exc).__name__, code or "-")

    out["ms"] = int((time.perf_counter() - t0) * 1000)
    return out
