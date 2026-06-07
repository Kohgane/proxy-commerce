"""통합 택배사 카탈로그 및 검색 유틸."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
import os
from typing import Iterable

import requests

logger = logging.getLogger(__name__)
DEFAULT_SWEET_CODE = "00"


@dataclass(frozen=True)
class CourierCatalogEntry:
    """통합 택배사 엔트리.

    trackingmore_code는 TrackingMore API 코드, sweet_code는 레거시 스윗트래커 코드다.
    aliases에는 한글/영문/약칭 검색어를 담아 검색 후보 및 코드 변환에 재사용한다.
    """

    name: str
    trackingmore_code: str
    sweet_code: str
    aliases: tuple[str, ...] = ()


_BUILTIN_ENTRIES: tuple[CourierCatalogEntry, ...] = (
    CourierCatalogEntry("CJ대한통운", "cj-korea", "04", ("CJ", "씨제이", "대한통운", "cj-korea", "cjkorea")),
    CourierCatalogEntry("한진택배", "hanjin", "05", ("한진", "hanjin", "hj")),
    CourierCatalogEntry("롯데택배", "lotte", "08", ("롯데", "lotte", "lotte-global-logistics")),
    CourierCatalogEntry("우체국택배", "korea-post", "01", ("우체국", "우정사업본부", "epost", "post", "korea-post")),
    CourierCatalogEntry("로젠택배", "logen", "06", ("로젠", "logen", "logen-delivery")),
    CourierCatalogEntry("대신택배", "daesin", "22", ("daesin",)),
    CourierCatalogEntry("경동택배", "kdexp", "23", ("경동", "kdexp", "kyungdong")),
    CourierCatalogEntry("일양로지스", "ilyanglogis", "18", ("일양", "ilyang", "ilyanglogis")),
    CourierCatalogEntry("합동택배", "hapdong", "32", ("합동", "hapdong")),
    CourierCatalogEntry("천일택배", "chunil", "24", ("천일", "chunil")),
)


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower().strip() if ch not in {" ", "-", "_"})


def _iter_terms(entry: CourierCatalogEntry) -> Iterable[str]:
    for value in (entry.name, entry.trackingmore_code, entry.sweet_code, *entry.aliases):
        if value:
            yield value
            normalized = _normalize(value)
            if normalized and normalized != value:
                yield normalized


def _to_payload(entry: CourierCatalogEntry, source: str = "builtin") -> dict:
    terms = sorted(set(_iter_terms(entry)))
    return {
        "name": entry.name,
        "trackingmore_code": entry.trackingmore_code,
        "sweet_code": entry.sweet_code,
        "aliases": list(entry.aliases),
        "search_terms": terms,
        "source": source,
    }


def _merge_catalog(rows: Iterable[dict]) -> list[dict]:
    by_name: dict[str, dict] = {}
    by_tm: dict[str, dict] = {}
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        tm_code = (row.get("trackingmore_code") or "").strip()
        key = tm_code or name
        existing = by_tm.get(key) or by_name.get(name)
        if existing:
            merged_terms = set(existing.get("search_terms") or [])
            merged_terms.update(row.get("search_terms") or [])
            existing["search_terms"] = sorted(merged_terms)
            aliases = set(existing.get("aliases") or [])
            aliases.update(row.get("aliases") or [])
            existing["aliases"] = sorted(aliases)
            if not existing.get("sweet_code"):
                existing["sweet_code"] = row.get("sweet_code", "")
            continue
        copied = dict(row)
        by_name[name] = copied
        by_tm[key] = copied
    return sorted(by_name.values(), key=lambda x: x["name"])


@lru_cache(maxsize=1)
def _fetch_trackingmore_catalog() -> tuple[dict, ...]:
    api_key = (os.getenv("TRACKINGMORE_API_KEY") or "").strip()
    if not api_key:
        return tuple()
    try:
        resp = requests.get(
            "https://api.trackingmore.com/v4/couriers/all",
            headers={"Tracking-Api-Key": api_key, "Content-Type": "application/json"},
            timeout=5,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("TrackingMore 택배사 카탈로그 확장 실패(%s, 내장 목록 폴백): %s", type(exc).__name__, exc)
        return tuple()

    rows: list[dict] = []
    for item in resp.json().get("data", []):
        code = (item.get("courier_code") or "").strip()
        name = (item.get("courier_name_kr") or item.get("courier_name") or code).strip()
        if not code or not name:
            continue
        entry = CourierCatalogEntry(
            name=name,
            trackingmore_code=code,
            sweet_code="",
            aliases=tuple(
                alias
                for alias in (
                    item.get("courier_name"),
                    item.get("courier_alias"),
                    code,
                )
                if alias
            ),
        )
        rows.append(_to_payload(entry, source="trackingmore"))
    return tuple(rows)


def get_courier_catalog(include_dynamic: bool = True) -> list[dict]:
    """UI/검색용 통합 택배사 카탈로그."""
    rows = [_to_payload(entry) for entry in _BUILTIN_ENTRIES]
    if include_dynamic:
        rows.extend(_fetch_trackingmore_catalog())
    merged = _merge_catalog(rows)
    return merged or [_to_payload(entry) for entry in _BUILTIN_ENTRIES]


def get_trackingmore_courier_map() -> dict[str, str]:
    """별칭 포함 택배사명 -> TrackingMore 코드."""
    mapping: dict[str, str] = {}
    for courier in get_courier_catalog(include_dynamic=False):
        code = courier.get("trackingmore_code", "")
        for term in courier.get("search_terms", []):
            if code and term:
                mapping[term] = code
    return mapping


def get_sweet_courier_map() -> dict[str, str]:
    """별칭 포함 택배사명 -> 스윗트래커 코드."""
    mapping: dict[str, str] = {}
    for courier in get_courier_catalog(include_dynamic=False):
        code = courier.get("sweet_code", "")
        for term in courier.get("search_terms", []):
            if code and term:
                mapping[term] = code
    return mapping


def find_couriers(query: str, limit: int = 12) -> list[dict]:
    """질의 문자열과 매칭되는 택배사 후보 목록."""
    normalized_query = _normalize(query)
    if not normalized_query:
        return get_courier_catalog(include_dynamic=True)[:limit]
    matches: list[dict] = []
    for courier in get_courier_catalog(include_dynamic=True):
        terms = [term.lower() for term in courier.get("search_terms", [])]
        if any(normalized_query in _normalize(term) for term in terms):
            matches.append(courier)
    return matches[:limit]


def lookup_trackingmore_code(name: str) -> str:
    """택배사 이름/별칭 -> TrackingMore 코드."""
    key = (name or "").strip()
    if not key:
        return ""
    mapping = get_trackingmore_courier_map()
    return mapping.get(key) or mapping.get(_normalize(key), "")


def lookup_sweet_code(name: str) -> str:
    """택배사 이름/별칭 -> 스윗트래커 코드."""
    key = (name or "").strip()
    if not key:
        return DEFAULT_SWEET_CODE
    mapping = get_sweet_courier_map()
    return mapping.get(key) or mapping.get(_normalize(key), DEFAULT_SWEET_CODE)
