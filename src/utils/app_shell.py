"""오너 11-23 「앱이 실제 앱처럼」 — 이 요청이 아이폰/안드로이드 앱 셸(웹뷰) 안에서 왔나.

신호(하나면 충분):
- 시작 주소 `?app=1`(→ 쿠키 `kgp_app=1`을 1년 남겨 이후 링크도 앱으로 본다) · 쿠키 `kgp_app=1`
- User-Agent에 `gogabridjApp`(대소문자 무시) — 앱이 WKWebView `customUserAgent`/`applicationNameForUserAgent`로 붙인다
브라우저 쪽(standalone PWA·WKWebView `window.webkit.messageHandlers`)은 m_shell.js가 html.kgp-app을 따로 붙인다.
앱이면 「데스크톱 →」·「홈 화면에 추가」·「BETA」 같은 웹 전용 안내를 숨긴다(가짜가 아니라 앱 안에선 쓸모가 없어서).
"""
from __future__ import annotations

APP_COOKIE = "kgp_app"
APP_UA_TOKEN = "gogabridjapp"


def is_app_request(req) -> bool:
    try:
        if str(req.args.get("app") or "") == "1":
            return True
        if str(req.cookies.get(APP_COOKIE) or "") == "1":
            return True
        return APP_UA_TOKEN in str(req.headers.get("User-Agent") or "").lower()
    except Exception:                                   # noqa: BLE001 — 판정 실패 = 웹으로 본다
        return False


def remember_app(req, response):
    """`?app=1`로 들어온 요청은 쿠키를 남긴다(이후 링크엔 ?app=1이 없다). `?app=0`이면 지운다."""
    try:
        v = str(req.args.get("app") or "")
        if v == "1" and req.cookies.get(APP_COOKIE) != "1":
            response.set_cookie(APP_COOKIE, "1", max_age=365 * 24 * 3600, samesite="Lax", secure=req.is_secure)
        elif v == "0" and req.cookies.get(APP_COOKIE):
            response.delete_cookie(APP_COOKIE)
    except Exception:                                   # noqa: BLE001
        pass
    return response
