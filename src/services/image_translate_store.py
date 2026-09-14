"""src/services/image_translate_store.py — 번역 이미지 저장·장부 (D1).

## 규칙 셋 (D0에서 정한 것)

1. **원본 `images`는 영구 보존 — 절대 덮어쓰지 않는다.** 번역이 마음에 안 들 때 되돌릴 데가
   있어야 하고, 공급사를 바꿔 다시 돌릴 때도 원본이 유일한 진본이다.
2. 번역본은 `images_ko`에 **장별 상태**로. 전부 아니면 전부가 아니다 — 장 단위다.
3. 못 한 장은 **왜 못 했는지**까지 적는다(`failed`/`skipped` + 사유).

## 번역 이미지를 어디에 두나

공급사는 **base64 JPG**를 돌려준다. 그걸 그대로 `extra_json`에 넣으면 행이 수백 KB로 붓는다 —
DB에 이미지를 넣는 셈이다. 그래서 바이트는 밖에 두고, 행에는 **가리키는 값만** 남긴다.

  · CDN(Cloudinary)이 설정돼 있으면 거기에(`stored_by="cdn"`).
  · 아니면 **파일**로 두고 우리 라우트로 서빙한다(`stored_by="file"`).

> **파일은 Render에서 배포마다 사라진다.** 그래서 `stored_by`를 행에 적어 둔다 —
> 나중에 「왜 이미지가 안 보이지」를 추측으로 풀지 않게. D2(등록)에서 영속이 필요해지면
> 그때 CDN을 필수로 올린다. 지금(D1=수동 번역·검토)은 파일로도 일이 된다.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

IMAGES_KO_DIR = Path(os.getenv("IMAGES_KO_DIR", "data/images_ko"))
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


def store_translated(item_id: str, idx: int, image_b64: str) -> dict:
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
    try:
        d = IMAGES_KO_DIR / str(item_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{idx}.jpg").write_bytes(raw)
        return {"url": f"/seller/collect/image-ko/{item_id}/{idx}", "stored_by": "file",
                "bytes": len(raw),
                "note": "파일 저장 — 배포 시 사라집니다(CDN 미설정)"}
    except Exception as exc:
        logger.warning("[이미지번역] 파일 저장 실패: %s", exc)
        return {"url": "", "stored_by": "", "bytes": len(raw), "note": f"저장 실패: {exc}"}


def read_translated(item_id: str, idx: int) -> bytes:
    """파일로 둔 번역 이미지 읽기. 없으면 빈 바이트."""
    if not (_SAFE.match(str(item_id)) and str(idx).isdigit()):
        return b""
    p = IMAGES_KO_DIR / str(item_id) / f"{int(idx)}.jpg"
    try:
        return p.read_bytes() if p.is_file() else b""
    except Exception:
        return b""


# ---------------------------------------------------------------------------
# 장별 결과 → `images_ko`
# ---------------------------------------------------------------------------

def build_entry(idx: int, result: dict, *, item_id: str = "", seller_id: str = "") -> dict:
    """공급사 결과 1장 → `images_ko` 한 줄. **이 모양을 만드는 자리는 여기 하나다.**

    `status`: `done`(번역본이 실제로 놓였다) / `failed`(사유 있음) / `skipped`(할 게 없었다)
    `warn`: 번역문에 걸린 금칙어 목록 — **번역은 저장하고** 등록 때 경고한다(오너 지시).
    """
    entry = {"idx": int(idx), "at": _now(), "vendor": result.get("vendor", ""),
             "ms": int(result.get("ms") or 0)}

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
    placed = store_translated(item_id, int(idx), result.get("image_b64") or "")
    entry.update({
        "status": "done" if placed.get("url") else "failed",
        "url": placed.get("url", ""),
        "stored_by": placed.get("stored_by", ""),
        "bytes": placed.get("bytes", 0),
        "target_text": target_text[:2000],
        "source_text": str(result.get("source_text") or "")[:2000],
        "lines": len(result.get("lines") or []),
        "warn": banned_in(target_text, seller_id),
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
    """화면용 한 줄 요약 — `{done, failed, skipped, warn, total}`."""
    rows = (extra or {}).get("images_ko") or []
    out = {"done": 0, "failed": 0, "skipped": 0, "warn": 0, "total": len(rows)}
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
