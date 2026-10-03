"""src/services/image_translate_auto.py — D3-8: 수집 시 이미지 번역 **자동**(퍼센티 방식).

흐름: 중국 소싱처(타오바오·티몰·1688) 초안의 **상세 보강이 끝나면**(`/enrich`) 갤러리+상세 이미지를
장 단위로 큐에 넣는다 → 워커가 한 장씩 벤치 최신 파이프라인으로 번역 → 장별로 저장.

파이프라인 = 벤치 D3 최신: Tencent **박스+원문**(렌더본은 버림) → 용어집(옵션 값·관용구·브랜드 보존)
→ D3-5/6/7 렌더(telea) + gen_remove 한 번 더 → **F축(지운 자리 vs 주변 링)이 나은 쪽 자동 선택**.
글자가 없는 장은 원본을 쓴다(skipped — 실패 아님).

비용 가드(오너 2026-09-27):
  - 공급사 초당 1회 — `tc.translate_image`가 서버 전역 차례표(`rate_slot`)를 지난다(워커 여럿이어도 1).
  - **일일 상한** `IMAGE_TRANSLATE_DAILY_CAP`(기본 200) = **번역을 시작한 장 수**(실패·재시도 포함),
    **KST 자정**에 새로 센다. 닿으면 큐는 대기(보내지 않은 장은 queued로 되돌림) · 화면 「번역 대기 N장」.
  - **실패 누적 20장**(마지막 재개 이후)이면 큐 자동 일시정지 + 화면 경고 — 오너가 「재개」를 눌러야 계속.
  - Cloudinary gen_remove 크레딧 추정치는 장마다 로그(렌더가 내는 `cloud_credits` 그대로 — 지어내지 않음).
설정: 소싱처별 토글(기본 켬) — `app_state` 키 `imgko_auto:<user_id>`.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

ENV_CAP = "IMAGE_TRANSLATE_DAILY_CAP"
DEFAULT_CAP = 200
FAIL_PAUSE_AT = 20
SOURCES = ("taobao", "tmall", "1688")
_KST = timezone(timedelta(hours=9))
_STATE_KEY = "imgko_auto:global"
_CN_RE = re.compile(r"(^|\.)(taobao|tmall|1688)\.com$")

_WORKER = {"thread": None, "lock": threading.Lock()}


# ── 규칙 ──────────────────────────────────────────────────────────────────────

def daily_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, str(DEFAULT_CAP))))
    except (TypeError, ValueError):
        return DEFAULT_CAP


def kst_day(now=None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(_KST).strftime("%Y-%m-%d")


def _day_key(now=None) -> str:
    return "imgko_auto:day:" + kst_day(now)


def source_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        h = (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""
    m = _CN_RE.search(h)
    return m.group(2) if m else ""


def _q():
    from src.db import image_translate_queue_pg as q
    return q


def settings(user_id: str) -> dict:
    v = _q().state_get(f"imgko_auto:{user_id}")
    return {s: (v.get(s) is not False) for s in SOURCES}          # 기본 켬


def save_settings(user_id: str, toggles: dict) -> dict:
    cur = settings(user_id)
    for s in SOURCES:
        if s in (toggles or {}):
            cur[s] = bool(toggles[s])
    _q().state_set(f"imgko_auto:{user_id}", cur)
    return cur


def pause_state() -> dict:
    return _q().state_get(_STATE_KEY)


def _since_resume():
    st = pause_state()
    ts = st.get("resumed_at") or ""
    try:
        return datetime.fromisoformat(ts) if ts else datetime(1970, 1, 1, tzinfo=timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def pause(reason: str) -> None:
    st = pause_state()
    st.update({"paused": True, "reason": reason, "paused_at": datetime.now(timezone.utc).isoformat()})
    _q().state_set(_STATE_KEY, st)
    logger.warning("[이미지번역·자동] 큐 일시정지 — %s", reason)


def heal_breaker() -> dict:
    """Y4: 차단기가 「번역 실패 N장」으로 멈췄는데, 글자 없는 사진을 뺀 **진짜 실패**가 상한 아래면 풀고 다시 돈다.
    사람이 멈춘 것(다른 사유)은 건드리지 않는다. → `{healed, real_failed, reason}`"""
    st = pause_state()
    if not st.get("paused") or not str(st.get("reason") or "").startswith("번역 실패"):
        return {"healed": False, "real_failed": None, "reason": "멈춤 아님 또는 사람이 멈춘 것"}
    n = _q().failed_since(_since_resume())
    if n >= FAIL_PAUSE_AT:
        return {"healed": False, "real_failed": n, "reason": f"진짜 실패 {n}장 — 상한 {FAIL_PAUSE_AT} 이상이라 그대로"}
    resume()
    logger.warning("[이미지번역·자동] 차단기 해제 — 글자 없는 사진을 실패에서 빼니 진짜 실패 %s장(상한 %s)", n, FAIL_PAUSE_AT)
    return {"healed": True, "real_failed": n, "reason": f"진짜 실패 {n}장 < {FAIL_PAUSE_AT}"}


def resume() -> dict:
    st = {"paused": False, "reason": "", "resumed_at": datetime.now(timezone.utc).isoformat()}
    _q().state_set(_STATE_KEY, st)
    kick()
    return st


def status(item_id: str = "") -> dict:
    """화면(드로어·설정)용 — 오늘 N/상한 · 대기 · 일시정지 · 실패 누적."""
    q = _q()
    st = pause_state()
    today = q.day_count(_day_key())
    cap = daily_cap()
    all_c = q.counts()
    item_c = q.counts(item_id) if item_id else None
    waiting_cap = bool(all_c.get("queued")) and today >= cap
    return {"ok": True, "today": today, "cap": cap, "day": kst_day(), "env": ENV_CAP,
            "paused": bool(st.get("paused")), "pause_reason": st.get("reason") or "",
            "failed_since_resume": q.failed_since(_since_resume()), "fail_pause_at": FAIL_PAUSE_AT,
            "queued": all_c.get("queued", 0), "running": all_c.get("running", 0),
            "waiting_cap": waiting_cap, "item": item_c}


# ── 접수 ──────────────────────────────────────────────────────────────────────

def enqueue_after_enrich(user_id: str, item_id: str, url: str, extra: dict) -> int:
    """보강 완료된 중국 소싱처 초안 → 갤러리+상세를 장 단위로 큐에. 이미 번역된 장·큐에 있는 장은 건너뛴다."""
    src = source_of(url)
    if not src or not settings(user_id).get(src):
        return 0
    try:
        from src.services import image_translate_tencent as tc
        if not tc.is_configured():
            # 공급사 키가 없으면 넣지 않는다 — 넣으면 장마다 「미연결」로 실패해 20장 뒤 큐가 멈춘다(의미 없는 경고).
            logger.info("[이미지번역·자동] 공급사 미연결 — 접수 안 함 item=%s", item_id)
            return 0
    except Exception:
        return 0
    done = set()
    for key, kind in (("images_ko", "gallery"), ("detail_images_ko", "detail")):
        for e in (extra.get(key) or []):
            if isinstance(e, dict) and e.get("status") in ("done", "skipped"):
                done.add((kind, int(e.get("idx", -1))))
    pages = []
    for key, kind in (("images", "gallery"), ("detail_images", "detail")):
        for i, u in enumerate([u for u in (extra.get(key) or []) if u]):
            if (kind, i) not in done:
                pages.append((kind, i))
    n = _q().enqueue(user_id, item_id, pages) if pages else 0
    if n:
        logger.info("[이미지번역·자동] 접수 item=%s %s장(갤러리+상세)", item_id, n)
        kick()
    return n


# ── 처리 ──────────────────────────────────────────────────────────────────────

def kick() -> None:
    """워커가 없으면 띄운다(프로세스당 하나 · 공급사 한도는 rate_slot이 전역으로 지킨다)."""
    if os.getenv("IMAGE_TRANSLATE_AUTO_SYNC") == "1":      # 테스트: 같은 스레드에서 끝까지
        run_until_idle()
        return
    from src.services import workers as _w
    if not _w.workers_enabled():                      # W2: 워커는 WORKERS_ENABLED 서비스에서만 — 여기선 접수만(큐에 남는다)
        logger.info("[이미지번역·자동] 이 서비스(%s)는 워커 꺼짐(%s) — 접수만", _w.service_name(), _w.gate_text())
        return
    with _WORKER["lock"]:
        th = _WORKER["thread"]
        if th and th.is_alive():
            return
        th = threading.Thread(target=run_until_idle, daemon=True, name="imgko-auto")
        _WORKER["thread"] = th
        th.start()


def run_until_idle(max_pages: int = 10_000) -> int:
    """W2: 서비스 간 단일 실행 — DB 리스를 잡은 한 곳만 돈다. 실행 기록은 서비스별로 남긴다."""
    from src.services import workers as _w
    if not _w.lease("imgko-auto"):
        logger.info("[이미지번역·자동] 다른 서비스가 돌리는 중 — 이번엔 건너뜀")
        return 0
    n = 0
    try:
        n = _drain(max_pages)
        return n
    finally:
        _w.release("imgko-auto")
        _w.record_run("imgko-auto", n)


def _drain(max_pages: int = 10_000) -> int:
    """큐가 빌 때까지(또는 상한·일시정지) 한 장씩. 처리한 장 수."""
    q = _q()
    n = 0
    while n < max_pages:
        if pause_state().get("paused"):
            return n
        from src.services import workers as _w
        _w.lease("imgko-auto")                                 # 리스 갱신(장마다)
        job = q.lease_next()
        if not job:
            return n
        took, today = q.take_start(_day_key(), daily_cap())
        if not took:
            q.requeue(job["id"])                  # 보내지 않았다 — 대기로(내일 KST 자정 뒤 다시)
            logger.info("[이미지번역·자동] 일일 상한 도달(%s/%s) — 대기", today, daily_cap())
            return n
        try:
            status_, reason = _translate_job(job)
        except Exception as exc:                   # pragma: no cover
            status_, reason = "failed", f"{type(exc).__name__}: {exc}"
        q.finish(job["id"], status_, reason)
        n += 1
        if status_ == "failed" and q.failed_since(_since_resume()) >= FAIL_PAUSE_AT:
            pause(f"번역 실패 {FAIL_PAUSE_AT}장 누적 — 원인을 확인한 뒤 「재개」를 눌러 주세요(마지막 사유: {reason[:80]})")
            return n
    return n


def _translate_job(job: dict) -> tuple:
    """한 장 — `(status, reason)`. 결과는 상품의 `images_ko`/`detail_images_ko`에 장별로 적는다."""
    import json as _json

    from src.seller_console import collect_history_store as store
    from src.services import image_translate_store as istore
    item_id, kind, idx, uid = job["item_id"], job["kind"], int(job["idx"]), job["user_id"]
    row = store.get(item_id, seller_ids={uid}) or {}
    try:
        extra = _json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        extra = {}
    src_key = "images" if kind == "gallery" else "detail_images"
    ko_key = "images_ko" if kind == "gallery" else "detail_images_ko"
    originals = [u for u in (extra.get(src_key) or []) if u]
    if not (0 <= idx < len(originals)):
        return "skipped", "그 장이 더는 없습니다"
    entry = translate_page(originals[idx], idx=idx, kind=kind, item_id=item_id, seller_id=uid,
                           title=str(extra.get("title_en") or extra.get("title") or row.get("title") or ""))
    # 저장 직전 다시 읽는다 — 그 사이 다른 장이 적혔을 수 있다(장별 병합).
    row = store.get(item_id, seller_ids={uid}) or {}
    try:
        extra = _json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        extra = {}
    by_idx = {int(e.get("idx", -1)): e for e in (extra.get(ko_key) or []) if isinstance(e, dict)}
    by_idx[idx] = entry
    by_idx.pop(-1, None)
    extra[ko_key] = [by_idx[k] for k in sorted(by_idx)]
    store.update(item_id, seller_ids={uid}, extra_json=_json.dumps(extra, ensure_ascii=False))
    try:
        istore.record_usage(uid, [entry], vendor="tencent")
    except Exception:
        pass
    st = entry.get("status")
    why = str(entry.get("error_message") or entry.get("reason") or "")
    if st not in ("done", "skipped") and _q().is_no_text(why):
        # Y4: 글자 없는 사진 = **성공(원본 유지)**. 실패로 세면 차단기가 멀쩡한 큐를 멈춘다(실측 20장 중 14장이 이것).
        return "skipped", f"글자 없는 사진 — 원본 그대로({why[:60]})"
    return (st if st in ("done", "skipped") else "failed"), why


def translate_page(url: str, *, idx: int, kind: str, item_id: str, seller_id: str, title: str = "") -> dict:
    """한 장 = 벤치 최신 D3 파이프라인. `images_ko` 한 줄(`build_entry` 모양)을 돌려준다."""
    from src.media.image_label import make_label, run_stamp
    from src.services import image_translate_bench as bench
    from src.services import image_translate_store as istore
    from src.services import image_translate_tencent as tc
    from src.services.image_bench_axes import brand_tokens

    res = tc.translate_image(url=url)            # 박스+원문(렌더본은 쓰지 않는다)
    if not res.get("ok"):
        return istore.build_entry(idx, res, item_id=item_id, seller_id=seller_id, kind=kind)
    lines = res.get("lines") or []
    if not lines:
        return {"idx": int(idx), "kind": kind, "status": "skipped", "vendor": "d3", "ms": int(res.get("ms") or 0),
                "reason": "이미지에 번역할 글자가 없습니다 — 원본을 씁니다", "at": datetime.now(timezone.utc).isoformat()}
    raw, why = tc.fetch_image(url)
    if not raw:
        return istore.build_entry(idx, {"ok": False, "vendor": "d3", "error_class": "FetchFailed",
                                        "error_message": f"원본을 받지 못했습니다: {why}"},
                                  item_id=item_id, seller_id=seller_id, kind=kind)
    out = bench._render_d3_for(raw, lines, brand_tokens(title), gen_remove=True)
    pick, pipe = _pick_render(out)
    credits = float((out.get("gen_remove") or {}).get("cloud_credits") or 0.0)
    if credits:
        logger.info("[이미지번역·자동] item=%s %s#%s gen_remove 크레딧 추정 %.3f", item_id, kind, idx, credits)
    if not (pick and pick.get("ok") and pick.get("image_bytes")):
        err = (pick or {}).get("error") or out.get("error") or "렌더 결과가 없습니다"
        return istore.build_entry(idx, {"ok": False, "vendor": "d3", "error_class": "RenderFailed",
                                        "error_message": err}, item_id=item_id, seller_id=seller_id, kind=kind)
    rows = out.get("rows") or []
    result = {"ok": True, "vendor": "d3", "ms": int(res.get("ms") or 0),
              "image_b64": base64.b64encode(pick["image_bytes"]).decode("ascii"),
              "lines": lines,
              "source_text": "\n".join(str(r.get("source") or "") for r in rows),
              "target_text": "\n".join(str(r.get("render_text") or "") for r in rows)}
    label = make_label(run_stamp("auto"), item_id, idx, pipe, folder="seller")
    entry = istore.build_entry(idx, result, item_id=item_id, seller_id=seller_id, kind=kind, label=label)
    entry["pipeline"] = pipe
    if credits:
        entry["cloud_credits"] = credits
    return entry


def _f_score(one: dict):
    try:
        return float(((one or {}).get("axes") or {}).get("F", {}).get("score"))
    except (TypeError, ValueError):
        return None


def _pick_render(out: dict) -> tuple:
    """telea vs gen_remove — **실제로 gen_remove가 그렸고**(폴백 아님) F축이 같거나 높으면 gen_remove."""
    tel = out if out.get("ok") else None
    g = out.get("gen_remove") or {}
    g_ok = bool(g.get("ok") and g.get("image_bytes") and g.get("inpainter") == "gen_remove")
    if g_ok and (not tel or (_f_score(g) or 0) >= (_f_score(tel) or 0)):
        return g, "GEN_REMOVE"
    return (tel, "TELEA") if tel else (None, "TELEA")
