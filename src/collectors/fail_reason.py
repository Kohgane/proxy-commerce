"""수집 실패 사유 한 문장 — **어느 사이트라 안 되는지**(M4, 오너 2026-09-28).

미리보기(`/seller/collect/preview`)와 수집 코어(`collect_one_url` — 일괄·단축어·텔레그램·공유 시트)가
같은 문장을 쓴다. 두 벌이면 같은 테무 주소가 입구마다 다른 이유로 실패한다.
봇 차단은 **실측된 곳만** 단정한다(그 밖은 가능한 이유를 나열).
"""
from __future__ import annotations

from urllib.parse import urlparse

SITE_NAMES = (("temu.com", "테무"), ("amazon.", "아마존"), ("aliexpress.", "알리익스프레스"),
              ("coupang.com", "쿠팡"), ("rakuten.co.jp", "라쿠텐"), ("shein.", "쉬인"),
              ("yoshidakaban.com", "요시다카반"))
BOT_WALL = ("temu.com", "amazon.", "aliexpress.")


def fail_message(url: str) -> str:
    host = (urlparse(str(url or "")).hostname or "").lower()
    name = next((n for key, n in SITE_NAMES if key in host), "")
    who = f"{name}({host})" if name else (host or "이 주소")
    if any(k in host for k in BOT_WALL):
        return (f"{who}는 서버에서 상품 페이지를 읽을 수 없어요(봇 차단) — "
                "그 페이지를 PC 크롬에서 열고 고가수집기로 담아 주세요.")
    return (f"{who}에서 상품 정보를 읽지 못했어요 — 로그인·봇 차단이거나 상품 정보(메타)가 없는 페이지예요. "
            "제목·가격·이미지를 직접 넣거나 PC 고가수집기로 담아 주세요.")
