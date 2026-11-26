"""오너 11-25 00:58 ②⑦ — **읽기 전용** 관리자 진단(운영 DB·네이버 API는 서버에서만 닿는다).

⑦ 스스 한도 의심(「천 개 있던 게 언제 빠졌나」): 스토어 키마다
   · 그 키가 가리키는 실제 스토어(채널 조회 `GET /v1/seller/channels` · 주소록 대조)
   · 상태별 상품 수(SALE·WAIT·OUTOFSTOCK·SUSPENSION·CLOSE·PROHIBITION) — 화면의 「97/1,000」은 SALE+WAIT+OUTOFSTOCK 합
   · 지정한 채널 상품번호가 이 키로 조회되나(어느 스토어에 있나)
   키-스토어가 엇갈리면 `mismatch` — 10월 두부 소파 건 재발 여부.
② 표본 행: 마켓 상품번호로 수집 행을 찾아 url·raw_url·수집 경로·images[] 원문과 실제 픽셀 크기.

쓰기 0 · 마켓 전송 0. 키 값은 싣지 않는다.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

STATUSES = ("SALE", "WAIT", "OUTOFSTOCK", "SUSPENSION", "CLOSE", "PROHIBITION")


def _channels(up) -> List[Dict[str, str]]:
    ch = up._api_request("GET", "/v1/seller/channels")
    rows = ch if isinstance(ch, list) else ((ch or {}).get("contents") or (ch or {}).get("channels") or []) if isinstance(ch, dict) else []
    out = []
    for c in rows if isinstance(rows, list) else []:
        if isinstance(c, dict):
            nm = str(c.get("name") or c.get("channelName") or "").strip()
            no = str(c.get("channelNo") or c.get("id") or "").strip()
            if nm or no:
                out.append({"name": nm, "no": no})
    if not out and isinstance(ch, dict) and ch.get("error"):
        out.append({"name": "", "no": "", "error": "조회 실패: " + str(ch["error"])[:160]})
    return out


def _channel_names(up) -> List[str]:
    return [c.get("error") or (f"{c['name']} ({c['no']})" if c.get("no") else c.get("name", "")) for c in _channels(up)]


def key_match(store: str, channels: List[Dict[str, str]], expected_no: str, expected_label: str) -> Dict[str, Any]:
    """오너 11-26 진단 2 — 키-스토어 대조는 **채널번호로**. 번호를 모르면 판정하지 않는다(라벨 글자 비교는 오경보였다:
    고코스모스 키 → 실제 채널 이름 「나의코스모스(102783356)」)."""
    nos = [c.get("no") for c in channels if c.get("no")]
    if not nos:
        return {"state": "unknown", "line": "채널을 못 읽었어요 — 판정 안 함"}
    if not expected_no:
        return {"state": "unpinned", "line": f"기대 채널번호가 아직 없어요(지금 {', '.join(nos)}) — 판정 안 함"}
    if expected_no in nos:
        return {"state": "ok", "line": f"키 정상 — 채널 {expected_no}"}
    return {"state": "mismatch", "line": f"{store} 키 → 채널 {', '.join(nos)} (기대: {expected_label} {expected_no})"}


def _product(up, no: str) -> Dict[str, Any]:
    res = up._api_request("GET", f"/v2/products/channel-products/{no}")
    if not isinstance(res, dict) or "error" in res:
        return {"found": False, "why": str((res or {}).get("error") if isinstance(res, dict) else res)[:160]}
    op = res.get("originProduct") or {}
    return {"found": True, "name": str(op.get("name") or "")[:80], "status": str(op.get("statusType") or ""),
            "images": len(((op.get("images") or {}).get("optionalImages") or [])) + (1 if (op.get("images") or {}).get("representativeImage") else 0)}


def store_audit(channel_nos=()) -> Dict[str, Any]:
    from src.seller_console import smartstore_routing as R
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    out: Dict[str, Any] = {"stores": [], "mismatch": [], "products": {}}
    expected = {st: R.store_label(st) for st in R.STORES}
    for st in R.STORES:
        row: Dict[str, Any] = {"store": st, "label": expected[st], "counts": {}, "channels": [], "token": False}
        try:
            up = NaverSmartStoreUploader(account=st)
            row["token"] = bool(up.client_id and up.client_secret and up._get_access_token())
            if not row["token"]:
                row["why"] = (getattr(up, "token_error", "") or "키 없음·토큰 실패")[:200]
                out["stores"].append(row)
                continue
            _chs = _channels(up)
            row["channels"] = [c.get("error") or (f"{c['name']} ({c['no']})" if c.get("no") else c.get("name", "")) for c in _chs]
            for s in STATUSES:
                row["counts"][s] = up.count_products([s])
            row["limit_count"] = up.count_products(["SALE", "WAIT", "OUTOFSTOCK"])
            for no in channel_nos:
                out["products"].setdefault(str(no), {})[st] = _product(up, str(no))
            row["key_match"] = key_match(st, _chs, R.store_channel_no(st), expected[st])
            if row["key_match"]["state"] == "mismatch":
                out["mismatch"].append(row["key_match"]["line"])
        except Exception as exc:                                   # noqa: BLE001 — 진단은 죽지 않는다
            row["why"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        out["stores"].append(row)
    try:
        out["our_records"] = our_store_records()
    except Exception as exc:                                       # noqa: BLE001
        out["our_records"] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    try:
        out["common_key"] = R.identify_common_key(force=True)
    except Exception as exc:                                       # noqa: BLE001
        out["common_key"] = {"state": "fail", "evidence": type(exc).__name__}
    return out


def item_audit(market_no: str) -> Dict[str, Any]:
    from src.db import collect_history_pg as P
    from src.services import coupang_image_check as C
    rows = P.find_by_text(market_no, limit=3)
    out = []
    for r in rows:
        try:
            ex = json.loads(r.get("extra_json") or "{}") or {}
        except Exception:                                          # noqa: BLE001
            ex = {}
        imgs = []
        for u in (ex.get("images") or [])[:20]:
            sz = C.size_of(u)
            imgs.append({"url": u, "w": sz.get("w"), "h": sz.get("h"), "why": sz.get("why", "")})
        out.append({"id": r.get("id"), "source": r.get("source"), "url": r.get("url"), "raw_url": ex.get("raw_url") or "",
                    "final_url": ex.get("final_url") or "", "share_src": ex.get("share_src") or ex.get("src") or "",
                    "share_raw": str(ex.get("share_raw") or "")[:200], "item_id_taobao": ex.get("item_id_taobao") or "",
                    "mode": ex.get("mode") or "", "enrich_state": ex.get("enrich_state") or "",
                    "images_stored": len(ex.get("images_stored") or []), "detail_images": len(ex.get("detail_images") or []),
                    "rep_image": ex.get("rep_image") or "", "images": imgs, "title": r.get("title"),
                    "skus": len(ex.get("skus") or []), "options": [o.get("name") for o in (ex.get("options") or []) if isinstance(o, dict)]})
    return {"market_no": market_no, "rows": out}


def our_store_records(days: int = 3650) -> Dict[str, Any]:
    """오너 11-26 진단 2 — 스토어별 판매중지가 **고가브릿지 기록에** 몇 건 있나(등록 기록 · 「이 마켓에서 내리기」 기록).
    마켓 쪽 판매중지 수와의 차이는 「우리 기록에 없음」 — 다른 도구·판매자센터·마켓 직권(지어내지 않음). 읽기만."""
    from src.seller_console import collect_history_store as chs
    out: Dict[str, Any] = {}
    rows = chs.list_items(days=days, extra_keys=["uploaded", "takedowns"]) or []
    for r in rows:
        try:
            ex = json.loads(r.get("extra_json") or "{}") if isinstance(r.get("extra_json"), str) else (r.get("extra_json") or {})
        except Exception:                                          # noqa: BLE001
            continue
        for u in ex.get("uploaded") or []:
            m = str((u or {}).get("market") or "") if isinstance(u, dict) else ""
            if m.startswith("smartstore"):
                st = m.partition(":")[2] or "chezgoga"
                d = out.setdefault(st, {"registered": 0, "taken_down_ok": 0, "taken_down_fail": 0})
                d["registered"] += 1
        for t in ex.get("takedowns") or []:
            m = str((t or {}).get("market") or "") if isinstance(t, dict) else ""
            if m.startswith("smartstore"):
                st = m.partition(":")[2] or "chezgoga"
                d = out.setdefault(st, {"registered": 0, "taken_down_ok": 0, "taken_down_fail": 0})
                d["taken_down_ok" if t.get("ok") else "taken_down_fail"] += 1
    return out


STATUS_KO = {"SALE": "판매중", "WAIT": "판매대기", "OUTOFSTOCK": "품절", "SUSPENSION": "판매중지", "CLOSE": "판매종료", "PROHIBITION": "판매금지"}


def store_verdict(d: Dict[str, Any]) -> str:
    """판정 한 줄 — 「키 정상 1/2 · 판정 안 함 1 · 엇갈림 0」."""
    st = [r.get("key_match", {}).get("state") for r in d.get("stores") or []]
    n = len(st)
    return (f"키 정상 {st.count('ok')}/{n}" + (f" · 판정 안 함 {st.count('unpinned') + st.count('unknown')}" if (st.count('unpinned') + st.count('unknown')) else "")
            + f" · 엇갈림 {len(d.get('mismatch') or [])}" + (" — P0" if d.get("mismatch") else ""))


def item_verdict(d: Dict[str, Any]) -> str:
    """판정 한 줄 — 행마다 「쓸 만한 사진 u/n」(긴 변 500px 이상을 실제로 잰 장)."""
    rows = d.get("rows") or []
    if not rows:
        return "이 상품번호로 수집 행을 못 찾았어요"
    parts = []
    for r in rows:
        imgs = r.get("images") or []
        good = sum(1 for i in imgs if isinstance(i.get("w"), int) and max(i.get("w") or 0, i.get("h") or 0) >= 500)
        parts.append(f"{str(r.get('id'))[:8]} 쓸 만한 사진 {good}/{len(imgs)} · 옵션 {len(r.get('options') or [])} · SKU {r.get('skus', 0)}")
    return " / ".join(parts)
