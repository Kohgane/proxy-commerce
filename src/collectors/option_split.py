"""Y8(오너 2026-10-04 20:44 실측, 티몰 JOYE 멀티탭) — 광고문형 옵션 값을 **축으로 분해**한다.

증상: 축 「颜色」 하나에 값 12개, 값마다 「✅弹簧线ꙮPD65W快充✅双层粘夹白色【7五孔+1A1C】⭐升降桌专用款⭐」 —
번역은 되지만 30자를 넘어 미해석 보류, 줄이면(정리 규칙) 「2단 클램프 화이트」처럼 **SKU끼리 같은 값**이 돼 가격이 섞인다.

순서:
1. 정리 — 장식 기호(✅⭐ꙮ★…)·괄호(【】[]())·광고 꼬리(升降桌专用款·新品…) 제거.
2. 분해 — 색상(黑/白/曜石黑…) · 구성(N五孔 → N구, NA1C, 抽拉线 → 인출선) · 출력(PD65W·20W) · 케이블(弹簧线 → 스프링 / 없으면 일반)
   · 길이(1.8米 → 1.8m). 값마다 다른 축만 남긴다. **원래 값 → 분해 결과가 1:1**(서로 다른 값이 같은 조합이 되면 안 됨)일 때만 채택.
3. 안 되면 축소 — 색상 · 구성 · 출력만 이어 한 값(30자 이내)으로. 그것도 겹치거나 넘치면 **손대지 않는다**(보류 문구가 사유를 말한다).

SKU는 값 → 조합 표로 옮긴다. 가격·재고·SKU 수는 그대로여야 하며(검증), 하나라도 어긋나면 원래대로 둔다.
원본은 `options_src`·`skus_src`에 남긴다(되돌리기·감사용).
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

MAX = 30
_SYMBOLS = re.compile("[✀-➿☀-⛿⬀-⯿Ꙁ-ꚟ\U0001F300-\U0001FAFF★☆●○◆◇■□▲△▼▽◎※√✔✓❗❕‼！~～|｜]+")
_BRACKETS = re.compile(r"[【】\[\]()（）「」『』<>《》]")
AD_TAILS = ("升降桌专用款", "专用款", "新品", "新款", "爆款", "热卖", "推荐", "限时", "特价", "官方正品", "正品", "现货", "包邮")

# 색상 — 긴 낱말부터(曜石黑이 黑보다 먼저)
COLORS = (("曜石黑", "오닉스 블랙"), ("磨砂黑", "매트 블랙"), ("象牙白", "아이보리"), ("黑色", "블랙"), ("白色", "화이트"),
          ("灰色", "그레이"), ("银色", "실버"), ("金色", "골드"), ("粉色", "핑크"), ("蓝色", "블루"), ("绿色", "그린"),
          ("红色", "레드"), ("黑", "블랙"), ("白", "화이트"), ("灰", "그레이"), ("粉", "핑크"), ("蓝", "블루"))
AXES = (("color", "색상"), ("config", "구성"), ("power", "출력"), ("cable", "케이블"), ("length", "길이"))
_MISSING = {"cable": "일반", "length": "기본", "config": "기본", "power": "기본", "color": "기본"}


def clean(value: str) -> str:
    s = _SYMBOLS.sub(" ", str(value or ""))
    s = _BRACKETS.sub(" ", s)
    for w in AD_TAILS:
        s = s.replace(w, " ")
    return re.sub(r"\s+", " ", s).strip()


def facets(value: str) -> Dict[str, Optional[str]]:
    s = clean(value)
    out: Dict[str, Optional[str]] = {k: None for k, _n in AXES}
    for cn, ko in COLORS:
        if cn in s:
            out["color"] = ko
            break
    parts = []
    m = re.search(r"(\d+)\s*(?:五孔|插孔|孔位|位)", s)
    if m:
        parts.append(f"{m.group(1)}구")
    m = re.search(r"(\d+)\s*A\s*(\d+)\s*C", s, re.I)
    if m:
        parts.append(f"{m.group(1)}A{m.group(2)}C")
    else:
        m = re.search(r"(?<![A-Za-z\d])(\d+)\s*C(?![A-Za-z])", s)
        if m:
            parts.append(f"{m.group(1)}C")
    if "抽拉线" in s:
        parts.append("인출선")
    out["config"] = "+".join(parts) or None
    m = re.search(r"PD\s*(\d+)\s*W", s, re.I) or re.search(r"(?<![A-Za-z\d])(\d+)\s*W(?![A-Za-z])", s)
    if m:
        out["power"] = ("PD" if m.group(0).upper().startswith("PD") else "") + f"{m.group(1)}W"
    out["cable"] = "스프링" if "弹簧线" in s else None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:米|m(?![A-Za-z]))", s)
    out["length"] = f"{m.group(1)}m" if m else None
    return out


def split_values(values: List[str]) -> Dict:
    """`{state: split|compact|none, axes: [(축 이름, [값별 결과])], map: {원래 값: (조합)}, why}`."""
    vals = [str(v) for v in values]
    if len(set(vals)) != len(vals) or len(vals) < 2:
        return {"state": "none", "why": "값이 2개 미만이거나 같은 값이 겹쳐 있어요"}
    fs = [facets(v) for v in vals]
    axes = []
    for key, name in AXES:
        col = [f[key] for f in fs]
        if not any(col):
            continue
        col = [c or _MISSING[key] for c in col]
        if len(set(col)) > 1:
            axes.append((name, col))
    tuples = list(zip(*[c for _n, c in axes])) if axes else []
    if len(axes) >= 2 and len(set(tuples)) == len(vals) and all(len(x) <= MAX for _n, c in axes for x in c):
        return {"state": "split", "axes": axes, "map": dict(zip(vals, tuples)), "why": ""}
    # 축소: 색상 · 구성 · 출력만 이어 한 값으로
    comp = [" · ".join(x for x in (f["color"], f["config"], f["power"]) if x) for f in fs]
    if all(comp) and len(set(comp)) == len(vals) and all(len(c) <= MAX for c in comp):
        return {"state": "compact", "axes": [("옵션", comp)], "map": {v: (c,) for v, c in zip(vals, comp)}, "why": ""}
    dup = len(vals) - len(set(tuples)) if axes else len(vals)
    return {"state": "none", "why": f"분해해도 값 {dup}개가 다른 값과 같은 조합이 돼 SKU를 1:1로 못 옮겨요(가격이 섞임)"}


def _needs(o: dict) -> bool:
    vals = [str(v.get("name") if isinstance(v, dict) else v) for v in (o.get("values") or [])]
    return len(vals) >= 2 and any(len(clean(v)) > MAX or _SYMBOLS.search(v) or "【" in v for v in vals)


def apply(extra: dict) -> Optional[Dict]:
    """광고문형 축이 있으면 그 자리에서 분해(검증 통과 시) → 보고 dict. 이미 했거나 대상 없으면 None."""
    if not isinstance(extra, dict) or extra.get("option_split"):
        return None
    opts = extra.get("options") if isinstance(extra.get("options"), list) else []
    skus = extra.get("skus") if isinstance(extra.get("skus"), list) else []
    for ai, o in enumerate(opts):
        if not (isinstance(o, dict) and _needs(o)):
            continue
        vals = [str(v.get("name") if isinstance(v, dict) else v) for v in (o.get("values") or [])]
        r = split_values(vals)
        rec = {"state": r["state"], "axis": str(o.get("name") or ""), "values": len(vals),
               "at": datetime.now(timezone.utc).isoformat(), "why": r.get("why", "")}
        if r["state"] == "none":
            extra["option_split"] = rec
            return rec
        new_opts = opts[:ai] + [{"name": n, "name_ko": n, "values": list(dict.fromkeys(c)), "values_ko": list(dict.fromkeys(c))}
                                for n, c in r["axes"]] + opts[ai + 1:]
        new_skus, ok = [], True
        for k in skus:
            if not isinstance(k, dict):
                new_skus.append(k)
                continue
            spec = list(k.get("spec") or [])
            if ai >= len(spec) or str(spec[ai]) not in r["map"]:
                ok = False
                break
            new_skus.append(dict(k, spec=spec[:ai] + list(r["map"][str(spec[ai])]) + spec[ai + 1:]))
        # 검증 — SKU 수·가격·재고 그대로, 새 조합이 서로 다름
        if ok:
            old = [(k.get("price"), k.get("stock")) for k in skus if isinstance(k, dict)]
            new = [(k.get("price"), k.get("stock")) for k in new_skus if isinstance(k, dict)]
            specs = [tuple(k.get("spec") or []) for k in new_skus if isinstance(k, dict)]
            ok = old == new and len(set(specs)) == len(specs)
        if not ok:
            rec.update(state="none", why="분해 뒤 SKU가 원본과 1:1로 맞지 않아(가격·재고 매핑) 원래대로 뒀어요")
            extra["option_split"] = rec
            return rec
        extra["options_src"] = copy.deepcopy(opts)
        extra["skus_src"] = copy.deepcopy(skus)
        extra["options"], extra["skus"] = new_opts, new_skus
        rec["axes"] = [n for n, _c in r["axes"]]
        extra["option_split"] = rec
        return rec
    return None


def cap_axes(product: dict, limit: int = 3) -> dict:
    """쿠팡 옵션 속성 3개 제한(볼트 지뢰) — 분해로 축이 넘치면 3번째부터 「사양」 한 축으로 잇는다(30자·1:1일 때만).
    못 이으면 그대로(쿠팡 계획이 「3개 초과」로 보류한다). 원본 dict는 건드리지 않는다."""
    opts = product.get("options") if isinstance(product.get("options"), list) else []
    if len(opts) <= limit or not (product.get("option_split") or {}).get("axes"):
        return product
    head = limit - 1
    skus = [k for k in (product.get("skus") or []) if isinstance(k, dict)]
    merged = [" · ".join(str(x) for x in (k.get("spec") or [])[head:]) for k in skus]
    specs = [tuple((k.get("spec") or [])[:head]) + (m,) for k, m in zip(skus, merged)]
    if not merged or any(len(m) > MAX for m in merged) or len(set(specs)) != len(specs):
        return product
    out = dict(product)
    out["options"] = opts[:head] + [{"name": "사양", "name_ko": "사양", "values": list(dict.fromkeys(merged)),
                                     "values_ko": list(dict.fromkeys(merged))}]
    out["skus"] = [dict(k, spec=list(s)) for k, s in zip(skus, specs)]
    return out
