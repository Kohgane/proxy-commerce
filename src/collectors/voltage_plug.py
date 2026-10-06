"""Y8 확장(오너 2026-10-05, 실측 667810641388 제습기) — 옵션 값 속 **전압·플러그(지역)** 토큰을 별도 축으로 분리하고
한국 판매 가능 여부를 SKU마다 판정한다(쿠팡 고가네·우주대행 공통 — 판정은 상품 단위, 등록은 `upload_dispatcher`가 거른다).

값 예: 「白色110V台湾美国日本加拿大」 → 색상 「白色」 + 전압/플러그 「110V A형」(판매 제외: 110V 전용).
      「黑色220V 国内用」 → 색상 「黑色」 + 「220V」(등록 가능 · 상세 맨 위 플러그 안내 — `notice_texts`).

토큰(오너 표):
  전압  110V · 220V · 100V · 110-220V·宽电压(겸용 — 숫자 없이 「宽电压」만 적혀도 110-220V)
  플러그 国内用|国标 → CN · 美规|美国|台湾|日本|加拿大 → A형(110V권) · 英规|香港|澳门|英国 → G형 · 澳规|澳洲 → I형 ·
        欧规|欧标|韩国|韩规 → F/C형
판매 필터:
  110V(·100V) 단독 → 「판매 제외: 110V 전용」(100V면 「100V 전용」) · 플러그 G/A/I형 → 「판매 제외: 플러그 규격」
  220V(·겸용) + CN → 등록 가능 + 상세 플러그 안내 · 220V + F/C형 또는 전압 토큰 없음 → 그대로
멀티탭 자체(五孔·国标插座, `ko_polish.cn_plug_hits`)는 별개 규칙 — 여기서 건드리지 않는다.
원래 값 → (나머지 글자, 전압/플러그 값)이 **1:1**일 때만 분리한다. 원본은 `options_src`·`skus_src`(이미 있으면 그대로).
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

AXIS_NAME = "전압/플러그"
_VOLT = re.compile(r"(110\s*[-~/～]\s*220\s*[Vv伏]|(?<!\d)(?:100|110|220)\s*[Vv伏])")
# 숫자 없는 전압 낱말(오너 표) — 값 속에 있으면 그 전압으로 본다. 숫자 토큰(_VOLT)이 함께 있으면 숫자가 먼저.
VOLT_WORDS = (("110-220V", ("宽电压",)),)
PLUGS = (("CN", ("国内用", "国标")),
         ("A", ("美规", "美国", "台湾", "日本", "加拿大")),
         ("G", ("英规", "香港", "澳门", "英国")),
         ("I", ("澳规", "澳洲")),
         ("F/C", ("欧规", "欧标", "韩国", "韩规")))
_PLUG_LABEL = {"CN": "중국 플러그", "A": "A형", "G": "G형", "I": "I형", "F/C": "F/C형"}
EXCLUDED_PLUGS = ("A", "G", "I")
_FILLER = re.compile(r"^[\s用版款型·,，/、+\-]+|[\s用版款型·,，/、+\-]+$")


def _volt_norm(tok: str) -> str:
    t = re.sub(r"\s+", "", tok).upper().replace("伏", "V")
    return "110-220V" if re.match(r"110[-~/～]220", t) else t


def parse(value: str) -> Dict:
    """`{voltage, plug, rest}` — 토큰이 없으면 둘 다 None. 플러그 계열이 둘 이상 섞이면 `plug="혼합"`."""
    s = str(value or "")
    m = _VOLT.search(s)
    voltage = _volt_norm(m.group(0)) if m else None
    rest = _VOLT.sub(" ", s)
    for v, words in VOLT_WORDS:
        for w in sorted(words, key=len, reverse=True):
            if w in rest:
                rest = rest.replace(w, " ")
                voltage = voltage or v
    found = []
    for cls, words in PLUGS:
        for w in sorted(words, key=len, reverse=True):
            if w in rest:
                rest = rest.replace(w, " ")
                if cls not in found:
                    found.append(cls)
    plug = found[0] if len(found) == 1 else ("혼합" if found else None)
    rest = _FILLER.sub("", re.sub(r"\s+", " ", rest)).strip()
    return {"voltage": voltage, "plug": plug, "rest": rest}


def verdict(voltage: Optional[str], plug: Optional[str]) -> Dict:
    """`{sellable, reason, notice}` — 한국(220V · F/C형) 기준."""
    if voltage in ("110V", "100V"):
        return {"sellable": False, "reason": f"판매 제외: {voltage} 전용", "notice": False}
    if plug in EXCLUDED_PLUGS or plug == "혼합":
        return {"sellable": False, "reason": "판매 제외: 플러그 규격", "notice": False}
    return {"sellable": True, "reason": "", "notice": plug == "CN" and voltage in ("220V", "110-220V")}


def _label(p: Dict, full: bool) -> str:
    v, g = p["voltage"], p["plug"]
    if not full and v and g in ("CN", "F/C", None):
        return v                                    # 등록되는 220V는 전압만(지역 토큰 제거 — 오너 지시)
    parts = [x for x in (v, _PLUG_LABEL.get(g, g) if g else None) if x]
    return " ".join(parts) or "기본"


def _vals(o: dict) -> List[str]:
    return [str(v.get("name") if isinstance(v, dict) else v) for v in (o.get("values") or [])]


def apply(extra: dict) -> Optional[Dict]:
    """전압·플러그 토큰이 있는 첫 축을 분리(1:1 검증 통과 시) → 보고 dict. 이미 했거나 대상 없으면 None."""
    if not isinstance(extra, dict) or extra.get("voltage_split"):
        return None
    opts = extra.get("options") if isinstance(extra.get("options"), list) else []
    skus = extra.get("skus") if isinstance(extra.get("skus"), list) else []
    for ai, o in enumerate(opts):
        if not isinstance(o, dict):
            continue
        vals = _vals(o)
        ps = [parse(v) for v in vals]
        if not any(p["voltage"] or p["plug"] for p in ps):
            continue
        rec = {"axis": str(o.get("name") or ""), "values": len(vals), "at": datetime.now(timezone.utc).isoformat()}
        mapping = None
        for full in (False, True):
            tuples = [(p["rest"], _label(p, full)) for p in ps]
            if len(set(tuples)) == len(vals) and len(set(vals)) == len(vals):
                mapping = dict(zip(vals, tuples))
                break
        if mapping is None:
            rec.update(state="none", why="전압·플러그를 떼면 값이 서로 같아져 SKU를 1:1로 못 옮겨요 — 원래대로 뒀어요")
            extra["voltage_split"] = rec
            return rec
        verdicts = {v: verdict(p["voltage"], p["plug"]) for v, p in zip(vals, ps)}
        rests = [mapping[v][0] for v in vals]
        keep_rest = any(rests)
        new_axes = []
        if keep_rest:
            new_axes.append({"name": o.get("name"), **({"name_ko": o["name_ko"]} if o.get("name_ko") else {}),
                             "values": list(dict.fromkeys(r or "기본" for r in rests))})
        labels = list(dict.fromkeys(mapping[v][1] for v in vals))
        new_axes.append({"name": AXIS_NAME, "name_ko": AXIS_NAME, "values": labels, "values_ko": labels})
        new_skus = []
        for k in skus:
            if not isinstance(k, dict):
                new_skus.append(k)
                continue
            spec = list(k.get("spec") or [])
            cur = str(spec[ai]) if ai < len(spec) else ""
            if cur not in mapping:
                rec.update(state="none", why=f"SKU 조합에 축 값이 없어요({cur[:20] or '빈 값'}) — 원래대로 뒀어요")
                extra["voltage_split"] = rec
                return rec
            rest, lab = mapping[cur]
            mid = ([rest or "기본"] if keep_rest else []) + [lab]
            vd = verdicts[cur]
            p = ps[vals.index(cur)]
            nk = dict(k, spec=spec[:ai] + mid + spec[ai + 1:], voltage=p["voltage"] or "", plug=p["plug"] or "")
            nk.pop("sale_excluded", None)
            if not vd["sellable"]:
                nk["sale_excluded"] = vd["reason"]
            if vd["notice"]:
                nk["plug_notice"] = True
            new_skus.append(nk)
        old = [(k.get("price"), k.get("stock")) for k in skus if isinstance(k, dict)]
        new = [(k.get("price"), k.get("stock")) for k in new_skus if isinstance(k, dict)]
        specs = [tuple(k.get("spec") or []) for k in new_skus if isinstance(k, dict)]
        if old != new or len(set(specs)) != len(specs):
            rec.update(state="none", why="분리 뒤 SKU가 원본과 1:1로 맞지 않아(가격·재고 매핑) 원래대로 뒀어요")
            extra["voltage_split"] = rec
            return rec
        extra.setdefault("options_src", copy.deepcopy(opts))
        extra.setdefault("skus_src", copy.deepcopy(skus))
        extra["options"] = opts[:ai] + new_axes + opts[ai + 1:]
        extra["skus"] = new_skus
        excl = [k for k in new_skus if isinstance(k, dict) and k.get("sale_excluded")]
        rec.update(state="split", sellable=len(new_skus) - len(excl), excluded=len(excl),
                   reasons=sorted({k["sale_excluded"] for k in excl}),
                   plug_notice=any(isinstance(k, dict) and k.get("plug_notice") for k in new_skus))
        extra["voltage_split"] = rec
        return rec
    return None


def plug_notice_needed(skus) -> bool:
    """등록 대상(제외 아닌) SKU 중 220V(겸용) + 중국 플러그가 하나라도 있나."""
    return any(isinstance(k, dict) and k.get("plug_notice") and not k.get("sale_excluded") for k in (skus or []))


def drop_excluded(pd: dict) -> dict:
    """등록 사본에서 판매 제외 SKU와 그 SKU만 쓰던 옵션 값을 뺀다. **전부 제외면 그대로**(보류 판정이 사유를 말함),
    「그래도 등록」(`voltage_override`)이면 아무것도 빼지 않는다. 저장값은 건드리지 않는다."""
    skus = [k for k in (pd.get("skus") or []) if isinstance(k, dict)]
    keep = [k for k in skus if not k.get("sale_excluded")]
    if pd.get("voltage_override") or not skus or len(keep) == len(skus) or not keep:
        return pd
    out = dict(pd)
    out["skus"] = keep
    out["skus_excluded"] = [k for k in skus if k.get("sale_excluded")]
    used = [set() for _ in (pd.get("options") or [])]
    for k in keep:
        for i, v in enumerate(k.get("spec") or []):
            if i < len(used):
                used[i].add(str(v))
    opts = []
    for i, o in enumerate(pd.get("options") or []):
        if not isinstance(o, dict):
            opts.append(o)
            continue
        vals = o.get("values") or []
        vko = list(o.get("values_ko") or [])
        idx = [j for j, v in enumerate(vals) if str(v.get("name") if isinstance(v, dict) else v) in used[i]]
        no = dict(o, values=[vals[j] for j in idx])
        if vko:
            no["values_ko"] = [vko[j] for j in idx if j < len(vko)]
        opts.append(no)
    out["options"] = opts
    return out


def hold(pd: dict) -> Optional[Dict[str, str]]:
    """모든 SKU가 판매 제외면 보류 줄(「그래도 등록」 `voltage_override`면 None)."""
    skus = [k for k in (pd.get("skus") or []) if isinstance(k, dict)]
    if not skus or pd.get("voltage_override") or any(not k.get("sale_excluded") for k in skus):
        return None
    reasons = sorted({k["sale_excluded"] for k in skus})
    return {"short": "전압/플러그 불일치", "fix": "voltage",
            "line": f"모든 옵션이 국내(220V·F/C형) 판매 대상이 아니에요 — {' · '.join(reasons)}. 확인했다면 「그래도 등록」"}
