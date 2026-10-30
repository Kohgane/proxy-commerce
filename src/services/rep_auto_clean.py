"""순찰 148 H-rep(감독 2026-10-28 · 오너 10-26 21:18 「제품 하나하나 수정해야 하느냐」) — 쿠팡 대표 후보가 **전부** 글자 장일 때
사람에게 넘기지 않고 자동으로 정리한다.

H-rep2: 검토된 상품 보호 근거가 있는 후보를 상자 수 순서로 검사한다. 가장자리 crop 우선,
안 되면 TELEA + 분산/상품 픽셀 검사. 재OCR 0 및 CDN 바이트 일치 후 쿠팡 전용 버전으로만 저장.
원본/번역본/다른 마켓 선택은 불변. 근거 없음·손상·잔여 글자는 다음 후보 또는 보류.
하루 대표/사진 편집 상한을 유지하고 같은 버전+검토 근거로는 반복하지 않는다.
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
    known = {int(i): int(n) for i, n in counts.items() if type(n) is int and n >= 0}
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
    if rc.get("pipeline") == "hrep2":
        from src.services.rep_clean_edit import attempt_key
        if rc.get("attempt_key") != attempt_key(extra, int(rc["idx"])):
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
    """H-rep2: crop/guarded inpaint candidates, then publish one verified version.

    Unknown protection is a hold, never permission for legacy rectangle fill.
    Failed candidates leave outbound selection unchanged and try the next image.
    The optional URL OCR callback adds a check; it cannot bypass byte validation.
    """
    from src.services import rep_clean_edit as E
    from src.services import image_edit as IE
    from src.db import image_translate_queue_pg as q
    out = {"ok": False, "tried": False, "idx": -1, "why": "", "attempts": []}
    eligible = set(candidates(extra))
    known = {i: n for i, n in counts.items()
             if type(i) is int and i in eligible and type(n) is int and n >= 0}
    if not known or 0 in known.values():
        return dict(out, why="0상자 장이 있거나 잴 수 있는 후보가 없음")
    # Successful existing records remain untouched. Legacy failure records do
    # not prevent a newly reviewed H-rep2 attempt.
    if valid(extra) and extra["rep_auto_clean"].get("pipeline") == "hrep2" and \
            extra["rep_auto_clean"].get("attempt_key") == E.attempt_key(extra, extra["rep_auto_clean"]["idx"]):
        return dict(out, why="검증된 대표 정리본이 이미 있어요")
    originals = [u for u in extra.get("images") or [] if isinstance(u, str) and u.strip()]
    history = dict(extra.get("rep_clean_attempts") or {})
    for idx in sorted(known, key=lambda i: (known[i], i)):
        token = E.attempt_key(extra, idx)
        if history.get(str(idx)) == token:
            out["attempts"].append({"idx": idx, "why": "같은 사진과 검토 근거로 이미 시도했어요"})
            continue
        try:
            prepared = E.prepare(extra, idx)
        except Exception:
            prepared = {"ok": False, "why": "사진과 상품 보호 근거를 확인하지 못했어요"}
        if not prepared.get("ok"):
            out["attempts"].append({"idx": idx, "why": prepared.get("why") or "검토 근거 없음"})
            continue
        cap = daily_cap()
        took, _today = q.take_start(_day_key(), cap) if cap else (False, 0)
        if not took:
            out["why"] = f"오늘 대표 자동 정리 한도({cap}회)를 다 썼어요"
            break
        took_edit, _ = q.take_start(IE._day_key(), IE.daily_cap())
        if not took_edit:
            out["why"] = "오늘 사진 편집 한도를 다 썼어요"
            break
        out.update(tried=True, idx=idx, boxes_before=known[idx])
        history[str(idx)] = token
        extra["rep_clean_attempts"] = history
        try:
            result = E.render(prepared)
            if result.get("ok"):
                # Work on a copy until publication and optional URL check pass.
                import copy
                staged = copy.deepcopy(extra)
                published = E.publish(staged, idx, prepared, result)
                if not published.get("ok"):
                    result = published
                elif ocr is not None:
                    count, why = ocr(published["url"])
                    if type(count) is not int or count != 0:
                        result = {"ok": False, "boxes_after": count, "why": why or "글자가 남아 있어요"}
                if result.get("ok"):
                    # Never restore a stale choice over a user's newer choice.
                    if E.identity(extra, idx) != prepared["identity"]:
                        result = {"ok": False, "why": "처리 중 사진 버전이 바뀌었어요"}
                    else:
                        entry = IE._entry(extra, KIND, idx, create=True)
                        accepted = IE._entry(staged, KIND, idx)
                        entry["edits"] = accepted["edits"]
                        entry["vboxes"] = accepted["vboxes"]
                        extra["rep_auto_clean"] = {
                            "idx": idx, "orig": originals[idx], "url": published["url"],
                            "version": published["version"], "boxes_before": known[idx],
                            "boxes_after": 0, "at": datetime.now(timezone.utc).isoformat(),
                            "by": by, "ok": True, "pipeline": "hrep2",
                            "method": result.get("method"), "attempt_key": token}
                        extra["rep_image"] = originals[idx]
                        extra.pop("rep_need_change", None)
                        return dict(out, ok=True, boxes_after=0, method=result.get("method"))
        except Exception:
            result = {"ok": False, "why": "사진 정리 또는 재검사를 완료하지 못했어요"}
        out["boxes_after"] = result.get("boxes_after")
        out["attempts"].append({"idx": idx, "why": str(result.get("why") or "품질 검사 미통과")[:120],
                                "boxes_after": result.get("boxes_after")})
    reason = out["why"] or " · ".join(f"{a['idx'] + 1}번: {a['why']}" for a in out["attempts"])
    note = "자동 정리 시도: " + reason
    base = str(extra.get("rep_need_change") or "").split(" · 자동 정리 시도")[0]
    if base.startswith("자동 정리 시도:"):
        base = ""
    extra["rep_need_change"] = (base + " · " if base else "") + note
    if isinstance(extra.get("rep_auto_clean"), dict):
        extra["rep_auto_clean"] = dict(extra["rep_auto_clean"], ok=False, why=reason)
    return dict(out, why=reason)


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
