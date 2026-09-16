"""src/services/image_translate_store.py — 번역 이미지 저장·장부 (D1).

## 규칙 셋 (D0에서 정한 것)

1. **원본 `images`는 영구 보존 — 절대 덮어쓰지 않는다.** 번역이 마음에 안 들 때 되돌릴 데가
   있어야 하고, 공급사를 바꿔 다시 돌릴 때도 원본이 유일한 진본이다.
2. 번역본은 `images_ko`에 **장별 상태**로. 전부 아니면 전부가 아니다 — 장 단위다.
3. 못 한 장은 **왜 못 했는지**까지 적는다(`failed`/`skipped` + 사유).

## 번역 이미지를 어디에 두나

공급사는 **base64 JPG**를 돌려준다. 그걸 그대로 `extra_json`에 넣으면 행이 수백 KB로 붓는다 —
그 행은 목록·서랍·폴러가 매번 통째로 읽는다. 그래서 바이트는 **별도 자리**에 두고,
행에는 **가리키는 URL만** 남긴다.

갈래는 **셋뿐**이다:

  · `cdn` — Cloudinary가 붙어 있다(영속·외부 URL). 등록에 그대로 쓴다.
           env는 **기존 것 그대로**: `CLOUDINARY_CLOUD_NAME`·`CLOUDINARY_API_KEY`·
           `CLOUDINARY_API_SECRET`(+선택 `CLOUDINARY_FOLDER`). 새 이름을 만들지 않는다 —
           두 벌이 되면 한쪽만 채워 두고 「연결했는데 왜 안 되지」를 겪는다.
  · `db`  — `image_ko_blobs`(영속·우리 라우트로 서빙). CDN 붙기 전의 기본값.
  · `""`  — 못 뒀다. **가짜 URL을 만들지 않는다.**

> **로컬 파일은 없앴다(D2).** D1에서 `data/images_ko/<item>/<idx>.jpg`에 뒀는데,
> Render는 배포마다 그 디스크를 버린다 — 볼트 [[Render tmp 휘발]]에 이미 적힌 지뢰를
> 「CDN 붙기 전 임시」라는 이유로 다시 밟았다. **장당 과금으로 만든 결과물이 배포에 사라지면
> 그 돈을 다시 쓴다.** 배포에 사라지는 자리를 「저장했다」고 부르지 않는다.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 바이트 두기
# ---------------------------------------------------------------------------

def _store_via_cdn(raw: bytes) -> str:
    """CDN에 올리고 URL. 미설정·실패면 빈 문자열(가짜 URL을 만들지 않는다)."""
    try:
        from src.media.image_pipeline import _upload_to_cdn      # noqa: SLF001
    except Exception:
        return ""
    try:
        return str(_upload_to_cdn(raw) or "")
    except Exception as exc:
        logger.warning("[이미지번역] CDN 업로드 실패: %s", exc)
        return ""


def storage_backend() -> str:
    """지금 번역본이 어디에 놓이는가 — `"cdn"` / `"db"` / `""`(둘 다 없음).

    화면이 「저장소 미연결」 배너를 **사실일 때만** 띄우려면 이 값을 물어야 한다.
    """
    try:
        from src.media.image_pipeline import _cloudinary_configured, _CDN_UPLOAD_ENABLED
        if _CDN_UPLOAD_ENABLED and _cloudinary_configured():
            return "cdn"
    except Exception:
        pass
    try:
        from src.db import pg
        if pg.pg_enabled():
            return "db"
    except Exception:
        pass
    return ""


def store_translated(item_id: str, idx: int, image_b64: str, *,
                     seller_id: str = "", kind: str = "gallery") -> dict:
    """번역 이미지를 두고 `{url, stored_by, bytes}`. 못 두면 `stored_by=""`."""
    try:
        raw = base64.b64decode(image_b64 or "", validate=False)
    except Exception:
        return {"url": "", "stored_by": "", "bytes": 0, "note": "base64 해독 실패"}
    if not raw:
        return {"url": "", "stored_by": "", "bytes": 0, "note": "빈 이미지"}

    url = _store_via_cdn(raw)
    if url:
        return {"url": url, "stored_by": "cdn", "bytes": len(raw), "note": ""}

    if not (_SAFE.match(str(item_id)) and isinstance(idx, int) and 0 <= idx < 1000):
        return {"url": "", "stored_by": "", "bytes": len(raw), "note": "식별자 형식 오류"}

    # D2: 로컬 파일이 아니라 **DB**. 배포에 사라지는 자리를 「저장했다」고 부르지 않는다.
    from src.db import image_ko_blobs_pg as blobs
    if blobs.put(item_id, idx, raw, seller_id=seller_id, kind=kind):
        suffix = "" if kind == "gallery" else f"?kind={kind}"
        return {"url": f"/seller/collect/image-ko/{item_id}/{idx}{suffix}",
                "stored_by": "db", "bytes": len(raw),
                "note": "" if _durable() else "임시 보관 — 저장소가 붙기 전까지 유지되지 않습니다"}
    return {"url": "", "stored_by": "", "bytes": len(raw), "note": "번역본을 저장하지 못했습니다"}


def _durable() -> bool:
    """이 환경에서 번역본이 **배포를 넘겨 살아남는가**."""
    return storage_backend() in ("cdn", "db")


def read_translated(item_id: str, idx: int, *, kind: str = "gallery") -> bytes:
    """둔 번역 이미지 읽기. 없으면 빈 바이트."""
    if not (_SAFE.match(str(item_id)) and str(idx).isdigit()):
        return b""
    from src.db import image_ko_blobs_pg as blobs
    raw, _ct = blobs.get(item_id, int(idx), kind=kind)
    return raw


# ---------------------------------------------------------------------------
# 장별 결과 → `images_ko`
# ---------------------------------------------------------------------------

# 글자가 빽빽한 장은 번역 후 **줄바꿈이 원본과 달라질 수 있다** — 사람이 한 번 보게 표시한다.
#   기준은 번역된 줄 수. 임의 점수가 아니라 공급사가 돌려준 `TransDetails` 길이 그대로다.
DENSE_TEXT_LINES = 8


def build_entry(idx: int, result: dict, *, item_id: str = "", seller_id: str = "",
                kind: str = "gallery") -> dict:
    """공급사 결과 1장 → `images_ko` 한 줄. **이 모양을 만드는 자리는 여기 하나다.**

    `status`: `done`(번역본이 실제로 놓였다) / `failed`(사유 있음) / `skipped`(할 게 없었다)
    `warn`: 번역문에 걸린 금칙어 목록 — **번역은 저장하고** 등록 때 경고한다(오너 지시).
    `use`: 등록에 **번역본을 쓸지**. 성공한 장은 기본 ON(그러려고 번역했다) — 사람이 끌 수 있다.
    `dense`: 글자가 빽빽했다 → 레이아웃 확인 권고.
    """
    entry = {"idx": int(idx), "at": _now(), "vendor": result.get("vendor", ""),
             "kind": str(kind), "ms": int(result.get("ms") or 0)}

    if not result.get("ok"):
        entry.update({
            "status": "failed",
            "error_class": str(result.get("error_class") or ""),
            "error_code": str(result.get("error_code") or ""),
            "error_message": str(result.get("error_message") or "")[:300],
            "hint": str(result.get("hint") or ""),
        })
        return entry

    target_text = str(result.get("target_text") or "")
    placed = store_translated(item_id, int(idx), result.get("image_b64") or "",
                              seller_id=seller_id, kind=kind)
    n_lines = len(result.get("lines") or [])
    entry.update({
        "status": "done" if placed.get("url") else "failed",
        "url": placed.get("url", ""),
        "stored_by": placed.get("stored_by", ""),
        "bytes": placed.get("bytes", 0),
        "target_text": target_text[:2000],
        "source_text": str(result.get("source_text") or "")[:2000],
        "lines": n_lines,
        "warn": banned_in(target_text, seller_id),
        # 성공한 장은 **기본으로 쓴다** — 그러려고 번역했으니까. 사람이 장별로 끌 수 있다.
        "use": bool(placed.get("url")),
        "dense": n_lines >= DENSE_TEXT_LINES,
    })
    if not placed.get("url"):
        entry.update({"error_class": "NotStored", "error_code": "",
                      "error_message": placed.get("note") or "번역본을 저장하지 못했습니다"})
    elif placed.get("note"):
        entry["store_note"] = placed["note"]
    return entry


def banned_in(text: str, seller_id: str = "") -> list:
    """번역문에 걸린 금칙어. 없으면 빈 목록.

    D0-4 ③: `爆款`·`必备` 류가 「최고」·「필수」로 **직역되면 쿠팡 금칙어**다.
    번역은 저장하되(사람이 보고 고치게) 경고를 남긴다 — 조용히 지우면 무엇이 바뀌었는지 모른다.
    """
    if not str(text or "").strip():
        return []
    try:
        from src.seller_console.word_rules import apply_rules
        return list(apply_rules(text, seller_id or None).get("removed") or [])
    except Exception as exc:
        logger.warning("[이미지번역] 금칙어 검사 실패(경고 없음으로 계속): %s", exc)
        return []


def merge_images_ko(extra: dict, entries: list) -> list:
    """기존 `images_ko`에 새 결과를 **장 번호 기준으로** 덮어쓴다(나머지는 보존).

    한 번에 몇 장만 번역해도 앞서 번역한 장이 사라지지 않아야 한다.
    """
    cur = extra.get("images_ko") if isinstance(extra, dict) else None
    by_idx = {int(e.get("idx", -1)): e for e in (cur or []) if isinstance(e, dict)}
    for e in entries or []:
        by_idx[int(e.get("idx", -1))] = e
    by_idx.pop(-1, None)
    return [by_idx[k] for k in sorted(by_idx)]


def summarize(extra: dict) -> dict:
    """화면용 한 줄 요약 — `{done, failed, skipped, queued, warn, total}`.

    F25: `queued`(접수됐지만 아직 안 보낸 장)를 **따로 센다.** 없으면 화면이
    「아직 안 된 장」을 실패로 읽거나, 다 된 줄 알고 폴링을 멈춘다.
    """
    rows = (extra or {}).get("images_ko") or []
    out = {"done": 0, "failed": 0, "skipped": 0, "queued": 0, "warn": 0, "total": len(rows)}
    for r in rows:
        if not isinstance(r, dict):
            continue
        out[str(r.get("status") or "failed")] = out.get(str(r.get("status") or "failed"), 0) + 1
        if r.get("warn"):
            out["warn"] += 1
    return out


# ---------------------------------------------------------------------------
# 비용 장부
# ---------------------------------------------------------------------------

def record_usage(seller_id: str, entries: list, *, vendor: str = "tencent") -> bool:
    """호출 1회분(장 여러 개)을 장부에 적는다. 실패해도 번역을 막지 않는다.

    **카운터를 따로 두지 않는다** — 이 행들을 더해서 집계한다.
    카운터와 실제가 갈리면 어느 쪽이 맞는지 알 수 없게 된다(D0-6).
    """
    try:
        from src.db import image_translate_usage_pg as usage
        pages = len(entries or [])
        ok = sum(1 for e in entries or [] if e.get("status") == "done")
        ms = sum(int(e.get("ms") or 0) for e in entries or [])
        return usage.add(seller_id, vendor=vendor, pages=pages, ok_pages=ok, ms=ms)
    except Exception as exc:
        logger.warning("[이미지번역] 사용량 기록 실패(계속): %s", exc)
        return False


def load_extra(row: dict) -> dict:
    try:
        return json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# D2 — 등록에 실제로 나갈 배열
# ---------------------------------------------------------------------------

def effective_images(extra: dict, *, kind: str = "gallery", originals=None) -> list:
    """등록에 **실제로 나갈** 이미지 배열. 원본은 건드리지 않는다.

    규칙은 하나다: 그 장의 번역본이 **놓여 있고**(`status=done` + `url`) **쓰기로 돼 있으면**
    (`use`) 번역본, 아니면 원본. 순서와 장수는 원본 그대로다 —
    번역이 안 된 장을 빼 버리면 상품에 구멍이 난다.

    **이 배열을 만드는 자리는 여기 하나다.** 화면과 등록 파이프가 각자 계산하면
    「서랍에선 한국어인데 마켓엔 중국어」가 된다 — 그게 D2가 고치러 온 바로 그 증상이다.
    """
    ex = extra if isinstance(extra, dict) else {}
    src_key = "images" if kind == "gallery" else "detail_images"
    ko_key = "images_ko" if kind == "gallery" else "detail_images_ko"
    # `originals`를 주면 **그걸** 기준으로 매핑한다 — 사람이 서랍에서 방금 고친 목록이
    #   저장된 목록과 다를 수 있고, 등록에는 **지금 화면의 것**이 나가야 한다.
    if originals is None:
        originals = [u for u in (ex.get(src_key) or []) if u]
    else:
        originals = [u for u in (originals or []) if u]
    by_idx = {int(e.get("idx", -1)): e for e in (ex.get(ko_key) or []) if isinstance(e, dict)}

    out = []
    for i, orig in enumerate(originals):
        e = by_idx.get(i) or {}
        if e.get("use") and e.get("status") == "done" and e.get("url"):
            out.append(e["url"])
        else:
            out.append(orig)
    return out


def effective_plan(extra: dict, *, kind: str = "gallery", originals=None) -> list:
    """화면용 — 장마다 `{idx, url, source, translated_url, use, warn, dense, status}`.

    썸네일 탭이 **등록에 나갈 목록 그대로**를 보여 주려면 「이 장이 원본인지 번역본인지」를
    알아야 한다. 같은 판단을 화면이 다시 하지 않게 여기서 함께 낸다.
    """
    ex = extra if isinstance(extra, dict) else {}
    src_key = "images" if kind == "gallery" else "detail_images"
    ko_key = "images_ko" if kind == "gallery" else "detail_images_ko"
    if originals is None:
        originals = [u for u in (ex.get(src_key) or []) if u]
    else:
        originals = [u for u in (originals or []) if u]
    by_idx = {int(e.get("idx", -1)): e for e in (ex.get(ko_key) or []) if isinstance(e, dict)}

    plan = []
    for i, orig in enumerate(originals):
        e = by_idx.get(i) or {}
        usable = bool(e.get("status") == "done" and e.get("url"))
        use = bool(usable and e.get("use"))
        plan.append({
            "idx": i, "original": orig, "kind": kind,
            "translated_url": e.get("url", "") if usable else "",
            "url": (e.get("url") if use else orig),
            "source": "translated" if use else "original",
            "translatable": usable,          # 번역본이 있다(토글을 켤 수 있다)
            "use": use,
            "status": e.get("status", ""),
            "warn": list(e.get("warn") or []),
            "dense": bool(e.get("dense")),
            "stored_by": e.get("stored_by", ""),
        })
    return plan


def set_use_flags(extra: dict, flags: dict, *, kind: str = "gallery") -> list:
    """장별 「번역본 사용」을 바꾼다. `flags` = `{idx: bool}`. 갱신된 `images_ko`를 돌려준다.

    **번역본이 없는 장은 켜지지 않는다.** 켜 봐야 `effective_images`가 원본을 쓰므로,
    화면만 켜진 척하면 사람이 「켰는데 왜 원본이지」를 겪는다.
    """
    ko_key = "images_ko" if kind == "gallery" else "detail_images_ko"
    rows = [dict(e) for e in ((extra or {}).get(ko_key) or []) if isinstance(e, dict)]
    want = {int(k): bool(v) for k, v in (flags or {}).items()}
    for e in rows:
        i = int(e.get("idx", -1))
        if i in want:
            e["use"] = bool(want[i] and e.get("status") == "done" and e.get("url"))
    return rows


def effective_summary(extra: dict) -> dict:
    """등록 직전에 사람이 봐야 할 것 — `{translated, original, warn_idx, dense_idx}`.

    `warn_idx`가 비어 있지 않으면 **등록 전에 확인 문구**를 띄운다(오너 지시 D2-3).
    """
    out = {"translated": 0, "original": 0, "warn_idx": [], "dense_idx": []}
    for kind in ("gallery", "detail"):
        for p in effective_plan(extra, kind=kind):
            out["translated" if p["source"] == "translated" else "original"] += 1
            if p["source"] == "translated" and p["warn"]:
                out["warn_idx"].append({"kind": kind, "idx": p["idx"], "warn": p["warn"]})
            if p["source"] == "translated" and p["dense"]:
                out["dense_idx"].append({"kind": kind, "idx": p["idx"]})
    return out
