"""Y11-S(오너 2026-10-16 07:46) — 이미 올라간 네이버 상품의 **상품명만** 고친다(중괄호 묶음 규칙).

실측: 셰고가 13813465384·고코스모스 13813465493 상품명이 「[해외직구] VRSUK{비즈니스 시리즈} 심플 리클라이너 …」.
Y11-D 괄호 규칙이 쿠팡명에만 들어가 있었다. 새 등록은 `ko_polish.unbrace_title`이 막고, 이미 올라간 것은 여기서
`GET origin-products/{원상품번호}` → 이름만 바꿔 → `PUT`(다른 칸은 조회한 값 그대로 — `NaverSmartStoreUploader.update_name`).

- 지금 이름에 중괄호가 없으면 보내지 않는다(같은 이름 — `unchanged`).
- 결과(전·후 이름·네이버 응답 원문)는 등록 기록 `uploaded[].name_fix`에 남긴다 — 보고·팝업이 그걸 읽는다.
- 마켓 상태 팝업이 지금 이름에서 중괄호를 보면 **한 번** 자동으로 부른다(같은 상품·스토어는 기록이 있으면 다시 안 부름).
  「상품명 다시 보내기」 버튼은 언제든 다시 부른다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def has_brace(name: str) -> bool:
    s = str(name or "")
    return "{" in s or "}" in s or "｛" in s or "｝" in s


def _uploader(account: str):
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    return NaverSmartStoreUploader(account=account or None)


def fix_name(item: dict, market: str, *, save: Optional[Callable[[dict], None]] = None,
             make_up: Optional[Callable[[str], object]] = None) -> dict:
    """그 스토어 등록본의 상품명에서 중괄호 묶음을 정리해 보낸다 → `{ok, unchanged, before, after, raw, error, at}`."""
    from src.collectors.ko_polish import unbrace_title
    from src.seller_console import listing_status as MS
    make_up = make_up or _uploader
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    rec = next((r for r in MS.records(ex) if r["market"] == market), None)
    now = datetime.now(timezone.utc).isoformat()
    if not rec or not rec.get("product_id"):
        return {"ok": False, "error": "이 스토어에 등록한 기록(원상품번호)이 없어요.", "at": now}
    try:
        res = make_up(rec["account"]).update_name(rec["product_id"], unbrace_title)
    except Exception as exc:                                     # noqa: BLE001 — 원문 그대로
        res = {"success": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    out = {"ok": bool(res.get("success")), "unchanged": bool(res.get("unchanged")), "at": now,
           "before": str(res.get("before_name") or ""), "after": str(res.get("after_name") or ""),
           "status_type": str(res.get("status_type") or ""), "error": str(res.get("error") or "")[:600],
           "raw": (json.dumps(res.get("raw"), ensure_ascii=False) if isinstance(res.get("raw"), (dict, list))
                   else str(res.get("raw") or ""))[:1500]}
    logger.info("[네이버 상품명] item=%s %s 원상품=%s ok=%s 그대로=%s 응답=%s", str(item.get("id") or "")[:8], market,
                rec["product_id"], out["ok"], out["unchanged"], (out["error"] or out["raw"])[:300])
    for u in ex.get("uploaded") or []:
        if isinstance(u, dict) and u.get("market") == market and str(u.get("product_id") or "") == str(rec["product_id"]):
            u["name_fix"] = out
    if save:
        save(ex)
    return out


def line(rec_or_upload: dict) -> str:
    """팝업 한 줄 — 「상품명 고침: 전 → 후」 / 「상품명 고치기 실패 — 사유」."""
    nf = (rec_or_upload or {}).get("name_fix") or {}
    if not nf:
        return ""
    if nf.get("ok") and nf.get("unchanged"):
        return "상품명: 중괄호 없음 — 고칠 것 없음"
    if nf.get("ok"):
        return f"상품명 고침: {nf.get('before') or '?'} → {nf.get('after') or '?'}"
    return f"상품명 고치기 실패 — {nf.get('error') or '사유 미상'}"
