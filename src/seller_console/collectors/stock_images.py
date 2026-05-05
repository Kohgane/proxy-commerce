"""src/seller_console/collectors/stock_images.py — 무료 보조 이미지 검색 (Phase 130).

키워드 입력 → Pexels/Unsplash에서 무료 이미지 5개 후보 반환.
키 미설정 시 빈 목록 반환 (UI 안 깨짐).

환경변수:
  PEXELS_API_KEY       — Pexels API 키
  UNSPLASH_ACCESS_KEY  — Unsplash API 액세스 키
"""
from __future__ import annotations

import logging
import os
from typing import List

logger = logging.getLogger(__name__)

_PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
_UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"


def search_images(keyword: str, count: int = 5) -> List[dict]:
    """키워드로 무료 이미지 검색.

    Pexels 우선 → 없으면 Unsplash → 둘 다 없으면 빈 목록.

    Args:
        keyword: 검색 키워드
        count: 반환할 이미지 수 (최대 10)

    Returns:
        이미지 목록:
        [{"url": str, "thumbnail": str, "source": str, "photographer": str}, ...]
    """
    count = min(count, 10)

    if os.getenv("PEXELS_API_KEY"):
        results = _search_pexels(keyword, count)
        if results:
            return results

    if os.getenv("UNSPLASH_ACCESS_KEY"):
        results = _search_unsplash(keyword, count)
        if results:
            return results

    logger.debug("PEXELS_API_KEY/UNSPLASH_ACCESS_KEY 미설정 — 이미지 검색 비활성")
    return []


def _search_pexels(keyword: str, count: int) -> List[dict]:
    """Pexels 이미지 검색."""
    try:
        import requests
        api_key = os.getenv("PEXELS_API_KEY", "")
        resp = requests.get(
            _PEXELS_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": keyword, "per_page": count, "orientation": "square"},
            timeout=8,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        return [
            {
                "url": p["src"]["original"],
                "thumbnail": p["src"]["medium"],
                "source": "pexels",
                "photographer": p.get("photographer", ""),
                "pexels_url": p.get("url", ""),
            }
            for p in photos
        ]
    except Exception as exc:
        logger.warning("Pexels 검색 실패: %s", exc)
        return []


def _search_unsplash(keyword: str, count: int) -> List[dict]:
    """Unsplash 이미지 검색."""
    try:
        import requests
        access_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
        resp = requests.get(
            _UNSPLASH_SEARCH_URL,
            params={
                "query": keyword,
                "per_page": count,
                "orientation": "squarish",
                "client_id": access_key,
            },
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [
            {
                "url": r["urls"]["full"],
                "thumbnail": r["urls"]["thumb"],
                "source": "unsplash",
                "photographer": r.get("user", {}).get("name", ""),
                "unsplash_url": r.get("links", {}).get("html", ""),
            }
            for r in results
        ]
    except Exception as exc:
        logger.warning("Unsplash 검색 실패: %s", exc)
        return []
