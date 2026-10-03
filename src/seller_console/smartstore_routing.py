"""U0b(오너 2026-10-02 정정) — 스마트스토어 두 스토어: 셰고가(`chezgoga`, 고가네 축) · 고코스모스(`gocosmos`, 우주대행 축).

- **배정**: 상품 카테고리·상품명 낱말로 한 스토어를 고른다(표 `smartstore_routing.json` — 원격 JSON, 관리자 덮어쓰기
  `app_state smartstore:routing`). 근거가 없으면 빈 값 — 지어서 고르지 않는다(오너가 화면에서 고름). 「양쪽 다」는 화면에서 둘 다 체크.
- **승인 = 실측(V, 오너 2026-10-03)**: 수동 플래그(`SMARTSTORE_*_APPROVED`)는 폐기. 스토어 키로 커머스API 토큰을
  **실제로 발급**해 본다(client_credentials) — 성공 = 승인, 실패 = 응답 코드·본문 **원문**을 그대로 보인다(「미승인」이라고
  추측해 쓰지 않는다). 결과 10분 캐시(`probe`). 확인 시각·원문은 `app_state smartstore:probe`에도 남긴다(토큰 값은 안 남김).
  테스트·로컬은 `SMARTSTORE_LIVE_PROBE=0`(conftest 기본) — 그땐 「실측 꺼짐」이라고 말하고 승인으로 치지 않는다.
- **한도**: 스토어당 판매중·판매대기·품절 합계 1,000(볼트 「스마트스토어 등록 한도」). 숫자는 토큰이 나온 스토어만 커머스 API
  (`products/search` `totalElements`)로 센다 — 못 세면 「조회 불가」+원문(지어내지 않음). 같은 10분 캐시.
- **니치·고단가만**: 표의 `min_price_krw` — 볼트에 수치 결정이 없어 기본 **꺼짐**(null). 오너가 값을 넣으면 그 아래는 보류.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_FILE = Path(__file__).with_name("smartstore_routing.json")
_STATE_KEY = "smartstore:routing"
STORES = ("chezgoga", "gocosmos")
_TTL = 60.0
_COUNT_TTL = 600.0
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "rules": None}
_counts: Dict[str, tuple] = {}
_probes: Dict[str, tuple] = {}
_PROBE_KEY = "smartstore:probe"


def rules() -> dict:
    now = time.monotonic()
    with _lock:
        if _cache["rules"] is not None and now - _cache["at"] < _TTL:
            return _cache["rules"]
    r = json.loads(_FILE.read_text(encoding="utf-8"))
    try:
        from src.db import image_translate_queue_pg as st
        over = (st.state_get(_STATE_KEY) or {}).get("rules")
        if isinstance(over, dict) and over:
            r = dict(r, **over)
    except Exception:
        pass
    with _lock:
        _cache.update(at=now, rules=r)
    return r


def reset_cache() -> None:
    with _lock:
        _cache.update(at=0.0, rules=None)
        _counts.clear()
        _probes.clear()


def store_label(store: str) -> str:
    return str(((rules().get("stores") or {}).get(store) or {}).get("label") or store)


def _live_on() -> bool:
    return str(os.getenv("SMARTSTORE_LIVE_PROBE", "1")).strip().lower() not in ("0", "false", "no", "off")


def _issue(store: str) -> dict:
    """그 스토어 키로 토큰을 **실제로** 발급해 본다 → `{state, raw, count, count_raw}`. 토큰 값은 밖으로 안 낸다.

    state: ok(발급 성공) · fail(네이버가 거부 — raw=응답 원문) · no_creds(키 없음 — 보낸 적 없음) · off(실측 꺼짐).
    토큰이 나오면 같은 업로더로 한도 대상 상품 수를 센다(V2).
    """
    if not _live_on():
        return {"state": "off", "raw": "실측 꺼짐 — SMARTSTORE_LIVE_PROBE=0이라 토큰을 발급해 보지 않았어요",
                "count": None, "count_raw": ""}
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    from src.market_relay import route_text
    up = NaverSmartStoreUploader(account=store or None)
    via = route_text("smartstore", up._TOKEN_URL)
    if not (up.client_id and up.client_secret):
        return {"state": "no_creds", "raw": "키 없음 — " + up._cred_env_hint() + " 를 설정하세요(발급 요청은 보내지 않았어요)",
                "count": None, "count_raw": "", "via": via, "env": _env_names(up)}
    if not up._get_access_token():
        return {"state": "fail", "raw": up.token_error or "사유 원문 없음", "count": None, "count_raw": "",
                "via": via, "env": _env_names(up)}
    n = up.count_products(rules().get("limit_statuses") or None)
    return {"state": "ok", "raw": "토큰 발급 OK", "count": n, "via": via, "env": _env_names(up),
            "count_raw": "" if n is not None else (getattr(up, "count_error", "") or "응답에 totalElements 없음")}


def _env_names(up) -> list:
    """그 스토어가 실제로 읽는 키 이름(값 아님) — 진단 매트릭스·Health 카드가 같은 이름을 본다."""
    pfx = up.ACCOUNT_PREFIXES.get(up.account or "")
    return [f"{pfx}_CLIENT_ID", f"{pfx}_CLIENT_SECRET"] if pfx else ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"]


def probe(store: str = "", *, force: bool = False) -> dict:
    """스토어별 토큰 실측(10분 캐시) — `{store, label, state, ok, raw, count, count_raw, at}`."""
    now = time.monotonic()
    with _lock:
        hit = _probes.get(store)
    if hit and not force and now - hit[0] < _COUNT_TTL:
        return hit[1]
    try:
        r = _issue(store)
    except Exception as exc:          # 실측 도구가 터진 것도 원문으로(조용한 실패 금지)
        r = {"state": "fail", "raw": f"확인 중 오류: {type(exc).__name__}: {str(exc)[:160]}", "count": None, "count_raw": ""}
    from datetime import datetime, timedelta, timezone
    out = dict(r, store=store, label=store_label(store) if store else "스마트스토어", ok=(r.get("state") == "ok"),
               at=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST"))
    with _lock:
        _probes[store] = (now, out)
    if r.get("state") in ("ok", "fail", "no_creds"):
        logger.info("[스스 실측] %s — %s · 상품 수 %s · 경로 %s", out["label"], out["raw"][:200],
                    out["count"] if out["count"] is not None else ("조회 불가 " + out["count_raw"][:120] if out["ok"] else "—"),
                    out.get("via") or "—")
        try:
            from src.db import image_translate_queue_pg as st
            snap = st.state_get(_PROBE_KEY) or {}
            snap[store or "_default"] = {k: out.get(k) for k in ("label", "state", "raw", "count", "count_raw", "at", "via")}
            st.state_set(_PROBE_KEY, snap)
        except Exception as exc:
            logger.debug("[스스 실측] 기록 실패(계속): %s", exc)
    return out


def probe_all(*, force: bool = False) -> list:
    """두 스토어를 나란히 확인(화면이 두 번 기다리지 않게)."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(STORES)) as ex:
        return list(ex.map(lambda st: probe(st, force=force), STORES))


def approved(store: str = "") -> bool:
    """그 스토어 토큰이 실제로 발급되는가(V — 수동 플래그 폐기)."""
    return probe(store)["ok"]


def status_text(store: str = "") -> str:
    """승인 아님일 때 화면에 그대로 보일 문장 — 추측 없이 원문."""
    p = probe(store)
    if p["ok"]:
        return ""
    head = {"fail": "토큰 발급 실패", "no_creds": "키 없음", "off": "실측 꺼짐"}.get(p["state"], "확인 실패")
    raw = p["raw"]
    if raw.startswith(head):
        raw = raw[len(head):].lstrip(" —:")
    return f"{head} — {raw}" if raw else head


def assign_store(product: dict) -> dict:
    """`{store, why}` — 카테고리 코드가 맞으면 2점, 상품명 낱말 하나당 1점. 동점·0점이면 빈 값(오너가 고름)."""
    p = product or {}
    cat = str(p.get("category_code") or p.get("category") or "").strip().upper()
    title = " ".join(str(p.get(k) or "") for k in ("title_ko", "coupang_name", "title"))
    score, why = {}, {}
    for st, conf in (rules().get("stores") or {}).items():
        sc, hits = 0, []
        if cat and cat in (conf.get("categories") or []):
            sc += 2
            hits.append(f"카테고리 {cat}")
        for kw in conf.get("keywords") or []:
            if kw and re.search(re.escape(kw), title, re.I):
                sc += 1
                hits.append(kw)
        score[st], why[st] = sc, hits
    ranked = sorted(score.items(), key=lambda x: -x[1])
    if not ranked or ranked[0][1] == 0 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return {"store": "", "why": "카테고리·상품명으로 정하지 못했어요 — 직접 골라 주세요"}
    st = ranked[0][0]
    return {"store": st, "why": "자동 배정 — " + ", ".join(why[st][:3])}


def price_hold(product: dict) -> str:
    """니치·고단가만(오너 U0 정정) — `min_price_krw`가 있을 때만. 없으면(기본) 빈 문자열."""
    floor = rules().get("min_price_krw")
    if not floor:
        return ""
    try:
        price = float((product or {}).get("sell_price_krw") or (product or {}).get("price_krw") or 0)
    except (TypeError, ValueError):
        price = 0
    if price and price < float(floor):
        return f"스마트스토어는 고단가만 — 판매가 {int(price):,}원이 기준 {int(floor):,}원보다 낮아요"
    return ""


def store_count(store: str, *, fetch=None) -> Optional[int]:
    """한도 대상(판매중·판매대기·품절) 상품 수 — 실측(probe)에서 센 값. 못 세면 None. 10분 캐시.
    `fetch`는 시험용 주입(그때만 따로 센다)."""
    if fetch is None:
        return probe(store)["count"]
    now = time.monotonic()
    hit = _counts.get(store)
    if hit and now - hit[0] < _COUNT_TTL:
        return hit[1]
    try:
        n = fetch(store)
    except Exception as exc:
        logger.warning("[스스 한도] %s 상품 수 조회 실패: %s", store, exc)
        n = None
    if n is not None:
        _counts[store] = (now, n)
    return n


def limit_state(store: str, *, fetch=None) -> dict:
    """`{count, limit, full, text}` — 화면·사전검증 공용. 토큰이 안 나온 스토어는 세지 않는다(원문으로 이유를 말한다)."""
    limit = int(rules().get("limit") or 1000)
    p = probe(store)
    if not p["ok"]:
        return {"count": None, "limit": limit, "full": False,
                "text": f"{store_label(store)} ?/{limit:,} — 조회 불가({status_text(store)})"}
    n = store_count(store, fetch=fetch)
    if n is None:
        why = (p.get("count_raw") if fetch is None else "") or "조회 실패"
        return {"count": None, "limit": limit, "full": False, "text": f"{store_label(store)} ?/{limit:,} — 조회 불가({why})"}
    return {"count": n, "limit": limit, "full": n >= limit, "text": f"{store_label(store)} {n:,}/{limit:,}"}


def store_choices(product: Optional[dict] = None) -> list:
    """마켓 선택 줄 재료 — `[{code, store, label, business, ready, approved, assigned, note, limit_text}]`."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    assigned = assign_store(product or {}) if product else {"store": "", "why": ""}
    probe_all()
    out = []
    for st in STORES:
        conf = (rules().get("stores") or {}).get(st) or {}
        try:
            up = NaverSmartStoreUploader(account=st)
            ready = bool(up.client_id and up.client_secret)
        except Exception:
            ready = False
        ok = approved(st)
        why = "" if ok else status_text(st)
        note = why
        if assigned.get("store") == st:
            note = (assigned["why"] + (" · " + note if note else ""))
        out.append({"code": f"smartstore:{st}", "store": st, "label": f"스마트스토어 — {conf.get('label') or st}",
                    "business": conf.get("business") or "", "ready": ready, "approved": ok,
                    "assigned": assigned.get("store") == st, "note": note,
                    "pending_head": why.split(" — ")[0] if why else "", "pending_why": why,
                    "limit_text": limit_state(st)["text"] if ok else ""})
    return out
