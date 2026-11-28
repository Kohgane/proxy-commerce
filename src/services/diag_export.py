"""오너 11-27 감독 1 — 오너를 진단 배달부로 쓰지 않는다: 운영 진단을 CC가 스스로 읽는 길(읽기 전용).

길: CC(볼트 오라클 작업) → 운영 DB(kg-a1 PostgreSQL, 같은 기계 — 비밀값을 옮기지 않는다)
  ① 부탁: `ops:oneshot:queue`에 `{op: "diag_snapshot", name, arg}` 한 줄을 덧붙인다(오너가 이미 허용한 운영 DB 쓰기 그대로).
  ② 앱 10분 틱이 그 줄을 꺼내 **여기 `snapshot`**을 부른다 — 관리자 진단 화면과 같은 함수로 계산하고, 개인정보 칸을 지운 뒤
     `app_state diag:snap:<name>[:<arg>]` 한 곳에만 적는다(진단 결과 칸 — 상품·주문·마켓은 손대지 않는다).
  ③ CC는 그 키만 읽는다(READ ONLY 트랜잭션).

이 길로 **절대 안 나가는 것**(계약 `tests/test_owner1127_diag_export.py`로 고정):
  · 쓰기 — 상품 행 저장·병합·등록·판매중지·재개·사진 다시 보내기 · 사전검증의 자동 적용(드라이 표시로 막는다).
  · 마켓 전송 — 진단은 마켓에 **읽기 조회**만 한다(스마트스토어 상품 조회·쿠팡 카테고리 메타).
  · 개인정보 — 주문자·수령인·주소·전화·이메일·통관부호 칸은 이름째 지우고, 남은 글자에서 전화·이메일 꼴도 가린다.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SNAP_PREFIX = "diag:snap:"
NAMES = ("restarts", "sources", "relist", "reenrich", "stores", "item", "prevalidate", "jobs", "blacklist", "taobao")
MAX_BYTES = 400_000

#: 이름째 지우는 칸(대소문자 무시 · 부분 일치) — 주문·배송·개인 연락처
_PII_KEYS = ("buyer", "orderer", "receiver", "recipient", "address", "addr", "zipcode", "zip_code", "postcode", "phone", "tel",
             "mobile", "email", "e_mail", "customs", "pccc", "personal", "birth", "orderer_name", "shipping_name", "주문자", "수령인",
             "주소", "전화", "연락처", "이메일", "통관")
#: 남은 글자 안의 전화·이메일·통관부호 꼴
_PII_RE = [re.compile(p) for p in (r"[\w.+-]+@[\w-]+\.[\w.-]+", r"(?<!\d)01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)",
                                    r"\+82[-\s]?\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}", r"(?<![A-Z0-9])P\d{12}(?![0-9])")]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pii_key(k: str) -> bool:
    kl = str(k or "").lower()
    return any(p in kl for p in _PII_KEYS)


def sanitize(obj: Any) -> Any:
    """개인정보 칸을 이름째 지우고 남은 글자의 전화·이메일·통관부호 꼴을 가린다(되살릴 수 없게)."""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items() if not _pii_key(k)}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, str):
        s = obj
        for rx in _PII_RE:
            s = rx.sub("<가림>", s)
        return s
    return obj


def key_for(name: str, arg: str = "") -> str:
    return SNAP_PREFIX + name + ((":" + str(arg)[:80]) if arg else "")


# ── 진단마다(전부 읽기) ───────────────────────────────────────────────────────

def _restarts(arg: str) -> Dict:
    from src.utils import restart_log as RL
    rows = list(RL.rows() or [])
    return {"rows": rows[-60:], "n": len(rows)}


def _sources(arg: str) -> Dict:
    from src.seller_console.collect_history_store import list_items
    from src.services import source_audit as SA
    days = max(1, min(365, int(arg or 90))) if str(arg or "").isdigit() else 90
    from src.utils.test_accounts import is_test_account
    rows = [r for r in (list_items(days=days, extra_keys=SA.KEYS) or []) if not is_test_account(r.get("seller_id"))]   # 11-28 감독 6: 시험용 행 뺌
    data = {"days": days, **SA.audit(rows)}
    return {**data, "verdict": SA.verdict(data)}


def _relist(arg: str) -> Dict:
    """셰고가(기본) 목록 요약 + 뺄 사유별 표본(사유마다 5 · 고정 시드) + 목록 만들기·판매 재개 진행."""
    from src.services import smartstore_relist as SR
    from src.services import durable_job as DJ
    store = arg or "chezgoga"
    p = SR.plan(store)
    rows = p.get("rows") or []
    rnd = random.Random(1127)
    by: Dict[str, list] = {}
    for x in rows:
        if x.get("action") != "on":
            for k in x.get("exclude") or []:
                by.setdefault(k, []).append(x)
    keep = ("channel_no", "name", "sale_price", "cost", "currency", "margin", "floor", "sold_ss", "sold_cp", "exclude",
            "exclude_detail", "our_reason", "photo_small", "tier", "category", "modified")
    samples = {k: [{f: x.get(f) for f in keep} for x in rnd.sample(xs, min(5, len(xs)))] for k, xs in by.items()}
    # 오너 11-27 11:51 ⑤: 뺄 것 표본 20 · 금지 브랜드 줄 전부를 지금 규칙(호환 액세서리 자리 빼기)으로 다시 판정 · 관리 코드 꼴 · 마지막 수정일
    skips = [x for x in rows if x.get("action") != "on"]
    keep2 = keep + ("seller_code", "vault_reason", "cost_src", "cost_note")
    skip20 = [{f: x.get(f) for f in keep2} for x in rnd.sample(skips, min(20, len(skips)))]
    from src.services import risk_gate as RG
    try:
        _bl = [b for b in RG.active_blacklist() if str(b).strip().lower() not in SR.BRAND_EXCEPT]
    except Exception:                                              # noqa: BLE001
        _bl = []
    brand_rows = []
    for x in [x for x in skips if "brand" in (x.get("exclude") or [])][:400]:
        word = (x.get("exclude_detail") or [""])[(x.get("exclude") or []).index("brand")]
        now = [w for w in RG.blacklist_words(x.get("name") or "", _bl) if SR._words_hit(x.get("name") or "", [w])]
        brand_rows.append({"channel_no": x.get("channel_no"), "name": str(x.get("name") or "")[:80], "word": word,
                           "now": ("그대로 금지 — " + now[0]) if now else "호환 액세서리 — 금지 아님(지금 규칙)"})
    from collections import Counter
    from src.services.relist_ledger import norm_code
    kinds = Counter(("CP" if norm_code(x.get("seller_code")).startswith("CP-") else ("빈칸" if not x.get("seller_code") else "품번"))
                    for x in rows)
    mods = Counter(str(x.get("modified") or "")[:10] for x in rows).most_common(12)
    # 오너 11-27 오후 ①: 마진 손계산 대조용 — 운영 입력값(환율·배대지·국제배송·관부가세·수수료·국내배송)과 켤 후보 표본 20(원가·출처·판매가·마진·사진)
    mi = {}
    try:
        import os as _os
        from src import price as P
        fx = P._build_fx_rates()
        mi = {"fx": {k: float(v) for k, v in (fx or {}).items() if isinstance(v, (int, float)) or hasattr(v, "as_tuple")},
              "forwarder_fee_jpy": _os.getenv("FORWARDER_FEE_JPY", "300"), "shipping_fee_krw": _os.getenv("SHIPPING_FEE_DEFAULT", "12000"),
              "customs_rate": _os.getenv("CUSTOMS_RATE_DEFAULT", "0.20"), "customs_threshold_krw": _os.getenv("CUSTOMS_THRESHOLD_KRW", "150000"),
              "commission_pct": float(P.commission_pct("smartstore")[0] or 0), "domestic_shipping_krw": float(P.domestic_shipping_krw("smartstore"))}
    except Exception as exc:                                       # noqa: BLE001
        mi = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    keep3 = keep + ("cost_src", "cost_note", "policy_price", "seller_code", "vault_reason", "src_url", "owner_ok")
    ons = [x for x in rows if x.get("action") == "on"]
    on20 = [{f: x.get(f) for f in keep3} for x in rnd.sample(ons, min(20, len(ons)))]
    return {"store": store, "plan": {k: v for k, v in p.items() if k != "rows"}, "samples": samples,
            "margin_inputs": mi, "on20": on20,
            "skip20": skip20, "brand_rows": brand_rows, "code_kinds": dict(kinds), "modified_top": mods,
            "why_zero": SR.why_zero(p),
            "on_head": [{f: x.get(f) for f in keep} for x in rows if x.get("action") == "on"][:20],
            "build": SR.build_state(store), "run": {k: v for k, v in DJ.status(SR._RUN_KEY.format(store)).items() if k != "targets"}}


def _reenrich(arg: str) -> Dict:
    from src.services import durable_job as DJ
    from src.services import taobao_reenrich_batch as TB
    st = DJ.status(TB.KEY)
    return {k: v for k, v in st.items() if k != "rows"}


def _stores(arg: str) -> Dict:
    from src.services.admin_diag import store_audit, store_verdict
    nos = [n.strip() for n in str(arg or "").split(",") if n.strip().isdigit()][:5]
    d = store_audit(nos)
    return {**d, "verdict": store_verdict(d)}


def _item(arg: str) -> Dict:
    from src.services.admin_diag import item_audit, item_verdict
    d = item_audit(str(arg or "")[:20])
    return {**d, "verdict": item_verdict(d)}


def _prevalidate(arg: str) -> Dict:
    """`arg` = 수집 행 id[|마켓,마켓] — 관리자 진단 화면과 같은 읽기 전용 사전검증(드라이: 행에 쓰지 않음 · 전송 0)."""
    from src.seller_console import collect_history_store as chs
    item_id, _, mk = str(arg or "").partition("|")
    item = chs.get(item_id.strip())
    if not item:
        return {"error": "그 상품을 못 찾았어요."}
    markets = [m.strip() for m in (mk or "coupang:gogane,coupang:woojoo").split(",") if m.strip()][:6]
    from src.order_webhook import app
    from src.seller_console.views import diag_prevalidate_data
    with app.test_request_context("/_diag_export"):
        data, verdict = diag_prevalidate_data(item, markets)
    return {**data, "verdict": verdict}


def _jobs(arg: str) -> Dict:
    """관리자 긴 작업 줄(durable_job) — 상태·진행·멈춤."""
    from src.services import durable_job as DJ
    from src.db import image_translate_queue_pg as st
    idx = dict(st.state_get(DJ.INDEX_KEY) or {})
    out = {}
    for key in list(idx)[:30]:
        s = DJ.status(key)
        out[key] = {k: s.get(k) for k in ("state", "kind", "progress", "stalled", "idle_sec", "started_at", "finished_at", "error", "steps")}
    return {"jobs": out}


def _blacklist_diag(arg: str) -> Dict:
    """오너 11-27 15:18 0-2 — 운영 금지 브랜드 목록 원문(env COUPANG_BLACKLIST85) · 브랜드 낱말로 거른 것 · 허용 목록 · 지금 막는 것(읽기만)."""
    from src.pipeline.coupang_replicate import load_blacklist85
    from src.services import risk_gate as RG
    raw = load_blacklist85()
    return {"source": raw.get("source"), "count": raw.get("count"), "terms": list(raw.get("terms") or []),
            "brand_terms": RG._blacklist(), "allow": sorted(RG.allowlist()), "active": RG.active_blacklist()}


def _taobao_diag(arg: str) -> Dict:
    """오너 11-27 오후 ③ — 온바운드 「5000: data error」 상품번호를 다른 길(mtop)로 읽어 건별 판정(읽기만 · 행 쓰기 0).
    arg = 상품번호 쉼표(최대 10). 경로는 앱 자동 경로(`taobao_auto.effective_route`)와 같다."""
    from src.collectors import taobao_mtop as T
    try:
        from src.services.taobao_auto import effective_route
        via = effective_route() or "relay"
    except Exception:                                              # noqa: BLE001
        via = "relay"
    if via == "onebound":
        via = "relay"
    out = []
    for iid in [x.strip() for x in str(arg or "").split(",") if x.strip().isdigit()][:10]:
        try:
            r = T.probe(iid, via=via)
            d = r.get("detail") or {}
            txt = f"{r.get('reason') or ''} {r.get('kind') or ''}"
            gone = any(w in txt for w in ("下架", "不存在", "已删除", "ITEM_NOT_FOUND", "NOT_EXIST", "宝贝不存在", "delisted", "not found"))
            out.append({"item_id": iid, "via": r.get("via"), "state": r.get("state"), "kind": r.get("kind"), "reason": str(r.get("reason") or "")[:200],
                        "title": str(d.get("title") or "")[:80], "price": d.get("price"), "skus": len(d.get("skus") or []) if isinstance(d.get("skus"), list) else d.get("skus"),
                        "desc_images": r.get("desc_images"), "verdict": ("소싱처에서 내려감" if gone else ("읽힘" if r.get("state") == "ok" else "못 읽음(막힘·오류)"))})
        except Exception as exc:                                   # noqa: BLE001
            out.append({"item_id": iid, "verdict": "못 읽음", "reason": f"{type(exc).__name__}: {str(exc)[:160]}"})
    return {"via": via, "rows": out}


_BUILDERS = {"restarts": _restarts, "sources": _sources, "relist": _relist, "reenrich": _reenrich, "stores": _stores,
             "item": _item, "prevalidate": _prevalidate, "jobs": _jobs, "blacklist": _blacklist_diag, "taobao": _taobao_diag}


def build(name: str, arg: str = "") -> Dict:
    if name not in NAMES:
        raise ValueError(f"모르는 진단: {name}")
    return _BUILDERS[name](str(arg or ""))


def snapshot(name: str, arg: str = "") -> Dict:
    """계산 → 개인정보 지움 → `diag:snap:<name>[:<arg>]`에만 적는다. 결과 `{ok, key, bytes}` 또는 `{ok: False, why}`."""
    if name not in NAMES:
        return {"ok": False, "why": f"모르는 진단({str(name)[:30]})"}
    rec: Dict[str, Any] = {"name": name, "arg": str(arg or "")[:80], "at": _now()}
    try:
        rec["data"] = sanitize(build(name, arg))
        rec["ok"] = True
    except Exception as exc:                                       # noqa: BLE001 — 실패도 원문째 남긴다(조용히 사라지지 않게)
        logger.warning("[운영 진단] %s 실패: %s", name, exc)
        rec.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:300]}")
    body = json.dumps(rec, ensure_ascii=False, default=str)
    if len(body.encode("utf-8")) > MAX_BYTES:
        rec = {**{k: rec[k] for k in ("name", "arg", "at")}, "ok": rec.get("ok", False), "truncated": True,
               "data_head": body[:MAX_BYTES // 2]}
        body = json.dumps(rec, ensure_ascii=False, default=str)
    from src.db import image_translate_queue_pg as st
    st.state_set(key_for(name, arg), json.loads(body))
    return {"ok": bool(rec.get("ok")), "key": key_for(name, arg), "bytes": len(body.encode("utf-8"))}


def read(name: str, arg: str = "") -> Optional[Dict]:
    from src.db import image_translate_queue_pg as st
    return st.state_get(key_for(name, arg))
