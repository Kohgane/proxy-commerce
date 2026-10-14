"""Y11-I(오너 2026-10-14) — 번역 다듬기(자동). 텐센트 번역본의 상자 글자를 상품 설명 톤 한국어로 고쳐 **새 버전**을 만든다.

실측(VRSUK 운영 상자): 상세 13 「프로피리티어 20」(원문 영어 Proprietary 20) · 상세 17 「아만 평연 봉선」(亚曼平韧缝线) · 상세 8 「자리 Eams」(원문 Chair Eams) —
텐센트는 낱말만 옮기고 문맥(상품명·카테고리·같은 사진의 다른 줄)을 모른다.

흐름(번역 완료 직후, 큐 워커):
1. 상자별 {원문(SourceText) · 텐센트 한국어} + 상품명 · 카테고리 · 같은 사진 다른 상자를 Claude haiku 한 번에(상자 10개씩).
   규칙: 상품 설명 톤 · 브랜드·규격·숫자 보존 · 뜻 모를 원문은 빈칸(지움). 용어집(`src/uploaders/image_glossary.json`)을
   프롬프트에 넣고 텐센트 결과에도 **먼저** 적용한다(AI가 없어도 용어집 고침은 들어간다).
2. 고친 상자만 「글자 고치기」 렌더(`image_edit.apply` — 지우고 글자 얹기)로 **번역본(다듬음)** 버전을 만든다.
   텐센트 번역본은 버전 목록에 남는다(원본 불변 — Y11-E). 기본 선택은 다듬은 쪽.
3. 반례(오너): AI가 「최고·1위·100%」 같은 과장을 만들면 Y10 금지어에 걸린다 — 프롬프트에 금지어를 넣고, **금지어·과장·
   숫자 누락·새 상표 이름이 있는 상자 결과는 버린다**(그 상자는 텐센트 글자 그대로).
4. 비용: haiku 호출마다 하루 카운터(`IMAGE_POLISH_DAILY_CAP`, 기본 400) — 「오늘 텐센트 호출」 옆에 「다듬기 n/400」.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENV_CAP = "IMAGE_POLISH_DAILY_CAP"
DEFAULT_CAP = 400
BATCH = 10
POLISH_BY = "polish"
POLISH_LABEL = "번역본(다듬음)"
_KST = timezone(timedelta(hours=9))
_GLOSSARY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploaders", "image_glossary.json")
#: 다듬기 결과에서 버리는 과장(Y10 금지어 ban_ko에 더해 — 오너 반례 「최고·1위·100%」)
_HYPE = re.compile(r"최고|1\s*위|100\s*%|백\s*퍼센트|최저가?|완벽|유일|무조건|보장|국내\s*최초|세계\s*최초|넘버\s*원|No\.?\s*1", re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def enabled() -> bool:
    return str(os.getenv("IMAGE_POLISH", "1")).strip() != "0"


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, str(DEFAULT_CAP)) or DEFAULT_CAP))
    except ValueError:
        return DEFAULT_CAP


def _day_key() -> str:
    return "imgpolish:day:" + datetime.now(_KST).strftime("%Y-%m-%d")


def today_count() -> int:
    from src.db import image_translate_queue_pg as q
    try:
        return int(q.day_count(_day_key()) or 0)
    except Exception:                                            # noqa: BLE001
        return 0


def glossary() -> List[Dict]:
    try:
        with open(_GLOSSARY_PATH, encoding="utf-8") as f:
            return [t for t in (json.load(f).get("terms") or []) if isinstance(t, dict) and t.get("src") and t.get("ko")]
    except Exception:                                            # noqa: BLE001
        return []


def _srcs(t: Dict) -> List[str]:
    v = t.get("src")
    return [str(x) for x in v] if isinstance(v, list) else [str(v or "")]


def apply_glossary(src: str, tgt: str, terms: Optional[List[Dict]] = None) -> str:
    """원문에 용어가 있고 한국어에 그 용어의 「틀린 말」이 있으면 바른 말로(이미 바른 말이면 그대로)."""
    out = str(tgt or "")
    for t in terms if terms is not None else glossary():
        if not any(s and s in str(src or "") for s in _srcs(t)) or t["ko"] in out:
            continue
        for bad in sorted(t.get("bad") or [], key=len, reverse=True):
            if bad and bad in out:
                out = out.replace(bad, t["ko"])
                break
    return out


def _bans(text: str) -> List[str]:
    hits = []
    try:
        from src.collectors import ko_polish as kp
        hits += [str(x) for x in kp.ban_hits(text) or []]
    except Exception:                                            # noqa: BLE001
        pass
    hits += _HYPE.findall(text or "")
    return hits


def _new_trademark(ko: str, before: str) -> str:
    """다듬은 글자에 원문·텐센트에 없던 상표 이름이 생겼나 — 그 이름(없으면 "")."""
    try:
        from src.services import risk_gate as R
        for e in R._trademark_entries():
            names, case = e.get("names") or [], bool(e.get("case"))
            got = R._find(ko, names, case)
            if got and not R._find(before, names, case):         # 같은 상표의 다른 표기(伊姆斯→임스)는 새 이름이 아니다
                return got[0]
    except Exception:                                            # noqa: BLE001
        pass
    return ""


def check(src: str, tgt: str, ko: str) -> str:
    """다듬은 상자 하나를 쓸 수 있나 — 버릴 사유(쓸 수 있으면 "")."""
    if ko == "":
        return ""                                                # 빈칸(지움) — 뜻 모를 원문
    b = _bans(ko)
    if b:
        return f"금지어·과장({b[0]})"
    before = f"{src} {tgt}"
    for n in _NUM.findall(f"{src}"):
        if n not in ko and n in tgt:
            return f"숫자 누락({n})"                             # 원문·텐센트 둘 다 있던 숫자를 잃었다
    tm = _new_trademark(ko, before)
    if tm:
        return f"없던 상표 이름({tm})"
    if len(ko) > max(2 * len(tgt or ""), len(tgt or "") + 12):
        return "너무 길어 상자에 안 들어감"
    return ""


_SYSTEM = (
    "너는 쇼핑몰 상품 사진 속 글자를 고치는 한국어 편집자다. 중국어 원문과 기계 번역 한국어를 받아, 사진에 그대로 얹을 "
    "자연스러운 한국어로 고친다. 규칙: ① 상품 설명 톤(짧은 명사·설명형), 원문 뜻만 — 없는 내용·과장 추가 금지. "
    "② 브랜드·모델명·규격·숫자·단위는 원문 그대로 둔다. ③ 원문 뜻을 알 수 없거나 깨진 글자면 \"\"(빈칸 — 그 상자는 지운다). "
    "④ 용어집을 반드시 따른다. ⑤ 금지어는 쓰지 않는다. ⑥ 상자 크기에 맞게 기계 번역과 비슷한 길이. "
    "출력은 JSON 하나만: {\"boxes\":[{\"id\":\"t0\",\"ko\":\"...\"}]} — 받은 id 전부."
)


def _prompt(rows: List[Dict], ctx: Dict, terms: List[Dict]) -> str:
    lines = [f"상품명: {ctx.get('title') or '-'}", f"카테고리: {ctx.get('category') or '-'}",
             "용어집(원문→한국어): " + ", ".join(f"{'/'.join(_srcs(t))}→{t['ko']}" for t in terms),
             "금지어: 최고, 1위, 100%, 최저가, 완벽, 유일, 무조건, 보장, 국내 최초, 세계 최초, 할인율·쿠폰 문구",
             "같은 사진의 상자들(id · 원문 · 기계 번역):"]
    for r in rows:
        lines.append(json.dumps({"id": r["id"], "src": r["src"], "mt": r["tgt"]}, ensure_ascii=False))
    return "\n".join(lines)


def _parse(text: str) -> Dict[str, str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
    except Exception:                                            # noqa: BLE001
        return {}
    out = {}
    for b in d.get("boxes") or []:
        if isinstance(b, dict) and isinstance(b.get("id"), str) and isinstance(b.get("ko"), str):
            out[b["id"]] = b["ko"].strip()
    return out


def polish_boxes(boxes: List[Dict], ctx: Dict) -> Dict:
    """상자들 → `{rows:[{id, src, tgt, glossary, ko, from, why}], calls, ai_why}`.
    `from` = polish(AI 다듬음 채택) · glossary(용어집만) · tencent(그대로). AI가 없거나 상한이면 용어집만."""
    from src.ai import llm
    terms = glossary()
    rows = []
    for b in boxes:
        src, tgt = str(b.get("src") or ""), str(b.get("tgt") or "")
        g = apply_glossary(src, tgt, terms)
        rows.append({"id": b["id"], "src": src, "tgt": tgt, "glossary": g, "ko": g,
                     "from": "glossary" if g != tgt else "tencent", "why": ""})
    calls, ai_why = 0, ""
    if not rows:
        return {"rows": rows, "calls": 0, "ai_why": ""}
    if not llm.anthropic_ready():
        ai_why = "AI 다듬기 못 씀(Claude 미연결) — 용어집만 적용"
        return {"rows": rows, "calls": 0, "ai_why": ai_why}
    from src.db import image_translate_queue_pg as q
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        took, n = q.take_start(_day_key(), daily_cap())
        if not took:
            ai_why = f"오늘 다듬기 상한({daily_cap()}회)을 다 써서 용어집만 적용"
            break
        calls += 1
        res = llm.complete(_prompt([dict(r, tgt=r["glossary"]) for r in chunk], ctx, terms), system=_SYSTEM, size="small",
                           max_tokens=1200, purpose="image_polish", timeout=30.0, json_mode=True, providers=["anthropic"])
        got = _parse(res.get("text") or "")
        if not got:
            ai_why = f"AI 응답을 읽지 못함({str(res.get('error') or '빈 응답')[:60]}) — 용어집만 적용"
            continue
        for r in chunk:
            if r["id"] not in got:
                continue
            ko = got[r["id"]]
            r["ai"] = ko
            why = check(r["src"], r["glossary"], ko)
            if why:
                r["why"] = why                                   # 버림 — 텐센트(용어집) 글자 그대로
                continue
            if ko != r["glossary"]:
                r["ko"], r["from"] = ko, "polish"
    return {"rows": rows, "calls": calls, "ai_why": ai_why}


def polish_entry(extra: dict, kind: str, idx: int) -> Dict:
    """번역본 한 장 → 다듬은 버전(편집본, by=polish). 결과 `{ok, changed, version?, rows, calls, why}` — 저장은 호출부."""
    from src.services import image_edit as IE
    if not enabled():
        return {"ok": False, "why": "다듬기 꺼짐"}
    e = IE._entry(extra, kind, idx) or {}
    if IE.current_key(e) != IE.V_TRANSLATED:
        return {"ok": False, "why": "번역본이 지금 버전이 아님(사람이 고른 버전은 건드리지 않음)"}
    if any(x.get("by") == POLISH_BY for x in IE.edits(e)):
        return {"ok": False, "why": "이미 다듬음"}
    ok_c, _w = IE.configured()
    if not ok_c:
        return {"ok": False, "why": "사진 편집을 쓸 수 없어 다듬은 버전을 못 만듦"}
    p = IE.plan(extra, kind, idx)
    boxes = [b for b in p.get("boxes") or [] if b.get("tgt") or b.get("src")]
    if not boxes:
        return {"ok": False, "why": p.get("why") or "다듬을 글자 상자가 없음"}
    ctx = {"title": str(extra.get("title_ko") or extra.get("title") or "")[:80],
           "category": str(extra.get("coupang_category_name") or extra.get("naver_category_name")
                           or extra.get("category") or "")[:60]}
    pr = polish_boxes(boxes, ctx)
    ops = []
    for r in pr["rows"]:
        if r["ko"] == r["tgt"]:
            continue
        ops.append({"id": r["id"], "action": "erase"} if r["ko"] == "" else {"id": r["id"], "action": "text", "text": r["ko"]})
    out = {"ok": True, "changed": len(ops), "rows": pr["rows"], "calls": pr["calls"], "why": pr["ai_why"]}
    e = IE._entry(extra, kind, idx, create=True)
    e["polish"] = {"at": datetime.now(timezone.utc).isoformat(), "calls": pr["calls"], "changed": len(ops),
                   "rows": [{k: r.get(k, "") for k in ("id", "src", "tgt", "ko", "ai", "from", "why")} for r in pr["rows"]][:40],
                   "why": pr["ai_why"]}
    if not ops:
        return out
    res = IE.apply(extra, kind, idx, ops, by=POLISH_BY)
    if not res.get("ok"):
        e["polish"]["why"] = str(res.get("error") or "다듬은 버전을 만들지 못함")[:120]
        return dict(out, ok=False, why=e["polish"]["why"])
    e["polish"]["version"] = res.get("version")
    _carry_boxes(e, str(res.get("version") or ""), {r["id"]: r["ko"] for r in pr["rows"]})
    return dict(out, version=res.get("version"), pending=res.get("pending"))


def _carry_boxes(e: dict, key: str, ko_by_id: Dict[str, str]) -> None:
    """다듬은 버전의 글자 상자 = 번역본 상자 + 다듬은 한국어(지운 상자는 뺌) — 편집기가 그 버전을 다시 OCR하지 않게."""
    from src.services import image_edit as IE
    ed = next((x for x in IE.edits(e) if f"edit:{x['n']}" == key), None)
    boxes, size = e.get("boxes"), e.get("box_size")
    if not ed or not isinstance(boxes, list) or not size:
        return
    out = []
    for i, b in enumerate(boxes):
        ko = ko_by_id.get(f"t{i}", b.get("tgt"))
        if ko == "":
            continue
        out.append(dict(b, tgt=ko))
    e.setdefault("vboxes", {})[key] = {"boxes": out, "size": size, "img": ed["url"], "source": "polish",
                                       "at": datetime.now(timezone.utc).isoformat(), "angle": 0}


def polish_job(item_id: str, uid: str, kind: str, idx: int) -> Dict:
    """큐 워커 — 저장된 상품을 다시 읽어 다듬고 저장. 실패해도 번역 결과는 그대로(예외 없음)."""
    from src.seller_console import collect_history_store as store
    try:
        row = store.get(item_id, seller_ids={uid}) or {}
        extra = json.loads(row.get("extra_json") or "{}") or {}
        res = polish_entry(extra, kind, idx)
        if "rows" in res:                                        # 다듬기 기록(바뀐 것 없음 포함)이 생겼을 때만 저장
            from src.services import image_edit as IE
            mine = IE._entry(extra, kind, idx)
            ko_key = "images_ko" if kind == "gallery" else "detail_images_ko"
            row = store.get(item_id, seller_ids={uid}) or {}     # 그 사이 다른 장이 적혔을 수 있다 — 이 장만 바꿔 넣는다
            fresh = json.loads(row.get("extra_json") or "{}") or {}
            ents = [x for x in fresh.get(ko_key) or [] if isinstance(x, dict) and int(x.get("idx", -1)) != int(idx)]
            fresh[ko_key] = sorted(ents + [mine], key=lambda x: int(x.get("idx", -1)))
            store.update(item_id, seller_ids={uid}, extra_json=json.dumps(fresh, ensure_ascii=False))
        logger.info("[다듬기] item=%s %s#%s 바뀐 상자 %s · haiku %s회 · %s", item_id, kind, idx, res.get("changed", 0),
                    res.get("calls", 0), res.get("why") or "ok")
        return res
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[다듬기] item=%s %s#%s 실패: %s", item_id, kind, idx, exc)
        return {"ok": False, "why": f"{type(exc).__name__}"}


def item_targets(extra: dict) -> List[Tuple[str, int]]:
    """다듬을 장 — 번역본(상자 있음)이 지금 버전이고 아직 안 다듬은 장."""
    from src.services import image_edit as IE
    from src.services import image_translate_store as istore
    out = []
    for key, kind in (("images_ko", "gallery"), ("detail_images_ko", "detail")):
        for e in extra.get(key) or []:
            if not isinstance(e, dict) or e.get("status") != "done" or not istore.has_boxes(e):
                continue
            if IE.current_key(e) != IE.V_TRANSLATED or any(x.get("by") == POLISH_BY for x in IE.edits(e)):
                continue
            out.append((kind, int(e.get("idx", -1))))
    return out


_RUN = {"busy": False}


def start_item(item_id: str) -> Dict:
    """이미 번역된 상품 한 개를 다듬는다(관리자 버튼 — 이 기능 전에 번역된 장용). 백그라운드 · 결과는 장마다 `polish` 기록."""
    import threading
    from src.services.ocr_compare_diag import _item
    if _RUN["busy"]:
        return {"ok": False, "why": "다듬는 중이에요 — 끝나면 다시 눌러 주세요"}
    row, uid = _item(item_id)
    if not row:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    targets = item_targets(json.loads(row.get("extra_json") or "{}") or {})
    if not targets:
        return {"ok": True, "n": 0, "why": "다듬을 번역본이 없어요(상자 없는 번역본·이미 다듬음·다른 버전 선택 제외)"}

    from src.db import image_translate_queue_pg as q
    _RUN["busy"] = True                                          # 시작 응답 전에 잡아 둔다(연타 두 번 시작 금지)
    q.state_set(_item_key(item_id), {"running": True, "n": len(targets), "at": datetime.now(timezone.utc).isoformat()})

    def _go():
        done, whys = 0, []
        try:
            for kind, idx in targets:
                r = polish_job(item_id, uid, kind, idx) or {}
                done += 1
                if r.get("why") and not r.get("changed"):
                    whys.append(str(r["why"]))
        finally:
            _RUN["busy"] = False
            q.state_set(_item_key(item_id), {"running": False, "n": len(targets), "done": done,
                                             "why": (max(set(whys), key=whys.count) if whys else ""),
                                             "at": datetime.now(timezone.utc).isoformat()})

    threading.Thread(target=_go, daemon=True, name="image-polish").start()
    return {"ok": True, "n": len(targets)}


def _item_key(item_id: str) -> str:
    return f"imgpolish:item:{item_id}"


def item_line(item_id: str, extra: dict) -> str:
    """결과줄 — 「번역 다듬기 n장: 바뀐 상자 n · AI n회 · 버린 결과 n」 + 장별 한 줄 요약(앞 3장)."""
    from src.db import image_translate_queue_pg as q
    st = q.state_get(_item_key(item_id)) or {}
    rows = []
    for key, lab in (("images_ko", "사진"), ("detail_images_ko", "상세")):
        for e in extra.get(key) or []:
            pl = e.get("polish") if isinstance(e, dict) else None
            if isinstance(pl, dict):
                rows.append((f"{lab} {int(e.get('idx', -1)) + 1}", pl))
    if st.get("running"):
        return f"번역 다듬기 중… ({len(rows)}/{st.get('n') or '?'}장)"
    if not rows:
        if not st:
            return ""
        return "번역 다듬기: 다듬은 사진이 아직 없어요" + (f" — {st['why']}" if st.get("why") else "")
    changed = sum(int(pl.get("changed") or 0) for _n, pl in rows)
    calls = sum(int(pl.get("calls") or 0) for _n, pl in rows)
    dropped = sum(1 for _n, pl in rows for r in pl.get("rows") or [] if r.get("why"))
    whys = sorted({str(pl.get("why")) for _n, pl in rows if pl.get("why")})
    s = f"번역 다듬기 {len(rows)}장: 바뀐 상자 {changed} · AI {calls}회"
    if dropped:
        s += f" · AI 결과 버림 {dropped}(금지어·숫자 등)"
    if whys:
        s += " · " + whys[0][:60]
    return s
