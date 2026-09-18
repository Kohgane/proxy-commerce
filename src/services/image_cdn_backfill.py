"""src/services/image_cdn_backfill.py — 번역본을 **외부에서 열리는 주소**로 (D2b).

## 왜

D2는 번역본을 DB에 두고 `/seller/collect/image-ko/<item>/<idx>`로 서빙했다.
그 주소는 **로그인 게이트 뒤**다 — 우리 화면엔 보이지만 **마켓 서버는 못 가져간다.**
쿠팡이 그 URL로 이미지를 받으러 오면 404를 본다(우리 세션 쿠키가 없으니까).

그래서 등록에 나가는 주소는 외부에서 열리는 것이어야 한다 → Cloudinary.

## 멱등

이미 `cdn_url`이 있으면 **다시 올리지 않는다.** 백필은 몇 번을 돌려도 같은 결과여야 한다 —
돌릴 때마다 새로 올리면 CDN에 같은 이미지가 쌓이고, 그게 비용이 된다.

바이트가 바뀌면(다시 번역) `put`이 `cdn_url`을 비우므로 그때만 다시 올라간다.

## 실패는 행별로 적는다

한 장이 실패했다고 나머지를 멈추지 않는다. 대신 **왜 실패했는지**를 그 행에 적는다
(`cdn_error`) — 나중에 「왜 이 장만 안 올라갔지」를 추측으로 풀지 않게.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# 한 번에 올릴 장수. 부팅 때 도는 것이라 길면 기동이 늦어진다.
BATCH = 50


def cdn_ready() -> bool:
    """Cloudinary가 붙어 있나. 없으면 백필은 **아무것도 하지 않는다**(할 수가 없다)."""
    try:
        from src.media.image_pipeline import _CDN_UPLOAD_ENABLED, _cloudinary_configured
        return bool(_CDN_UPLOAD_ENABLED and _cloudinary_configured())
    except Exception:
        return False


def _upload(raw: bytes) -> tuple:
    """`(url, error)` — 하나만 채워진다. 가짜 URL을 만들지 않는다.

    F31: 예전엔 `_upload_to_cdn`(반환 `str|None`)을 불러서, 여섯 가지 실패가 전부
    **「업로드가 주소를 돌려주지 않았습니다」** 한 문장이 됐다(오너 실측 ×5).
    이제 **결과 dict**를 받아 사유를 그대로 올린다 — 토글·자격·dry-run·SDK 미설치·
    SDK 예외·응답에 주소 없음(+ **응답 키 목록**)이 각각 다른 문장이다.
    """
    try:
        from src.media.image_pipeline import upload_bytes
    except Exception as exc:
        return "", f"이미지 파이프라인 미가용: {type(exc).__name__}"
    try:
        res = upload_bytes(raw)
    except Exception as exc:
        return "", f"{type(exc).__name__}: {str(exc)[:160]}"
    if res.get("ok") and res.get("secure_url"):
        return str(res["secure_url"]), ""
    # 원본 URL 되돌림 같은 「성공 같은 실패」도 여기서 실패로 떨어진다(ok가 아니면 실패다).
    #   사유는 **화면에 닿기 전에** 같은 세척기를 지난다(한 필드 두 규칙 금지).
    from src.utils.redact import scrub_infra
    return "", scrub_infra(str(res.get("error") or "업로드가 주소를 돌려주지 않았습니다"))


def _point_entry_at_cdn(item_id: str, idx: int, kind: str, url: str) -> bool:
    """초안의 그 장이 **CDN 주소를 가리키게** 한다. 원본 `images`는 건드리지 않는다.

    이걸 해야 `effective_images`가 저절로 외부 주소를 쓴다 — 계산하는 자리를 늘리지 않는다.
    """
    try:
        from src.seller_console import collect_history_store as store
        row = store.get(item_id) or {}
        if not row:
            return False
        extra = json.loads(row.get("extra_json") or "{}") or {}
        ko_key = "images_ko" if kind == "gallery" else "detail_images_ko"
        rows = extra.get(ko_key) or []
        hit = False
        for e in rows:
            if isinstance(e, dict) and int(e.get("idx", -1)) == int(idx):
                e["url"] = url
                e["stored_by"] = "cdn"
                hit = True
        if not hit:
            return False
        extra[ko_key] = rows
        return bool(store.update(item_id, extra_json=json.dumps(extra, ensure_ascii=False)))
    except Exception as exc:
        logger.warning("[CDN 백필] 초안 갱신 실패 item=%s idx=%s: %s", item_id, idx, exc)
        return False


def run(limit: int = BATCH) -> dict:
    """대기 중인 번역본을 올린다. `{ok, uploaded, failed, skipped, reason}`.

    Cloudinary가 없으면 **아무것도 하지 않고 그렇게 말한다** — 「0건 처리」가 아니라 「할 수 없다」다.
    """
    from src.db import image_ko_blobs_pg as blobs

    if not cdn_ready():
        return {"ok": False, "uploaded": 0, "failed": 0, "skipped": 0,
                "reason": "CDN 미연결 — CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET 확인"}

    pending = blobs.pending_cdn(limit=limit)
    uploaded = failed = skipped = 0
    # F31-3: 「지금 올리기」가 숫자만 돌려주면 **어느 장이 왜 실패했는지**를 또 모른다.
    #   장별 결과를 그대로 싣는다(화면이 바로 편다).
    results = []
    for p in pending:
        item_id, idx, kind = p["item_id"], int(p["idx"]), p.get("kind", "gallery")
        # 멱등: 그 사이 누가 올렸으면 건너뛴다.
        if blobs.get_cdn(item_id, idx, kind=kind):
            skipped += 1
            results.append({"item_id": item_id, "idx": idx, "kind": kind,
                            "ok": True, "skipped": True, "error": "이미 올라가 있음"})
            continue
        raw, _ct = blobs.get(item_id, idx, kind=kind)
        if not raw:
            blobs.set_cdn(item_id, idx, "", kind=kind, error="바이트가 없습니다")
            failed += 1
            results.append({"item_id": item_id, "idx": idx, "kind": kind,
                            "ok": False, "error": "바이트가 없습니다"})
            continue
        url, err = _upload(raw)
        if not url:
            blobs.set_cdn(item_id, idx, "", kind=kind, error=err)
            failed += 1
            results.append({"item_id": item_id, "idx": idx, "kind": kind,
                            "ok": False, "error": err})
            logger.warning("[CDN 백필] 실패 item=%s idx=%s: %s", item_id, idx, err)
            continue
        blobs.set_cdn(item_id, idx, url, kind=kind)
        _point_entry_at_cdn(item_id, idx, kind, url)
        uploaded += 1
        results.append({"item_id": item_id, "idx": idx, "kind": kind, "ok": True, "error": ""})

    if uploaded or failed:
        logger.info("[CDN 백필] 올림 %s · 실패 %s · 건너뜀 %s (대기 %s)",
                    uploaded, failed, skipped, len(pending))
    return {"ok": True, "uploaded": uploaded, "failed": failed, "skipped": skipped,
            "pending": len(pending), "reason": "", "results": results}


def run_quietly() -> None:
    """부팅 훅용 — 실패해도 기동을 막지 않는다(백필은 부가 작업이다)."""
    try:
        run()
    except Exception as exc:
        logger.warning("[CDN 백필] 건너뜀: %s", exc)
