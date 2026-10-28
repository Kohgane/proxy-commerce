"""순찰 148 H-rep(감독 2026-10-28 · 오너 10-26 21:18 「제품 하나하나 수정해야 하느냐」) — 쿠팡 대표 후보가 **전부** 글자 장일 때
사람에게 넘기지 않고 자동으로 정리한다.

1. 후보 중 글자 상자 수 최소 장(동률이면 앞 번호)을 고른다. 0상자 장이 하나라도 있으면 돌지 않는다(`pick_rep`가 먼저).
2. 그 장의 글자 상자를 전부 픽셀 지우기(`image_edit.apply` erase — 위험 게이트 「빼고 등록」과 같은 길) → 갤러리 그 idx 엔트리의
   **편집 버전**으로만 남긴다. 나가는 버전 선택은 원래대로 돌려 둔다 — 네이버·상세·다른 마켓은 원본/번역본 그대로(수집 원본 불변).
3. 정리본을 텐센트 OCR로 다시 재서 0상자면 `rep_image`=그 장(원본 주소) · `rep_auto_clean{idx, orig, url, version, boxes_before,
   boxes_after, at, by, ok}` · `rep_need_change` 해제. 쿠팡 등록·사전검증만 대표 자리에 `url`을 쓴다(`coupang_rep_images`).
   0상자가 안 나오면(로고·큰 글자) 보류 그대로 + 사유 「자동 정리 시도: N상자 → M상자」.
4. 하루 상한 `REP_AUTO_CLEAN_DAILY_CAP`(50). 상품마다 한 번만(기록이 있으면 다시 돌지 않는다 — 사람이 대표를 바꾸면 그때 다시).
Y11-N 「다듬기는 지우지 않는다」는 상세·갤러리 **번역 다듬기** 규칙 — 이 함수는 그 길을 안 탄다(별도 함수 · 쿠팡 대표 전용).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

KIND = "gallery"
MAX_CANDIDATES = 6


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv("REP_AUTO_CLEAN_DAILY_CAP", "50") or 0))
    except ValueError:
        return 50


def _day_key() -> str:
    from datetime import timedelta
    return "rep_auto_clean:day:" + (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y%m%d")


def candidates(extra: dict) -> List[int]:
    """대표 후보 장 — 갤러리 원본 앞에서부터(위험 게이트가 뺀 장 제외) 최대 `MAX_CANDIDATES`장."""
    originals = [u for u in (extra or {}).get("images") or [] if isinstance(u, str) and u.strip()]
    excluded = {int(e.get("idx", -1)) for e in (extra or {}).get("images_ko") or [] if isinstance(e, dict) and e.get("risk_exclude")}
    return [i for i in range(len(originals)) if i not in excluded][:MAX_CANDIDATES]


def pick_min(counts: Dict[int, object]) -> int:
    """상자 수 최소 장(동률 앞 번호) — 재지 못한 장(None)은 빼고. 0상자 장이 있거나 잴 수 있는 장이 없으면 -1."""
    known = {int(i): int(n) for i, n in counts.items() if isinstance(n, int)}
    if not known or any(n == 0 for n in known.values()):
        return -1
    return min(known, key=lambda i: (known[i], i))


def valid(extra: dict) -> Optional[dict]:
    """지금 쿠팡 대표 자리에 쓸 정리본(없으면 None) — 성공 기록 · 그 장이 지금 대표(`rep_image`) · 그 편집 버전이 아직 있을 때만."""
    rc = (extra or {}).get("rep_auto_clean")
    if not isinstance(rc, dict) or not rc.get("ok") or not rc.get("url"):
        return None
    if str((extra or {}).get("rep_image") or "") != str(rc.get("orig") or ""):
        return None
    from src.services import image_edit as IE
    if not IE._version(extra, KIND, int(rc.get("idx", -1)), str(rc.get("version") or "")):
        return None
    return rc


def coupang_rep_images(pd: dict) -> List[str]:
    """쿠팡이 보낼 이미지 목록 — 대표 자리(첫 장)만 정리본으로. 정리본이 없으면 그대로(새 목록)."""
    imgs = [u for u in (pd.get("images_effective") or pd.get("images") or []) if isinstance(u, str) and u.strip()]
    rc = pd.get("rep_auto_clean") if isinstance(pd.get("rep_auto_clean"), dict) else None
    if not imgs or not rc or not rc.get("ok") or not rc.get("url") or not pd.get("rep_auto_clean_valid"):
        return imgs
    return [str(rc["url"])] + imgs[1:]


def apply_to_coupang(payload: dict) -> dict:
    """등록 몸통(쿠팡) — 대표 자리를 정리본으로(`images`·`images_effective`·`thumbnail`). 다른 마켓은 부르지 않는다."""
    imgs = coupang_rep_images(payload)
    if imgs and imgs[0] != (payload.get("images_effective") or payload.get("images") or [None])[0]:
        payload = dict(payload, images=imgs, images_effective=list(imgs), thumbnail=imgs[0])
    return payload


def clean(extra: dict, counts: Dict[int, object], *, by: str = "auto",
          ocr: Optional[Callable[[str], Tuple[Optional[int], str]]] = None) -> Dict:
    """대표 후보가 전부 글자 장일 때 한 번 — `{ok, tried, idx, boxes_before, boxes_after, why}`. 저장은 부른 쪽(extra를 고친다)."""
    out: Dict = {"ok": False, "tried": False, "idx": -1, "why": ""}
    originals = [u for u in (extra or {}).get("images") or [] if isinstance(u, str) and u.strip()]
    idx = pick_min(counts)
    if idx < 0 or idx >= len(originals):
        out["why"] = "0상자 장이 있거나 잴 수 있는 후보가 없음"
        return out
    prev = extra.get("rep_auto_clean") if isinstance(extra.get("rep_auto_clean"), dict) else None
    if prev and prev.get("orig") == originals[idx]:
        out["why"] = "이미 자동 정리를 해 본 장"
        out.update(idx=idx, boxes_before=prev.get("boxes_before"), boxes_after=prev.get("boxes_after"))
        return out
    cap = daily_cap()
    from src.db import image_translate_queue_pg as q
    took, today = q.take_start(_day_key(), cap) if cap else (False, 0)
    if not took:
        out["why"] = f"오늘 대표 자동 정리 한도({cap}회)를 다 썼어요"
        return out
    from src.services import image_edit as IE
    out.update(tried=True, idx=idx, boxes_before=int(counts[idx]))
    before_key = IE.current_key(IE._entry(extra, KIND, idx))
    try:
        p = IE.plan(extra, KIND, idx)
        ids = [b["id"] for b in p.get("boxes") or []]
        res = IE.apply(extra, KIND, idx, [{"id": i, "action": "erase"} for i in ids], by="rep_auto") if ids else \
            {"ok": False, "error": p.get("why") or "지울 글자 상자를 못 찾음"}
    except Exception as exc:                                       # noqa: BLE001
        res = {"ok": False, "error": type(exc).__name__}
    if res.get("ok"):
        IE.select(extra, KIND, idx, before_key)                    # 나가는 버전은 그대로 — 정리본은 쿠팡 대표 자리에만
    url = str(res.get("url") or "") if res.get("ok") else ""
    after, why = (None, str(res.get("error") or "지우기 실패")[:80]) if not url else (ocr or _ocr)(url)
    now = datetime.now(timezone.utc).isoformat()
    rec = {"idx": idx, "orig": originals[idx], "url": url, "version": str(res.get("version") or ""),
           "boxes_before": int(counts[idx]), "boxes_after": after, "at": now, "by": by, "ok": after == 0}
    if not url:
        rec["why"] = why
    extra["rep_auto_clean"] = rec
    if after == 0:
        extra["rep_image"] = originals[idx]
        extra.pop("rep_need_change", None)
        out.update(ok=True, boxes_after=0)
        logger.info("[쿠팡 대표 자동 정리] %d번 %d상자 → 0 — 대표로", idx + 1, rec["boxes_before"])
        return out
    note = f"자동 정리 시도: {idx + 1}번 {rec['boxes_before']}상자 → " + (f"{after}상자" if isinstance(after, int) else f"못 잼({why})")
    base = str(extra.get("rep_need_change") or "").split(" · 자동 정리 시도")[0]
    extra["rep_need_change"] = (base + " · " if base else "") + note
    out.update(boxes_after=after, why=note)
    return out


def _ocr(url: str):
    from src.services.oneshot_ops import _ocr_box_count
    return _ocr_box_count(url)


def measure(extra: dict, idxs: List[int], ocr: Optional[Callable] = None) -> Dict[int, object]:
    """후보 장마다 원본 OCR 상자 수(재지 못하면 None)."""
    originals = [u for u in (extra or {}).get("images") or [] if isinstance(u, str) and u.strip()]
    f = ocr or _ocr
    out: Dict[int, object] = {}
    for i in idxs:
        if 0 <= i < len(originals):
            n, _why = f(originals[i])
            out[i] = n
    return out
