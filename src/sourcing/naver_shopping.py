"""src/sourcing/naver_shopping.py — 국내 베스트셀러(네이버 쇼핑 검색) 실데이터 클라이언트 (v12).

키워드로 국내에서 실제 팔리는 상품(제목·이미지·가격·판매몰)을 네이버 쇼핑 검색 오픈 API로 가져온다.
- 키(NAVER_SEARCH_CLIENT_ID/SECRET) 미설정·네트워크 실패·ADAPTER_DRY_RUN=1 → 빈 리스트(날조 금지).
- 가짜 수치/카드 절대 생성하지 않는다. 데이터 없으면 호출부가 '데이터 없음'으로 표시.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_ENDPOINT = "https://openapi.naver.com/v1/search/shop.json"
_TAG_RE = re.compile(r"<[^>]+>")


def is_configured() -> bool:
    """네이버 쇼핑 검색 오픈 API 키가 설정돼 있는가?"""
    return bool(
        (os.getenv("NAVER_SEARCH_CLIENT_ID") or "").strip()
        and (os.getenv("NAVER_SEARCH_CLIENT_SECRET") or "").strip()
    )


def _strip_tags(s: str) -> str:
    return _TAG_RE.sub("", s or "").strip()


def search_domestic_products(keyword: str, *, limit: int = 12, sort: str = "sim") -> List[Dict[str, Any]]:
    """키워드로 국내 판매 상품을 검색해 카드용 dict 리스트로 반환.

    반환 각 항목: {title, image, price(int KRW), mall, link, brand}.
    키 미설정/실패/dry-run → [] (정직).
    sort: sim(정확도)·date·asc·dsc(가격). 베스트셀러 느낌은 'sim'(기본) 또는 별도 정렬.
    """
    kw = (keyword or "").strip()
    if not kw:
        return []
    if os.getenv("ADAPTER_DRY_RUN") == "1":
        return []
    if not is_configured():
        return []

    cid = os.getenv("NAVER_SEARCH_CLIENT_ID", "").strip()
    csec = os.getenv("NAVER_SEARCH_CLIENT_SECRET", "").strip()
    try:
        display = max(1, min(int(limit), 40))
    except (TypeError, ValueError):
        display = 12

    qs = urllib.parse.urlencode({"query": kw, "display": display, "sort": sort})
    req = urllib.request.Request(_ENDPOINT + "?" + qs, headers={
        "X-Naver-Client-Id": cid,
        "X-Naver-Client-Secret": csec,
        "User-Agent": "KOHgogane/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("네이버 쇼핑 검색 실패(키워드=%r): %s", kw, exc)
        return []

    out: List[Dict[str, Any]] = []
    for it in (data.get("items") or []):
        try:
            price = int(str(it.get("lprice") or "0").strip() or "0")
        except (TypeError, ValueError):
            price = 0
        title = _strip_tags(it.get("title", ""))
        if not title:
            continue
        out.append({
            "title": title,
            "image": (it.get("image") or "").strip(),
            "price": price,
            "mall": (it.get("mallName") or "").strip(),
            "brand": (it.get("brand") or it.get("maker") or "").strip(),
            "link": (it.get("link") or "").strip(),
        })
    return out
