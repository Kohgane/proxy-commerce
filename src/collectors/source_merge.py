"""F49-T 2부-c — 같은 상품을 다시 받았을 때 **소스 우선순위**로 병합한다.

실측(2026-09-27 03:21Z, ext 1.5.156, 티몰 617129397971): 확장 페이로드는 정상이었다(SKU 10·옵션 1그룹·
가격 29.90, field_sources 전부 ice_context). 그런데 초안은 tier2 잡음 옵션(17/13/12/11)·가격 없음 그대로였다.
이미 보강이 끝난(`enrich_state=done`) 행이라 수집 라우트가 「이미 수집한 상품」으로 돌려보내며 **아무것도 쓰지
않았고**, 보강 라우트(`/enrich`)도 「빈 칸만 채움」이라 상위 소스가 하위 소스를 못 이겼다.

규칙(한 곳):
  - 필드마다 저장된 출처(`extra.field_sources[f]`)와 들어온 출처의 순위를 비교한다.
    ice_context(4) > tier1·json·adapter·buybox(3) > tier2·dom(2) > ldjson·tier3·og·server·출처 기록 없음(1) > none(0)
  - 저장 값이 비었으면 채운다. 들어온 순위가 **더 높으면** 덮는다. 재수집(`force`)은 **같은 순위도** 덮는다.
  - 오너가 드로어에서 손으로 고친 필드(`extra.manual_fields`)는 **어떤 경우에도** 건드리지 않는다.
  - 무엇을 바꾸고 무엇을 남겼는지 `extra.merge_log`(최근 5건)에 남긴다 — 드로어가 그대로 보여 준다.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

RANK = {
    "ice_context": 4,
    "tier1": 3, "json": 3, "adapter": 3, "buybox": 3, "network": 3,
    "tier2": 2, "dom": 2,
    "ldjson": 1, "tier3": 1, "og": 1, "meta": 1, "server": 1, "": 1,
    "none": 0,
}
# 드로어 표기(사람 말). 저장 값 그대로가 아니라 이 라벨로 보인다.
LABEL = {
    "ice_context": "티몰 상태(ICE)", "tier1": "페이지 데이터", "json": "페이지 데이터",
    "adapter": "사이트 규칙", "buybox": "사이트 규칙", "network": "페이지 데이터",
    "tier2": "화면 읽기", "dom": "화면 읽기", "ldjson": "메타 태그", "tier3": "메타 태그", "og": "메타 태그",
    "meta": "메타 태그", "server": "서버 파싱", "": "출처 기록 없음", "none": "없음", "manual": "직접 수정",
}

# 병합 단위 필드 → extra 키(함께 움직이는 값). 출처 키는 확장 field_sources와 같다.
FIELD_KEYS = {
    "title": ("title",),
    "price": ("price", "currency"),
    "images": ("images", "gallery_images"),
    "options": ("options",),
    "sku": ("skus",),
    "description": ("description",),
    "detail_images": ("detail_images",),
}
FIELD_LABEL = {"title": "제목", "price": "가격", "images": "갤러리", "options": "옵션", "sku": "SKU",
               "description": "상세설명", "detail_images": "상세이미지"}


def rank(src) -> int:
    return RANK.get(str(src or "").strip().lower(), 1)


def label(src) -> str:
    return LABEL.get(str(src or "").strip().lower(), str(src or "") or LABEL[""])


def _empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip() or v.strip() in ("0", "0.0", "0.00")
    if isinstance(v, (list, tuple, dict)):
        return len(v) == 0
    return False


def _now() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def merge_by_source(extra: Dict[str, Any], incoming: Dict[str, Any], sources: Optional[Dict[str, Any]],
                    *, force: bool = False, path: str = "") -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
    """`incoming`(필드키 → 값; price는 {"price","currency"}처럼 extra 키로)을 `extra`에 병합한다.

    Returns: (extra, changed{field: "이전 출처→새 출처"}, kept{field: 사유})
    `incoming`에 없는 필드는 보지 않는다. 값이 빈 필드는 절대 덮지 않는다(비파괴).
    """
    extra = extra if isinstance(extra, dict) else {}
    sources = sources if isinstance(sources, dict) else {}
    stored_src = extra.get("field_sources") if isinstance(extra.get("field_sources"), dict) else {}
    manual = extra.get("manual_fields") if isinstance(extra.get("manual_fields"), dict) else {}
    changed: Dict[str, str] = {}
    kept: Dict[str, str] = {}
    for field, keys in FIELD_KEYS.items():
        if keys[0] not in incoming:
            continue
        new_val = incoming.get(keys[0])
        if _empty(new_val):
            continue
        new_src = str(sources.get(field) or "").strip().lower()
        old_src = str(stored_src.get(field) or "").strip().lower()
        old_val = extra.get(keys[0])
        if field in manual:
            if old_val != new_val:
                kept[field] = "직접 수정한 값이라 유지"
            continue
        if _empty(old_val):
            why = "빈 칸 채움"
        elif rank(new_src) > rank(old_src):
            why = "상위 출처"
        elif force and rank(new_src) >= rank(old_src):
            why = "다시 수집"
        else:
            if old_val != new_val:
                kept[field] = f"기존 출처({label(old_src)})가 같거나 높음"
            continue
        if old_val == new_val and old_src == new_src:
            continue
        for k in keys:
            if k in incoming and not _empty(incoming.get(k)):
                extra[k] = incoming[k]
        if new_src or old_src:
            fs = dict(stored_src)
            fs[field] = new_src
            extra["field_sources"] = stored_src = fs
        changed[field] = f"{label(old_src) if not _empty(old_val) else '비어 있음'}→{label(new_src)} ({why})"
    if changed or kept:
        log: List[Dict[str, Any]] = list(extra.get("merge_log") or [])[-4:]
        log.append({"at": _now(), "path": path, "changed": changed, "kept": kept})
        extra["merge_log"] = log
    return extra, changed, kept


def incoming_from_payload(p: Dict[str, Any], *, images=None, title_ko: str = "") -> Dict[str, Any]:
    """수집/보강 본문 → 병합 입력(extra 키). 없는 필드는 싣지 않는다."""
    out: Dict[str, Any] = {}
    if p.get("title"):
        out["title"] = p.get("title")
    if str(p.get("price") or "").strip():
        out["price"] = str(p.get("price")).strip()
        if p.get("currency"):
            out["currency"] = p.get("currency")
    imgs = images if images is not None else (p.get("gallery") or p.get("gallery_images") or p.get("images"))
    if isinstance(imgs, list) and imgs:
        out["images"] = list(imgs)
        out["gallery_images"] = list(imgs)
    for k_in, k_out in (("options", "options"), ("skus", "skus"), ("detail_images", "detail_images")):
        v = p.get(k_in)
        if isinstance(v, list) and v:
            out[k_out] = v
    d = str(p.get("description") or "").strip()
    if len(d) >= 20:
        out["description"] = d
    return out


def mark_manual_edits(extra: Dict[str, Any], edited: Dict[str, Any]) -> List[str]:
    """드로어 저장 — **값이 실제로 바뀐** 필드만 직접 수정으로 표시한다(폼이 통째로 와도 오탐 0)."""
    manual = dict(extra.get("manual_fields") or {}) if isinstance(extra.get("manual_fields"), dict) else {}
    marked = []

    def _norm_price(v):
        try:
            return round(float(str(v).replace(",", "").strip()), 4)
        except Exception:
            return str(v or "").strip()

    def _norm_opts(v):
        out = []
        for o in (v or []):
            if isinstance(o, dict):
                out.append((str(o.get("name") or "").strip(),
                            tuple(str(x.get("name") if isinstance(x, dict) else x).strip() for x in (o.get("values") or []))))
        return out

    checks = {
        "title": (lambda: str(edited.get("title") or "").strip(),
                  lambda: str(extra.get("title_ko") or extra.get("title") or "").strip()),
        "price": (lambda: _norm_price(edited.get("price")), lambda: _norm_price(extra.get("price"))),
        "options": (lambda: _norm_opts(edited.get("options")), lambda: _norm_opts(extra.get("options"))),
        "description": (lambda: str(edited.get("description") or "").strip(),
                        lambda: str(extra.get("description_ko") or extra.get("description") or "").strip()),
        "images": (lambda: [str(u).strip() for u in (edited.get("images") or [])],
                   lambda: [str(u).strip() for u in (extra.get("images") or [])]),
    }
    for field, (new_f, old_f) in checks.items():
        if edited.get(field) is None:
            continue
        if field == "title" and not new_f():
            continue
        if field == "price" and new_f() in ("", None):
            continue
        if new_f() != old_f():
            manual[field] = _now()
            marked.append(field)
    if marked:
        extra["manual_fields"] = manual
    return marked
