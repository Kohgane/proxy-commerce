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
    "mirror": "원가 미확인 · 쿠팡 미러",
    "vault_hard": "볼트 기록: 반려·상표·KC·카테고리 오매칭으로 내림",
    "rejected_hist": "반려 이력",
}
#: 오너 11-27 11:51 ③: 오너가 「켤 목록으로」 골라도 못 옮기는 사유(도검·렌즈·금지 브랜드 · 볼트에 반려·상표로 내린 기록)
LOCKED = ("knife", "lens", "brand", "vault_hard", "rejected_hist")


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


def _is_mirror(x: Dict) -> bool:
    from src.services.relist_ledger import norm_code
    return norm_code(x.get("seller_code")).startswith("CP-")


def _rules():
    from src.services import risk_gate as RG
    knife = []
    for c in (RG.tokens().get("cert") or []):
        if isinstance(c, dict) and c.get("key") == "knife":
            knife = list(c.get("names") or [])
    brands = [b for b in RG.active_blacklist() if str(b).strip().lower() not in BRAND_EXCEPT]   # 허용 목록 반영(등록과 같은 목록)
    return knife, brands


def _margin(row: Dict, ours: Optional[Dict], sold: bool, ledger: Optional[Dict] = None) -> Dict:
    """지금 원가로 그 판매가의 실수령 마진(%) — 원가가 없으면 None. 소싱처 재확인가(monitor)가 있으면 그것.
    오너 11-27 11:51 ①: 우리 수집 기록에 원가가 없으면 볼트 장부(오너 입력 먼저)의 원가 — 출처를 그 장부 이름으로 적는다."""
    from src.price import calc_sell_price, landed_cost_krw, net_margin_pct, target_margin_pct
    floor = SOLD_FLOOR_PCT if sold else float(target_margin_pct((ours or {}).get("ex")))
    out = {"cost": None, "currency": "", "cost_src": "", "margin": None, "floor": floor, "policy_price": None}
    ex = (ours or {}).get("ex") or {}
    mon = ex.get("monitor") if isinstance(ex.get("monitor"), dict) else {}
    cost, src = (mon.get("current_price"), "소싱처 재확인") if mon.get("current_price") else (ex.get("price"), "수집 때")
    cur = str(ex.get("currency") or "")
    if ledger and ledger.get("cost") and (ledger.get("src") == "오너 입력" or not (cost and cur)):
        cost, cur, src = ledger["cost"], str(ledger.get("currency") or ""), str(ledger.get("src") or "볼트 장부")
    if not (cost and cur):
        return out
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


_BUILD_KEY = "smartstore_relist:build:{}"
PHOTO_WORKERS = 2                          # 오너 11-27: 켤 후보만 · 동시 2 · 머리 바이트만
PHOTO_SAVE_EVERY = 20


_BRIEF_KEYS = ("state", "phase", "progress", "stalled", "idle_sec", "started_at", "heartbeat_at", "error", "rss_peak_mb",
               "result", "finished_at", "steps")


def build_state(store: str) -> Dict:
    """화면용 요약 — 줄에는 판매중지 행 전부가 들어 있어(중간 단계) 그건 빼고 진행만."""
    from src.services import durable_job as DJ
    st = DJ.status(_BUILD_KEY.format(store))
    return {k: st.get(k) for k in _BRIEF_KEYS if k in st}


def _judge_row(r: Dict, o: Optional[Dict], s: Dict, knife, brands, theme, L: Optional[Dict] = None) -> Dict:
    """한 줄 판정(사진 빼고) — 사유·마진·켤 순서 단계. 사진은 켤 후보에만 따로 잰다.
    `L` = 볼트 장부 줄(오너 11-27 11:51 — 원가·소싱처·볼트 사유·쿠팡 판매 건수)."""
    from src.services import relist_ledger as RL
    s = {"ss": int(s.get("ss") or 0), "cp": max(int(s.get("cp") or 0), int((L or {}).get("cp_sold") or 0))}
    sold = (s["ss"] + s["cp"]) > 0
    mg = _margin(r, o, sold, L)
    why = []
    if (k := _words_hit(r["name"], knife)):
        why.append(("knife", k))
    if (k := _words_hit(r["name"], LENS_WORDS)):
        why.append(("lens", k))
    from src.services.risk_gate import blacklist_words as _bl_words   # 등록 사전검증과 같은 규칙(호환 액세서리 자리는 빼고)
    _bw = [w for w in _bl_words(r["name"], brands) if _words_hit(r["name"], [w])]
    if _bw:
        why.append(("brand", _bw[0]))
    ex = (o or {}).get("ex") or {}
    rej = [u for u in (ex.get("uploaded") or []) if isinstance(u, dict) and ((u.get("review") or {}).get("state") == "rejected")]
    if ex.get("risk_skip") or rej or ex.get("takedowns"):
        why.append(("ours_reject", (ex.get("risk_skip") or {}).get("reason") if isinstance(ex.get("risk_skip"), dict) else
                    ("반려: " + str(((rej[0].get("review") or {}).get("comment")) or "")[:60] if rej else "「이 마켓에서 내리기」 기록")))
    from src.services.risk_gate import rejected_match, rejected_line
    _rj = rejected_match(str((o or {}).get("url") or (L or {}).get("url") or ""),
                         [r.get("channel_no"), r.get("origin_no"), r.get("seller_code")])
    if _rj:                                                        # 오너 11-27 15:18 0-2: 반려·소명 났던 그 상품만 — 「반려 이력(날짜·사유)」
        why.append(("rejected_hist", rejected_line(_rj) or "반려·소명 이력"))
    if (hv := RL.hard_vault_reason(L)):
        why.append(("vault_hard", f"{hv}{(' · ' + L['vault_job']) if L.get('vault_job') else ''}"))
    mon = ex.get("monitor") if isinstance(ex.get("monitor"), dict) else {}
    if mon.get("in_stock") is False or str(mon.get("change") or "") in ("soldout", "gone", "removed"):
        why.append(("src_soldout", str(mon.get("summary") or "품절")))
    code = RL.norm_code(r.get("seller_code"))
    has_url = bool(str((o or {}).get("url") or "").startswith("http") or (L or {}).get("url"))
    if mg["cost"] is not None and not o:
        pass                                                       # 볼트 장부에서 원가를 찾았다 — 원본 기록 없음·미러는 사유가 아니다
    elif not o and code.startswith("CP-"):
        # 오너 11-27 ⑤ 표본 검수: 1,679건 전부 「원본 주소 없음」이었다 — 대부분 오라클이 쿠팡에서 옮겨 깐 미러라 우리 수집 기록에 없다.
        #   원본이 없는 게 아니라 **앱이 못 읽는 장부**에 있다 — 사유를 그렇게 말한다(원가 미확인이라 켜지 않는 건 그대로).
        why.append(("mirror", f"쿠팡 {code} 미러 — 원가가 우리 기록·볼트 장부에 없어요(「원가 넣기」로 이 줄만 다시 판정)"))
    elif not o or not has_url:
        why.append(("no_source", "우리 수집 기록에 원본 주소가 없어요" if not o else "원본 주소 없음"))
    if mg["cost"] is None:
        if o:
            why.append(("cost_unknown", ""))
    elif mg["margin"] is None or mg["margin"] < mg["floor"]:
        why.append(("margin_low", f"{mg['margin']}% < {mg['floor']:g}%"))
    name_l = (r["name"] + " " + r["category"]).lower()
    tier = 1 if sold else (3 if any(str(w).lower() in name_l for w in theme) else 4)
    pp = mg["policy_price"]
    try:
        sp = int(float(r.get("sale_price") or 0))
    except (TypeError, ValueError):
        sp = 0
    return {**r, "item_id": (o or {}).get("item_id", ""), "sold_ss": s["ss"], "sold_cp": s["cp"], "views": None,
            "cost": mg["cost"], "currency": mg["currency"], "cost_src": mg["cost_src"], "margin": mg["margin"],
            "vault_reason": str((L or {}).get("vault_reason") or ""), "vault_job": str((L or {}).get("vault_job") or ""),
            "src_url": str((o or {}).get("url") or (L or {}).get("url") or "")[:300],
            "owner_ok": bool(r.get("owner_ok")),
            "floor": mg["floor"], "policy_price": pp,
            "price_diff": (pp is not None and sp > 0 and abs(pp - sp) / sp >= 0.01),
            "our_reason": "기록 없음" if not (ex.get("takedowns") or ex.get("risk_skip") or rej) else
                          (dict(why).get("ours_reject") or "기록 있음"),
            "photo_small": None, "tier": tier, "exclude": [k for k, _ in why], "exclude_detail": [d for _, d in why]}


def _advance(store: str, rec: Dict, deadline: float, *, up, size_of, now_count=None, save=None) -> Dict:
    """목록 만들기 한 걸음 — 단계(fetch → judge → photos → final)와 커서를 rec에 적는다. `save(rec)`는 100건마다 부른다.
    읽기만(마켓 전송 0). 끝나면 `plan(store)`에 결과 · rec.state=done."""
    from src.seller_console import smartstore_routing as R
    save = save or (lambda _r: None)
    phase = rec.get("phase") or "fetch"
    if phase == "fetch":
        rows = rec.setdefault("fetched", [])
        while time.time() < deadline:
            page = int(rec.get("page_next") or 1)
            if page > MAX_PAGES:
                rec["phase"] = "judge"
                break
            res = up._api_request("POST", "/v1/products/search",
                                  data={"productStatusTypes": ["SUSPENSION"], "page": page, "size": PAGE_SIZE})
            if not isinstance(res, dict) or "error" in res:
                rec["fetch_error"] = str((res or {}).get("error") if isinstance(res, dict) else res)[:300]
                rec["phase"] = "judge"
                break
            rec["total"] = res.get("totalElements", rec.get("total"))
            contents = res.get("contents") or []
            for c in contents:
                for ch in (c or {}).get("channelProducts") or []:
                    if str(ch.get("statusType") or "SUSPENSION") != "SUSPENSION":
                        continue
                    rows.append({
                        "origin_no": str((c or {}).get("originProductNo") or ch.get("originProductNo") or ""),
                        "channel_no": str(ch.get("channelProductNo") or ""), "name": str(ch.get("name") or ""),
                        "sale_price": ch.get("discountedPrice") or ch.get("salePrice"), "list_price": ch.get("salePrice"),
                        "reg": str(ch.get("regDate") or ""), "modified": str(ch.get("modifiedDate") or ""),
                        "rep_image": str(((ch.get("representativeImage") or {}).get("url")) or ""),
                        "stock": ch.get("stockQuantity"), "category": str(ch.get("wholeCategoryName") or ""),
                        # 오너 11-27 ⑤: 오라클 미러(쿠팡→스스)는 판매자 관리 코드 `CP-<쿠팡 상품번호>`를 남긴다 — 원본·원가는 쿠팡 장부
                        "seller_code": str(ch.get("sellerManagementCode") or (c or {}).get("sellerManagementCode") or "")})
            rec["page_next"] = page + 1
            rec["progress"] = {"n": len(rows), "total": rec.get("total"), "label": f"판매중지 읽는 중 {len(rows):,}/{int(rec.get('total') or 0):,}"}
            save(rec)                                              # 100건(한 쪽)마다 저장 — 재시작 뒤 이 쪽부터
            if len(contents) < PAGE_SIZE:
                rec["phase"] = "judge"
                break
        return rec
    if phase == "judge":
        limit = int(R.rules().get("limit") or 1000)
        if now_count is None:
            now_count = up.count_products(["SALE", "WAIT", "OUTOFSTOCK"])
        room = None if now_count is None else max(0, limit - int(now_count))
        status_counts = {}
        for _s in ("SALE", "WAIT", "OUTOFSTOCK", "SUSPENSION", "CLOSE", "PROHIBITION"):
            try:
                status_counts[_s] = up.count_products([_s])
            except Exception:                                      # noqa: BLE001 — 못 세면 비움(지어내지 않음)
                status_counts[_s] = None
        ours = _ours_index(store)
        sales = _sales_index(ours)
        knife, brands = _rules()
        theme = [str(w) for w in (((R.rules().get("stores") or {}).get(store) or {}).get("keywords") or [])]
        from src.services import relist_ledger as RL
        led = RL.index(store)
        judged = [_judge_row(r, ours.get(r["channel_no"]), sales.get(r["channel_no"], {"ss": 0, "cp": 0}), knife, brands, theme,
                             RL.find(led, r)) for r in rec.get("fetched") or []]
        rec["ledger"] = RL.summary(store)
        elig = [x for x in judged if not x["exclude"]]
        elig.sort(key=lambda x: (x["tier"], -(x["sold_ss"] + x["sold_cp"]), _neg(x["reg"])))
        rec.update(rows=judged, fetched=[], elig=[x["channel_no"] for x in elig], photo_i=0, on=[], limit=limit,
                   now_count=now_count, room=room, status_counts=status_counts, phase="photos",
                   complete=(not rec.get("fetch_error")) and rec.get("total") is not None and len(judged) >= int(rec["total"]))
        rec["progress"] = {"n": 0, "total": len(elig) if room is None else min(len(elig), room),
                           "label": f"판정 끝 — 켤 후보 사진 확인 0/{len(elig) if room is None else min(len(elig), room):,}"}
        save(rec)
        return rec
    if phase == "photos":
        by = {x["channel_no"]: x for x in rec.get("rows") or []}
        elig, on, room = rec.get("elig") or [], rec.setdefault("on", []), rec.get("room")
        want = len(elig) if room is None else min(len(elig), int(room))
        with ThreadPoolExecutor(max_workers=PHOTO_WORKERS) as pool:
            while time.time() < deadline and len(on) < want and int(rec.get("photo_i") or 0) < len(elig):
                i = int(rec.get("photo_i") or 0)
                need = want - len(on)
                batch = [by[c] for c in elig[i:i + max(1, min(PHOTO_WORKERS, need))] if c in by]
                res = list(pool.map(lambda r: _photo_small(r, up, size_of), batch))
                for r, sm in zip(batch, res):
                    r["photo_small"] = sm
                    if sm is True:
                        r["exclude"] = ["photos_small"]
                        r["exclude_detail"] = [""]
                    elif len(on) < want:
                        on.append(r["channel_no"])
                rec["photo_i"] = i + len(batch)
                rec["progress"] = {"n": len(on), "total": want, "label": f"켤 후보 사진 확인 {len(on):,}/{want:,}(확인 {rec['photo_i']:,}건)"}
                if rec["photo_i"] // PHOTO_SAVE_EVERY != i // PHOTO_SAVE_EVERY:
                    save(rec)                                      # 줄이 1MB 안팎이라 20장마다만 저장(재시작 땐 최대 20장 다시 잼)
        if len(on) >= want or int(rec.get("photo_i") or 0) >= len(elig):
            rec["phase"] = "final"
        return rec
    # final — 예전 build()와 같은 모양의 결과
    rows = rec.get("rows") or []
    on_ids = set(rec.get("on") or [])
    order = {c: i for i, c in enumerate(rec.get("elig") or [])}
    by_reason: Dict[str, int] = {}
    for x in rows:
        if x["channel_no"] in on_ids:
            x["action"] = "on"
            continue
        x["action"] = "skip"
        if not x["exclude"]:
            x["exclude"] = ["no_room"]
            x["exclude_detail"] = ["빈자리 없음 — 다음 차례"]
        for k in x["exclude"]:
            by_reason[k] = by_reason.get(k, 0) + 1
    rows.sort(key=lambda x: (x["action"] != "on", order.get(x["channel_no"], 10 ** 6)))
    out = {"store": store, "at": _now(), "secs": round(time.time() - float(rec.get("t0") or time.time()), 1),
           "complete": bool(rec.get("complete")), "total": rec.get("total"), "read": len(rows), "error": rec.get("fetch_error") or "",
           "limit": rec.get("limit"), "now_count": rec.get("now_count"), "room": rec.get("room"),
           "on": len(on_ids), "skip": len(rows) - len(on_ids), "by_reason": by_reason,
           "tiers": {str(t): sum(1 for x in rows if x["action"] == "on" and x["tier"] == t) for t in (1, 3, 4)},
           "price_diff": sum(1 for x in rows if x["action"] == "on" and x["price_diff"]),
           "photos_checked": int(rec.get("photo_i") or 0), "rss_peak_mb": rec.get("rss_peak_mb"),
           "mirrors": sum(1 for x in rows if _is_mirror(x)),
           "ours": sum(1 for x in rows if x.get("item_id")),
           "ledger_hit": sum(1 for x in rows if not x.get("item_id") and x.get("cost") is not None),
           "ledger": rec.get("ledger") or {},
           "views_note": VIEWS_NOTE, "status_counts": rec.get("status_counts") or {}, "rows": rows}
    out["owner_ok"] = 0
    _state_set(_PLAN_KEY.format(store), out)
    from src.seller_console import smartstore_routing as R2
    rec.update(state="done", phase="done", rows=[], elig=[], on=[], result={k: v for k, v in out.items() if k != "rows"},
               progress={"n": out["on"], "total": out["on"], "label": f"끝 — 켤 {out['on']:,} · 뺄 {out['skip']:,}"},
               push={"title": f"{R2.store_label(store)} 목록 완료 — 켤 {out['on']:,} · 뺄 {out['skip']:,}",
                     "body": "눌러서 켤 것·뺄 것(사유)을 확인해요.", "path": f"/seller/admin/smartstore-relist?store={store}"})
    logger.info("[셰고가 재개] 목록 %s — 판매중지 %s 읽음 · 켤 %d · 뺄 %d · 빈자리 %s · 사진 확인 %s · %s", store, len(rows), out["on"],
                out["skip"], rec.get("room"), out["photos_checked"], by_reason)
    return rec


def _build_step(key: str, rec: Dict, deadline: float) -> Dict:
    """durable_job 걸음 — 운영 경로(네이버 키 · 머리 바이트 크기 재기)."""
    from src.services import durable_job as DJ
    from src.services.coupang_image_check import head_size
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    store = str(rec.get("store") or "")
    return _advance(store, rec, deadline, up=NaverSmartStoreUploader(account=store), size_of=head_size,
                    save=lambda r: DJ.save(key, r))


def start_build(store: str, by_uid: str = "") -> Dict:
    """「목록 만들기」 — 줄에 세우고 바로 시작(재시작돼도 틱·부팅이 저장한 쪽부터 잇는다). 이미 돌면 그대로."""
    from src.services import durable_job as DJ
    key = _BUILD_KEY.format(store)
    cur = DJ.status(key)
    if cur.get("state") == "running":
        if cur.get("stalled"):
            r = DJ.resume(key)
            return {"ok": True, "resumed": True, "started": r.get("started")}
        return {"ok": True, "already": True}
    r = DJ.begin(key, "relist_build", {"store": store, "phase": "fetch", "page_next": 1, "fetched": [], "t0": time.time(),
                                       "progress": {"n": 0, "total": None, "label": "판매중지 읽는 중 0"}}, by_uid=by_uid)
    return {"ok": True, "started": r["started"]}


def build(store: str, *, up=None, size_of: Optional[Callable] = None, now_count: Optional[int] = None) -> Dict:
    """한 번에 끝까지(시험·스크립트용) — 운영 화면은 `start_build`(줄·이어하기). 같은 걸음 함수를 쓴다."""
    if up is None:
        from src.uploaders.naver_uploader import NaverSmartStoreUploader
        up = NaverSmartStoreUploader(account=store)
    if size_of is None:
        from src.services.coupang_image_check import head_size as size_of
    rec = {"store": store, "phase": "fetch", "page_next": 1, "fetched": [], "t0": time.time(), "state": "running"}
    while rec.get("state") == "running":
        rec = _advance(store, rec, time.time() + 3600, up=up, size_of=size_of, now_count=now_count)
    return plan(store)


def _neg(s: str) -> str:
    """문자열 내림차순 정렬 키(등록일 최신 먼저)."""
    return "".join(chr(0x10FFFF - ord(ch)) for ch in str(s or ""))


def csv_text(p: Dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["판정", "켤순서단계", "상품번호", "원상품번호", "상품명", "판매가", "정책가", "가격다름", "우리원가", "통화", "원가출처", "마진%", "하한%",
                "마지막수정", "등록일", "우리기록사유", "판매_스스", "판매_쿠팡", "조회수", "사진전부500미만", "뺄사유",
                "관리코드", "볼트사유", "볼트작업", "소싱처주소", "오너확인"])
    for x in p.get("rows") or []:
        w.writerow(["켤 것" if x.get("action") == "on" else "뺌", x.get("tier"), x.get("channel_no"), x.get("origin_no"), x.get("name"),
                    x.get("sale_price"), x.get("policy_price") or "", "예" if x.get("price_diff") else "", x.get("cost") or "", x.get("currency"),
                    x.get("cost_src"), "" if x.get("margin") is None else x.get("margin"), x.get("floor"), x.get("modified"), x.get("reg"),
                    x.get("our_reason"), x.get("sold_ss"), x.get("sold_cp"), "모름(API 없음)",
                    {True: "예", False: "아니오"}.get(x.get("photo_small"), "못 잼"),
                    " · ".join(f"{REASON_KO.get(k, k)}{(' — ' + d) if d else ''}" for k, d in zip(x.get("exclude") or [], x.get("exclude_detail") or [])),
                    x.get("seller_code") or "", x.get("vault_reason") or "", x.get("vault_job") or "", x.get("src_url") or "",
                    "예" if x.get("owner_ok") else ""])
    return "﻿" + buf.getvalue()


# ── 오너 11-27 11:51 ②③①: 왜 0인지 · 골라 켜기 · 원가 넣기 ─────────────────────────

def recount(p: Dict) -> Dict:
    """줄을 고친 뒤 요약 숫자를 다시 센다(켤·뺄·사유별·단계·가격 다름·오너 확인)."""
    rows = p.get("rows") or []
    by: Dict[str, int] = {}
    for x in rows:
        if x.get("action") == "on":
            continue
        for k in x.get("exclude") or []:
            by[k] = by.get(k, 0) + 1
    on = [x for x in rows if x.get("action") == "on"]
    p.update(on=len(on), skip=len(rows) - len(on), by_reason=by,
             tiers={str(t): sum(1 for x in on if x.get("tier") == t) for t in (1, 3, 4)},
             price_diff=sum(1 for x in on if x.get("price_diff")), owner_ok=sum(1 for x in on if x.get("owner_ok")),
             ledger_hit=sum(1 for x in rows if not x.get("item_id") and x.get("cost") is not None))
    return p


def why_zero(p: Dict) -> str:
    """켤 것이 0일 때 한 줄 — 가장 큰 사유를 숫자로(「1,679건 중 1,600건이 우리 기록에 없어요」)."""
    rows = p.get("rows") or []
    if not rows or int(p.get("on") or 0) > 0:
        return ""
    n = len(rows)
    no_cost = [x for x in rows if x.get("cost") is None and not x.get("item_id")]
    if len(no_cost) * 2 >= n:
        mir = sum(1 for x in no_cost if _is_mirror(x))
        return (f"{n:,}건 중 {len(no_cost):,}건이 우리 기록·볼트 장부에 원가가 없어요"
                f"(쿠팡 미러 {mir:,} · 그 밖 {len(no_cost) - mir:,}) — 원가를 모르면 켜지 않아요. "
                "줄마다 「원가 넣기」로 넣거나, 아는 상품은 골라 「켤 목록으로」.")
    by = dict(p.get("by_reason") or {})
    if not by:
        return f"{n:,}건 모두 켤 조건을 못 채웠어요."
    k, c = max(by.items(), key=lambda kv: kv[1])
    return f"{n:,}건 중 {c:,}건이 「{REASON_KO.get(k, k)}」 — 가장 큰 사유예요."


def _busy(store: str) -> str:
    from src.services import durable_job as DJ
    if DJ.status(_BUILD_KEY.format(store)).get("state") == "running":
        return "목록을 새로 만드는 중이에요 — 끝난 뒤에 고쳐 주세요(만든 목록이 덮어써요)."
    if DJ.status(_RUN_KEY.format(store)).get("state") == "running":
        return "판매 재개가 도는 중이에요 — 끝난 뒤에 고쳐 주세요."
    return ""


def owner_pick(store: str, channel_nos, by: str = "") -> Dict:
    """뺄 줄을 골라 켤 목록으로 — 사유 「오너 확인」. 도검·렌즈·금지 브랜드·볼트 반려 기록은 못 옮긴다.
    빈자리보다 많이 고르면 하나도 안 옮긴다(네이버 1,000칸 한도). 마켓에는 아무것도 안 보낸다(목록만 고침)."""
    if (b := _busy(store)):
        return {"ok": False, "error": b}
    p = plan(store)
    want = {str(c) for c in (channel_nos or []) if str(c).strip()}
    if not want:
        return {"ok": False, "error": "고른 상품이 없어요."}
    by_no = {str(x.get("channel_no")): x for x in p.get("rows") or []}
    locked, moved, missing = [], [], []
    for c in sorted(want):
        x = by_no.get(c)
        if not x:
            missing.append(c)
        elif x.get("action") == "on":
            continue
        elif set(x.get("exclude") or []) & set(LOCKED):
            locked.append({"channel_no": c, "name": str(x.get("name") or "")[:60],
                           "why": REASON_KO.get(next(k for k in x["exclude"] if k in LOCKED), "")})
        else:
            moved.append(x)
    room = p.get("room")
    on_now = sum(1 for x in p.get("rows") or [] if x.get("action") == "on")
    if room is not None and on_now + len(moved) > int(room):
        return {"ok": False, "error": f"빈자리 {int(room):,}칸인데 켤 것이 {on_now + len(moved):,}건이 돼요 — {on_now + len(moved) - int(room):,}건 덜 골라 주세요.",
                "locked": locked}
    at = _now()
    for x in moved:
        x["owner_prev"] = {"exclude": list(x.get("exclude") or []), "exclude_detail": list(x.get("exclude_detail") or []),
                           "our_reason": x.get("our_reason")}
        x.update(action="on", owner_ok=True, owner_at=at, owner_by=str(by or "")[:120], exclude=[], exclude_detail=[],
                 our_reason="오너 확인")
    recount(p)
    _state_set(_PLAN_KEY.format(store), p)
    logger.info("[셰고가 재개] %s 오너 확인 %d건 켤 목록으로 · 못 옮김 %d", store, len(moved), len(locked))
    return {"ok": True, "moved": len(moved), "locked": locked, "missing": missing, "on": p["on"], "skip": p["skip"]}


def owner_unpick(store: str, channel_nos) -> Dict:
    """오너가 옮긴 줄을 뺄 목록으로 되돌린다(원래 사유 그대로)."""
    if (b := _busy(store)):
        return {"ok": False, "error": b}
    p = plan(store)
    want = {str(c) for c in (channel_nos or [])}
    n = 0
    for x in p.get("rows") or []:
        if str(x.get("channel_no")) in want and x.get("owner_ok"):
            prev = x.pop("owner_prev", None) or {}
            x.update(action="skip", owner_ok=False, exclude=prev.get("exclude") or ["no_room"],
                     exclude_detail=prev.get("exclude_detail") or [""], our_reason=prev.get("our_reason") or "기록 없음")
            n += 1
    recount(p)
    _state_set(_PLAN_KEY.format(store), p)
    return {"ok": True, "back": n, "on": p["on"], "skip": p["skip"]}


def set_cost(store: str, channel_no: str, cost, currency: str, url: str = "", *, up=None, size_of=None) -> Dict:
    """「원가 넣기」 — 그 줄 하나만 다시 판정(마진·정책가·사진). 통과하고 빈자리가 있으면 켤 목록으로.
    원가는 장부(`relist:ledger`)에 출처 「오너 입력」으로 남아 다음 목록 만들기에도 쓰인다. 네이버에는 읽기만."""
    from src.services import relist_ledger as RL
    from src.seller_console import smartstore_routing as R
    if (b := _busy(store)):
        return {"ok": False, "error": b}
    p = plan(store)
    rows = p.get("rows") or []
    x = next((r for r in rows if str(r.get("channel_no")) == str(channel_no)), None)
    if not x:
        return {"ok": False, "error": "그 상품이 목록에 없어요 — 목록을 새로 만든 뒤 다시."}
    saved = RL.set_owner_cost(store, str(channel_no), cost, currency, url)
    if not saved.get("ok"):
        return saved
    o = _ours_index(store).get(str(channel_no)) if x.get("item_id") else None
    knife, brands = _rules()
    theme = [str(w) for w in (((R.rules().get("stores") or {}).get(store) or {}).get("keywords") or [])]
    base = {k: v for k, v in x.items() if k not in ("exclude", "exclude_detail", "owner_prev")}
    j = _judge_row(base, o, {"ss": x.get("sold_ss") or 0, "cp": x.get("sold_cp") or 0}, knife, brands, theme,
                   RL.find(RL.index(store), x))
    if not j["exclude"]:
        if up is None:
            from src.uploaders.naver_uploader import NaverSmartStoreUploader
            up = NaverSmartStoreUploader(account=store)
        if size_of is None:
            from src.services.coupang_image_check import head_size as size_of
        j["photo_small"] = _photo_small(j, up, size_of)
        if j["photo_small"] is True:
            j["exclude"], j["exclude_detail"] = ["photos_small"], [""]
    on_now = sum(1 for r in rows if r.get("action") == "on" and r is not x)
    room = p.get("room")
    if not j["exclude"] and room is not None and on_now >= int(room):
        j["exclude"], j["exclude_detail"] = ["no_room"], ["빈자리 없음 — 다음 차례"]
    j["action"] = "on" if not j["exclude"] else "skip"
    rows[rows.index(x)] = j
    recount(p)
    _state_set(_PLAN_KEY.format(store), p)
    verdict = ("켤 목록으로 옮겼어요" if j["action"] == "on" else
               "아직 뺄 것 — " + " · ".join(f"{REASON_KO.get(k, k)}{(' ' + d) if d else ''}" for k, d in zip(j["exclude"], j["exclude_detail"])))
    return {"ok": True, "row": {k: j.get(k) for k in ("channel_no", "name", "action", "cost", "currency", "cost_src", "margin",
                                                      "floor", "policy_price", "exclude", "exclude_detail")},
            "verdict": verdict, "on": p["on"], "skip": p["skip"]}


# ── 실행(오너 탭) ────────────────────────────────────────────────────────────

_RUNNER_OVERRIDE: Dict[str, Callable] = {}                 # 시험만 — 줄에는 함수를 저장할 수 없다


def start(store: str, confirm: int, by: str, *, runner=None, by_uid: str = "") -> Dict:
    from src.services import durable_job as DJ
    if store not in RUN_STORES:
        return {"ok": False, "error": "이 스토어는 보기만 해요 — 실행은 오너가 말할 때 열어요."}
    p = plan(store)
    targets = [x for x in p.get("rows") or [] if x.get("action") == "on"]
    if not targets:
        return {"ok": False, "error": "켤 상품이 없어요 — 목록을 먼저 만들어 주세요."}
    if int(confirm) != len(targets):
        return {"ok": False, "error": f"건수가 바뀌었어요(지금 {len(targets)}건) — 화면을 새로 고친 뒤 다시 눌러 주세요."}
    key = _RUN_KEY.format(store)
    cur = DJ.status(key)
    if cur.get("state") == "running":
        if cur.get("stalled") or not cur.get("kind"):
            # 재시작에 끊긴 실행(예전 스레드 기록 포함) — 처음부터 다시 말고 끝낸 데서 잇는다
            cur["kind"] = "relist_run"
            DJ.save(key, cur)
            r = DJ.resume(key)
            return {"ok": True, "resumed": True, "total": cur.get("total"), "started": r.get("started")}
        return {"ok": False, "error": f"이미 도는 중이에요({len(cur.get('done') or [])}/{cur.get('total')})."}
    if runner is not None:
        _RUNNER_OVERRIDE[store] = runner
    rec = {"store": store, "total": len(targets), "by": str(by or "")[:200], "plan_at": p.get("at"),
           "targets": [{"origin_no": x["origin_no"], "channel_no": x["channel_no"], "name": x["name"][:60]} for x in targets],
           "done": [], "stop": False}
    r = DJ.begin(key, "relist_run", rec, by_uid=by_uid)
    if not r["started"]:
        return {"ok": True, "total": rec["total"], "queued": True,
                "note": "서버 메모리 여유가 없어 바로 못 시작했어요 — 줄에 세워 뒀고 10분 안에 저절로 시작해요."}
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


def _run_step(key: str, rec: Dict, deadline: float, *, runner=None, up=None) -> Dict:
    """판매 재개 한 걸음 — 끝낸 건 건너뛰고(재시작 뒤 이어서) 한 건씩 · 한 건마다 저장 · 멈춤 확인."""
    store = str(rec.get("store") or "")
    if up is None:
        from src.uploaders.naver_uploader import NaverSmartStoreUploader
        up = NaverSmartStoreUploader(account=store)
    runner = runner or _RUNNER_OVERRIDE.get(store) or (lambda o: _resume_one(up, o))
    targets = rec.get("targets") or []
    while time.time() < deadline:
        cur = run_state(store)
        if cur.get("stop"):
            cur["state"] = "stopped"
            cur["stopped_at"] = _now()
            return _finish(store, cur, up)
        done = cur.get("done") or []
        if len(done) >= len(targets):
            cur["state"] = "finished"
            return _finish(store, cur, up)
        t = targets[len(done)]
        try:
            r = runner(t["origin_no"]) or {}
        except Exception as exc:                                   # noqa: BLE001 — 한 건 실패가 나머지를 막지 않는다
            r = {"ok": False, "raw": f"{type(exc).__name__}: {str(exc)[:200]}"}
        cur = run_state(store)                                     # 보내는 사이 눌린 「멈춤」을 덮지 않게 다시 읽고 덧붙인다
        cur.setdefault("done", []).append({"channel_no": t["channel_no"], "name": t["name"], "ok": bool(r.get("ok")), "raw": r.get("raw", "")})
        cur["progress"] = {"n": len(cur["done"]), "total": len(targets), "label": f"판매 재개 {len(cur['done']):,}/{len(targets):,}"}
        cur["heartbeat_at"] = _now()
        _state_set(_RUN_KEY.format(store), cur)
        rec = cur
        if len(cur["done"]) % CHUNK == 0:
            logger.info("[셰고가 재개] %s %d/%d", store, len(cur["done"]), len(targets))
    return rec


def _run(store: str, runner=None) -> Dict:
    """한 번에 끝까지(시험용) — 운영은 durable_job 걸음."""
    rec = run_state(store)
    while rec.get("state") == "running":
        rec = _run_step(_RUN_KEY.format(store), rec, time.time() + 3600, runner=runner)
    return {"ok": True, "stopped": rec.get("state") == "stopped"}


def _finish(store: str, rec: Dict, up) -> Dict:
    rec["finished_at"] = _now()
    rec["ok_count"] = sum(1 for d in rec.get("done") or [] if d.get("ok"))
    try:                                                           # 끝나면 상태별 수를 다시 읽는다
        rec["after_counts"] = {s: up.count_products([s]) for s in ("SALE", "WAIT", "OUTOFSTOCK", "SUSPENSION")}
    except Exception as exc:                                       # noqa: BLE001
        rec["after_counts"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    from src.seller_console import smartstore_routing as R
    word = "멈춤" if rec.get("state") == "stopped" else "완료"
    rec["push"] = {"title": f"{R.store_label(store)} 판매 재개 {word} — 성공 {rec['ok_count']:,}/{rec.get('total')}",
                   "body": f"실패 {len(rec.get('done') or []) - rec['ok_count']}건은 네이버 원문으로 남겼어요.",
                   "path": f"/seller/admin/smartstore-relist?store={store}"}
    _state_set(_RUN_KEY.format(store), rec)
    logger.warning("[셰고가 재개] %s 끝 — 성공 %d/%d · 다시 읽은 수 %s", store, rec["ok_count"], rec.get("total"), rec["after_counts"])
    return rec


def _register():
    from src.services import durable_job as DJ
    DJ.register("relist_build", _build_step)
    DJ.register("relist_run", lambda key, rec, deadline: _run_step(key, rec, deadline))


_register()
