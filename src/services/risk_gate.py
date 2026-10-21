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
- 학습: 같은 낱말에 「그래도 등록」 2번이면 허용 후보(설정에서 확정) · 「빼고 등록」은 그 낱말의 기본 동작으로 기억(다음 상품은 자동으로 뺀다)
  — **상표/캐릭터/디자인만**(오너 2026-10-13). 인증·과장·레플리카·블랙리스트는 매번 묻는다.
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


def _whole_prop(e: dict) -> bool:
    """장 전체가 소품(소품 글자뿐 · 사진이 통째 돌아간 틀) — 위험 검사 대상이 아니다(Y11-O: 「참고」만)."""
    from src.services import prop_text as PT
    return bool(e.get("prop_only") or str(e.get("box_frame") or "") in PT.ROTATED_FRAMES)


def _outbound_excluded(kind: str, e: dict, originals: List[str]) -> bool:
    """등록에 안 나가는 상세 장(판촉·쿠폰·주소 제외 등) — 게이트 대상 아님(Y11-O: 「나가지 않는 그림에 보류를 걸지 않는다」).
    「빼고 등록」으로 뺀 장(risk_exclude)은 위에서 이미 걸러진다."""
    if kind != "detail":
        return False
    try:
        from src.services.detail_image_plan import verdict
        i = int(e.get("idx", -1))
        orig = originals[i] if 0 <= i < len(originals) else ""
        return verdict(e, orig)["use"] == "excluded"
    except Exception:                                              # noqa: BLE001
        return False


def _images(extra: dict, *, props: Optional[list] = None):
    """`[(kind, idx, 이름, 글자)]` — 번역 기록이 있는 장(OCR·원문·번역문) 중 **등록에 나가는 장**만.

    Y11-G(오너): 소품(책등·책 표지·포장) 글자는 글자가 아니다 — 위험 검사에서 빼고, `props`가 주어지면 거기에
    `(kind, idx, 이름, 소품 글자)`로 따로 담는다(상표가 걸려도 「참고」 한 줄). 책·포스터 상품(반례)이면 빼지 않는다.
    Y11-O: 장 전체가 소품이면 그 장은 통째로 검사 밖(예전엔 소품 글자를 한 줄로 이어 붙여 빼려다 못 빼서 상표가 다시 셌다).
    소품 상자는 상자마다(원문·번역문 각각) 뺀다."""
    from src.services.detail_image_plan import entry_text
    from src.services import prop_text as PT
    off = PT.exempt(extra)
    originals = [u for u in ((extra or {}).get("detail_images") or []) if u]
    known = [] if off else PT.echo_texts(extra)
    out = []
    # Y13-D 2(오너 2026-10-18 BLACKHOLES): 옵션(SKU) 사진도 나간다(쿠팡 옵션 대표) — 영화 포스터 「INTERSTELLAR」가 검사 밖이었다
    for key, kind, lab in (("images_ko", "gallery", "사진"), ("detail_images_ko", "detail", "상세"), ("sku_images_ko", "sku", "옵션 사진")):
        for e in (extra or {}).get(key) or []:
            if not (isinstance(e, dict) and e.get("idx") is not None) or e.get("risk_exclude"):   # 이미 뺀 장은 안 센다
                continue
            if _outbound_excluded(kind, e, originals):
                continue
            t = entry_text(e)
            nm = f"{lab} {int(e['idx']) + 1}"
            if not off and _whole_prop(e):
                pt = (str(e.get("prop_text") or "") + " " + t).strip()
                if pt and props is not None:
                    props.append((kind, int(e["idx"]), nm, pt))
                continue
            frags = [] if off else prop_frags(e, known)
            if frags and props is not None:
                props.append((kind, int(e["idx"]), nm, " ".join(dict.fromkeys(frags))))
            t = _minus(t, frags)                                  # 소품 상자 글자는 상자 수만큼만 뺀다(같은 낱말이 소품 밖에도 있으면 남는다)
            for frag in sorted(_risk_erased(e), key=len, reverse=True):       # Y11-J6: 「빼고 등록」으로 지운 상자 글자
                t = t.replace(frag, " ")
            for frag in sorted(_risk_cleared(e), key=len, reverse=True):      # Y14: 지금 그림엔 없고 원본 원문에만 있는 이름
                t = t.replace(frag, " ")
            if t.strip():
                out.append((kind, int(e["idx"]), nm, t))
    return out


def _minus(text: str, frags: List[str]) -> str:
    """글자에서 조각을 **조각 하나에 한 번씩**만 뺀다(긴 것부터) — 소품 상자 「Zaha Hadid」 하나가 본문의 「Zaha Hadid」까지 지우지 않게."""
    for f in sorted(frags or [], key=len, reverse=True):
        text = text.replace(f, " ", 1)
    return text


def prop_frags(e: dict, known: Optional[List[str]] = None) -> List[str]:
    """소품 상자의 글자 — 상자마다 원문·번역문 따로(이어 붙이지 않는다: 이어 붙인 줄은 장 글자 어디에도 없다).
    소품 상자 = 소품 표시(`prop`) 또는 같은 상품의 통째 소품 사진 글자와 같은 작은 상자(`prop_text.echoes`)."""
    from src.services import prop_text as PT
    size = e.get("box_size") or e.get("size")
    frags = []
    for b in e.get("boxes") or []:
        if isinstance(b, dict) and (b.get("prop") or (known and PT.echoes(b, size, known))):
            frags += [str(b.get(k) or "").strip() for k in ("src", "tgt")]
    return [f for f in frags if f]


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


_LATIN = re.compile(r"[A-Za-z]")
_MARKS = re.compile(r"[™®©]")


def _brand_names() -> set:
    """브랜드 목록에 등재된 이름 — 상표 표(risk_tokens·ko_polish 상표) + 쿠팡 브랜드 표."""
    out = set()
    for e in _trademark_entries():
        out |= {str(n) for n in e.get("names") or [] if n}
    try:
        p = Path(__file__).resolve().parents[1] / "uploaders" / "coupang_brands.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        b = d.get("brands") if isinstance(d, dict) else None
        if isinstance(b, dict):
            out |= {str(k) for k in b} | {str(v) for v in b.values() if isinstance(v, str)}
        elif isinstance(b, list):
            out |= {str(x) for x in b}
    except Exception:                                              # noqa: BLE001
        pass
    return out


def _common_nouns() -> set:
    """한글 보통명사(브랜드 아님) — risk_tokens.json `blacklist_common` + 네이버 카테고리 이름 칸(「향수」「캔들」…)."""
    out = {str(x) for x in tokens().get("blacklist_common") or []}
    try:
        from src.uploaders import naver_categories as _nc
        leaves = (_nc.tree() or {}).get("leaves") or {}
    except Exception:                                              # noqa: BLE001 — 트리가 없으면 표만
        leaves = {}
    if leaves:
        if _common_cache.get("id") != id(leaves):
            segs = set()
            for whole in leaves.values():
                for seg in str(whole).split(">"):
                    segs |= {w for w in re.split(r"[/·,\s]+", seg) if w}
            _common_cache.update(id=id(leaves), segs=segs)
        out |= _common_cache["segs"]
    return out


_common_cache: dict = {}


def brand_token(term: str, brands: Optional[set] = None, common: Optional[set] = None) -> bool:
    """Y11-O(오너): 블랙리스트 낱말 중 **브랜드로 볼 것** — 영문(라틴 글자)·™®·브랜드 표 등재, 그리고 한글 고유명사(음역 브랜드
    「아디다스」「애플」). 한글 보통명사 단독(「향수」「캔들」 — `blacklist_common` 표·네이버 카테고리 이름 칸)은 브랜드가 아니다.
    사진 속 「고급 광석 향수*1」(쿠폰 증정품)에 브랜드 보류를 걸지 않는다."""
    t = str(term or "").strip()
    if not t:
        return False
    if _LATIN.search(t) or _MARKS.search(t):
        return True
    if t in (brands if brands is not None else _brand_names()):
        return True
    return t not in (common if common is not None else _common_nouns())


def brand_filter(terms) -> List[str]:
    brands, common = _brand_names(), _common_nouns()
    return [t for t in terms or [] if brand_token(t, brands, common)]


_ITEM_FILE = Path(__file__).resolve().parents[1] / "uploaders" / "item_caution.json"


def _item_cautions() -> List[dict]:
    try:
        return list(json.loads(_ITEM_FILE.read_text(encoding="utf-8")).get("items") or [])
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("[리스크] 품목 주의 표 읽기 실패: %s", exc)
        return []


def _blacklist() -> List[str]:
    """등록 금지 브랜드(COUPANG_BLACKLIST85 — 소싱 판정과 같은 로더) 중 브랜드 낱말만(`brand_token`)."""
    try:
        from src.pipeline.coupang_replicate import load_blacklist85
        raw = [str(x).strip() for x in (load_blacklist85().get("terms") or []) if str(x).strip()]
    except Exception:                                              # noqa: BLE001
        return []
    keep = brand_filter(raw)
    if len(keep) != len(raw):
        logger.info("[리스크] 블랙리스트 %d개 중 보통명사 %d개는 브랜드 검사에서 뺌(%s)", len(raw), len(raw) - len(keep),
                    ", ".join(t for t in raw if t not in keep)[:200])
    return keep


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
    props: list = []
    imgs = _images(ex, props=props)
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
    for c in tokens().get("compat_replace") or []:               # Y14: 호환 표기 — 바꿔서 등록(지우지 않음)
        if c.get("label") in allow:
            continue
        h = _hit("compat:" + str(c["label"]), "호환 표기", c["label"], "hold", c.get("names") or [], False, where_text, imgs,
                 f"상표 이름 — 「빼고 등록」은 「{c.get('to')}」로 바꿔요(사진은 글자 고치기)")
        if h:
            h["to"] = str(c.get("to") or "")
            hits.append(h)
    bl = [t for t in _blacklist() if t not in allow]
    if bl:
        h = _hit("blacklist", "브랜드 블랙리스트", "브랜드 블랙리스트", "hold", bl, False, where_text, imgs,
                 "등록 금지 브랜드 목록에 있는 이름")
        if h:
            hits.append(h)
    # Y11O-2(오너): 품목 주의(src/uploaders/item_caution.json) — 항공 운송 제한 품목(향수·캔들·레이저포인터…) = 주의(막지 않음)
    for it in _item_cautions():
        if it.get("label") in allow:
            continue
        h = _hit("item:" + str(it.get("key")), it.get("label") or "품목 주의", it.get("label") or "품목 주의",
                 it.get("grade") or "caution", it.get("names") or [], False, where_text, imgs, it.get("line") or "")
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
    # Y11-G: 상표가 소품 글자에만 걸리면 차단·주의가 아니다 — 「참고: 소품(사진 4)에 'Zaha Hadid'」 한 줄(오너가 책 표지는 괜찮다고 정함)
    notes, seen = [], set()
    from src.services.prop_text import note_line
    for e in _trademark_entries():
        if e["label"] in allow:
            continue
        for _k, _i, nm, txt in props:
            for f in _find(txt, e.get("names") or [], bool(e.get("case")))[:1]:      # 한 장에 한 상표 한 줄(원문·번역문 둘 다 세지 않는다)
                if (nm, e["label"]) not in seen:
                    seen.add((nm, e["label"]))
                    notes.append({"label": e["label"], "found": f, "where": nm, "line": note_line(f, nm)})
    return {"hits": hits, "notes": notes, "waiting": int(pending_images or 0),
            "skip": (ex.get("risk_skip") or {}) if isinstance(ex.get("risk_skip"), dict) else {}}


def where_line(h: dict) -> str:
    """「상품명 0 · 본문 1 · 참수 1 · 검색어 2 · 이미지 3장(사진 3·4 · 상세 8)」 — 원문 글자와 사진 번호."""
    w0 = dict(h.get("where") or {})
    parts = [f"상품명 {w0.pop('상품명', 0)}"] if h.get("cat", "").startswith("상표") else []   # 상품명이 깨끗한지도 보인다
    parts += [f"{w} {n}" for w, n in w0.items()]
    if h.get("images"):
        parts.append(f"이미지 {len(h['images'])}장({' · '.join(i['name'] for i in h['images'])})")
    return " · ".join(parts)


def skip_hint(sc: dict) -> str:
    """Y11-O — 「등록 안 함」 사유였던 상표가 지금 규칙으론 소품 「참고」뿐(걸린 항목 없음)이면 그렇다고 한 줄. 결정은 오너가 푼다."""
    reason = str(((sc or {}).get("skip") or {}).get("reason") or "")
    if not reason:
        return ""
    live = {h["label"] for h in sc.get("hits") or []}
    noted = sorted({n["label"] for n in sc.get("notes") or [] if n["label"] not in live
                    and (n["label"] in reason or n["found"] in reason)})
    if not noted:
        return ""
    return (f"보류 사유였던 「{'·'.join(noted)}」는 지금 규칙으로는 소품(책 표지 등) 글자라 「참고」뿐이에요 — "
            "「보류 풀기」를 누르면 등록할 수 있어요.")


def holds(sc: dict) -> List[dict]:
    """사전검증 보류 줄 — 결정 안 된 차단·보류, 「등록 안 함」, 이미지 검사 대기."""
    out = []
    if (sc or {}).get("skip"):
        reason = str(sc["skip"].get("reason") or "")
        line = "「등록 안 함」으로 보류한 상품이에요 — 다시 올리려면 위험 블록에서 결정을 바꾸세요."
        out.append({"short": "등록 보류: " + (reason or "직접 보류"), "fix": "risk_skip", "code": "risk_skip", "line": line})
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


def _repl_pat(name: str, case: bool = False) -> "re.Pattern":
    """Y14 — 치환용: 라틴 이름은 바로 뒤 숫자까지 한 덩어리(「applewatch7」 → 「스마트워치」). 그 밖은 `_pat`과 같다."""
    if re.fullmatch(r"[A-Za-z][A-Za-z .'&èé-]*", name or ""):
        return re.compile(rf"(?<![A-Za-z]){re.escape(name)}\d*(?![A-Za-z])", 0 if case else re.I)
    return _pat(name, case)


def _replace(text: str, names, to: str, case=False) -> str:
    """Y14 호환 표기 — 이름을 지우지 않고 `to`로 바꾼다(긴 이름부터). 바꾼 뒤 같은 말이 붙어 겹치면 하나로."""
    s = str(text or "")
    for n in sorted(names or [], key=len, reverse=True):
        s = _repl_pat(n, case).sub(to, s)
    s = re.sub(rf"({re.escape(to)})(\s*\1)+", r"\1", s) if to else s
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def strip_extra(extra: dict, h: dict, *, erase_pixels: bool = False, pixels: str = "") -> dict:
    """「빼고 등록」 — 그 낱말을 상품명·검색어·옵션·본문·참수에서 지우고, 걸린 사진은 등록에서 뺀다(사유: 위험 라벨).
    `erase_pixels`(사람이 누른 「빼고 등록」만) — 사진째 빼는 대신 그 낱말 상자만 지운 편집본(Y11-J6). 자동 적용은 픽셀을 안 바꾼다.
    `pixels="restore"`(Y13-D 2 오너 결정) — 지우지 않고 **음차 상자만 원본 픽셀로 되살린다**. 원문 상자 자체가 그 낱말
    (영문 「INTERSTELLAR」)이면 되살려도 사진에 상표가 남으니 그 장은 사진째 뺀다."""
    ex = extra
    names, case = h.get("names") or [], bool(h.get("case"))
    to = str(h.get("to") or "")
    # Y14(SPORTLINK): 호환 표기(`compat:`)는 지우지 않고 보통 이름으로 바꾼다 — 「애플워치 호환」 → 「스마트워치 호환」
    fix = (lambda t: _replace(t, names, to, case)) if to else (lambda t: _strip(t, names, case))
    # 수집 원문 `title`은 지우기에선 예전처럼 고치지만, 바꾸기에선 손대지 않는다(수집 원본 불변 · 나가는 이름은 title_ko·coupang_name)
    for k in (("title_ko", "coupang_name", "description", "description_ko") if to
              else ("title_ko", "coupang_name", "title", "description", "description_ko")):
        if ex.get(k):
            ex[k] = fix(ex[k])
    for k in ("keywords", "tags"):
        if isinstance(ex.get(k), list):
            if to:
                ex[k] = list(dict.fromkeys(fix(str(x)) for x in ex[k] if fix(str(x))))
            else:
                ex[k] = [x for x in ex[k] if not _find(str(x), names, case)]
    for o in ex.get("options") or []:
        if isinstance(o, dict):
            for k in ("values_ko", "values"):
                if isinstance(o.get(k), list):
                    o[k] = [fix(v) or v for v in o[k]]
    if isinstance(ex.get("option_value_overrides"), dict):       # Y13-D 2: 옵션 탭·AI 축약으로 정한 값도 나간다
        ex["option_value_overrides"] = {k: (fix(v) or v) if isinstance(v, str) else v
                                        for k, v in ex["option_value_overrides"].items()}
    if isinstance(ex.get("detail_specs"), list):
        specs = []
        for kv in ex["detail_specs"]:
            if isinstance(kv, (list, tuple)) and len(kv) == 2:
                specs.append([kv[0], fix(kv[1])])
            else:
                specs.append(kv)
        ex["detail_specs"] = specs
    if isinstance(ex.get("detail_auto"), dict) and ex["detail_auto"].get("text"):
        ex["detail_auto"]["text"] = fix(ex["detail_auto"]["text"])
    if pixels == "keep":
        return ex                                                # Y14: 글자만 — 사진은 앞 결정(글자 고치기)이 맡았다
    want = {(i["kind"], int(i["idx"])) for i in h.get("images") or []}
    label = f"위험 — {h['cat']}({', '.join(h['found'][:2])})"
    for key, kind in (("images_ko", "gallery"), ("detail_images_ko", "detail"), ("sku_images_ko", "sku")):
        for e in ex.get(key) or []:
            if isinstance(e, dict) and (kind, int(e.get("idx", -1))) in want:
                if _whole_prop(e) and not _prop_off(ex):
                    continue                     # Y11-O: 소품뿐인 사진은 절대 빼지 않는다(상표가 걸려도 「참고」 — 오너 2026-10-15)
                if to and erase_pixels:
                    _retext_or_exclude(ex, kind, e, names, case, to, label)
                    continue
                if to:
                    continue                     # 자동 적용(글자만) — 사진은 사람이 누른 「빼고 등록」에서만 다시 그린다
                if pixels == "restore":
                    _restore_or_exclude(ex, kind, e, names, case, label)
                    continue
                # Y11-J6(오너 2026-10-14): 사진째 빼지 않고 **그 낱말이 든 글자 상자만 지운다**(빈칸 렌더 = 새 편집본).
                #   오너가 「빼고 등록」을 누른 것이 곧 사람 지시다(자동 픽셀 변경 아님 — Y11-E). 상자를 못 찾거나 편집을 못 쓰면
                #   예전처럼 사진째 뺀다(사유에 왜 못 지웠는지).
                if not erase_pixels:
                    e["risk_exclude"] = label
                    continue
                er = _erase_hit(ex, kind, int(e.get("idx", -1)), names, case)
                if er.get("ok"):
                    e.pop("risk_exclude", None)
                    e["risk_erase"] = {"edit": er["n"], "erased": er["erased"], "label": label,
                                       "at": datetime.now(timezone.utc).isoformat(), "pending": bool(er.get("pending"))}
                else:
                    e["risk_exclude"] = f"{label} — 사진째 뺌({er.get('why') or '상자를 지우지 못함'})"
    return ex


RETEXT_MISS = "그 낱말이 든 번역 글자 상자를 못 찾음"


def _retext_or_exclude(ex: dict, kind: str, e: dict, names, case: bool, to: str, label: str) -> None:
    """Y14(오너 2026-10-21 SPORTLINK) — 「사진 편집 → 글자 고치기」와 같은 길: 그 낱말이 든 **지금 그림의 글자 상자만** 바꾼 글자로
    다시 그린 새 편집본(원본 불변 · `IE.apply` action=text). 상자를 못 찾거나 편집을 못 쓰면 사진째 뺀다(사유). 바꾼 상자의
    **예전 글자**를 `risk_erase.erased`에 남겨 검사가 그 편집본에선 세지 않는다(다시 그리지 않게).

    상자 글자 = 번역문(`tgt`)이 있으면 그것, 없으면 `src`. 운영(10-21 01:50 SPORTLINK 사진 1·3·4·5): 번역본 그림을 OCR로 읽은 상자는
    한국어가 `src`에 있고 `tgt`는 빈칸이다 — `tgt`만 봐서 4장 모두 「상자를 못 찾음」으로 사진째 빠졌다(대표 사진 포함)."""
    idx = int(e.get("idx", -1))
    try:
        from src.services import image_edit as IE
        ok_c, _why = IE.configured()
        if not ok_c:
            e["risk_exclude"] = f"{label} — 사진째 뺌(지금은 사진 편집을 쓸 수 없음)"
            return
        p = IE.plan(ex, kind, idx)
    except Exception as exc:                                     # noqa: BLE001
        e["risk_exclude"] = f"{label} — 사진째 뺌(글자 상자를 읽지 못함 {type(exc).__name__})"
        return
    ops, old = [], []
    for b in p.get("boxes") or []:
        tgt = str(b.get("tgt") or "") or str(b.get("src") or "")
        if tgt and _find(tgt, names, case):
            new = _replace(tgt, names, to, case)
            if new and new != tgt:
                ops.append({"id": b["id"], "action": "text", "text": new})
                old.append(tgt)
    if not ops:
        if p.get("boxes"):
            # Y14(운영 10-21 04:50 SPORTLINK 사진 3): 지금 나가는 그림의 글자를 읽었는데 그 이름이 없다 — 이름은 **원본 사진의 원문**
            #   (`source_text` 「Airpods Airpods Pro」)에만 있고 번역본·편집본엔 「무선 이어폰」으로 그려져 있다. 그림에 없는 이름 때문에
            #   사진째 빼지 않는다. 그 그림(주소)에선 그 낱말을 세지 않게 `risk_clear`에 적는다(그림이 바뀌면 다시 센다).
            from src.services.detail_image_plan import entry_text
            words = [m.group(0) for n in names or [] if n for m in _repl_pat(n, case).finditer(entry_text(e))]
            prev = e.get("risk_clear") if isinstance(e.get("risk_clear"), dict) else {}
            if prev.get("img") != str(e.get("url") or ""):
                prev = {}
            e.pop("risk_exclude", None)
            e["risk_clear"] = {"img": str(e.get("url") or ""), "words": list(dict.fromkeys((prev.get("words") or []) + words)),
                               "label": label, "why": "지금 나가는 그림의 글자 상자에 없음(원본 원문에만 있음)",
                               "at": datetime.now(timezone.utc).isoformat()}
            return
        e["risk_exclude"] = f"{label} — 사진째 뺌({RETEXT_MISS})"
        return
    try:
        res = IE.apply(ex, kind, idx, ops, by="risk")
    except Exception as exc:                                     # noqa: BLE001
        res = {"ok": False, "error": type(exc).__name__}
    if not res.get("ok"):
        e["risk_exclude"] = f"{label} — 사진째 뺌(글자 고치기 실패: {str(res.get('error') or '')[:60]})"
        return
    e.pop("risk_exclude", None)
    e["risk_erase"] = {"edit": int(str(res.get("version") or "edit:0").split(":")[-1]), "how": "retext", "to": to,
                       "erased": old, "label": label, "at": datetime.now(timezone.utc).isoformat(),
                       "pending": bool(res.get("pending"))}


def _restore_or_exclude(ex: dict, kind: str, e: dict, names, case: bool, label: str) -> None:
    """Y13-D 2(오너 「인터스텔라 음차 상자만 원본 픽셀 복원 — 지우기 아님. 영문 Interstellar가 사진에 남으면 그 장은 뺀다」).

    상자마다 원문(`src`)·번역문(`tgt`)을 본다. 원문이 그 낱말이면(되살려도 상표가 그대로) → 사진째 뺀다(픽셀 0 · 렌더 0).
    번역문에만 있으면(음차) → 그 상자만 원본 픽셀로 되살린 편집본. 상자를 못 읽거나 편집을 못 쓰면 사진째 뺀다(사유)."""
    idx = int(e.get("idx", -1))
    try:
        from src.services import image_edit as IE
        p = IE.plan(ex, kind, idx, fetch=False)                  # 저장된 상자만 — 판정에 사진을 받지 않는다(그리기는 apply가)
    except Exception as exc:                                     # noqa: BLE001
        e["risk_exclude"] = f"{label} — 사진째 뺌(글자 상자를 읽지 못함 {type(exc).__name__})"
        return
    boxes = p.get("boxes") or []
    src_hit = [b for b in boxes if _find(str(b.get("src") or ""), names, case)]
    tgt_only = [b for b in boxes if not _find(str(b.get("src") or ""), names, case) and _find(str(b.get("tgt") or ""), names, case)]
    if src_hit:
        e["risk_exclude"] = (f"{label} — 사진째 뺌(원문 글자에 상표가 그대로: "
                             f"「{'」·「'.join(dict.fromkeys(str(b.get('src')) for b in src_hit[:3]))}」 — 되살려도 남음)")
        return
    if not tgt_only:
        e["risk_exclude"] = f"{label} — 사진째 뺌(그 낱말이 든 글자 상자를 못 찾음)"
        return
    try:
        res = IE.apply(ex, kind, idx, [{"id": b["id"], "action": "restore"} for b in tgt_only], by="risk")
    except Exception as exc:                                     # noqa: BLE001
        res = {"ok": False, "error": type(exc).__name__}
    if not res.get("ok"):
        e["risk_exclude"] = f"{label} — 사진째 뺌(원본 되살리기 실패: {str(res.get('error') or '')[:60]})"
        return
    e.pop("risk_exclude", None)
    e["risk_erase"] = {"edit": int(str(res.get("version") or "edit:0").split(":")[-1]), "how": "restore",
                       "erased": [str(b.get("tgt")) for b in tgt_only if b.get("tgt")], "label": label,
                       "at": datetime.now(timezone.utc).isoformat(), "pending": bool(res.get("pending"))}


def _prop_off(ex: dict) -> bool:
    from src.services import prop_text as PT
    return PT.exempt(ex)


def heal_prop_excludes(extra: dict) -> List[str]:
    """Y11-O — 예전 「빼고 등록」(자동 적용 포함)이 건 사진 제외 중 **지금 규칙으로 걸 이유가 없는 것**을 푼다. 푼 사진 이름 목록.

    - 소품뿐인 사진(거꾸로·옆으로 돌린 틀 · 소품 글자뿐) — 위험 검사 대상이 아니다(소품 글자 = 「참고」만).
    - 그 낱말이 소품 상자에만 있던 사진(VRSUK 상세 25 책등 「Zaha Hadid」) — 소품 상자를 빼고 다시 보면 낱말이 없다.
    상품이 책·포스터(반례)면 손대지 않는다. 사람이 「빼고 등록」해 상자를 지운 편집본(risk_erase)은 건드리지 않는다."""
    if _prop_off(extra):
        return []
    from src.services.detail_image_plan import entry_text
    from src.services import prop_text as PT
    names, cases = [], []
    for d in ((extra or {}).get("risk_decisions") or {}).values():
        if isinstance(d, dict) and d.get("action") == "strip" and d.get("names"):
            names.append(list(d["names"]))
            cases.append(bool(d.get("case")))
    known = PT.echo_texts(extra)
    out = []
    for key, lab in (("images_ko", "사진"), ("detail_images_ko", "상세")):
        for e in (extra or {}).get(key) or []:
            if not (isinstance(e, dict) and str(e.get("risk_exclude") or "").startswith("위험 —")):
                continue
            if not _whole_prop(e):
                t = _minus(entry_text(e), prop_frags(e, known))
                if not names or any(_find(t, n, c) for n, c in zip(names, cases)):
                    continue                     # 소품 밖에 아직 그 낱말이 있다(또는 무슨 낱말로 뺐는지 모름) — 그대로 둔다
            e.pop("risk_exclude")
            e["risk_exclude_healed"] = datetime.now(timezone.utc).isoformat()
            out.append(f"{lab} {int(e.get('idx', 0)) + 1}")
    return out


def heal_retext_excludes(extra: dict) -> List[str]:
    """Y14(운영 10-21 01:50 SPORTLINK) — 호환 표기 「글자 고치기」가 상자를 못 찾아 **사진째 뺀** 장을 다시 고친다. 다시 시도한 사진 이름.

    그때 `_retext_or_exclude`는 번역문(`tgt`)만 봤고, 번역본을 OCR로 읽은 상자는 글자가 `src`에 있어 4장이 빠졌다(대표 포함).
    결정(`risk_decisions`의 바꾸기 `to`)이 있는 낱말이 그 장 글자에 있을 때만 — 사진째 빼기를 풀고 같은 길로 다시 그린다.
    또 못 찾으면 다시 빠진다(사유 그대로). 다른 사유로 뺀 장(판촉·편집 불가·되살리기)은 건드리지 않는다."""
    from src.services.detail_image_plan import entry_text
    decs = [d for d in ((extra or {}).get("risk_decisions") or {}).values()
            if isinstance(d, dict) and d.get("action") == "strip" and d.get("to") and d.get("names")]
    if not decs:
        return []
    out = []
    for key, kind, lab in (("images_ko", "gallery", "사진"), ("detail_images_ko", "detail", "상세"), ("sku_images_ko", "sku", "옵션 사진")):
        for e in (extra or {}).get(key) or []:
            rx = str((e or {}).get("risk_exclude") or "") if isinstance(e, dict) else ""
            if not (rx.startswith("위험 —") and RETEXT_MISS in rx):
                continue
            t = entry_text(e)
            d = next((d for d in decs if _find(t, d["names"], bool(d.get("case")))), None)
            if d is None:
                continue
            label = rx.split(" — 사진째 뺌", 1)[0]
            e.pop("risk_exclude", None)
            _retext_or_exclude(extra, kind, e, d["names"], bool(d.get("case")), str(d["to"]), label)
            out.append(f"{lab} {int(e.get('idx', 0)) + 1}" + ("" if e.get("risk_erase") else "(또 못 고침)"))
    return out


def strip_image_line(ex: dict, h: Optional[dict]) -> str:
    """「빼고 등록」 사진 결과 한 줄 — 「사진 2장: 글자 상자만 지움 1(만드는 중 1) · 사진째 뺌 1(그 낱말이 든 글자 상자를 못 찾음)」."""
    want = {(i["kind"], int(i["idx"])) for i in (h or {}).get("images") or []}
    if not want:
        return ""
    erased = pending = restored = 0
    dropped = []
    for key, kind in (("images_ko", "gallery"), ("detail_images_ko", "detail"), ("sku_images_ko", "sku")):
        for e in ex.get(key) or []:
            if not (isinstance(e, dict) and (kind, int(e.get("idx", -1))) in want):
                continue
            if e.get("risk_erase"):
                if e["risk_erase"].get("how") == "restore":
                    restored += 1
                else:
                    erased += 1
                pending += bool(e["risk_erase"].get("pending"))
            elif e.get("risk_exclude"):
                m = re.search(r"사진째 뺌\((.+)\)$", str(e["risk_exclude"]))
                dropped.append(m.group(1) if m else "")
    parts = []
    if restored:
        parts.append(f"음차 상자만 원본 복원 {restored}")
    if erased:
        parts.append(f"글자 상자만 지움 {erased}" + (f"(만드는 중 {pending})" if pending else ""))
    if dropped:
        why = next((d for d in dropped if d), "")
        parts.append(f"사진째 뺌 {len(dropped)}" + (f"({why})" if why else ""))
    return f"사진 {len(want)}장: " + " · ".join(parts) if parts else ""


def _erase_hit(ex: dict, kind: str, idx: int, names, case: bool) -> dict:
    """그 장에서 낱말이 든 글자 상자(원문·번역문)만 지운 편집본 — `{ok, n, erased, pending}` 또는 `{ok: False, why}`."""
    from src.services import image_edit as IE
    ok_c, why_c = IE.configured()
    if not ok_c:
        logger.info("[위험 게이트] 상자 지우기 불가 — %s", why_c)          # 설정 이름은 로그에만(화면엔 일반 문구)
        return {"ok": False, "why": "지금은 사진 편집을 쓸 수 없음"}
    try:
        p = IE.plan(ex, kind, idx)
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "why": f"글자 상자를 읽지 못함({type(exc).__name__})"}
    ids = [b["id"] for b in p.get("boxes") or [] if _find(f"{b.get('src') or ''} {b.get('tgt') or ''}", names, case)]
    if not ids:
        return {"ok": False, "why": "그 낱말이 든 글자 상자를 못 찾음" + (f" — {p['why']}" if p.get("why") else "")}
    try:
        res = IE.apply(ex, kind, idx, [{"id": i, "action": "erase"} for i in ids], by="risk")
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "why": f"지우기 실패({type(exc).__name__})"}
    if not res.get("ok"):
        return {"ok": False, "why": str(res.get("error") or "지우기 실패")[:80]}
    return {"ok": True, "n": int(str(res.get("version") or "edit:0").split(":")[-1]), "erased": res.get("erased") or [],
            "pending": bool(res.get("pending"))}


def _risk_cleared(e: dict) -> list:
    """Y14 — 글자 고치기가 「지금 나가는 그림엔 그 이름이 없다」고 확인한 낱말(원본 사진 원문에만 있음). 그 그림 그대로일 때만."""
    rc = e.get("risk_clear") if isinstance(e.get("risk_clear"), dict) else None
    if not rc or not rc.get("img") or str(rc.get("img")) != str(e.get("url") or ""):
        return []
    return [str(x) for x in rc.get("words") or [] if str(x).strip()]


def _risk_erased(e: dict) -> list:
    """「빼고 등록」으로 지운 글자 — 그 편집본이 지금 나가는(또는 만드는 중인) 버전일 때만. 되돌렸으면 다시 센다."""
    re_ = e.get("risk_erase") if isinstance(e.get("risk_erase"), dict) else None
    if not re_:
        return []
    from src.services import image_edit as IE
    key = f"edit:{re_.get('edit')}"
    if IE.current_key(e) == key or e.get("pending_select") == key:
        return [str(x) for x in re_.get("erased") or [] if str(x).strip()]
    return []


def decide(extra: dict, key: str, action: str, *, by: str = "", reason: str = "", pixels: str = "restore") -> dict:
    """`action` = strip(빼고 등록) · allow(그래도 등록, 차단 등급엔 없음) · skip(등록 안 함) · reset(결정 지우기). 결과 `{ok, error?, hit}`.

    Y13-F(Y13-E 이월 1, 오너 2026-10-19): 「빼고 등록」 버튼 기본 = `pixels="restore"` — 음차 상자는 원본 픽셀로 되살리고, 원문에
    그 상표가 남는 장은 사진째 뺀다(BLACKHOLES 결정과 같은 길). 옛 「그 낱말 상자만 지우기」(Y11-J6)는 `pixels="erase"`."""
    if pixels == "erase":
        pixels = ""
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
    changed = True
    if action == "strip":
        before = json.dumps(ex, ensure_ascii=False, sort_keys=True, default=str)
        strip_extra(ex, h, erase_pixels=True, pixels=pixels)
        changed = json.dumps(ex, ensure_ascii=False, sort_keys=True, default=str) != before
    dec = ex.setdefault("risk_decisions", {})
    dec[key] = {"action": action, "at": now, "by": by, "found": h["found"][:6], "label": h["label"], "cat": h["cat"],
                "names": list(h.get("names") or []), "case": bool(h.get("case"))}
    if h.get("to"):
        dec[key]["to"] = h["to"]                                 # Y14: 치환값 — enforce·다시 걸기가 지우지 않고 바꾼다
    _learn(key, action, h)
    return {"ok": True, "hit": h, "changed": changed}


def _auto_strippable(key: str) -> bool:
    """오너(2026-10-13): 「빼고 등록」 자동 적용은 **상표/캐릭터/디자인** 토큰에만 — 인증·과장 카테고리는 매번 묻는다."""
    return str(key or "").startswith("tm:")


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
        elif action == "strip" and _auto_strippable(key):
            k["default"] = "strip"               # 상표/캐릭터/디자인만 기억 — 인증·과장·레플리카·블랙리스트는 매번 묻는다
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
    """기억된 「빼고 등록」 — 결정 안 된 보류 항목 중 그 낱말의 기본이 strip이면 바로 뺀다. 뺀 라벨 목록.

    Y14(오너 2026-10-21 「AI 초안에 애플 재발 검사」): 이미 「빼고 등록」한 **호환 표기**가 다시 보이면(새 AI 초안 · 나중에 번역된
    상세·옵션 사진) 같은 결정을 다시 건다 — 글자는 바꾸고, 사진은 글자 고치기(오너가 이미 고른 결정이라 사람 지시로 본다)."""
    mem = learned()
    done = []
    for h in scan(extra)["hits"]:
        if h["decided"] == "strip" and h["key"].startswith("compat:"):
            strip_extra(extra, h, erase_pixels=True)
            done.append(h["label"] + "(다시 걸기)")
            continue
        if h["decided"] or h["grade"] == "caution":
            continue
        if _auto_strippable(h["key"]) and (mem.get(h["key"]) or {}).get("default") == "strip":
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
            names = brand_filter(d["names"]) if d.get("cat") == "브랜드 블랙리스트" else d["names"]   # Y11-O: 보통명사는 다시 안 뺀다
            h = {"names": names, "case": bool(d.get("case")), "images": [], "cat": d.get("cat", ""), "found": d.get("found") or [],
                 "to": str(d.get("to") or "")}
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
    return {"count": len(rows), "hits": rows, "waiting": sc.get("waiting") or 0, "skip": sc.get("skip") or {},
            "notes": [n["line"] for n in sc.get("notes") or []], "skip_hint": skip_hint(sc)}
