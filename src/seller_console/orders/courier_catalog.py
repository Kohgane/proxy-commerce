"""통합 택배사 카탈로그 및 검색 유틸."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
import os
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

# F45 — 모르는 택배사는 **빈 코드**다. 예전엔 `"00"`을 조용히 돌려줬다:
#   카탈로그에 없는 이름이 들어와도 **아무 말 없이 코드가 하나 나왔다.**
#   그건 「미지원」을 「00번 택배사」로 바꿔 말한 것이고, 침묵 매핑이다(F44 b 금지사항).
SWEET_CODE_UNSUPPORTED = ""
DEFAULT_SWEET_CODE = SWEET_CODE_UNSUPPORTED   # 옛 이름 — 값이 바뀌었다(위 참조)


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
    # F44-a: **마켓별 컬럼**을 한 표에 둔다. 쿠팡 열이 먼저 붙었고(정본 코드표 확보),
    #   네이버·11번가는 코드표 문서가 오면 같은 자리에 열을 늘린다.
    #   기존 TrackingMore/스윗 축은 **그대로** 둔다 — 추적 공급사와 마켓 코드는 다른 축이다.
    coupang = _coupang_code_for(entry)
    return {
        "name": entry.name,
        "trackingmore_code": entry.trackingmore_code,
        "sweet_code": entry.sweet_code,
        "coupang_code": coupang,
        # 「미지원」은 **빈칸과 다르다** — 빈칸은 「아직 안 붙였다」이고 이건 「그 마켓엔 없다」다.
        "coupang_status": _coupang_status(coupang),
        "naver_code": "",          # 코드표 문서 대기 — 짐작해 채우지 않는다
        "elevenst_code": "",       # 〃
        "aliases": list(entry.aliases),
        "search_terms": terms,
        "source": source,
    }


def _coupang_code_for(entry: CourierCatalogEntry) -> str:
    """우리 카탈로그 행 → 쿠팡 코드. **확실할 때만** 채운다(부분일치 금지)."""
    try:
        from .coupang_courier_rules import resolve_name
    except Exception:                                   # pragma: no cover
        return ""
    for cand in (entry.name, *entry.aliases):
        code = resolve_name(cand)
        if code:
            return code
    return ""


def _coupang_status(code: str) -> dict:
    if not code:
        return {"found": False, "selectable": False, "reason": "쿠팡 코드 미매핑", "lens_label": ""}
    from .coupang_courier_rules import status
    return status(code)


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


def get_courier_catalog(include_dynamic: bool = True,
                        include_coupang: bool = True) -> list[dict]:
    """UI/검색용 통합 택배사 카탈로그.

    F44-c: **쿠팡 코드표 전체**를 함께 싣는다 — 드롭다운에서 「모든 코드가 검색으로
    도달 가능」해야 하고, **합병/폐업도 보여야** 한다(숨기면 「내 택배사가 왜 없지」가 된다).
    폐업 행은 `coupang_status.selectable=False`로 내려가고 **화면이 회색·선택 불가**로 그린다.
    """
    rows = [_to_payload(entry) for entry in _BUILTIN_ENTRIES]
    if include_dynamic:
        rows.extend(_fetch_trackingmore_catalog())
    if include_coupang:
        rows.extend(_coupang_rows())
    merged = _merge_catalog(rows)
    return merged or [_to_payload(entry) for entry in _BUILTIN_ENTRIES]


def _coupang_rows() -> list[dict]:
    """쿠팡 코드표 → 카탈로그 행. **추적 공급사 축은 비운다**(그건 다른 축이다)."""
    try:
        from .coupang_courier_codes import COUPANG_COURIERS
        from .coupang_courier_rules import COUPANG_ALIASES, status
    except Exception:                                   # pragma: no cover
        return []
    out = []
    for c in COUPANG_COURIERS:
        st = status(c.code)
        terms = {c.code, c.code.lower(), c.name, _normalize(c.name)}
        terms |= {a for a, code in COUPANG_ALIASES.items() if code == c.code}
        out.append({
            "name": c.name,
            "trackingmore_code": "",      # 이 축은 이 행이 모른다 — 빈칸이 정직하다
            "sweet_code": "",
            "coupang_code": c.code,
            "coupang_status": st,
            "naver_code": "",
            "elevenst_code": "",
            "aliases": sorted(a for a, code in COUPANG_ALIASES.items() if code == c.code),
            "search_terms": sorted(t for t in terms if t),
            "source": "coupang",
        })
    return out


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
    """택배사 이름/별칭 -> 스윗트래커 코드. **모르면 빈 문자열**(F45).

    ★ 예전엔 모르는 이름에 `"00"`을 돌려줬다 — 호출부는 그게 **찾은 코드인지
    폴백인지 구분할 수 없었다.** 빈 값이면 호출부가 「미지원」이라고 말할 수 있다.
    """
    key = (name or "").strip()
    if not key:
        return SWEET_CODE_UNSUPPORTED
    mapping = get_sweet_courier_map()
    return mapping.get(key) or mapping.get(_normalize(key), SWEET_CODE_UNSUPPORTED)
