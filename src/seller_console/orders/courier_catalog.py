"""통합 택배사 카탈로그 및 검색 유틸."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable

logger = logging.getLogger(__name__)

# F45 — 모르는 택배사는 **빈 코드**다. 예전엔 `"00"`을 조용히 돌려줬다:
#   카탈로그에 없는 이름이 들어와도 **아무 말 없이 코드가 하나 나왔다.**
#   그건 「미지원」을 「00번 택배사」로 바꿔 말한 것이고, 침묵 매핑이다(F44 b 금지사항).
SWEET_CODE_UNSUPPORTED = ""
DEFAULT_SWEET_CODE = SWEET_CODE_UNSUPPORTED   # 옛 이름 — 값이 바뀌었다(위 참조)


@dataclass(frozen=True)
class CourierCatalogEntry:
    """통합 택배사 엔트리.

    `sweet_code`는 레거시 스윗트래커 코드다. 추적 공급사 축은 **17TRACK**이고
    (F44-b, TrackingMore 교체 — 병존 금지), 그 코드는 **정수 `key`**라 문서가 와야 채운다.
    aliases에는 한글/영문/약칭 검색어를 담아 검색 후보 및 코드 변환에 재사용한다.
    """

    name: str
    sweet_code: str
    aliases: tuple[str, ...] = ()


_BUILTIN_ENTRIES: tuple[CourierCatalogEntry, ...] = (
    CourierCatalogEntry("CJ대한통운", "04", ("CJ", "씨제이", "대한통운", "cj-korea", "cjkorea")),
    CourierCatalogEntry("한진택배", "05", ("한진", "hanjin", "hj")),
    CourierCatalogEntry("롯데택배", "08", ("롯데", "lotte", "lotte-global-logistics")),
    CourierCatalogEntry("우체국택배", "01", ("우체국", "우정사업본부", "epost", "post", "korea-post")),
    CourierCatalogEntry("로젠택배", "06", ("로젠", "logen", "logen-delivery")),
    CourierCatalogEntry("대신택배", "22", ("daesin",)),
    CourierCatalogEntry("경동택배", "23", ("경동", "kdexp", "kyungdong")),
    CourierCatalogEntry("일양로지스", "18", ("일양", "ilyang", "ilyanglogis")),
    CourierCatalogEntry("합동택배", "32", ("합동", "hapdong")),
    CourierCatalogEntry("천일택배", "24", ("천일", "chunil")),
)


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.lower().strip() if ch not in {" ", "-", "_"})


def _iter_terms(entry: CourierCatalogEntry) -> Iterable[str]:
    for value in (entry.name, entry.sweet_code, *entry.aliases):
        if value:
            yield value
            normalized = _normalize(value)
            if normalized and normalized != value:
                yield normalized


def _to_payload(entry: CourierCatalogEntry, source: str = "builtin") -> dict:
    terms = sorted(set(_iter_terms(entry)))
    # F44-a: **마켓별 컬럼**을 한 표에 둔다. 쿠팡 열이 먼저 붙었고(정본 코드표 확보),
    #   네이버·11번가는 코드표 문서가 오면 같은 자리에 열을 늘린다.
    #   추적 공급사 축과 마켓 코드는 **다른 축**이다 — 섞지 않는다.
    coupang = _coupang_code_for(entry)
    return {
        "name": entry.name,
        # F44-b: 추적 공급사 = 17TRACK. 코드는 목록 문서의 정수 `key`라
        #   **문서가 와야 채운다** — 빈칸이 「아직 안 붙였다」를 정직하게 말한다.
        "seventeentrack_code": "",
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
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        existing = by_name.get(name)
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
        by_name[name] = dict(row)
    return sorted(by_name.values(), key=lambda x: x["name"])


def get_courier_catalog(include_dynamic: bool = True,
                        include_coupang: bool = True) -> list[dict]:
    """UI/검색용 통합 택배사 카탈로그.

    F44-c: **쿠팡 코드표 전체**를 함께 싣는다 — 드롭다운에서 「모든 코드가 검색으로
    도달 가능」해야 하고, **합병/폐업도 보여야** 한다(숨기면 「내 택배사가 왜 없지」가 된다).
    폐업 행은 `coupang_status.selectable=False`로 내려가고 **화면이 회색·선택 불가**로 그린다.
    """
    rows = [_to_payload(entry) for entry in _BUILTIN_ENTRIES]
    if include_dynamic:
        rows.extend(_vendor_rows())
    if include_coupang:
        rows.extend(_coupang_rows())
    merged = _merge_catalog(rows)
    return merged or [_to_payload(entry) for entry in _BUILTIN_ENTRIES]


def _vendor_rows() -> list[dict]:
    """추적 공급사가 주는 택배사 목록 — **지금은 없다**(F44-b).

    예전엔 TrackingMore의 `couriers/all`을 받아 카탈로그를 넓혔다. 그 공급사는
    **무료 쿼터 소진(4190)으로 교체**됐고(병존 금지), 17TRACK의 캐리어 목록은
    문서에 **링크로만** 있어 이 자리에 받아 적을 주소가 없다.

    ★ **짐작한 주소를 박아 두면** 매 요청이 없는 곳을 두드리고, 실패는 조용히 빈 목록이
    된다 — 그건 「목록이 비었다」와 구분되지 않는다. 그래서 **안 부른다.**
    목록 주소가 들어오면 여기에 붙인다(`SEVENTEENTRACK_CARRIER_LIST_URL`).
    """
    return []


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
            "seventeentrack_code": "",    # 이 축은 이 행이 모른다 — 빈칸이 정직하다
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
