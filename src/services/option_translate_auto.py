"""src/services/option_translate_auto.py — J1(오너 2026-09-30-J): 수집하면 옵션 값·상품명 **자동 번역**(퍼센티처럼).

T2에서는 「수집 시 자동 큐는 안 넣음(무료 한도를 조용히 쓰지 않게)」으로 뒀다 — 오너가 폐기했다.

흐름:
  1) 수집·확장 보강이 끝나는 자리에서 **정리 규칙(ko_polish) 단계를 즉시** 돌린다(비용 0) —
     `values_ko`·`name_ko`를 채우고, 규칙으로 안 풀린 **외국어(한자·가나) 값만** 남긴다.
  2) 남은 게 있으면 상품 하나를 큐에 넣는다 → 워커가 번역기 체인(`translate_options`)으로 옮긴다.
     상품명도 번역본이 없거나 한자가 남았으면 같은 일에서 옮긴다(1개로 센다).

비용 가드(이미지 번역 큐와 같은 틀):
  - **일일 상한** `OPTION_TRANSLATE_DAILY_CAP`(기본 2000) = **번역기에 보낸 값 수**(실패 포함), KST 자정에 새로 센다.
    남은 몫이 모자라면 그만큼만 보내고 나머지는 대기(내일 이어서).
  - **실패 20회**(마지막 재개 이후 실패한 상품 수)면 자동 일시정지 — 오너가 「재개」를 눌러야 계속.
  - 셀러별 무료 번역 카운터(`translation_usage`, 상품 단위)는 건드리지 않는다 — 이 큐의 한도는 위 상한 하나.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

ENV_CAP = "OPTION_TRANSLATE_DAILY_CAP"
DEFAULT_CAP = 2000
FAIL_PAUSE_AT = 20
MAX_VALUES_PER_JOB = 180            # translate_options 한 번이 보내는 최대(12묶음 × 15)
_KST = timezone(timedelta(hours=9))
_STATE_KEY = "optko_auto:global"
_KANA = re.compile("[぀-ヿ]")

_WORKER = {"thread": None, "lock": threading.Lock()}


def _q():
    from src.db import option_translate_queue_pg as q
    return q


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, str(DEFAULT_CAP))))
    except (TypeError, ValueError):
        return DEFAULT_CAP


def kst_day(now=None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(_KST).strftime("%Y-%m-%d")


def _day_key(now=None) -> str:
    return "optko_auto:day:" + kst_day(now)


# ── 규칙 단계(비용 0) ─────────────────────────────────────────────────────────

def foreign(text) -> bool:
    """한국어로 아직 안 옮겨진 글(한자·가나)이 있나."""
    from src.collectors.ko_polish import has_han
    s = str(text or "")
    return has_han(s) or bool(_KANA.search(s))


def _val(v) -> str:
    return str((v or {}).get("name") or "") if isinstance(v, dict) else str(v or "")


def _rule(term: str) -> str:
    """규칙표로 풀리면 한국어, 아니면 ''. 중국어(가나 없음)만 — 일본어는 번역기로."""
    from src.collectors import ko_polish as kp
    if not kp.has_han(term) or _KANA.search(term):
        return ""
    return kp.option_value(term)["value"]


def rule_pass(extra: dict) -> dict:
    """`extra["options"]`에 규칙 결과를 **그 자리에서** 채운다 → `{changed, pending, title_pending}`.

    이미 한국어로 옮겨진 값(오너 수정·번역기 결과)은 건드리지 않는다. 못 옮긴 자리는 원문을 둔다(가짜 번역 0).
    """
    changed = False
    pending: list = []
    for o in (extra.get("options") or []) if isinstance(extra.get("options"), list) else []:
        if not isinstance(o, dict):
            continue
        vals = [_val(v).strip() for v in (o.get("values") or [])]
        vko = list(o.get("values_ko") or [])
        vko += [""] * (len(vals) - len(vko))
        new = []
        for v, k in zip(vals, vko):
            k = str(k or "").strip()
            if k and k != v and not foreign(k):
                # T1/T4(오너 2026-10-02): 이미 옮긴 값도 **새 정리 규칙**을 한 번 더(이모지·판촉·직역 — 비용 0).
                from src.collectors import ko_polish as _kp
                k2 = _kp.polish_ko(k) or k
                new.append(k2)
                continue
            if not foreign(v):
                new.append(v)                           # 영문·숫자·한국어 — 옮길 것 없음
                continue
            from src.collectors import ko_polish as _kp
            if _kp.non_option(v):
                new.append(k or v)                      # U4: 옵션 아님(보증·서비스 문구) — 번역기에 보내지 않는다
                continue
            r = _rule(v)
            if r:
                new.append(r)
                continue
            new.append(v)
            if v not in pending:
                pending.append(v)
        if new != list(o.get("values_ko") or []):
            o["values_ko"] = new
            changed = True
        nm = str(o.get("name") or "").strip()
        nk = str(o.get("name_ko") or "").strip()
        if nm and not (nk and not foreign(nk)):
            # Y2: 축 **이름**은 옵션 이름 용어집이 먼저(大小·尺寸·尺码→사이즈, 颜色·颜色分类→색상) — 쿠팡 필수 옵션과 같은 말.
            from src.uploaders.coupang_options import OPTION_NAME_GLOSSARY as _ONG
            r = _ONG.get(nm) or (_rule(nm) if foreign(nm) else nm)
            if r and r != nk:
                o["name_ko"] = r
                changed = True
            elif not r and nm not in pending:
                pending.append(nm)
    return {"changed": changed, "pending": pending, "title_pending": title_pending(extra)}


def title_pending(extra: dict) -> bool:
    """상품명 번역본이 없거나 한자·가나가 남았나(원문이 외국어일 때만)."""
    src = str(extra.get("title_en") or extra.get("title") or "")
    if not foreign(src):
        return False
    ko = str(extra.get("title_ko") or "")
    return (not ko) or ko == src or foreign(ko)


def enqueue_if_pending(user_id: str, item_id: str, extra: dict, *, kick_worker: bool = True) -> bool:
    """규칙 단계 뒤 남은 게 있으면 큐에. 번역 끄기(`translate_requested is False`)면 넣지 않는다."""
    if not (user_id and item_id) or extra.get("translate_requested") is False:
        return False
    st = rule_pass(dict(extra, options=json.loads(json.dumps(extra.get("options") or []))))
    if not (st["pending"] or st["title_pending"]):
        return False
    try:
        n = _q().enqueue(user_id, item_id)
    except Exception as exc:
        logger.warning("[옵션번역·자동] 접수 실패 item=%s: %s", item_id, exc)
        return False
    if n:
        logger.info("[옵션번역·자동] 접수 item=%s 값 %s개%s", item_id, len(st["pending"]),
                    " + 상품명" if st["title_pending"] else "")
        if kick_worker:
            kick()
    return bool(n)


# ── 상태 ──────────────────────────────────────────────────────────────────────

def pause_state() -> dict:
    return _q().state_get(_STATE_KEY)


def _since_resume():
    ts = pause_state().get("resumed_at") or ""
    try:
        return datetime.fromisoformat(ts) if ts else datetime(1970, 1, 1, tzinfo=timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def pause(reason: str) -> None:
    st = pause_state()
    st.update({"paused": True, "reason": reason, "paused_at": datetime.now(timezone.utc).isoformat()})
    _q().state_set(_STATE_KEY, st)
    logger.warning("[옵션번역·자동] 큐 일시정지 — %s", reason)


def resume() -> dict:
    st = {"paused": False, "reason": "", "resumed_at": datetime.now(timezone.utc).isoformat()}
    _q().state_set(_STATE_KEY, st)
    kick()
    return st


def status() -> dict:
    q = _q()
    st = pause_state()
    c = q.counts()
    today, cap = q.day_count(_day_key()), daily_cap()
    return {"ok": True, "today": today, "cap": cap, "day": kst_day(), "env": ENV_CAP,
            "paused": bool(st.get("paused")), "pause_reason": st.get("reason") or "",
            "failed_since_resume": q.failed_since(_since_resume()), "fail_pause_at": FAIL_PAUSE_AT,
            "queued": c.get("queued", 0), "running": c.get("running", 0), "done": c.get("done", 0),
            "failed": c.get("failed", 0), "waiting_cap": bool(c.get("queued")) and today >= cap}


# ── 처리 ──────────────────────────────────────────────────────────────────────

def kick() -> None:
    if os.getenv("OPTION_TRANSLATE_AUTO_SYNC") == "1":      # 테스트: 같은 스레드에서 끝까지
        run_until_idle()
        return
    if os.getenv("OPTION_TRANSLATE_AUTO_OFF") == "1":
        return
    from src.services import workers as _w
    if not _w.workers_enabled():                      # W2: 워커는 WORKERS_ENABLED 서비스에서만 — 여기선 접수만(큐에 남는다)
        logger.info("[옵션번역·자동] 이 서비스(%s)는 워커 꺼짐(%s) — 접수만", _w.service_name(), _w.gate_text())
        return
    with _WORKER["lock"]:
        th = _WORKER["thread"]
        if th and th.is_alive():
            return
        th = threading.Thread(target=run_until_idle, daemon=True, name="optko-auto")
        _WORKER["thread"] = th
        th.start()


def run_until_idle(max_jobs: int = 10_000) -> int:
    """W2: 서비스 간 단일 실행 — DB 리스를 잡은 한 곳만 돈다. 실행 기록은 서비스별로 남긴다."""
    from src.services import workers as _w
    if not _w.lease("optko-auto"):
        logger.info("[옵션번역·자동] 다른 서비스가 돌리는 중 — 이번엔 건너뜀")
        return 0
    n = 0
    try:
        n = _drain(max_jobs)
        return n
    finally:
        _w.release("optko-auto")
        _w.record_run("optko-auto", n)


def _drain(max_jobs: int = 10_000) -> int:
    q = _q()
    n = 0
    while n < max_jobs:
        if pause_state().get("paused"):
            return n
        from src.services import workers as _w
        _w.lease("optko-auto")                                 # 리스 갱신(장마다)
        job = q.lease_next()
        if not job:
            return n
        try:
            status_, reason, sent = _job(job)
        except Exception as exc:                          # pragma: no cover
            status_, reason, sent = "failed", f"{type(exc).__name__}: {exc}", 0
        if status_ == "cap":
            q.requeue(job["id"])                          # 보내지 않았다 — 내일(KST) 다시
            logger.info("[옵션번역·자동] 일일 상한 도달(%s/%s) — 대기", q.day_count(_day_key()), daily_cap())
            return n
        q.finish(job["id"], status_, reason, sent)
        n += 1
        if status_ == "failed" and q.failed_since(_since_resume()) >= FAIL_PAUSE_AT:
            pause(f"번역 실패 {FAIL_PAUSE_AT}회 누적 — 원인을 확인한 뒤 「재개」를 눌러 주세요(마지막 사유: {reason[:80]})")
            return n
    return n


def _load(item_id: str, uid: str):
    from src.seller_console import collect_history_store as store
    row = store.get(item_id, seller_ids={uid}) or {}
    try:
        ex = json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    return row, ex


def _ko_count(ex: dict) -> int:
    """옵션 이름·값 중 한국어로 채워진 자리 수(외국어·빈칸 제외) — 규칙이 몇 개 옮겼는지 세는 데 쓴다."""
    n = 0
    for o in ex.get("options") or []:
        if not isinstance(o, dict):
            continue
        k = str(o.get("name_ko") or "").strip()
        n += bool(k and not foreign(k))
        n += sum(1 for v in o.get("values_ko") or [] if str(v or "").strip() and not foreign(v))
    return n


def _job(job: dict) -> tuple:
    """상품 하나 — `(status, reason, values_sent)`. status: done | failed | skipped | queued(나머지 내일) | cap."""
    from src.seller_console import collect_history_store as store
    from src.collectors import ko_polish as kp
    q = _q()
    item_id, uid = job["item_id"], job["user_id"]
    row, ex = _load(item_id, uid)
    if not row:
        return "skipped", "상품이 더는 없습니다", 0
    _ko0 = _ko_count(ex)
    st = rule_pass(ex)
    ruled = max(0, _ko_count(ex) - _ko0)          # Y2: 규칙(축 이름 사전·값 표)이 이번에 옮긴 자리 수
    want_vals = st["pending"][:MAX_VALUES_PER_JOB]
    need = len(want_vals) + (1 if st["title_pending"] else 0)
    if not need:
        if st["changed"]:
            store.update(item_id, seller_ids={uid}, extra_json=json.dumps(ex, ensure_ascii=False))
        return "done", "규칙으로 끝남(번역기 안 씀)", 0
    granted, _today = q.take_n(_day_key(), daily_cap(), need)
    if not granted:
        return "cap", "", 0
    from src.seller_console.ai.translator import AITranslator
    tr = AITranslator()
    title_upd = None
    moved, sent, errors = 0, 0, []
    budget = granted
    if st["title_pending"] and budget:
        budget -= 1
        sent += 1
        src = str(ex.get("title_en") or ex.get("title") or row.get("title") or "")
        src_t, brand = kp.title_for_translator(src, ex)
        try:
            out = tr.translate_product({"title": src_t or src, "description": ""})
            ko = kp.polish_ko(str(out.get("title_ko") or "").strip(), src=src)   # Y6: 원문 보고 오역 사전·IP 삭제
            prov = str(out.get("provider") or "")
            if ko and ko != src and not foreign(ko) and prov not in ("none", "stub", ""):
                if brand:
                    ko = kp.attach_brand(ko, brand)
                    ex["brand_romanized"] = {k: brand[k] for k in ("han", "latin", "field")}
                title_upd = ko
                moved += 1
            else:
                errors.append(str(out.get("error") or f"상품명 못 옮김({prov or '번역기 없음'})"))
        except Exception as exc:
            errors.append(f"상품명 {type(exc).__name__}: {exc}")
    vals = want_vals[:budget]
    mapping = {}
    if vals:
        sent += len(vals)
        try:
            out = tr.translate_options([{"name": "", "values": vals}])
            opt = (out.get("options") or [{}])[0]
            for v, k in zip(opt.get("values") or [], opt.get("values_ko") or []):
                k = str(k or "").strip()
                if k and k != v and not foreign(k):
                    mapping[v] = k
            if not mapping:
                errors.append(f"옵션 값을 하나도 못 옮김(번역기 {out.get('provider') or '없음'})")
        except Exception as exc:
            errors.append(f"옵션 {type(exc).__name__}: {exc}")
    moved += len(mapping)
    # 저장 직전 다시 읽는다 — 그 사이 오너가 고쳤을 수 있다(오너 값 우선: 이미 한국어인 자리는 안 덮음).
    row, ex2 = _load(item_id, uid)
    if not row:
        return "skipped", "상품이 더는 없습니다", sent
    rule_pass(ex2)
    for o in ex2.get("options") or []:
        if not isinstance(o, dict):
            continue
        vals2 = [_val(v).strip() for v in (o.get("values") or [])]
        vko = list(o.get("values_ko") or [])
        vko += [""] * (len(vals2) - len(vko))
        o["values_ko"] = [mapping.get(v, k) if (not k or k == v or foreign(k)) else k for v, k in zip(vals2, vko)]
        nm = str(o.get("name") or "").strip()
        if nm in mapping and (not o.get("name_ko") or foreign(o.get("name_ko"))):
            o["name_ko"] = mapping[nm]
    if "brand_romanized" in ex:
        ex2["brand_romanized"] = ex["brand_romanized"]
    fields = {}
    if title_upd:
        ex2["title_ko"] = title_upd
        fields["title"] = title_upd
    if mapping:
        ex2["options_translated"] = True
    ex2["options_auto_translated_at"] = datetime.now(timezone.utc).isoformat()
    store.update(item_id, seller_ids={uid}, extra_json=json.dumps(ex2, ensure_ascii=False), **fields)
    left = need - granted
    if moved == 0:
        why = "; ".join(errors)[:300] or "번역기가 하나도 옮기지 못했습니다"
        if ruled:
            # Y2: 규칙으로 옮긴 건 저장됐다 — 「하나도 못 옮김」으로만 말하면 거짓(실측: 사이즈·소형·대형·색상 저장됨).
            left_v = ", ".join(str(v) for v in want_vals[:3])
            why = f"규칙으로 {ruled}개 옮겨 저장 · 번역기 남은 {len(want_vals)}개({left_v}) 못 옮김 — {why}"
        return "failed", why[:300], sent
    if left > 0 or len(st["pending"]) > MAX_VALUES_PER_JOB:
        return "queued", f"오늘 {moved}개 옮김 — 남은 {max(left, 0)}개는 상한 뒤 이어서", sent
    return "done", ("; ".join(errors)[:300] if errors else ""), sent


def translate_now(user_id: str, item_id: str) -> dict:
    """X2: 사전검증이 「번역」 때문에 보류하기 **전에** 이 상품 하나를 지금 옮긴다(큐 워커와 같은 `_job` —
    규칙 → 번역기, 하루 상한·Papago 일한도 안에서). → `{status, reason, sent}`.
    번역 끄기(`translate_requested is False`)·일시정지면 손대지 않는다."""
    if pause_state().get("paused"):
        return {"status": "paused", "reason": pause_state().get("reason") or "일시정지", "sent": 0}
    try:
        _row, ex = _load(item_id, user_id)
    except Exception as exc:
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}", "sent": 0}
    if ex.get("translate_requested") is False:
        return {"status": "skipped", "reason": "이 상품은 번역을 끈 상태", "sent": 0}
    try:
        status_, reason, sent = _job({"item_id": item_id, "user_id": user_id})
    except Exception as exc:
        status_, reason, sent = "failed", f"{type(exc).__name__}: {exc}", 0
    logger.info("[옵션번역·즉시] item=%s %s %s", item_id, status_, (reason or "")[:120])
    return {"status": status_, "reason": reason or "", "sent": sent}


# ── 점검(J2 실측 보고) ───────────────────────────────────────────────────────

def audit(rows: list, *, samples: int = 20) -> dict:
    """저장된 값 그대로 센다(고유 값 기준): 규칙 해결 · 번역기 해결 · 외국어 잔존 + 번역기 결과 표본 + 상품명 전후."""
    from src.collectors import ko_polish as kp
    seen: dict = {}
    titles = []
    for r in rows or []:
        try:
            ex = json.loads(r.get("extra_json") or "{}") or {}
        except Exception:
            continue
        for o in ex.get("options") or []:
            if not isinstance(o, dict):
                continue
            vals = [_val(v).strip() for v in (o.get("values") or [])]
            vko = list(o.get("values_ko") or [])
            for i, v in enumerate(vals):
                if not v or v in seen or not foreign(v):
                    continue
                k = str(vko[i] if i < len(vko) else "").strip()
                if kp.non_option(v):
                    seen[v] = ("non_option", "")          # U4: 「남음」이 아니라 「옵션 아님」으로 따로 센다
                elif _rule(v):
                    seen[v] = ("rule", _rule(v))
                elif k and k != v and not foreign(k):
                    seen[v] = ("translator", k)
                else:
                    seen[v] = ("left", k or "")
        src = str(ex.get("title_en") or ex.get("title") or "")
        if foreign(src):
            ko = str(ex.get("title_ko") or "")
            titles.append({"item_id": r.get("id"), "src": src[:80], "before": str(ex.get("title_polish_before") or "")[:90],
                           "after": ko[:90], "promo_left": kp.promo_left(ko),         # T2: 삭제표와 같은 표
                           "han_left": foreign(ko) or not ko})
    c = {"rule": 0, "translator": 0, "left": 0, "non_option": 0}
    for how, _k in seen.values():
        c[how] += 1
    tr_samples = [{"src": v, "ko": k} for v, (how, k) in seen.items() if how == "translator"][:samples]
    # T4·U3: 「어색」 — 번역기 값을 **등록이 쓰는 해석 체인 그대로**(`resolve_option_value`: 정리 → 축약 → 30자) 돌려
    #   나가는 값으로 판정한다. 예전엔 번역기 원문 길이만 봐서, 축약하면 들어가는 값도 「28자 넘음」으로 셌다.
    from src.uploaders.coupang_options import resolve_option_value
    awkward = []
    awkward_total = {"over": 0, "other": 0}
    for v, (how, k) in seen.items():
        if how != "translator" or not k:
            continue
        r = resolve_option_value(v, values_ko=k)
        sent = r["value"]
        why = kp.promo_left(sent) if sent else []
        if sent and not why:
            continue
        if not sent and "넘습니다" in (r["why"] or ""):
            reason, key = f"{kp.MAX_OPTION_VALUE}자 넘음(줄여도)", "over"
        else:
            reason, key = (", ".join(why[:3]) if why else (r["why"] or "미해석")), "other"
        awkward_total[key] += 1
        if len(awkward) < samples:
            awkward.append({"src": v, "ko": k, "sent": sent, "len": len(sent or k), "why": reason})
    left_samples = [{"src": v, "ko": k} for v, (how, k) in seen.items() if how == "left"][:samples]
    total = len(seen)
    bad = c["left"]
    return {"values": total, "counts": c, "left_ratio": round(bad / total, 3) if total else None,
            "translator_samples": tr_samples, "left_samples": left_samples, "titles": titles,
            "awkward_samples": awkward, "awkward_over": awkward_total["over"], "awkward_other": awkward_total["other"],
            "non_option_samples": [v for v, (how, _k) in seen.items() if how == "non_option"][:samples],
            "titles_promo_left": sum(1 for t in titles if t["promo_left"]),
            "titles_han_left": sum(1 for t in titles if t["han_left"])}
