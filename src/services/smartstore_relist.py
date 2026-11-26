"""오너 11-26 11:58 「셰고가 다시 켜라」 — 판매중지(SUSPENSION) 상품을 골라 **판매 재개**. 목록은 읽기만, 실행은 오너 탭.

한도 1,000(판매중·판매대기·품절 합) − 지금 그 합 = 빈자리. 판매중지 전수를 읽어 줄마다:
  상품번호 · 상품명 · 판매가 · 우리 원가/마진(있으면) · 마지막 수정 시각(네이버가 판매중지 시각을 따로 주지 않는다) ·
  우리 기록의 판매중지 사유(없으면 「기록 없음」) · 누적 판매(우리 주문 기록 — 스스 + 같은 상품의 쿠팡) · 조회수(네이버 커머스 API에 없음 — 「모름」).
켜지 않을 것(줄마다 사유):
  · 마진이 하한 미만(팔린 적 있으면 15% · 그 외 기본 목표 마진 — 관부가세·배송비 포함 실수령) 또는 원가 미확인
  · 취급 중단: 도검(허가 필요 — risk_tokens `cert:knife` 낱말) · 도수 안경렌즈 · 금지 브랜드(블랙리스트, 스노우피크 예외)
  · 반려·소명·상표로 내린 것(우리 기록에 그 상품만 — 같은 브랜드를 묶어 빼지 않는다)
  · 소싱처 품절·단종 · 원본 주소 없음
  · 사진 전부 500px 미만(대표 사진을 재고, 작으면 그 상품 사진을 더 읽어 확인)
켤 순서: ① 팔린 적 있는 것(쿠팡에서 팔린 같은 상품 포함) ② 조회 많은데 안 팔린 것 — **조회수가 API에 없어 건너뜀(표시)** ·
  ③ 셰고가 주제(라우팅 표의 그 스토어 낱말 — 데스크·키보드·EDC·캠핑·아웃도어·충전 …) ④ 나머지 최신 순. 빈자리만큼 「켤 것」.
실행: `PUT /v1/products/origin-products/{no}/change-status {statusType: SALE}` — 50건씩 끊어, 진행 n/N, 실패는 네이버 응답 원문,
중간 「멈춤」, 끝나면 상태별 수를 다시 읽는다. 가격이 정책가와 다르면 **표시만**(바꾸지 않는다 — 오너 확인 따로).
고코스모스는 같은 화면에서 보기만(실행은 오너가 말할 때 — `RUN_STORES`).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

RUN_STORES = ("chezgoga",)                 # 오너 11-26: 셰고가만 실행. 고코스모스는 보기만(말할 때 추가)
CHUNK = 50
SOLD_FLOOR_PCT = 15.0
PAGE_SIZE = 100
MAX_PAGES = 40                             # 4,000건까지 — 넘으면 「다 못 읽음」으로 말한다
_PLAN_KEY = "smartstore_relist:plan:{}"
_RUN_KEY = "smartstore_relist:run:{}"
LENS_WORDS = ("도수 안경", "도수안경", "도수 렌즈", "도수렌즈", "안경렌즈", "안경 렌즈", "시력교정 렌즈", "근시 렌즈",
              "近视镜片", "处方镜片", "配镜", "prescription lens")
BRAND_EXCEPT = ("snow peak", "snowpeak", "스노우피크", "스노우 피크")
VIEWS_NOTE = "조회수는 네이버 커머스 API로 읽을 수 없어요 — ② 단계(조회 많은데 안 팔린 것)는 건너뛰었어요"

REASON_KO = {
    "margin_low": "마진 하한 미만", "cost_unknown": "원가 미확인", "knife": "도검(허가 필요)", "lens": "도수 안경렌즈",
    "brand": "금지 브랜드", "ours_reject": "반려·소명·상표로 내림(우리 기록)", "src_soldout": "소싱처 품절·단종",
    "no_source": "원본 주소 없음", "photos_small": "사진 전부 500px 미만", "no_room": "빈자리 없음(대기)",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _state_get(key):
    from src.db import image_translate_queue_pg as st
    return st.state_get(key)


def _state_set(key, val):
    from src.db import image_translate_queue_pg as st
    st.state_set(key, val)


def plan(store: str) -> Dict:
    return dict(_state_get(_PLAN_KEY.format(store)) or {})


def run_state(store: str) -> Dict:
    return dict(_state_get(_RUN_KEY.format(store)) or {})


# ── 읽기 ────────────────────────────────────────────────────────────────────

def fetch_suspended(up) -> Dict:
    """판매중지 전수 — `{ok, rows, total, complete, error}`. 줄: origin_no·channel_no·name·sale_price·reg·modified·rep_image·stock·category."""
    rows, total, err = [], None, ""
    for page in range(1, MAX_PAGES + 1):
        res = up._api_request("POST", "/v1/products/search",
                              data={"productStatusTypes": ["SUSPENSION"], "page": page, "size": PAGE_SIZE})
        if not isinstance(res, dict) or "error" in res:
            err = str((res or {}).get("error") if isinstance(res, dict) else res)[:300]
            break
        total = res.get("totalElements", total)
        contents = res.get("contents") or []
        for c in contents:
            for ch in (c or {}).get("channelProducts") or []:
                if str(ch.get("statusType") or "SUSPENSION") != "SUSPENSION":
                    continue
                rows.append({
                    "origin_no": str((c or {}).get("originProductNo") or ch.get("originProductNo") or ""),
                    "channel_no": str(ch.get("channelProductNo") or ""),
                    "name": str(ch.get("name") or ""),
                    "sale_price": ch.get("discountedPrice") or ch.get("salePrice"),
                    "list_price": ch.get("salePrice"),
                    "reg": str(ch.get("regDate") or ""),
                    "modified": str(ch.get("modifiedDate") or ""),
                    "rep_image": str(((ch.get("representativeImage") or {}).get("url")) or ""),
                    "stock": ch.get("stockQuantity"),
                    "category": str(ch.get("wholeCategoryName") or ""),
                })
        if len(contents) < PAGE_SIZE:
            break
    complete = (not err) and total is not None and len(rows) >= int(total)
    return {"ok": not err, "rows": rows, "total": total, "complete": complete, "error": err}


def _ours_index(store: str) -> Dict[str, Dict]:
    """우리 수집 행 중 이 스토어에 올린 기록이 있는 것 — 채널 상품번호 → {item_id, url, ex}."""
    from src.seller_console import collect_history_store as chs
    keys = ["uploaded", "takedowns", "risk_skip", "monitor", "price", "currency", "images", "target_margin_pct", "title_ko"]
    out: Dict[str, Dict] = {}
    for r in chs.list_items(days=3650, extra_keys=keys) or []:
        try:
            ex = json.loads(r.get("extra_json") or "{}") if isinstance(r.get("extra_json"), str) else (r.get("extra_json") or {})
        except Exception:                                          # noqa: BLE001
            continue
        for u in ex.get("uploaded") or []:
            if not isinstance(u, dict):
                continue
            m = str(u.get("market") or "")
            if not m.startswith("smartstore"):
                continue
            st = m.partition(":")[2] or "chezgoga"
            if st != store:
                continue
            for no in (u.get("channel_product_no"), u.get("product_id")):
                if str(no or "").strip():
                    out[str(no).strip()] = {"item_id": str(r.get("id") or ""), "url": str(r.get("url") or ""), "ex": ex}
    return out


def _sales_index(ours: Dict[str, Dict]) -> Dict[str, Dict[str, int]]:
    """채널 상품번호 → `{ss, cp}` 판매 건수(우리 주문 기록). 쿠팡은 같은 수집 행의 쿠팡 등록번호로 잇는다."""
    from src.seller_console.orders.sheets_adapter import _order_backend
    ss: Dict[str, int] = {}
    cp_sku: Dict[str, int] = {}
    for o in _order_backend().all_row_dicts() or []:
        mk = str(o.get("marketplace") or "").lower()
        try:
            items = json.loads(str(o.get("items_json") or "[]"))
        except Exception:                                          # noqa: BLE001
            items = []
        for it in items if isinstance(items, list) else []:
            sku = str((it or {}).get("sku") or "").strip()
            if not sku:
                continue
            q = int((it or {}).get("qty") or 1)
            if mk.startswith("smartstore") or mk.startswith("naver"):
                ss[sku] = ss.get(sku, 0) + q
            elif mk.startswith("coupang"):
                cp_sku[sku] = cp_sku.get(sku, 0) + q
    out = {}
    for ch, row in ours.items():
        cp = 0
        for u in row["ex"].get("uploaded") or []:
            if isinstance(u, dict) and str(u.get("market") or "").startswith("coupang"):
                for k in [u.get("product_id"), u.get("seller_product_id"), *(u.get("vendor_item_ids") or [])]:
                    cp += cp_sku.get(str(k or "").strip(), 0)
        out[ch] = {"ss": ss.get(ch, 0), "cp": cp}
    for ch, n in ss.items():
        out.setdefault(ch, {"ss": n, "cp": 0})
    return out


def _words_hit(text: str, words) -> str:
    t = " " + str(text or "").lower() + " "
    for w in words:
        w2 = str(w).strip().lower()
        if not w2:
            continue
        if re.match(r"^[a-z0-9 .'-]+$", w2):
            if re.search(r"(?<![a-z0-9])" + re.escape(w2) + r"(?![a-z0-9])", t):
                return str(w)
        elif w2 in t:
            return str(w)
    return ""


def _rules():
    from src.services import risk_gate as RG
    knife = []
    for c in (RG.tokens().get("cert") or []):
        if isinstance(c, dict) and c.get("key") == "knife":
            knife = list(c.get("names") or [])
    brands = [b for b in RG._blacklist() if str(b).strip().lower() not in BRAND_EXCEPT]
    return knife, brands


def _margin(row: Dict, ours: Optional[Dict], sold: bool) -> Dict:
    """지금 원가로 그 판매가의 실수령 마진(%) — 원가가 없으면 None. 소싱처 재확인가(monitor)가 있으면 그것."""
    from src.price import calc_sell_price, landed_cost_krw, net_margin_pct, target_margin_pct
    floor = SOLD_FLOOR_PCT if sold else float(target_margin_pct((ours or {}).get("ex")))
    out = {"cost": None, "currency": "", "cost_src": "", "margin": None, "floor": floor, "policy_price": None}
    if not ours:
        return out
    ex = ours["ex"]
    mon = ex.get("monitor") if isinstance(ex.get("monitor"), dict) else {}
    cost, src = (mon.get("current_price"), "소싱처 재확인") if mon.get("current_price") else (ex.get("price"), "수집 때")
    cur = str(ex.get("currency") or "")
    try:
        c = Decimal(str(cost).replace(",", ""))
        if c <= 0 or not cur:
            return out
    except Exception:                                              # noqa: BLE001
        return out
    out.update(cost=float(c), currency=cur, cost_src=src)
    try:
        landed = landed_cost_krw(c, cur)
        m = net_margin_pct(Decimal(str(row.get("sale_price") or 0)), landed, "smartstore")
        out["margin"] = None if m is None else float(round(m, 1))
        out["policy_price"] = int(calc_sell_price(c, cur, "smartstore", float(target_margin_pct(ex))))
    except Exception as exc:                                       # noqa: BLE001 — 계산 못 하면 원가 미확인과 같게(지어내지 않음)
        logger.warning("[셰고가 재개] 마진 계산 실패 %s: %s", row.get("channel_no"), exc)
        out["cost"] = None
    return out


def _photo_small(row: Dict, up, size_of) -> Optional[bool]:
    """사진 전부 500px 미만인가 — 대표가 500 이상이면 False, 작으면 그 상품 사진을 더 읽어 확인. 못 재면 None."""
    rep = size_of(row.get("rep_image")) if row.get("rep_image") else {"why": "주소 없음"}
    if rep.get("long_side") is None:
        return None
    if int(rep["long_side"]) >= 500:
        return False
    got = up._api_request("GET", f"/v2/products/channel-products/{row['channel_no']}") if up else {}
    imgs = ((got or {}).get("originProduct") or {}).get("images") or {} if isinstance(got, dict) else {}
    for o in imgs.get("optionalImages") or []:
        s = size_of((o or {}).get("url"))
        if s.get("long_side") and int(s["long_side"]) >= 500:
            return False
    return True


def build(store: str, *, up=None, size_of: Optional[Callable] = None, now_count: Optional[int] = None) -> Dict:
    """판매중지 전수 → 줄마다 판정 → 켤 순서 → 빈자리만큼 「켤 것」. **읽기만**(마켓 전송 0). 결과는 `plan(store)`."""
    from src.seller_console import smartstore_routing as R
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    if up is None:
        up = NaverSmartStoreUploader(account=store)
    if size_of is None:
        from src.services.coupang_image_check import size_of as _so
        size_of = _so
    t0 = time.time()
    got = fetch_suspended(up)
    limit = int(R.rules().get("limit") or 1000)
    if now_count is None:
        now_count = up.count_products(["SALE", "WAIT", "OUTOFSTOCK"])
    room = None if now_count is None else max(0, limit - int(now_count))
    status_counts = {}
    for _s in ("SALE", "WAIT", "OUTOFSTOCK", "SUSPENSION", "CLOSE", "PROHIBITION"):
        try:
            status_counts[_s] = up.count_products([_s])
        except Exception:                                          # noqa: BLE001 — 못 세면 비움(지어내지 않음)
            status_counts[_s] = None
    ours = _ours_index(store)
    sales = _sales_index(ours)
    knife, brands = _rules()
    theme = [str(w) for w in (((R.rules().get("stores") or {}).get(store) or {}).get("keywords") or [])]
    with ThreadPoolExecutor(max_workers=8) as pool:
        small = list(pool.map(lambda r: _photo_small(r, up, size_of), got["rows"]))
    rows = []
    for r, sm in zip(got["rows"], small):
        o = ours.get(r["channel_no"])
        s = sales.get(r["channel_no"], {"ss": 0, "cp": 0})
        sold = (s["ss"] + s["cp"]) > 0
        mg = _margin(r, o, sold)
        why = []
        if (k := _words_hit(r["name"], knife)):
            why.append(("knife", k))
        if (k := _words_hit(r["name"], LENS_WORDS)):
            why.append(("lens", k))
        if (k := _words_hit(r["name"], brands)):
            why.append(("brand", k))
        ex = (o or {}).get("ex") or {}
        rej = [u for u in (ex.get("uploaded") or []) if isinstance(u, dict) and ((u.get("review") or {}).get("state") == "rejected")]
        if ex.get("risk_skip") or rej or ex.get("takedowns"):
            why.append(("ours_reject", (ex.get("risk_skip") or {}).get("reason") if isinstance(ex.get("risk_skip"), dict) else
                        ("반려: " + str(((rej[0].get("review") or {}).get("comment")) or "")[:60] if rej else "「이 마켓에서 내리기」 기록")))
        mon = ex.get("monitor") if isinstance(ex.get("monitor"), dict) else {}
        if mon.get("in_stock") is False or str(mon.get("change") or "") in ("soldout", "gone", "removed"):
            why.append(("src_soldout", str(mon.get("summary") or "품절")))
        if not o or not str(o.get("url") or "").startswith("http"):
            why.append(("no_source", "우리 수집 기록에 원본 주소가 없어요" if not o else "원본 주소 없음"))
        if mg["cost"] is None:
            if o:
                why.append(("cost_unknown", ""))
        elif mg["margin"] is None or mg["margin"] < mg["floor"]:
            why.append(("margin_low", f"{mg['margin']}% < {mg['floor']:g}%"))
        if sm is True:
            why.append(("photos_small", ""))
        name_l = (r["name"] + " " + r["category"]).lower()
        tier = 1 if sold else (3 if any(str(w).lower() in name_l for w in theme) else 4)
        pp = mg["policy_price"]
        try:
            sp = int(float(r.get("sale_price") or 0))
        except (TypeError, ValueError):
            sp = 0
        rows.append({**r, "item_id": (o or {}).get("item_id", ""), "sold_ss": s["ss"], "sold_cp": s["cp"], "views": None,
                     "cost": mg["cost"], "currency": mg["currency"], "cost_src": mg["cost_src"], "margin": mg["margin"],
                     "floor": mg["floor"], "policy_price": pp,
                     "price_diff": (pp is not None and sp > 0 and abs(pp - sp) / sp >= 0.01),
                     "our_reason": "기록 없음" if not (ex.get("takedowns") or ex.get("risk_skip") or rej) else
                                   (dict(why).get("ours_reject") or "기록 있음"),
                     "photo_small": sm, "tier": tier, "exclude": [k for k, _ in why], "exclude_detail": [d for _, d in why]})
    elig = [x for x in rows if not x["exclude"]]
    # ① 팔린 것(많이 팔린 것 먼저) → ③ 주제 → ④ 나머지 — 같은 단계 안에서는 등록일 최신 먼저
    elig.sort(key=lambda x: (x["tier"], -(x["sold_ss"] + x["sold_cp"]), _neg(x["reg"])))
    n_on = len(elig) if room is None else min(len(elig), room)
    on_ids = {x["channel_no"] for x in elig[:n_on]}
    for x in elig[n_on:]:
        x["exclude"] = ["no_room"]
        x["exclude_detail"] = ["빈자리 없음 — 다음 차례"]
    by_reason: Dict[str, int] = {}
    for x in rows:
        if x["channel_no"] in on_ids:
            x["action"] = "on"
            continue
        x["action"] = "skip"
        for k in x["exclude"]:
            by_reason[k] = by_reason.get(k, 0) + 1
    order = {x["channel_no"]: i for i, x in enumerate(elig)}
    rows.sort(key=lambda x: (x["action"] != "on", order.get(x["channel_no"], 10 ** 6)))
    out = {"store": store, "at": _now(), "secs": round(time.time() - t0, 1), "complete": got["complete"], "total": got["total"],
           "read": len(got["rows"]), "error": got["error"], "limit": limit, "now_count": now_count, "room": room,
           "on": len(on_ids), "skip": len(rows) - len(on_ids), "by_reason": by_reason,
           "tiers": {str(t): sum(1 for x in rows if x["action"] == "on" and x["tier"] == t) for t in (1, 3, 4)},
           "price_diff": sum(1 for x in rows if x["action"] == "on" and x["price_diff"]),
           "views_note": VIEWS_NOTE, "status_counts": status_counts, "rows": rows}
    _state_set(_PLAN_KEY.format(store), out)
    logger.info("[셰고가 재개] 목록 %s — 판매중지 %s 읽음 · 켤 %d · 뺄 %d · 빈자리 %s · %s", store, len(rows), out["on"], out["skip"], room, by_reason)
    return out


def _neg(s: str) -> str:
    """문자열 내림차순 정렬 키(등록일 최신 먼저)."""
    return "".join(chr(0x10FFFF - ord(ch)) for ch in str(s or ""))


def csv_text(p: Dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["판정", "켤순서단계", "상품번호", "원상품번호", "상품명", "판매가", "정책가", "가격다름", "우리원가", "통화", "원가출처", "마진%", "하한%",
                "마지막수정", "등록일", "우리기록사유", "판매_스스", "판매_쿠팡", "조회수", "사진전부500미만", "뺄사유"])
    for x in p.get("rows") or []:
        w.writerow(["켤 것" if x.get("action") == "on" else "뺌", x.get("tier"), x.get("channel_no"), x.get("origin_no"), x.get("name"),
                    x.get("sale_price"), x.get("policy_price") or "", "예" if x.get("price_diff") else "", x.get("cost") or "", x.get("currency"),
                    x.get("cost_src"), "" if x.get("margin") is None else x.get("margin"), x.get("floor"), x.get("modified"), x.get("reg"),
                    x.get("our_reason"), x.get("sold_ss"), x.get("sold_cp"), "모름(API 없음)",
                    {True: "예", False: "아니오"}.get(x.get("photo_small"), "못 잼"),
                    " · ".join(f"{REASON_KO.get(k, k)}{(' — ' + d) if d else ''}" for k, d in zip(x.get("exclude") or [], x.get("exclude_detail") or []))])
    return "﻿" + buf.getvalue()


# ── 실행(오너 탭) ────────────────────────────────────────────────────────────

def start(store: str, confirm: int, by: str, *, runner=None) -> Dict:
    if store not in RUN_STORES:
        return {"ok": False, "error": "이 스토어는 보기만 해요 — 실행은 오너가 말할 때 열어요."}
    p = plan(store)
    targets = [x for x in p.get("rows") or [] if x.get("action") == "on"]
    if not targets:
        return {"ok": False, "error": "켤 상품이 없어요 — 목록을 먼저 만들어 주세요."}
    if int(confirm) != len(targets):
        return {"ok": False, "error": f"건수가 바뀌었어요(지금 {len(targets)}건) — 화면을 새로 고친 뒤 다시 눌러 주세요."}
    cur = run_state(store)
    if cur.get("state") == "running":
        return {"ok": False, "error": f"이미 도는 중이에요({len(cur.get('done') or [])}/{cur.get('total')})."}
    rec = {"state": "running", "store": store, "total": len(targets), "by": str(by or "")[:200], "started_at": _now(),
           "plan_at": p.get("at"), "targets": [{"origin_no": x["origin_no"], "channel_no": x["channel_no"], "name": x["name"][:60]} for x in targets],
           "done": [], "stop": False}
    _state_set(_RUN_KEY.format(store), rec)
    from src.utils import bg_job
    started, st = bg_job.start(f"smartstore-relist:{store}", lambda: _run(store, runner))
    if not started:
        rec["state"] = "refused"
        rec["error"] = "서버 메모리 여유가 없어 지금은 못 돌려요 — 잠시 뒤 다시 눌러 주세요." if st.get("busy_memory") else "다른 잡이 도는 중이에요."
        _state_set(_RUN_KEY.format(store), rec)
        return {"ok": False, "error": rec["error"]}
    return {"ok": True, "total": rec["total"]}


def stop(store: str) -> bool:
    rec = run_state(store)
    if rec.get("state") != "running":
        return False
    rec["stop"] = True
    _state_set(_RUN_KEY.format(store), rec)
    return True


def _resume_one(up, origin_no: str) -> Dict:
    res = up._api_request("PUT", f"/v1/products/origin-products/{origin_no}/change-status", data={"statusType": "SALE"})
    if not isinstance(res, dict) or "error" in res:
        return {"ok": False, "raw": str((res or {}).get("error") if isinstance(res, dict) else res)[:400]}
    return {"ok": True, "raw": ""}


def _run(store: str, runner=None) -> Dict:
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    up = NaverSmartStoreUploader(account=store)
    runner = runner or (lambda o: _resume_one(up, o))
    rec = run_state(store)
    targets = rec.get("targets") or []
    for i in range(0, len(targets), CHUNK):
        for t in targets[i:i + CHUNK]:
            if run_state(store).get("stop"):
                rec = run_state(store)
                rec["state"] = "stopped"
                rec["stopped_at"] = _now()
                _finish(store, rec, up)
                return {"ok": True, "stopped": True}
            try:
                r = runner(t["origin_no"]) or {}
            except Exception as exc:                               # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
                r = {"ok": False, "raw": f"{type(exc).__name__}: {str(exc)[:200]}"}
            rec = run_state(store)
            rec.setdefault("done", []).append({"channel_no": t["channel_no"], "name": t["name"], "ok": bool(r.get("ok")), "raw": r.get("raw", "")})
            _state_set(_RUN_KEY.format(store), rec)
        logger.info("[셰고가 재개] %s %d/%d", store, min(i + CHUNK, len(targets)), len(targets))
    rec = run_state(store)
    rec["state"] = "finished"
    _finish(store, rec, up)
    return {"ok": True}


def _finish(store: str, rec: Dict, up) -> None:
    rec["finished_at"] = _now()
    rec["ok_count"] = sum(1 for d in rec.get("done") or [] if d.get("ok"))
    try:                                                           # 끝나면 상태별 수를 다시 읽는다
        rec["after_counts"] = {s: up.count_products([s]) for s in ("SALE", "WAIT", "OUTOFSTOCK", "SUSPENSION")}
    except Exception as exc:                                       # noqa: BLE001
        rec["after_counts"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    _state_set(_RUN_KEY.format(store), rec)
    logger.warning("[셰고가 재개] %s 끝 — 성공 %d/%d · 다시 읽은 수 %s", store, rec["ok_count"], rec.get("total"), rec["after_counts"])
