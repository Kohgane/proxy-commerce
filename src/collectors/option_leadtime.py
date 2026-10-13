"""Y7-O(오너 2026-10-12 12:28 KST 그분 폰, 타오바오 ICE 1건) — 옵션 값 끝의 **발송 소요** 토큰을 값에서 떼어 낸다.

실측: 옵션 값 「泡泡粉（2-3周发货）」「黑色（2-3周发货）」 → 번역기 「버블 핑크(2~3주 배송)」 → 숫자 검사가 「2-3」을 「2~3」에서
못 찾아 **5마켓 전부** 보류(「번역기 값이 원문의 영문·숫자(2-3)를 잃었습니다」). 그런데 그 꼬리는 옵션이 아니라 **발송 정보**다 —
옵션 값은 「泡泡粉 → 버블 핑크」만 옮기고, 「2-3周发货」는 `options[i].lead_time`에 둔다(쿠팡 출고소요일·네이버 발송예정일·
사전검증 「선주문」 주의 칩의 재료).

규칙(토큰 표 = `src/uploaders/option_leadtime.json`):
  - 값 끝 괄호(전각·반각) 안 또는 값 끝에 붙은 「N-M周发货」「N天发货」「N周内发货」 → 범위(일). 「预售」 등 → 선주문(일수 모름).
  - 「现货」 등 현재고 표시 → 떼어 내되 발송 소요 아님(선주문 아님).
  - 뗀 뒤 같은 축 값끼리 같아지면(「黑色（现货）」·「黑色（2-3周发货）」) **그 축은 손대지 않는다**(SKU가 섞인다).
  - SKU `spec`도 같은 값으로 바꾼다(1:1 · SKU 수·가격·재고 그대로). 원본은 `options_src`·`skus_src`(이미 있으면 그대로).
"""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

_PATH = Path(__file__).resolve().parents[1] / "uploaders" / "option_leadtime.json"


@lru_cache(maxsize=1)
def table() -> Dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")


def nfkc(s: str) -> str:
    """전각 괄호·숫자·물결 → 반각, 제어문자 → 공백(비교용).

    실측(운영 DB 01f38481, 10-12 수집): 값은 「泡泡粉\x04\x042-3周发货」 — 사이가 괄호가 아니라 **제어문자 0x04 두 개**였다
    (타오바오 ICE의 구분자). 폰이 그걸 □로 그렸다."""
    s = _CTRL.sub(" ", str(s or ""))
    return unicodedata.normalize("NFKC", s).replace("∼", "~").replace("〜", "~")


def _alts(words) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


@lru_cache(maxsize=1)
def _patterns():
    t = table()
    units = _alts(t["units"].keys())
    ship = _alts(t["ship_words"])
    rng = rf"(\d+(?:\.\d+)?)\s*(?:-|~|–|—|至|到|to)\s*(\d+(?:\.\d+)?)\s*({units})\s*(?:{ship})?"
    one = rf"(\d+(?:\.\d+)?)\s*({units})\s*(?:{ship})"
    words = _alts(list(t["presale_words"]) + list(t["stock_words"]))
    body = rf"(?:{rng}|{one}|(?:{words})(?:\s*(?:{rng}|{one}))?)"
    # 값 끝: 괄호로 감싼 꼬리 또는 공백·하이픈 뒤 꼬리
    tail = re.compile(rf"\s*(?:[(\[【]\s*({body})\s*[)\]】]|[\s\-_/]*({body}))\s*$", re.I)
    return tail, re.compile(rng, re.I), re.compile(one, re.I)


def parse(value: str) -> Optional[Dict]:
    """값 → `{core, raw, kind, min_days, max_days}` — 꼬리가 없으면 None. kind: lead(일수 있음)·presale·stock."""
    s = nfkc(value).strip()
    tail, rng, one = _patterns()
    m = tail.search(s)
    if not m:
        return None
    raw = s[m.start():].strip().strip("()[]【】").strip(" -_/").strip()
    core = s[:m.start()].strip()
    if not core:
        return None
    t = table()
    units = t["units"]
    lo = hi = None
    mr = rng.search(raw)
    if mr:
        u = units.get(mr.group(3).lower(), units.get(mr.group(3), 1))
        lo, hi = int(round(float(mr.group(1)) * u)), int(round(float(mr.group(2)) * u))
    else:
        mo = one.search(raw)
        if mo:
            u = units.get(mo.group(2).lower(), units.get(mo.group(2), 1))
            lo = hi = int(round(float(mo.group(1)) * u))
    if lo is not None:
        kind = "lead"
    elif any(w in raw for w in t["presale_words"]):
        kind = "presale"
    else:
        kind = "stock"
    return {"core": core, "raw": raw, "kind": kind, "min_days": lo, "max_days": hi}


def _val(v) -> str:
    return str((v.get("name") if isinstance(v, dict) else v) or "").strip()


def apply(extra: dict) -> Optional[Dict]:
    """`extra`(수집 기록)의 옵션에서 발송 꼬리를 떼어 그 자리에서 바꾼다 → 보고 dict, 대상 없거나 이미 했으면 None."""
    if not isinstance(extra, dict) or (extra.get("option_leadtime") or {}).get("state") == "split":
        return None
    opts = extra.get("options") if isinstance(extra.get("options"), list) else []
    skus = extra.get("skus") if isinstance(extra.get("skus"), list) else []
    new_opts, new_skus, changed_axes = copy.deepcopy(opts), copy.deepcopy(skus), []
    for ai, o in enumerate(opts):
        if not isinstance(o, dict):
            continue
        vals = [_val(v) for v in (o.get("values") or [])]
        parsed = [parse(v) for v in vals]
        if not any(parsed):
            continue
        cores = [p["core"] if p else v for v, p in zip(vals, parsed)]
        if len(set(cores)) != len(cores):
            continue                                              # 떼면 값끼리 같아진다 — SKU가 섞인다, 손대지 않음
        remap = dict(zip(vals, cores))
        ok = True
        for k in new_skus:
            if not isinstance(k, dict):
                continue
            spec = list(k.get("spec") or [])
            if ai < len(spec):
                if str(spec[ai]) not in remap:
                    ok = False
                    break
                spec[ai] = remap[str(spec[ai])]
                k["spec"] = spec
        if not ok:
            new_skus = copy.deepcopy(skus) if not changed_axes else new_skus
            continue
        no = new_opts[ai]
        no["values"] = cores
        vko = list(o.get("values_ko") or [])
        if vko:
            # 번역기 값에도 꼬리가 붙어 있었다(「버블 핑크(2~3주 배송)」) — 핵심만 다시 옮기게 꼬리 붙은 자리는 비운다
            no["values_ko"] = ["" if p else (vko[i] if i < len(vko) else "") for i, p in enumerate(parsed)]
        no["lead_time"] = {c: {k2: p[k2] for k2 in ("raw", "kind", "min_days", "max_days")}
                           for c, p in zip(cores, parsed) if p}
        changed_axes.append(str(o.get("name") or ai))
        # 덮어쓰기(사람이 고친 값)는 원문 열쇠 — 열쇠도 핵심 값으로 옮긴다
        for key in ("option_value_overrides",):
            ov = extra.get(key) if isinstance(extra.get(key), dict) else None
            if ov:
                extra[key] = {remap.get(k2, k2): v2 for k2, v2 in ov.items()}
    if not changed_axes:
        return None
    # 전·후 검증: SKU 수·가격·재고 그대로, 조합 서로 다름
    old = [(k.get("price"), k.get("stock")) for k in skus if isinstance(k, dict)]
    new = [(k.get("price"), k.get("stock")) for k in new_skus if isinstance(k, dict)]
    specs = [tuple(k.get("spec") or []) for k in new_skus if isinstance(k, dict)]
    if old != new or len(set(specs)) != len(specs):
        return None
    extra.setdefault("options_src", copy.deepcopy(opts))
    if skus:
        extra.setdefault("skus_src", copy.deepcopy(skus))
    extra["options"], extra["skus"] = new_opts, new_skus
    rec = {"state": "split", "axes": changed_axes, "at": datetime.now(timezone.utc).isoformat()}
    extra["option_leadtime"] = rec
    return rec


def summary(pd: dict) -> Optional[Dict]:
    """상품 전체의 발송 소요 — `{kind, min_days, max_days, raw, label}`(가장 늦은 값). 없으면 None.
    kind=lead|presale(선주문). 현재고(stock)만 있으면 None."""
    best = None
    pd = pd or {}
    lts = [o.get("lead_time") for o in (pd.get("options") or []) if isinstance(o, dict)]
    lts += list(pd.get("option_lead_time") or [])           # 편집 화면이 보낸 옵션엔 없다 — 저장본에서 붙여 온 것
    for lt in lts:
        if not isinstance(lt, dict):
            continue
        for rec in lt.values():
            if not isinstance(rec, dict) or rec.get("kind") == "stock":
                continue
            if best is None or (rec.get("max_days") or 10 ** 6) > (best.get("max_days") or -1) or best.get("max_days") is None:
                best = dict(rec)
    if not best:
        return None
    lo, hi = best.get("min_days"), best.get("max_days")
    if hi is None:
        best["label"] = "선주문 — 발송일 미상"
    elif lo is not None and lo != hi and lo % 7 == 0 and hi % 7 == 0:
        best["label"] = f"선주문 — 발송 {lo // 7}~{hi // 7}주"
    elif lo is not None and lo != hi:
        best["label"] = f"선주문 — 발송 {lo}~{hi}일"
    else:
        best["label"] = f"선주문 — 발송 {hi}일"
    return best


def market_cap(market: str) -> int:
    base = str(market or "").split(":")[0]
    return int((table().get("max_days") or {}).get(base) or 0)


def days_for(pd: dict, market: str) -> Optional[int]:
    """그 마켓에 보낼 발송 소요(일) — 상한을 넘으면 상한(「그래도 등록」 때만 쓰인다). 발송 소요가 없으면 None."""
    s = summary(pd)
    if not s or s.get("max_days") is None:
        return None
    cap = market_cap(market)
    return min(int(s["max_days"]), cap) if cap else int(s["max_days"])


def caution(pd: dict) -> str:
    s = summary(pd)
    return s["label"] if s else ""


def hold(pd: dict, market: str) -> Optional[Dict[str, str]]:
    """선주문(발송 소요 꼬리) 상품 — 자동 등록 체인에선 **보류**(오너 방침: 선주문은 팔린 브랜드만), 「그래도 등록」으로 푼다.
    마켓 상한(쿠팡 20일·네이버 14일)을 넘으면 그 사실과 원문을 같은 줄에."""
    s = summary(pd)
    if not s or pd.get("lead_time_override"):
        return None
    cap = market_cap(market)
    raw = display(s.get("raw") or "")
    if s.get("max_days") is None:
        line = f"선주문 상품(원문 「{raw}」) — 발송일을 알 수 없어요. 확인했다면 「선주문 그래도 등록」"
    elif cap and s["max_days"] > cap:
        line = (f"선주문 — 발송 최대 {s['max_days']}일(원문 「{raw}」)이 이 마켓 상한 {cap}일을 넘어요. "
                f"「선주문 그래도 등록」하면 {cap}일로 보내요(발송 지연 위험)")
    elif cap:
        line = f"선주문 — 발송 최대 {s['max_days']}일(원문 「{raw}」). 확인했다면 「선주문 그래도 등록」 — 그 일수로 보내요"
    else:
        line = f"선주문 — 발송 최대 {s['max_days']}일(원문 「{raw}」). 확인했다면 「선주문 그래도 등록」"
    return {"short": s["label"], "fix": "lead_time", "line": line}


_HALF = str.maketrans({"（": "(", "）": ")", "［": "[", "］": "]", "｛": "{", "｝": "}", "，": ", ", "：": ":", "；": ";",
                       "！": "!", "？": "?", "～": "~", "　": " ", "／": "/", "－": "-", "＋": "+", "％": "%"})


def display(s: str) -> str:
    """Y7-O 4 — 카드 **표시용** 반각 + 제어문자(타오바오 구분자 0x04 — 폰에서 □)를 「 · 」로. 저장값은 원문 그대로."""
    return re.sub(r"\s*·\s*$", "", _CTRL.sub(" · ", str(s or "")).translate(_HALF))
