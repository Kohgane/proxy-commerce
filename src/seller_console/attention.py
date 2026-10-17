"""Y12-A(오너 2026-10-17) — 상품 한 개의 「마지막 동작」과 「손댈 것」을 한 곳에서.

목록 한 줄(마지막 동작 시각)·「손댈 것만」 필터·대시보드 「손댈 것」 묶음이 같은 판정을 쓴다.
저장할 때(`collect_history_store.update`) 한 번 계산해 열 두 개(`last_action_at`·`attn_n`)와 `extra.attn` 요약에 남긴다 —
목록·대시보드는 무거운 extra(사진 번역 기록)를 읽지 않고 그 값만 쓴다.

손댈 것(오너 결정 6): 반려(마켓별) · 보내기 실패 · 오너 확인 대기(지우기 제안 사진 · 등록 보류 · 「확인 필요」 원문 줄).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

KST = timezone(timedelta(hours=9))
_KO_KEYS = ("images_ko", "detail_images_ko", "sku_images_ko")


def _ts(v) -> Optional[datetime]:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def kst(v) -> str:
    """「10-17 14:10」(KST) — 못 읽으면 ""."""
    d = _ts(v)
    return d.astimezone(KST).strftime("%m-%d %H:%M") if d else ""


def _market_word(m: str) -> str:
    if m.startswith("coupang"):
        return "쿠팡"
    if m.startswith("smartstore"):
        return "네이버"
    from .listing_status import chip_label
    return chip_label(m)


def actions(extra: dict, collected_at: str = "") -> List[Dict]:
    """이 상품에 있었던 동작 `[{at, text}]` — 수집 · 마켓 등록 · 쿠팡 상세 보냄/실패 · 네이버 본문 보냄/실패 · 다듬기 완료."""
    ex = extra or {}
    out: List[Dict] = []
    if collected_at:
        out.append({"at": collected_at, "text": "수집"})
    for u in ex.get("uploaded") or []:
        if not isinstance(u, dict) or not u.get("market"):
            continue
        m = str(u["market"])
        if u.get("at"):
            out.append({"at": u["at"], "text": f"{_market_word(m)} 등록"})
        ds = u.get("detail_sync") if isinstance(u.get("detail_sync"), dict) else None
        if ds and ds.get("at") and not ds.get("same"):
            out.append({"at": ds["at"], "text": "네이버 본문 보냄" if ds.get("ok") else "네이버 본문 보내기 실패"})
    sync = ex.get("coupang_detail_sync") if isinstance(ex.get("coupang_detail_sync"), dict) else {}
    for _m, s in sync.items():
        if isinstance(s, dict) and s.get("at") and s.get("state") != "same":
            out.append({"at": s["at"], "text": "쿠팡 상세 보냄" if s.get("ok") else "쿠팡 상세 보내기 실패"})
    for key in _KO_KEYS:
        for e in ex.get(key) or []:
            pl = e.get("polish") if isinstance(e, dict) else None
            if isinstance(pl, dict) and pl.get("at") and pl.get("version"):
                out.append({"at": pl["at"], "text": "다듬기 완료"})
    return out


def last_action(extra: dict, collected_at: str = "") -> Dict:
    """가장 최근 동작 `{at, text, line}` — line = 「10-17 14:10 쿠팡 상세 보냄」(KST). 없으면 빈 값."""
    best = None
    for a in actions(extra, collected_at):
        d = _ts(a["at"])
        if d and (best is None or d > best[0]):
            best = (d, a)
    if not best:
        return {"at": "", "text": "", "line": "", "short": ""}
    d, a = best
    return {"at": d.astimezone(timezone.utc).isoformat(), "text": a["text"], "line": f"{kst(d.isoformat())} {a['text']}",
            "short": short_when(d)}


def short_when(d: datetime, now: Optional[datetime] = None) -> str:
    """모바일 한 줄용 짧은 시각(KST) — 오늘이면 「14:10」, 아니면 「10-17」."""
    k = d.astimezone(KST)
    today = (now or datetime.now(timezone.utc)).astimezone(KST).date()
    return k.strftime("%H:%M") if k.date() == today else k.strftime("%m-%d")


def erase_suggestions(extra: dict) -> int:
    """「지우기 제안」이 남은 **나가는** 사진 장 수(다듬기 기록 `suggest_erase` · 나가지 않는 장은 세지 않는다)."""
    n = 0
    for key in _KO_KEYS:
        for e in (extra or {}).get(key) or []:
            pl = e.get("polish") if isinstance(e, dict) else None
            if isinstance(pl, dict) and int(pl.get("suggest_erase") or 0) > 0 and pl.get("outbound", True):
                n += 1
    return n


def _title_marks(extra: dict, title: str = "") -> List[str]:
    try:
        from src.collectors.ko_polish import gated_names
        return list(gated_names(str((extra or {}).get("title_en") or (extra or {}).get("title") or title or "")))
    except Exception:                                            # noqa: BLE001
        return []


def summarize(extra: dict, title: str = "") -> Dict:
    """저장 때 남기는 작은 요약 `extra.attn` — 목록·대시보드는 이것만 읽는다(무거운 사진 기록은 저장 때 한 번)."""
    from .listing_status import records
    registered = bool(records(extra))
    return {"erase": erase_suggestions(extra),
            # 「확인 필요」 원문 줄(상표 이름) — 아직 안 올린 상품만(올린 상품은 등록 때 이미 넘었다)
            "check": _title_marks(extra, title) if not registered else []}


def _has(attn: Dict) -> bool:
    return bool(int((attn or {}).get("erase") or 0) or (attn or {}).get("check"))


def items(extra: dict, title: str = "", *, fresh: bool = False) -> List[Dict]:
    """손댈 것 `[{kind, market, text}]` — kind = rejected · send_fail · owner.
    오너 확인 대기(지우기 제안·「확인 필요」)는 저장 때 남긴 요약 `extra.attn`을 읽는다(목록·대시보드는 사진 기록 없이 읽는다 —
    요약이 없으면 없음). `fresh=True`면 그 자리에서 다시 잰다(저장·백필)."""
    from .listing_status import records, send_failed, state_word
    ex = extra or {}
    out: List[Dict] = []
    for r in records(ex):
        rv = r.get("review") or {}
        if str(rv.get("state") or "") == "rejected":
            out.append({"kind": "rejected", "market": r["market"],
                        "text": f"{r['label']} {state_word(r['market'], 'rejected', rv.get('status_raw'))}"})
        elif send_failed(ex, r["market"]):
            out.append({"kind": "send_fail", "market": r["market"],
                        "text": f"{r['label']} " + ("상세 보내기 실패" if r["market"].startswith("coupang") else "본문 보내기 실패")})
    attn = summarize(ex, title) if fresh else (ex.get("attn") if isinstance(ex.get("attn"), dict) else {})
    if int(attn.get("erase") or 0):
        out.append({"kind": "owner", "market": "", "text": f"지우기 제안 사진 {int(attn['erase'])}장"})
    rs = ex.get("risk_skip") if isinstance(ex.get("risk_skip"), dict) else None
    if rs and rs.get("reason"):
        out.append({"kind": "owner", "market": "", "text": f"등록 보류 — {str(rs['reason'])[:40]}"})
    if attn.get("check"):
        out.append({"kind": "owner", "market": "", "text": "확인 필요 — " + " · ".join(attn["check"][:3])})
    return out


def stamp(extra: dict, title: str = "", collected_at: str = "") -> Dict:
    """저장 직전: `extra.attn`을 새로 쓰고 열 값 `{last_action_at, attn_n}`을 돌려준다."""
    if not isinstance(extra, dict):
        return {}
    attn = summarize(extra, title)
    if _has(attn):                                               # 남길 게 있을 때만 — 빈 요약으로 extra를 늘리지 않는다
        extra["attn"] = attn
    else:
        extra.pop("attn", None)
    la = last_action(extra, collected_at)
    return {"last_action_at": la["at"] or None, "attn_n": len(items(extra, title))}
