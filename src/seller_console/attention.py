"""Y12-A(오너 2026-10-17) — 상품 한 개의 「마지막 동작」과 「손댈 것」을 한 곳에서.

목록 한 줄(마지막 동작 시각)·「손댈 것만」 필터·대시보드 「손댈 것」 묶음이 같은 판정을 쓴다.
저장할 때(`collect_history_store.update`) 한 번 계산해 열 두 개(`last_action_at`·`attn_n`)와 `extra.attn` 요약에 남긴다 —
목록·대시보드는 무거운 extra(사진 번역 기록)를 읽지 않고 그 값만 쓴다.

손댈 것(오너 결정 6): 반려(마켓별) · 보내기 실패 · 오너 확인 대기(지우기 제안 사진 · 등록 보류 · 「확인 필요」 원문 줄).
Y12-B(오너 2026-10-17): 기준 = **오너가 눌러야 풀리는 것만** 손댈 것.
  수집 실패 — 자동 재수집이 예정된 건은 「돌아가는 것 · 재수집 대기」(`attn.refetch`), 재수집 소진·자동 재수집 없음만 손댈 것(`attn.fail`).
  지우기 제안 — 사진별 「넘김」·상품별 「전부 넘김」. 지움이든 넘김이든 처리되면 빠진다(넘김은 기록만 · 픽셀 0).
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


#: Y12-A(오너 e): 반려는 숨기지 않는다 — 마지막 조회가 이보다 오래면 「조회 낡음」을 붙인다.
STALE_CHECK_HOURS = 24


def check_note(checked_at, now: Optional[datetime] = None) -> str:
    """「마지막 조회 10-17 14:10」(+ 24시간 넘으면 「· 조회 낡음」). 조회 기록이 없으면 「조회 기록 없음 · 조회 낡음」."""
    d = _ts(checked_at)
    if not d:
        return "조회 기록 없음 · 조회 낡음"
    now = now or datetime.now(timezone.utc)
    old = (now - d) > timedelta(hours=STALE_CHECK_HOURS)
    return f"마지막 조회 {kst(d.isoformat())}" + (" · 조회 낡음" if old else "")


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


_KIND_OF = {"images_ko": "gallery", "detail_images_ko": "detail", "sku_images_ko": "sku"}
_KIND_WORD = {"gallery": "대표·추가", "detail": "상세", "sku": "옵션 사진"}


def _suggested(pl: dict) -> List[str]:
    """다듬기 기록에서 AI가 「지우기 제안」한 상자의 글자(텐센트 글자 · 빈 글자는 뺀다)."""
    return [str(r.get("tgt") or "") for r in pl.get("rows") or []
            if isinstance(r, dict) and r.get("suggest_erase") and str(r.get("tgt") or "").strip()]


def erase_photos(extra: dict) -> List[Dict]:
    """Y12-B(오너 2026-10-17) — 지우기 제안이 있는 **나가는** 사진 `[{kind, idx, word, texts, state, url}]`.

    state: `pending`(아직 손 안 댐) · `erased`(지금 나가는 편집본이 그 글자를 지웠다) · `skipped`(오너가 「넘김」).
    지움이든 넘김이든 제안 글자가 **전부** 처리돼야 `pending`에서 빠진다. 넘김은 기록만 남긴다(원본·번역본 픽셀 0).
    다시 다듬어 **새 제안 글자**가 나오면 그 글자는 다시 `pending`이다(넘긴 글자 기준으로 맞춘다)."""
    out: List[Dict] = []
    for key in _KO_KEYS:
        for e in (extra or {}).get(key) or []:
            pl = e.get("polish") if isinstance(e, dict) else None
            if not (isinstance(pl, dict) and int(pl.get("suggest_erase") or 0) > 0 and pl.get("outbound", True)):
                continue
            texts = _suggested(pl)
            sk = e.get("erase_skip") if isinstance(e.get("erase_skip"), dict) else {}
            if not texts:
                # 상자 줄 없이 장 수만 남은 기록 — 글자로 못 맞추니 그 다듬기 실행(`polish.at`)째로 넘김을 맞춘다
                state = "skipped" if sk.get("polish_at") and sk.get("polish_at") == pl.get("at") else "pending"
                left = []
            else:
                ed = e.get("edit") if isinstance(e.get("edit"), dict) and e.get("use") else {}
                erased = {str(x) for x in (ed or {}).get("erased") or []}
                skipped = {str(x) for x in sk.get("texts") or []}
                left = [t for t in texts if t not in erased and t not in skipped]
                state = "pending" if left else ("skipped" if any(t in skipped and t not in erased for t in texts) else "erased")
            kind = str(e.get("kind") or _KIND_OF[key])
            out.append({"kind": kind, "idx": int(e.get("idx", -1)), "word": f"{_KIND_WORD.get(kind, kind)} {int(e.get('idx', -1)) + 1}번째",
                        "texts": left or texts, "state": state, "url": str(e.get("url") or "") if e.get("use") else "",
                        "skipped_at": kst(sk.get("at")) if state == "skipped" else ""})
    return out


def erase_suggestions(extra: dict) -> int:
    """「지우기 제안」이 남은 **나가는** 사진 장 수 — 지움·넘김으로 처리된 장은 세지 않는다(Y12-B)."""
    return sum(1 for p in erase_photos(extra) if p["state"] == "pending")


def skip_erase(extra: dict, kind: str, idx: int, by: str = "owner") -> bool:
    """「넘김」 — 그 사진의 지우기 제안 글자를 넘긴 것으로 적는다(사진·원본·번역본은 그대로). 넘길 제안이 없으면 False."""
    from src.services.image_translate_store import keys_of
    for e in (extra or {}).get(keys_of(kind)[1]) or []:
        if not (isinstance(e, dict) and int(e.get("idx", -1)) == int(idx)):
            continue
        pl = e.get("polish") if isinstance(e.get("polish"), dict) else {}
        texts = _suggested(pl)
        if not (texts or int(pl.get("suggest_erase") or 0) > 0):
            return False
        prev = e.get("erase_skip") if isinstance(e.get("erase_skip"), dict) else {}
        e["erase_skip"] = {"at": datetime.now(timezone.utc).isoformat(), "by": by, "polish_at": pl.get("at") or "",
                           "texts": sorted({*(str(x) for x in prev.get("texts") or []), *texts})}
        return True
    return False


#: 보강 큐 재시도 상한 — 서버 상한(`extension_api.ENRICH_MAX_ATTEMPTS`)을 그대로 읽는다(못 읽으면 같은 값 3).
def _max_attempts() -> int:
    try:
        from src.api.extension_api import ENRICH_MAX_ATTEMPTS
        return int(ENRICH_MAX_ATTEMPTS)
    except Exception:                                            # noqa: BLE001
        return 3


_CARRY_KINDS = ("provider_quota", "provider_cap")                # onebound_carry.CARRY_KINDS — 하루 한도에 막혀 이월 대기


def collect_fail(extra: dict, title: str = "") -> Optional[Dict]:
    """Y12-B(오너 2026-10-17 A3) — 수집 실패 판정 `{phase, text, why}` · 실패가 아니면 None.

    phase `waiting` = 자동 재수집이 예정됐다(PC 고가수집기 보강 큐에 남음 · 온바운드 하루 한도 이월) → 「돌아가는 것 · 재수집 대기」.
    phase `exhausted` = 자동으로는 다시 안 온다(보강 시도 상한 소진 · 막힘 · 보강 축 없는 완전 수집의 핵심 정보 미확보)
      → 「손댈 것」(오너가 「원본에서 다시 수집」을 눌러야 풀린다).
    보강 축만 있고 실패 기록이 없는 부분 초안(「보강 대기」)과 이미 마켓에 올라간 상품은 실패가 아니다."""
    from src.collectors.collect_status import compute_collect_status, enrich_axes
    from .listing_status import records
    ex = extra or {}
    if records(ex):                                              # 마켓에 올라간 상품 — 수집은 이미 넘었다
        return None
    ax = enrich_axes(ex)
    if ax["is_draft"]:
        st, att, cap = ax["enrich_state"], ax["attempts"], _max_attempts()
        if st == "done":
            return None
        if st == "blocked" or att >= cap:
            return {"phase": "exhausted", "text": "수집 실패 · " + (ax["reason"] or f"{att}회 시도 후 멈춤"),
                    "why": f"자동 재수집 {cap}회를 다 썼어요 — 「원본에서 다시 수집」"}
        ae = ex.get("auto_enrich") if isinstance(ex.get("auto_enrich"), dict) else {}
        failed = att > 0 or bool(ex.get("enrich_fail")) or str(ae.get("state") or "") == "manual"
        if not (failed or ex.get("enrich_rerun")):
            return None
        why = ("하루 한도 — 한도가 풀리면 서버가 자동으로" if str(ae.get("kind") or "") in _CARRY_KINDS
               else "PC 고가수집기가 켜지면 차례로 엽니다")
        return {"phase": "waiting", "text": "재수집 대기", "why": f"{why} · 시도 {att}/{cap}"}
    if compute_collect_status(ex, title)["status"] == "실패":
        return {"phase": "exhausted", "text": "수집 실패 · 가격·갤러리를 못 읽었어요",
                "why": "자동 재수집이 없어요 — 「원본에서 다시 수집」"}
    return None


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
    out = {"erase": erase_suggestions(extra),
           # 「확인 필요」 원문 줄(상표 이름) — 아직 안 올린 상품만(올린 상품은 등록 때 이미 넘었다)
           "check": _title_marks(extra, title) if not registered else []}
    cf = collect_fail(extra, title)                              # Y12-B: 수집 실패 — 소진은 손댈 것, 예정은 재수집 대기
    if cf:
        out["fail" if cf["phase"] == "exhausted" else "refetch"] = cf["text"] + " · " + cf["why"]
    return out


def _has(attn: Dict) -> bool:
    a = attn or {}
    return bool(int(a.get("erase") or 0) or a.get("check") or a.get("fail") or a.get("refetch"))


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
                        "text": f"{r['label']} {state_word(r['market'], 'rejected', rv.get('status_raw'))}",
                        "note": check_note(rv.get("checked_at"))})
        elif send_failed(ex, r["market"]):
            out.append({"kind": "send_fail", "market": r["market"],
                        "text": f"{r['label']} " + ("상세 보내기 실패" if r["market"].startswith("coupang") else "본문 보내기 실패")})
    attn = summarize(ex, title) if fresh else (ex.get("attn") if isinstance(ex.get("attn"), dict) else {})
    if attn.get("fail"):                                         # Y12-B: 재수집 소진 · 자동 재수집 없음 — 오너가 눌러야 풀린다
        out.append({"kind": "collect_fail", "market": "", "text": str(attn["fail"])})
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
