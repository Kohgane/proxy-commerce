"""오너 11-26 진단 1 — 아마존 상품 「다시 가져오기」는 **서버가 바로** 다시 읽는다(타오바오처럼 PC 확장을 기다리지 않는다).

새 수집기(`collectors.amazon_pdp` — 페이지의 사진 데이터·옵션·가격·A+)로 한 번 읽어 그 행에 합친다:
  · 사진은 새로 읽은 것이 있을 때만 바꾼다(못 읽으면 옛것을 그대로 두고 사유를 적는다 — 빈손으로 지우지 않는다).
  · 셀러가 직접 고친 칸(`manual_fields`)은 덮지 않는다.
  · 전후(장수·쓸 만한 장수·사진 출처)를 `extra.amazon_refetch`에 남긴다 — 관리자 진단(diag/item)이 장마다 실제 픽셀을 잰다.
마켓에는 아무것도 보내지 않는다(스스 「사진 다시 보내기」는 오너 탭).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _usable(imgs) -> int:
    from src.collectors.amazon_pdp import usable_photo
    return sum(1 for u in imgs or [] if isinstance(u, str) and usable_photo(u))


def run(item_id: str, seller_ids: Optional[set] = None, *, fetch=None, fetch_html=None, fill_children: bool = True) -> Dict:
    from src.collectors.universal_scraper import UniversalScraper
    from src.seller_console import collect_history_store as chs
    item = chs.get(item_id, seller_ids=seller_ids) if seller_ids else chs.get(item_id)
    if not item:
        return {"ok": False, "error": "상품을 찾지 못했어요."}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    url = str(item.get("url") or "")
    old = [u for u in (ex.get("images") or []) if isinstance(u, str)]
    before = {"images": len(old), "usable": _usable(old), "options": len(ex.get("options") or []),
              "detail": len(ex.get("detail_images") or [])}
    res = (fetch or UniversalScraper().fetch)(url)
    ap = (getattr(res, "raw_meta", None) or {}).get("amazon_pdp") or {}
    new = [u for u in (getattr(res, "images", None) or []) if isinstance(u, str)]
    man = ex.get("manual_fields") if isinstance(ex.get("manual_fields"), dict) else {}
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "before": before}
    if not ap:
        rec.update(ok=False, reason="아마존 화면을 읽지 못했어요(막힘·빈 화면) — 사진은 그대로 뒀어요.")
    elif not new:
        rec.update(ok=False, reason="화면은 열렸는데 사진 데이터가 없어요 — 사진은 그대로 뒀어요.")
    else:
        rec["ok"] = True
    row = {}
    if new and "images" not in man:
        ex["images"] = new
        ex.setdefault("field_sources", {})["images"] = "amazon_pdp"
        row["image_url"] = new[0]
    opts = [{"name": o["name"], "values": o["values"]} for o in (ap.get("options") or []) if o.get("values")]
    if opts and "options" not in man:
        ex["options"] = opts
    if ap.get("detail_images") and "detail_images" not in man:
        ex["detail_images"] = list(ap["detail_images"])
    price = str(getattr(res, "price", "") or "")
    if price and price not in ("0", "0.0") and "price" not in man:
        ex["price"] = price
        ex["currency"] = getattr(res, "currency", "") or ex.get("currency", "")
        row.update(price=price, currency=ex["currency"])
    desc = str(getattr(res, "description", "") or "").strip()
    if desc and not str(ex.get("description") or "").strip():
        ex["description"] = desc
    var = ap.get("variants") if isinstance(ap.get("variants"), dict) else {}
    if var.get("values_by_asin"):
        ex["amazon_variants"] = var
    cur = [u for u in (ex.get("images") or []) if isinstance(u, str)]
    rec["after"] = {"images": len(cur), "usable": _usable(cur), "options": len(ex.get("options") or []),
                    "detail": len(ex.get("detail_images") or []), "source": ap.get("image_source", ""),
                    "price_source": ap.get("price_source", "")}
    ex["amazon_refetch"] = rec
    if rec["ok"]:
        ex["enrich_state"] = "done"
        ex.pop("enrich_rerun", None)
    ok = bool(chs.update(item_id, seller_ids=seller_ids or {str(item.get("seller_id") or "")},
                         extra_json=json.dumps(ex, ensure_ascii=False), **row))
    logger.info("[아마존 다시 가져오기] item=%s ok=%s 전=%s 후=%s 저장=%s", item_id, rec["ok"], before, rec["after"], ok)
    if ok and ex.get("amazon_variants") and fill_children:
        rec["sku_fill"] = fill_skus(item_id, seller_ids, fetch_html=fetch_html)
    return {"ok": ok and rec["ok"], "saved": ok, **rec}


def fill_skus(item_id: str, seller_ids: Optional[set] = None, *, fetch_html=None, gap: float = 1.2, sleep=None) -> Dict:
    """오너 11-26 오후 ① — 옵션 조합마다 자식 ASIN 화면을 열어 가격을 읽고 **값이 있는 조합만** SKU로(지어내기 0).
    못 읽은 조합은 `sku_missing`에 사유째 — 카드가 「가격 없음 n개 — 빼고 등록」을 한 번에 묻는다. 셀러가 고친 옵션·SKU는 덮지 않는다."""
    from src.collectors.amazon_pdp import child_skus
    from src.collectors.universal_scraper import _fetch_html
    from src.seller_console import collect_history_store as chs
    item = chs.get(item_id, seller_ids=seller_ids) if seller_ids else chs.get(item_id)
    if not item:
        return {"ok": False, "error": "상품을 찾지 못했어요."}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    var = ex.get("amazon_variants") if isinstance(ex.get("amazon_variants"), dict) else {}
    man = ex.get("manual_fields") if isinstance(ex.get("manual_fields"), dict) else {}
    if not var.get("values_by_asin"):
        return {"ok": False, "error": "옵션 조합 표가 없어요."}
    if "sku" in man or "options" in man:
        return {"ok": False, "error": "셀러가 옵션을 직접 고친 상품이라 덮지 않아요."}
    r = child_skus(var, fetch_html or _fetch_html, gap=gap, sleep=sleep)
    ex["skus"] = r["skus"]
    ex["sku_missing"] = r["missing"]
    ex.pop("sku_missing_ack", None)
    ex["sku_fill"] = {"state": "done", "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "priced": len(r["skus"]), "missing": len(r["missing"]), "read": r["read"], "capped": r["capped"]}
    ex.setdefault("field_sources", {})["sku"] = "amazon_child"
    ok = bool(chs.update(item_id, seller_ids=seller_ids or {str(item.get("seller_id") or "")}, extra_json=json.dumps(ex, ensure_ascii=False)))
    logger.info("[아마존 옵션별 가격] item=%s 가격 %d · 없음 %d · 읽음 %d · 상한 %d · 저장=%s",
                item_id, len(r["skus"]), len(r["missing"]), r["read"], r["capped"], ok)
    return {"ok": ok, **ex["sku_fill"]}
