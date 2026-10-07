"""Y6-C(오너 2026-10-07): 옵션 한국어 — **한 함수**.

실측(「플리츠 미니멀 여성 여름 세트」, SKU 8): 옵션칸은 원문(黑色上衣…) + 힌트 줄은 번역기 값(「검은색 상의 · 이끼색 상의」),
쿠팡 SKU는 용어집·정리 규칙 값(「블랙 상의 · 모스 그린 상의」) — 두 경로가 서로 다른 소스를 읽었다:
힌트 줄 = `values_ko`(번역기 원문 그대로), 쿠팡 = `coupang_options.resolve_option_value`(직접 수정 → 용어집 → 용어집 조각 →
정리 규칙 → 번역기). 이제 옵션칸·SKU 조합표·쿠팡 SKU·네이버 옵션 값이 전부 여기(= `resolve_option_value` 한 사슬)를 지난다.
원문(`values`·SKU `spec`)은 데이터에 그대로 둔다(주문 때 타오바오 대조용) — 화면엔 「원문 보기」로만.
"""
from __future__ import annotations

from typing import Dict, List

_CJK_RE = None


def _cjk(s: str) -> bool:
    global _CJK_RE
    if _CJK_RE is None:
        import re
        _CJK_RE = __import__("re").compile(r"[぀-ヿ㐀-鿿豈-﫿]")
    return bool(_CJK_RE.search(str(s or "")))


def _val(v) -> str:
    return str(v.get("name") if isinstance(v, dict) else (v or "")).strip()


def axis_ko(option: Dict, name_overrides: Dict = None) -> str:
    """축 이름 한국어 — 직접 수정 → 축 용어집(颜色分类→색상) → 번역기 name_ko → 원문."""
    from src.uploaders.coupang_options import OPTION_NAME_GLOSSARY
    name = str((option or {}).get("name") or "").strip()
    ov = (name_overrides or {}).get(name)
    if str(ov or "").strip():
        return str(ov).strip()
    if name in OPTION_NAME_GLOSSARY:
        return OPTION_NAME_GLOSSARY[name]
    nk = str((option or {}).get("name_ko") or "").strip()
    if nk and not _cjk(nk):
        return nk
    return name


def value_ko(value: str, *, values_ko: str = "", override: str = "") -> Dict:
    """값 하나 — `{value, how, confirm, why}`(value가 비면 못 옮김, why가 사유). 사슬은 쿠팡 등록과 같다."""
    from src.uploaders.coupang_options import resolve_option_value
    return resolve_option_value(value, values_ko=values_ko, override=override)


def _overrides(product: Dict) -> Dict[str, str]:
    ov = product.get("option_value_overrides")
    return {str(k): str(v) for k, v in ov.items()} if isinstance(ov, dict) else {}


def options_view(product: Dict) -> List[Dict]:
    """화면용 — 축마다 `{name, name_ko, values: [{src, ko, how, confirm, why}]}`. `ko`가 비면 원문을 그대로 둔다."""
    from src.uploaders.coupang_options import value_ko_map
    vko = value_ko_map(product)
    ov = _overrides(product)
    nov = product.get("option_name_overrides") if isinstance(product.get("option_name_overrides"), dict) else {}
    out = []
    for o in product.get("options") or []:
        if not isinstance(o, dict):
            continue
        vals = []
        for v in o.get("values") or []:
            src = _val(v)
            r = value_ko(src, values_ko=vko.get(src, ""), override=ov.get(src, ""))
            vals.append({"src": src, "ko": r["value"] or "", "how": r["how"], "confirm": bool(r["confirm"]),
                         "why": r["why"]})
        out.append({"name": str(o.get("name") or ""), "name_ko": axis_ko(o, nov), "values": vals})
    return out


def spec_ko(product: Dict, spec: List[str]) -> List[str]:
    """SKU 조합 한 줄 — 원문 조각마다 같은 사슬. 못 옮긴 조각은 원문 그대로(가짜 번역 0)."""
    from src.uploaders.coupang_options import value_ko_map
    vko = value_ko_map(product)
    ov = _overrides(product)
    out = []
    for s in spec or []:
        src = str(s or "").strip()
        r = value_ko(src, values_ko=vko.get(src, ""), override=ov.get(src, ""))
        out.append(r["value"] or src)
    return out


def naver_option_values(product: Dict) -> List[Dict]:
    """네이버 옵션 값(조합형 그룹 이름·값) — 같은 사슬. `[{group, values}]`.
    ※ 2026-10-07 현재 네이버 등록 몸통엔 옵션 칸(optionInfo)이 없다(단일 SKU로 올림) — 붙일 때 이 값을 쓴다."""
    return [{"group": a["name_ko"], "values": [v["ko"] or v["src"] for v in a["values"]]} for a in options_view(product)]
