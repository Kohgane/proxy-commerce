"""src/api/media_cron.py — 이미지 저장본 큐 소비자 (F22).

## 왜 큐인가

보강(`POST /api/v1/collect/enrich`)이 **요청 안에서** 남의 서버 이미지를 내려받아
워터마크를 찾고 리사이즈하고 WebP로 바꿨다. 소싱처가 느린 날 그 요청이 gunicorn
`--timeout 120`을 넘겨 워커가 죽고, 프록시가 **502**를 돌려줬다
(실측 2026-09-14: 초안 1060535477134 · 3회 모두 502).

그래서 갈랐다 — **저장은 즉시**(원본 URL만, 응답 200 + 접수), **복사·변환은 여기서**.
사람이 기다리는 자리에서 남의 서버 사정을 떠안지 않는다.

## 아무도 못 비우는 큐는 만들지 않는다

Cloudinary가 없으면 저장본을 **둘 데가 없다**. 그때는 애초에 큐에 넣지 않는다
(`extension_api._cdn_configured`). 그래서 CDN을 연결하기 전까지 이 크론은
「할 일 0건」만 돌려준다 — 그게 정직한 값이고, 등록해 두면 연결하는 날부터 저절로 돈다.

## 부르는 법

    POST /cron/image-copies     헤더 `X-Cron-Secret: <CRON_SECRET>`

`CRON_SECRET` 미설정이면 거부한다(보호 없는 비용 유발 라우트를 열어 두지 않는다).
"""
from __future__ import annotations

import json
import logging
import os
import time

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

media_cron_bp = Blueprint("media_cron", __name__, url_prefix="/cron")

# 한 회전의 벽시계 예산. 크론은 사람이 안 기다리지만 워커는 하나 잡는다 —
#   gunicorn 타임아웃(120초) 근처에 가지 않게 넉넉히 아래로 둔다.
RUN_BUDGET_SEC = float(os.getenv("IMAGE_COPY_RUN_BUDGET_SEC", "45"))
ROWS_PER_RUN = int(os.getenv("IMAGE_COPY_ROWS_PER_RUN", "5"))


def _authorized() -> bool:
    secret = os.getenv("CRON_SECRET")
    if not secret:
        return False
    return request.headers.get("X-Cron-Secret", "") == secret


@media_cron_bp.post("/image-copies")
def drain_image_copies():
    """접수된 이미지 복사를 예산 안에서 비운다. `{ok, picked, stored_rows, left}`."""
    if not _authorized():
        return jsonify({"ok": False, "error": "cron 인증 실패"}), 403

    from src.api.extension_api import _cdn_configured, _store_image_copies
    from src.seller_console import collect_history_store as store

    if not _cdn_configured():
        # 둘 데가 없으면 할 일도 없다 — 「0건」이 거짓이 아니라 사실이다.
        return jsonify({"ok": True, "picked": 0, "stored_rows": 0, "left": 0,
                        "note": "CDN 미설정 — 저장본을 둘 데가 없습니다"})

    try:
        rows = store.list_items(days=90, limit=500)
    except Exception as exc:
        logger.warning("[이미지복사] 목록 조회 실패: %s", exc)
        return jsonify({"ok": False, "error": "목록을 읽지 못했습니다"}), 500

    queued = []
    for row in rows:
        try:
            ex = json.loads(row.get("extra_json") or "{}") or {}
        except Exception:
            continue
        if str(ex.get("images_copy_state") or "") == "queued":
            queued.append((row, ex))

    deadline = time.monotonic() + RUN_BUDGET_SEC
    picked = queued[:ROWS_PER_RUN]
    stored_rows = 0
    for row, ex in picked:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        out = _store_image_copies(list(ex.get("images") or []),
                                  already=ex.get("images_stored"),
                                  budget_sec=left, item_id=str(row.get("id") or ""))
        ex.update(out)
        # 상태는 **결과를 보고** 적는다. 저장본이 생겼으면 done, 아니면 사유를 남기고 done —
        #   못 한 것을 queued로 되돌리면 같은 벽에 영원히 머리를 박는다(C-F13-2b와 같은 규칙).
        ex["images_copy_state"] = "done"
        if out.get("images_stored"):
            stored_rows += 1
        try:
            store.update(row.get("id"), extra_json=json.dumps(ex, ensure_ascii=False))
        except Exception as exc:
            logger.warning("[이미지복사] 저장 실패 item=%s: %s", row.get("id"), exc)

    logger.info("[이미지복사] 접수 %s건 중 %s건 처리 · 저장본 생성 %s건",
                len(queued), len(picked), stored_rows)
    return jsonify({"ok": True, "picked": len(picked), "stored_rows": stored_rows,
                    "left": max(0, len(queued) - len(picked))})
