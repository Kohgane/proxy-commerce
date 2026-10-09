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


def axis_key(option: Dict) -> str:
    """Y7-I — 축의 **불변 열쇠** = 원래 옵션 이름(원문). 편집 화면은 보이는 이름을 `name`, 원문을 `src_name`에 싣는다."""
    o = option or {}
    return str(o.get("src_name") or o.get("name") or "").strip()


def split_name_overrides(extra: Dict) -> tuple:
    """Y7-I(오너 2026-10-09 23:25 KST 네이버 400 「중복된 옵션 — 색상」) — 저장된 축 이름 덮어쓰기를 **둘로 나눈다**.

    `option_name_overrides` 한 표에 두 가지가 섞여 있었다:
      ① 사람이 옵션 탭에서 고친 **보이는 이름**(Y6-C) — 모든 마켓·화면이 쓴다
      ② 쿠팡 SKU 칸 「메타 속성 고르기」로 고른 **쿠팡 메타 이름**(F51-b-3, 예: 「패션의류/잡화 사이즈」) — 쿠팡만 쓴다
    ②를 네이버 그룹 이름에 쓰면 「패션의류/잡화 사이즈」가 나가고, 열쇠가 원문이 아닌 줄(01:21 「패션의류/잡화 사이즈 → 색상」)은
    보이는 이름으로 찾는 순간 사이즈 축을 「색상」으로 바꿔 네이버가 「중복된 옵션」으로 거부했다.

    반환 `(human, coupang)`. 열쇠가 원래 옵션 이름이 아닌 줄은 **버린다**. ②는 `glossary_candidates`(kind=name)에
    같은 (원문, 값)이 남아 있는 줄 + 새 표 `coupang_option_names`.
    """
    ex = extra or {}
    srcs = {axis_key(o) for o in (ex.get("options") or []) if isinstance(o, dict)} - {""}     # 원문(편집 화면 모양이면 src_name)
    nov = ex.get("option_name_overrides") if isinstance(ex.get("option_name_overrides"), dict) else {}
    picks = {(str(g.get("orig") or ""), str(g.get("value") or "")) for g in (ex.get("glossary_candidates") or [])
             if isinstance(g, dict) and g.get("kind") == "name"}
    human, coupang = {}, {}
    for k, v in nov.items():
        k, v = str(k).strip(), str(v or "").strip()
        if not k or not v or (srcs and k not in srcs):
            continue
        (coupang if (k, v) in picks else human)[k] = v
    cp = ex.get("coupang_option_names") if isinstance(ex.get("coupang_option_names"), dict) else {}
    for k, v in cp.items():
        k, v = str(k).strip(), str(v or "").strip()
        if k and v and (not srcs or k in srcs):
            coupang[k] = v
    return human, coupang


def axis_ko(option: Dict, name_overrides: Dict = None) -> str:
    """축 이름 한국어 — 직접 수정 → 축 용어집(颜色分类→색상) → 번역기 name_ko → 원문.

    Y7-I: 덮어쓰기는 **원래 옵션 이름**(`axis_key`)으로만 찾는다 — 보이는 이름으로 찾으면 다른 축을 가로챈다(Y6-D와 같은 결함).
    """
    from src.uploaders.coupang_options import OPTION_NAME_GLOSSARY
    name = axis_key(option)
    ov = (name_overrides or {}).get(name)
    if str(ov or "").strip():
        return str(ov).strip()
    # 편집 화면 모양(보이는 이름 + src_name) — 사람이 칸에 적은 이름(아직 저장 전일 수 있음)이 원문 해석보다 앞선다
    vis = str((option or {}).get("name") or "").strip() if (option or {}).get("src_name") else ""
    if vis and vis != name and not _cjk(vis):
        return vis
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
    nov, cp = split_name_overrides(product)         # Y7-I: 사람이 고친 보이는 이름만(쿠팡 메타 이름·원문 아닌 열쇠 제외)
    out = []
    for o in product.get("options") or []:
        if not isinstance(o, dict):
            continue
        if o.get("src_name") and str(o.get("name") or "").strip() == cp.get(axis_key(o)):
            # 화면이 보인 이름이 그 축의 **쿠팡 메타 이름**(예전 화면이 섞어 보였다) — 사람이 고친 이름이 아니다
            o = {**o, "name": o["src_name"]}
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
    Y7(2026-10-08): 네이버 조합형 옵션(`naver_options.plan`)이 이 사슬(`options_view`·`spec_ko`)로 그룹 이름·값을 낸다."""
    return [{"group": a["name_ko"], "values": [v["ko"] or v["src"] for v in a["values"]]} for a in options_view(product)]
