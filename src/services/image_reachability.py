"""src/services/image_reachability.py — 등록 직전 **외부 관점** 이미지 확인 (D2b).

## 왜 등록 직전인가

마켓은 우리 세션 쿠키가 없다. `/seller/collect/image-ko/…`는 **로그인 게이트 뒤**라
쿠팡이 그 주소로 이미지를 받으러 오면 404를 본다. 그런데 우리 화면에선 잘 보인다 —
**보이는 것과 가져갈 수 있는 것이 다르다.**

등록을 보내고 나서 반려 통지로 아는 것보다, **보내기 전에** 아는 편이 싸다.

## 어떻게 재나 — 쿠키 없이

우리 세션을 태우면 우리 화면과 같은 답이 온다(당연히 200이다). 그래서 **새 세션**으로,
쿠키·인증 헤더 없이 묻는다. 그게 마켓이 보는 것이다.

HEAD를 먼저 쓴다(바이트를 안 받는다). HEAD를 막는 서버가 있어 405/501이면 GET으로
한 번 더 본다 — 다만 **스트리밍으로 헤더만** 보고 끊는다.

## 발명 금지

판정에 쓰는 것은 **실제 응답코드와 content-type**뿐이다. 「아마 될 것이다」는 없다.
못 물어본 경우(네트워크 오류)는 **통과도 실패도 아닌 `unknown`** — 그 사실을 그대로 올린다.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

TIMEOUT_SEC = float(os.getenv("IMAGE_REACH_TIMEOUT_SEC", "6"))
MAX_CHECKS = int(os.getenv("IMAGE_REACH_MAX", "20"))

# 우리 서버 주소는 **외부에서 열리지 않는다**(로그인 게이트 뒤). 물어보기 전에 안다.
INTERNAL_PREFIXES = ("/seller/", "/admin/", "/api/")


def is_internal(url: str) -> bool:
    """우리 서버 경로인가 — 절대 URL이 아닌 것도, 우리 호스트인 것도 포함."""
    u = str(url or "").strip()
    if not u:
        return True
    if u.startswith(INTERNAL_PREFIXES):
        return True
    try:
        p = urlparse(u)
    except Exception:
        return True
    if not p.scheme or not p.netloc:
        return True                      # 상대 경로 = 우리 것
    host = os.getenv("PUBLIC_HOST", "").strip().lower()
    if host and p.netloc.lower().endswith(host):
        return p.path.startswith(INTERNAL_PREFIXES)
    return False


def check_one(url: str) -> dict:
    """한 장. `{url, ok, status, content_type, reason}` — `status`는 **실제 응답코드**다."""
    out = {"url": url, "ok": False, "status": 0, "content_type": "", "reason": ""}
    if is_internal(url):
        out["reason"] = "우리 서버 주소라 마켓이 가져갈 수 없습니다"
        return out

    try:
        import requests
    except Exception as exc:                                   # pragma: no cover
        out["reason"] = f"확인 불가: {type(exc).__name__}"
        return out

    # **쿠키·인증 없이** 묻는다 — 그게 마켓이 보는 것이다.
    sess = requests.Session()
    sess.cookies.clear()
    try:
        r = sess.head(url, timeout=TIMEOUT_SEC, allow_redirects=True)
        # **HEAD 미지원 표준 응답일 때만** GET으로 다시 본다(405 Method Not Allowed ·
        #   501 Not Implemented). 다른 4xx·5xx는 GET으로도 같은 답이 오므로 왕복만 늘어난다 —
        #   그 서버가 HEAD에만 다르게 답한다는 실측이 생기면 그때 넓힌다(지금은 근거가 없다).
        if r.status_code in (405, 501):
            r = sess.get(url, timeout=TIMEOUT_SEC, allow_redirects=True, stream=True)
            r.close()
        out["status"] = int(r.status_code)
        out["content_type"] = str(r.headers.get("Content-Type") or "").split(";")[0].strip()
    except Exception as exc:
        # 못 물어본 것은 **실패가 아니라 모름**이다 — 그 사실을 그대로 올린다.
        out["reason"] = f"확인하지 못했습니다({type(exc).__name__})"
        out["unknown"] = True
        return out
    finally:
        try:
            sess.close()
        except Exception:
            pass

    if out["status"] != 200:
        out["reason"] = f"응답 {out['status']}"
        return out
    if not out["content_type"].startswith("image/"):
        out["reason"] = f"이미지가 아닙니다({out['content_type'] or '형식 미상'})"
        return out
    out["ok"] = True
    return out


def check_all(urls, *, limit: int = MAX_CHECKS) -> dict:
    """`{ok, checked, bad: [...], unknown: [...]}`.

    `ok`는 **나쁜 장이 하나도 없을 때만** True다. 모름(`unknown`)은 막지 않는다 —
    우리가 못 물어본 것으로 셀러의 등록을 세우면, 우리 네트워크 사정이 그 사람의 벽이 된다.
    """
    seen, bad, unknown, checked = set(), [], [], 0
    for u in (urls or []):
        u = str(u or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        if checked >= limit:
            break
        r = check_one(u)
        checked += 1
        if r.get("unknown"):
            unknown.append(r)
        elif not r["ok"]:
            bad.append(r)
    return {"ok": not bad, "checked": checked, "bad": bad, "unknown": unknown}


def message(result: dict) -> str:
    """셀러에게 나가는 한 줄. **응답코드는 사유에만**, 문장은 사람 말로."""
    bad = (result or {}).get("bad") or []
    if not bad:
        return ""
    return (f"이미지 {len(bad)}장이 외부에서 열리지 않아요 — 저장소 연결 확인")
