"""Y10(오너 2026-10-13) 리스크 게이트 — 「상품 뭐에 걸릴 거 같으면 다 빼자. 사전검증에서 체크해서 유저한테 확인시키고 선택권을 주자.」

실측: VRSUK 라운지체어 4ebaf1b8 — 원문 상세(리뷰 「伊姆斯躺椅」·참수 型号 「伊姆斯躺椅-油蜡皮」)·검색어(「이임스」「Eames」)·
사진 속 글자(갤러리 3·4 「Zaha Hadid」, 상세 8 「Eames Chair」)에 디자인 상표가 있었는데 예전 게이트는 통과시켰다
(상품명에서만 지웠고, 사진·검색어·참수는 안 봤다).

여기 있는 것:
- `scan(extra)` — 상품명·검색어·옵션·본문·참수·고시(브랜드)·사진 속 글자(갤러리·상세 OCR) 전부를 본다 →
  `{hits:[{key, cat, label, grade, found, where, images, decided}], waiting}`. 등급: block 차단 · hold 보류 · caution 주의.
  a 상표·캐릭터·디자인(`src/uploaders/risk_tokens.json` + `ko_polish_rules.json` trademarks의 replica·ip·drop)
  b 레플리카 신호(复刻·同款·平替·1:1…)가 a와 같이 나오면 「레플리카 의심」
  c 브랜드 블랙리스트(COUPANG_BLACKLIST85 · 소싱 판정과 같은 로더) — 허용 목록은 통과
  d 인증(의약품·의료기기=차단 / 전기 KC·어린이·전파·수입식품=보류 / 건기식·화장품=주의: 인허가 보유)
  e 표시광고 과장(Y7-J `ban_hits`) — 주의(보류는 기존 Y7-J가 마켓 판정에서 따로 건다)
- `holds(scan)` — 사전검증 보류 줄(결정 안 된 보류·차단 · 이미지 검사 대기).
- `apply(extra, key, action)` — 「빼고 등록」(낱말 제거 + 걸린 사진 제외) · 「그래도 등록」(기록) · 「등록 안 함」.
- 학습: 같은 낱말에 「그래도 등록」 2번이면 허용 후보(설정에서 확정) · 「빼고 등록」은 그 낱말의 기본 동작으로 기억(다음 상품은 자동으로 뺀다).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_TOKENS_FILE = Path(__file__).resolve().parents[1] / "uploaders" / "risk_tokens.json"
_HANGUL = "가-힣"
_CJK = re.compile("[㐀-䶿一-鿿]")
_LEARN_KEY = "risk_gate:learn"            # {key: {allow: n, default: "strip"}}
_ALLOW_KEY = "risk_gate:allow"            # {"labels": [...]} — 오너가 설정에서 확정한 허용
GRADE_ORDER = {"block": 0, "hold": 1, "caution": 2}
GRADE_LABEL = {"block": "차단", "hold": "보류", "caution": "주의"}
_cache: dict = {"at": 0.0, "t": None}


def tokens() -> dict:
    now = time.monotonic()
    if _cache["t"] is not None and now - _cache["at"] < 60:
        return _cache["t"]
    t = json.loads(_TOKENS_FILE.read_text(encoding="utf-8"))
    _cache.update(at=now, t=t)
    return t


def _pat(name: str, case: bool = False) -> "re.Pattern":
    esc = re.escape(name)
    if _CJK.search(name):
        return re.compile(esc)
    if re.search(f"[{_HANGUL}]", name):
        return re.compile(f"(?<![{_HANGUL}]){esc}")
    if re.fullmatch(r"[A-Za-z][A-Za-z .'&èé-]*", name):
        return re.compile(rf"(?<![A-Za-z]){esc}(?![A-Za-z])", 0 if case else re.I)
    return re.compile(esc, 0 if case else re.I)


def _find(text: str, names, case=False) -> List[str]:
    out = []
    for n in names or []:
        if n and _pat(n, case).search(text or ""):
            out.append(n)
    return out


def _count(text: str, names, case=False) -> int:
    return sum(len(_pat(n, case).findall(text or "")) for n in names or [] if n)


def _state():
    from src.db import image_translate_queue_pg as st
    return st


def allowlist() -> set:
    out = set(tokens().get("allow") or [])
    try:
        out |= set((_state().state_get(_ALLOW_KEY) or {}).get("labels") or [])
    except Exception:                                              # noqa: BLE001
        pass
    return out


def learned() -> dict:
    try:
        return dict((_state().state_get(_LEARN_KEY) or {}).get("keys") or {})
    except Exception:                                              # noqa: BLE001
        return {}


# ── 검사 대상 ──────────────────────────────────────────────────────────────────────────────

def _split_desc(desc: str):
    """원문 상세 → (본문, 참수). 타오바오 「参数信息」 블록(마지막 것 — 맨 위 탭 머리는 빈 칸)은 참수."""
    d = str(desc or "")
    i = d.rfind("参数信息")
    if i < 0:
        return d, ""
    j = d.find("图文详情", i)
    j = len(d) if j < 0 else j
    return d[:i] + d[j:], d[i:j]


def fields(extra: dict) -> Dict[str, str]:
    """위치 이름 → 글자. 상품명은 **보내는 것**(한국어·쿠팡명)만 — 원문 제목은 안 보낸다(번역 때 이미 지운 상표를 다시 세지 않음)."""
    ex = extra or {}
    opts = []
    for o in ex.get("options") or []:
        if isinstance(o, dict):
            opts += [str(o.get("name_ko") or ""), str(o.get("name") or "")]
            opts += [str(v) for v in (o.get("values_ko") or []) + (o.get("values") or [])]
    opts += [str(v) for v in (ex.get("option_value_overrides") or {}).values()] if isinstance(ex.get("option_value_overrides"), dict) else []
    body_src, spec_src = _split_desc(ex.get("description") or "")
    # 몸통의 description_ko는 번역이 없으면 원문 복사본이다 — 같은 글을 두 번 세지 않는다
    _dko = "" if str(ex.get("description_ko") or "").strip() == str(ex.get("description") or "").strip() else ex.get("description_ko")
    body_ko, spec_ko = _split_desc(_dko or "")
    da = ex.get("detail_auto") if isinstance(ex.get("detail_auto"), dict) else {}
    specs = " ".join(f"{k} {v}" for kv in (ex.get("detail_specs") or []) if isinstance(kv, (list, tuple)) and len(kv) == 2
                     for k, v in [kv])
    return {
        "상품명": " ".join(dict.fromkeys(str(ex.get(k) or "") for k in ("title_ko", "coupang_name"))),   # 쿠팡명 = 상품명이면 한 번
        "검색어": " ".join(dict.fromkeys(str(x) for x in list(ex.get("keywords") or []) + list(ex.get("tags") or []))),
        "옵션": "\n".join(opts),
        "본문": "\n".join([body_ko, body_src, str(da.get("text") or "")]),
        "참수": "\n".join([spec_ko, spec_src, specs]),
        "고시": str(ex.get("brand") or ""),
    }


def _images(extra: dict):
    """`[(kind, idx, 이름, 글자)]` — 번역 기록이 있는 장(OCR·원문·번역문)."""
    from src.services.detail_image_plan import entry_text
    out = []
    for key, kind, lab in (("images_ko", "gallery", "사진"), ("detail_images_ko", "detail", "상세")):
        for e in (extra or {}).get(key) or []:
            if isinstance(e, dict) and e.get("idx") is not None and not e.get("risk_exclude"):   # 이미 뺀 장은 안 센다
                t = entry_text(e)
                if t.strip():
                    out.append((kind, int(e["idx"]), f"{lab} {int(e['idx']) + 1}", t))
    return out


# ── 검사 ───────────────────────────────────────────────────────────────────────────────────

def _trademark_entries() -> List[dict]:
    t = tokens()
    ents = [dict(e, grade="hold") for e in (t.get("trademark") or [])]
    have = {e["label"] for e in ents}
    try:
        from src.collectors import ko_polish as kp
        for e in kp.rules().get("trademarks") or []:
            if e.get("mode") in ("replica", "ip", "drop") and e.get("label") not in have:
                ents.append({"label": e.get("label"), "kind": {"ip": "캐릭터", "replica": "디자인"}.get(e.get("mode"), "상표"),
                             "names": list(e.get("names") or []), "grade": "hold"})
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("[리스크] 상표 표 읽기 실패: %s", exc)
    return ents


def _blacklist() -> List[str]:
    try:
        from src.pipeline.coupang_replicate import load_blacklist85
        return [str(x) for x in (load_blacklist85().get("terms") or []) if str(x).strip()]
    except Exception:                                              # noqa: BLE001
        return []


def _hit(key, cat, label, grade, names, case, where_text, imgs, why="") -> Optional[dict]:
    where, found = {}, []
    for w, txt in where_text.items():
        n = _count(txt, names, case)
        if n:
            where[w] = n
            found += _find(txt, names, case)
    images = []
    for kind, idx, nm, txt in imgs:
        f = _find(txt, names, case)
        if f:
            images.append({"kind": kind, "idx": idx, "name": nm})
            found += f
    if not where and not images:
        return None
    return {"key": key, "cat": cat, "label": label, "grade": grade, "names": list(names), "case": case,
            "found": list(dict.fromkeys(found)), "where": where, "images": images, "why": why}


def scan(extra: dict, *, pending_images: int = 0) -> dict:
    """한 상품 전부 — `{hits, waiting, decided}`. `pending_images` = 아직 번역(OCR) 중인 장 수(「이미지 검사 대기 n장」)."""
    ex = extra or {}
    where_text = fields(ex)
    imgs = _images(ex)
    allow = allowlist()
    hits: List[dict] = []
    tm_hits = []
    for e in _trademark_entries():
        if e["label"] in allow:
            continue
        h = _hit("tm:" + e["label"], f"상표/{e.get('kind') or '상표'}", e["label"], "hold", e.get("names") or [],
                 bool(e.get("case")), where_text, imgs, "상표권자 신고 대상 — 정품·라이선스가 아니면 빼고 등록하세요")
        if h:
            tm_hits.append(h)
    hits += tm_hits
    if tm_hits:                                                    # b: 레플리카 신호가 상표와 같이 나오면
        sig = _hit("replica", "레플리카 의심", "레플리카 의심", "hold", tokens().get("replica_signals") or [], False,
                   where_text, imgs, "상표 + 「复刻·同款·平替·1:1·스타일」 — 모조품 신고 대상")
        if sig:
            sig["with"] = [h["label"] for h in tm_hits]
            hits.append(sig)
    bl = [t for t in _blacklist() if t not in allow]
    if bl:
        h = _hit("blacklist", "브랜드 블랙리스트", "브랜드 블랙리스트", "hold", bl, False, where_text, imgs,
                 "등록 금지 브랜드 목록에 있는 이름")
        if h:
            hits.append(h)
    shadowed = set()
    certs = []
    for c in tokens().get("cert") or []:
        if c["label"] in allow:
            continue
        h = _hit("cert:" + c["key"], c["label"], c["label"], c.get("grade") or "hold", c.get("names") or [], False,
                 where_text, imgs, c.get("why") or "")
        if h:
            certs.append(h)
            shadowed |= set(c.get("shadows") or [])
    hits += [h for h in certs if h["key"].split(":", 1)[1] not in shadowed]
    try:                                                           # e: 표시광고 과장(Y7-J) — 주의
        from src.collectors import ko_polish as kp
        claim = []
        for w in ("상품명", "옵션", "본문"):
            for frag in kp.ban_hits(where_text[w]) or []:
                claim.append(str(frag))
        if claim:
            hits.append({"key": "claim", "cat": "표시광고", "label": "과장·금칙 표현", "grade": "caution", "names": [],
                         "found": list(dict.fromkeys(claim))[:6], "where": {}, "images": [],
                         "why": "마켓 금칙어·과장 — 등록 전 문구 확인(기존 표시광고 검사가 마켓별로 따로 본다)"})
    except Exception:                                              # noqa: BLE001
        pass
    dec = (ex.get("risk_decisions") or {}) if isinstance(ex.get("risk_decisions"), dict) else {}
    for h in hits:
        d = dec.get(h["key"]) or {}
        h["decided"] = d.get("action") or ""
        h["grade_label"] = GRADE_LABEL[h["grade"]]
        h["can_allow"] = h["grade"] != "block"
    hits.sort(key=lambda h: (GRADE_ORDER[h["grade"]], h["cat"]))
    return {"hits": hits, "waiting": int(pending_images or 0),
            "skip": (ex.get("risk_skip") or {}) if isinstance(ex.get("risk_skip"), dict) else {}}


def where_line(h: dict) -> str:
    """「상품명 0 · 본문 1 · 참수 1 · 검색어 2 · 이미지 3장(사진 3·4 · 상세 8)」 — 원문 글자와 사진 번호."""
    w0 = dict(h.get("where") or {})
    parts = [f"상품명 {w0.pop('상품명', 0)}"] if h.get("cat", "").startswith("상표") else []   # 상품명이 깨끗한지도 보인다
    parts += [f"{w} {n}" for w, n in w0.items()]
    if h.get("images"):
        parts.append(f"이미지 {len(h['images'])}장({' · '.join(i['name'] for i in h['images'])})")
    return " · ".join(parts)


def holds(sc: dict) -> List[dict]:
    """사전검증 보류 줄 — 결정 안 된 차단·보류, 「등록 안 함」, 이미지 검사 대기."""
    out = []
    if (sc or {}).get("skip"):
        out.append({"short": "등록 보류: " + str(sc["skip"].get("reason") or "직접 보류"), "fix": "risk_skip", "code": "risk_skip",
                    "line": "「등록 안 함」으로 보류한 상품이에요 — 다시 올리려면 위험 블록에서 결정을 바꾸세요."})
    for h in (sc or {}).get("hits") or []:
        if h["grade"] == "caution":
            continue
        if h["decided"] == "allow" and h["grade"] != "block":
            continue
        out.append({"short": f"위험({h['grade_label']}) — {h['cat']}: {', '.join(h['found'][:3])}",
                    "fix": "risk_block" if h["grade"] == "block" else "risk", "code": "risk_" + h["grade"],
                    "line": f"{h['cat']}: {'·'.join(h['found'][:4])} — {where_line(h)}. {h['why']}"})
    if (sc or {}).get("waiting"):
        out.append({"short": f"이미지 검사 대기 {sc['waiting']}장", "fix": "risk_wait", "code": "risk_wait",
                    "line": f"사진 속 글자를 아직 읽는 중이에요({sc['waiting']}장) — 끝나면 위험 검사를 다시 해요."})
    return out


# ── 결정 ───────────────────────────────────────────────────────────────────────────────────

def _strip(text: str, names, case=False) -> str:
    s = str(text or "")
    for n in sorted(names or [], key=len, reverse=True):
        s = _pat(n, case).sub("", s)
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def strip_extra(extra: dict, h: dict) -> dict:
    """「빼고 등록」 — 그 낱말을 상품명·검색어·옵션·본문·참수에서 지우고, 걸린 사진은 등록에서 뺀다(사유: 위험 라벨)."""
    ex = extra
    names, case = h.get("names") or [], bool(h.get("case"))
    for k in ("title_ko", "coupang_name", "title", "description", "description_ko"):
        if ex.get(k):
            ex[k] = _strip(ex[k], names, case)
    for k in ("keywords", "tags"):
        if isinstance(ex.get(k), list):
            ex[k] = [x for x in ex[k] if not _find(str(x), names, case)]
    for o in ex.get("options") or []:
        if isinstance(o, dict):
            for k in ("values_ko", "values"):
                if isinstance(o.get(k), list):
                    o[k] = [_strip(v, names, case) or v for v in o[k]]
    if isinstance(ex.get("detail_specs"), list):
        specs = []
        for kv in ex["detail_specs"]:
            if isinstance(kv, (list, tuple)) and len(kv) == 2:
                specs.append([kv[0], _strip(kv[1], names, case)])
            else:
                specs.append(kv)
        ex["detail_specs"] = specs
    if isinstance(ex.get("detail_auto"), dict) and ex["detail_auto"].get("text"):
        ex["detail_auto"]["text"] = _strip(ex["detail_auto"]["text"], names, case)
    want = {(i["kind"], int(i["idx"])) for i in h.get("images") or []}
    for key, kind in (("images_ko", "gallery"), ("detail_images_ko", "detail")):
        for e in ex.get(key) or []:
            if isinstance(e, dict) and (kind, int(e.get("idx", -1))) in want:
                e["risk_exclude"] = f"위험 — {h['cat']}({', '.join(h['found'][:2])})"
    return ex


def decide(extra: dict, key: str, action: str, *, by: str = "", reason: str = "") -> dict:
    """`action` = strip(빼고 등록) · allow(그래도 등록, 차단 등급엔 없음) · skip(등록 안 함) · reset(결정 지우기). 결과 `{ok, error?, hit}`."""
    ex = extra
    now = datetime.now(timezone.utc).isoformat()
    if action == "skip":
        ex["risk_skip"] = {"reason": (reason or "위험 항목 확인 필요")[:60], "at": now, "by": by}
        return {"ok": True}
    if action == "reset":
        ex.pop("risk_skip", None)
        (ex.get("risk_decisions") or {}).pop(key, None)
        return {"ok": True}
    sc = scan(ex)
    h = next((x for x in sc["hits"] if x["key"] == key), None)
    if h is None:
        return {"ok": False, "error": "그 위험 항목이 지금은 없어요 — 사전검증을 다시 눌러 주세요."}
    if action == "allow" and h["grade"] == "block":
        return {"ok": False, "error": "차단 항목은 「그래도 등록」할 수 없어요 — 빼고 등록하거나 등록하지 마세요."}
    if action not in ("strip", "allow"):
        return {"ok": False, "error": "알 수 없는 선택이에요."}
    if action == "strip":
        strip_extra(ex, h)
    dec = ex.setdefault("risk_decisions", {})
    dec[key] = {"action": action, "at": now, "by": by, "found": h["found"][:6], "label": h["label"], "cat": h["cat"],
                "names": list(h.get("names") or []), "case": bool(h.get("case"))}
    _learn(key, action, h)
    return {"ok": True, "hit": h}


def _learn(key: str, action: str, h: dict) -> None:
    """같은 낱말에 「그래도 등록」 2번 → 허용 후보 · 「빼고 등록」 → 그 낱말의 기본 동작."""
    try:
        st = _state()
        cur = st.state_get(_LEARN_KEY) or {}
        keys = dict(cur.get("keys") or {})
        k = dict(keys.get(key) or {})
        k["label"] = h.get("label")
        if action == "allow":
            k["allow"] = int(k.get("allow") or 0) + 1
            k.pop("default", None)
        elif action == "strip":
            k["default"] = "strip"
        keys[key] = k
        st.state_set(_LEARN_KEY, {"keys": keys})
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("[리스크] 학습 기록 실패: %s", exc)


def allow_candidates() -> List[dict]:
    al = allowlist()
    return [{"key": k, "label": v.get("label") or k, "count": int(v.get("allow") or 0)}
            for k, v in learned().items() if int(v.get("allow") or 0) >= 2 and (v.get("label") or k) not in al]


def confirm_allow(label: str, on: bool = True) -> List[str]:
    st = _state()
    cur = set((st.state_get(_ALLOW_KEY) or {}).get("labels") or [])
    (cur.add if on else cur.discard)(str(label))
    st.state_set(_ALLOW_KEY, {"labels": sorted(cur)})
    return sorted(cur)


def auto_apply(extra: dict, *, by: str = "auto") -> List[str]:
    """기억된 「빼고 등록」 — 결정 안 된 보류 항목 중 그 낱말의 기본이 strip이면 바로 뺀다. 뺀 라벨 목록."""
    mem = learned()
    done = []
    for h in scan(extra)["hits"]:
        if h["decided"] or h["grade"] == "caution":
            continue
        if (mem.get(h["key"]) or {}).get("default") == "strip":
            strip_extra(extra, h)
            extra.setdefault("risk_decisions", {})[h["key"]] = {
                "action": "strip", "auto": True, "by": by, "at": datetime.now(timezone.utc).isoformat(), "found": h["found"][:6],
                "label": h["label"], "cat": h["cat"], "names": list(h.get("names") or []), "case": bool(h.get("case"))}
            done.append(h["label"])
    return done


def enforce(pd: dict, extra: dict) -> dict:
    """등록·사전검증 몸통에 **저장된 「빼고 등록」**을 다시 건다 — 화면이 예전 글자(상품명·본문)를 들고 있어도 서버가 뺀다.
    사진은 몸통 이미지 배열이 저장본(`risk_exclude`)으로 만들어지므로 여기선 글자만."""
    for d in ((extra or {}).get("risk_decisions") or {}).values():
        if isinstance(d, dict) and d.get("action") == "strip" and d.get("names"):
            h = {"names": d["names"], "case": bool(d.get("case")), "images": [], "cat": d.get("cat", ""), "found": d.get("found") or []}
            strip_extra(pd, h)
    return pd


def notice_kinds(sc: dict) -> dict:
    """Y10-B — 주의 등급 중 본문에 KC 고지를 넣을 것 `{kc: [라벨…], voltage: bool}`(없으면 빈 dict)."""
    want = {c["label"]: c for c in tokens().get("cert") or [] if c.get("notice") == "kc"}
    labs = [h["label"] for h in (sc or {}).get("hits") or [] if h["label"] in want]
    if not labs:
        return {}
    return {"kc": labs, "voltage": any(want[l].get("voltage") for l in labs)}


def card(sc: dict) -> dict:
    """화면용 — `{count, hits:[{key, cat, label, grade, grade_label, found, where_line, decided, can_allow, auto}], waiting, skip}`."""
    rows = []
    for h in sc.get("hits") or []:
        rows.append({k: h.get(k) for k in ("key", "cat", "label", "grade", "grade_label", "found", "decided", "can_allow", "why")}
                    | {"where_line": where_line(h)})
    return {"count": len(rows), "hits": rows, "waiting": sc.get("waiting") or 0, "skip": sc.get("skip") or {}}
