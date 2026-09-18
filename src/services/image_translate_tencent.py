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
import threading
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

# ── F25: 실측이 고친 두 가지 (2026-09-14 첫 라이브) ────────────────────────────
#
# ① **URL 입력은 받지 않는다.** SDK 주석은 「Url을 쓸 때 Data에 ""를 넣으라」고 적혀 있고
#    우리는 실제로 그렇게 보냈다. 전선에 실려 나간 것까지 확인했다:
#        {'Data': '', 'Target': 'ko', 'Url': 'https://…', 'Mode': 0}
#    그런데 공급사는 **「Data: is required」**로 거절했다 — **빈 문자열을 「없음」으로 본다.**
#    주석이 시킨 대로 해도 안 되는 길이다. 그래서 URL이 와도 **우리가 내려받아 base64로** 보낸다.
#
# ② **초당 1회가 계정 한도다.** 5장을 나란히 보내니 2~5번이 전부 `LimitExceeded`였다.
#    한도는 **계정 단위**라 사용자가 둘이어도 합쳐서 1회다 → 프로세스 전역으로 직렬화한다.
#
# 크기 상한은 **SDK 원문 그대로**다(지어낸 값 없음):
#   Data — 「经Base64编码后不超过 9M」 · 600×800 이상 권장 · PNG/JPG/JPEG
MAX_BASE64_BYTES = 9 * 1024 * 1024
DOWNLOAD_TIMEOUT_SEC = int(os.getenv("TENCENT_IMAGE_FETCH_TIMEOUT_SEC", "10"))

# 장 사이 최소 간격. 한도가 「초당 1회」라 1.0초로 두면 경계에서 계속 걸린다 — 여유를 둔다.
MIN_INTERVAL_SEC = float(os.getenv("TENCENT_TMT_MIN_INTERVAL_SEC", "1.1"))
RATE_RETRY_WAIT_SEC = float(os.getenv("TENCENT_TMT_RATE_RETRY_WAIT_SEC", "2"))

# 한도에 걸렸는지 알아보는 표식. 코드는 SDK 표에 실재하고(`LimitExceeded`),
#   메시지 조각은 **오너 실측 원문**에서 가져왔다.
_RATE_CODES = ("LimitExceeded",)
_RATE_TEXTS = ("频率", "每秒", "rate limit", "too many requests")

# 같은 워커 안 스레드끼리의 게이트. **이것만으로는 부족하다** —
#   실측: gunicorn `--workers 2`(start_render.sh:30) · gthread × threads 4(gunicorn.conf.py:6-7).
#   워커가 둘이면 잠금도 둘이라 각자 「하나씩」 보내면서 **합쳐서 둘**이 나간다.
#   그래서 서버 전역 차례표(`rate_slot`)를 함께 쓴다 — 이 잠금은 그 앞의 얕은 턱일 뿐이다.
_GATE = threading.Lock()
_LAST_CALL = [0.0]

# 한도가 걸리는 단위. 계정 하나가 한 줄을 선다(사용자가 여럿이어도 같은 줄이다).
RATE_KEY = "tencent:image-translate"

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
    # F25 실측(2026-09-14): 5장을 나란히 보내니 2~5번이 전부 이 코드로 돌아왔다.
    #   원문 「您当前每秒请求 N 次，超过了每秒频率上限 1」 = **초당 1회**가 계정 한도다.
    "LimitExceeded": "초당 1장 한도 — 순서대로 다시 보냅니다.",
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


def fetch_image(url: str) -> tuple:
    """이미지를 **우리가** 내려받는다. 반환 `(bytes, 오류문자열)` — 하나만 채워진다.

    F25: 공급사가 URL 입력을 거절해서(위 ① 참고) 우리가 받아 base64로 보낸다.
    받는 데도 예산이 있다 — 소싱처가 느린 날 여기서 워커를 잡으면 F22와 같은 자리다.
    """
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gogabridj/1.0"})
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
            # base64는 원본의 4/3이다 — 원본 단계에서 미리 끊어 9M 상한을 넘기지 않게.
            raw = resp.read(int(MAX_BASE64_BYTES * 3 / 4) + 1)
    except Exception as exc:
        return b"", f"이미지를 내려받지 못했습니다({type(exc).__name__})"
    if not raw:
        return b"", "이미지가 비어 있습니다"
    if len(raw) * 4 / 3 > MAX_BASE64_BYTES:
        return b"", "이미지가 너무 큽니다(공급사 상한 base64 9MB)"
    return raw, ""


def _is_rate_limited(code: str, message: str) -> bool:
    """초당 한도에 걸린 응답인가. 코드가 정본이고, 메시지는 보조 표식이다."""
    if str(code or "") in _RATE_CODES:
        return True
    low = str(message or "").lower()
    return any(t in low for t in _RATE_TEXTS)


def _wait_turn() -> None:
    """직전 호출과 **최소 간격**을 띄운다. 잠금을 쥔 채로 잔다 — 그래야 한 번에 하나다."""
    gap = MIN_INTERVAL_SEC - (time.monotonic() - _LAST_CALL[0])
    if gap > 0:
        time.sleep(gap)


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

    `url`이나 `data` 중 하나. **URL이면 우리가 내려받아** base64로 보낸다 —
    공급사가 URL 입력을 거절하기 때문이다(F25 실측: 「Data: is required」).

    반환(성공/실패 공통 키): `ok` · `ms` · `vendor` · `action` · `request_bytes`
    성공: `image_b64`(JPG) · `source_lang` · `target_lang` · `source_text` · `target_text`
          · `lines`[{source, target, box}] · `request_id`
    실패: `error_class`(예외 **클래스명 그대로**) · `error_code` · `error_message` · `hint`

    **재시도는 초당 한도에 걸렸을 때 1회뿐이다.** 그 외에는 하지 않는다 —
    장당 과금이라 조용한 재시도는 조용한 청구다. 한도 재시도는 「같은 장을 다시」가 아니라
    「아직 한 번도 못 보낸 장을 순서대로」라서 청구가 늘지 않는다.
    """
    t0 = time.perf_counter()
    out = {"ok": False, "vendor": VENDOR, "action": ACTION, "ms": 0,
           "request_bytes": len(data or b""), "used": "data"}

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

    # F25 ①: URL이 와도 **우리가 내려받는다.** 공급사가 URL 입력을 거절했다(실측).
    if not data:
        data, why = fetch_image(url)
        if why:
            out.update({"error_class": "FetchFailed", "error_code": "",
                        "error_message": why, "hint": "원본 주소가 아직 열려 있는지 확인하세요."})
            out["ms"] = int((time.perf_counter() - t0) * 1000)
            return out
        out["request_bytes"] = len(data)

    try:
        from tencentcloud.tmt.v20180321 import models
        req = models.ImageTranslateLLMRequest()
        # 요청 모델에 `Source`가 없다 — 자동 감지다(위 독스트링).
        #   `Url`도 보내지 않는다 — 보내면 「Data: is required」로 거절당한다(실측).
        payload = {"Target": TARGET_LANG, "Mode": int(mode),
                   "Data": base64.b64encode(data).decode("ascii")}
        req.from_json_string(__import__("json").dumps(payload))

        # F25 ②: 한도가 **계정 단위 초당 1회**다 → 프로세스 전역으로 하나씩 내보낸다.
        #   한도에 걸리면 **딱 한 번만** 쉬었다 다시 보낸다(그 외 재시도는 여전히 0 —
        #   장당 과금이라 조용한 재시도는 조용한 청구다).
        cli = _client(timeout_sec or DEFAULT_TIMEOUT_SEC)
        # F25b: **서버 전역** 차례표를 먼저 선다(워커가 둘이라 프로세스 잠금만으론 부족).
        #   기다림은 잠금 **밖**이다 — DB 연결을 붙잡은 채 자지 않는다.
        from src.services import rate_slot
        turn = rate_slot.wait_turn(RATE_KEY, MIN_INTERVAL_SEC)
        out["rate_scope"] = turn.get("backend", "")
        if turn.get("too_long"):
            out.update({"error_class": "RateQueueTooLong", "error_code": "",
                        "error_message": "지금은 번역 줄이 깁니다. 잠시 후 다시 시도해 주세요.",
                        "hint": f"앞에 {turn.get('wait', 0):.0f}초치가 밀려 있습니다."})
            out["ms"] = int((time.perf_counter() - t0) * 1000)
            return out
        with _GATE:
            _wait_turn()
            try:
                resp = cli.ImageTranslateLLM(req)
            except Exception as first:
                code = getattr(first, "code", "") or ""
                msg = getattr(first, "message", "") or str(first)
                if not _is_rate_limited(code, msg):
                    _LAST_CALL[0] = time.monotonic()
                    raise
                logger.info("[이미지번역] 초당 한도 — %.0f초 쉬고 1회 재시도", RATE_RETRY_WAIT_SEC)
                out["rate_retried"] = True
                time.sleep(RATE_RETRY_WAIT_SEC)
                resp = cli.ImageTranslateLLM(req)
            _LAST_CALL[0] = time.monotonic()

        lines = []
        for d in (getattr(resp, "TransDetails", None) or []):
            box = getattr(d, "BoundingBox", None)
            lines.append({
                "source": getattr(d, "SourceLineText", "") or "",
                "target": getattr(d, "TargetLineText", "") or "",
                "box": ({"x": getattr(box, "X", None), "y": getattr(box, "Y", None),
                         "w": getattr(box, "Width", None), "h": getattr(box, "Height", None)}
                        if box is not None else None),
                # F33: SDK 모델에 실재하는 필드다(`TransDetail.LineHeight`·`LinesCount` —
                #   `tencentcloud.tmt.v20180321.models` 원문 확인, 추측 아님).
                #   **C 축을 이걸로 판정하지는 않는다** — 박스는 「段落文本框位置」,
                #   곧 **원문** 문단의 자리이지 번역문이 그려진 자리가 아니다. 참고 수치다.
                "line_height": getattr(d, "LineHeight", None),
                "lines_count": getattr(d, "LinesCount", None),
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
