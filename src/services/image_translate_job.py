"""src/services/image_translate_job.py — 이미지 번역을 **요청 밖에서** 돈다 (F25).

## 왜 요청 밖인가

공급사 한도가 **계정 단위 초당 1회**다(실측 2026-09-14). 5장이면 최소 6초,
12장이면 15초가 넘는다. 그걸 응답 안에서 돌리면 gunicorn 타임아웃 근처로 간다 —
**F22에서 보강이 그렇게 502가 났다.** 같은 자리에 두 번 서지 않는다.

그래서 셋으로 가른다:

  ① 접수 — 고른 장을 `queued`로 적고 **바로 202**로 답한다.
  ② 처리 — 데몬 스레드가 **한 장씩** 번역해 장별로 저장한다.
  ③ 조회 — 화면이 폴링해 장별 상태를 갱신한다.

## 재시작하면 `queued`가 남는다 — 그렇게 말한다

데몬 스레드는 배포·재시작에 사라진다. 그때 `queued`로 남은 장은 **다시 누르면 된다**.
큐를 DB에 두고 크론으로 비우는 편이 튼튼하지만, 지금은 사람이 보고 누르는 단계라
그 복잡도를 살 값이 아니다. 대신 **남은 이유를 화면이 말할 수 있게** 상태를 남긴다.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 한 상품에 동시에 두 번 돌지 않게. 두 번 돌면 같은 장을 두 번 번역하고 **두 번 청구된다.**
_RUNNING: dict = {}
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reset_for_tests() -> None:
    with _LOCK:
        _RUNNING.clear()


def is_running(item_id: str) -> bool:
    with _LOCK:
        return bool(_RUNNING.get(str(item_id)))


def _load(item_id: str, seller_ids):
    from src.seller_console import collect_history_store as store
    row = store.get(item_id, seller_ids=seller_ids) or {}
    try:
        extra = json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        extra = {}
    return row, extra


def _save(item_id: str, seller_ids, extra: dict) -> bool:
    from src.seller_console import collect_history_store as store
    try:
        return bool(store.update(item_id, seller_ids=seller_ids,
                                 extra_json=json.dumps(extra, ensure_ascii=False)))
    except Exception as exc:
        logger.warning("[이미지번역] 저장 실패 item=%s: %s", item_id, exc)
        return False


def accept(item_id: str, seller_id: str, indices, *, seller_ids=None) -> dict:
    """① 접수 — 고른 장을 `queued`로 적고 바로 돌려준다. 실제 번역은 ②가 한다.

    반환 `{ok, accepted, queued:[idx], skipped:[{idx, reason}], already_running}`.
    """
    ids = seller_ids or {seller_id}
    row, extra = _load(item_id, ids)
    if not row:
        return {"ok": False, "error": "항목을 찾을 수 없습니다."}

    images = [u for u in (extra.get("images") or []) if u]
    if not images:
        return {"ok": False, "error": "이 상품엔 이미지가 없습니다."}

    from src.services.image_translate_tencent import _cap_full
    full = _cap_full()
    if full:
        # Y11-D: 하루 상한이 찼으면 받지 않는다(보내면 과금 · 예전엔 이 길이 상한을 안 봐서 320 → 322)
        return {"ok": False, "cap_full": True,
                "error": f"오늘 이미지 번역 상한({full[1]}장)에 닿았어요 — 내일 0시(KST) 이후 다시 눌러 주세요."}

    if is_running(item_id):
        # 돌고 있는데 또 받으면 같은 장을 두 번 보내고 **두 번 청구된다.**
        return {"ok": False, "error": "이미 번역 중입니다. 끝나면 다시 눌러 주세요.",
                "already_running": True}

    from src.services import image_translate_store as istore
    queued, skipped = [], []
    entries = []
    for i in sorted({int(x) for x in (indices or [])}):
        if not (0 <= i < len(images)):
            skipped.append({"idx": i, "reason": "그런 장이 없습니다"})
            continue
        if istore.has_boxes(next((e for e in (extra.get("images_ko") or [])
                                  if isinstance(e, dict) and int(e.get("idx", -1)) == i), None)):
            skipped.append({"idx": i, "reason": istore.PROTECTED_REASON})   # Y11-F: 상자 있는 번역본은 다시 안 보낸다
            continue
        queued.append(i)
        entries.append({"idx": i, "status": "queued", "at": _now(),
                        "vendor": "tencent", "ms": 0})
    if not queued:
        prot = [s for s in skipped if s["reason"] == istore.PROTECTED_REASON]
        return {"ok": False, "skipped": skipped, "protected": bool(prot),
                "error": (istore.PROTECTED_REASON + " — 편집 화면에서 글자 상자를 바로 쓸 수 있어요") if prot else "번역할 이미지를 골라 주세요."}

    extra["images_ko"] = istore.merge_images_ko(extra, entries)
    if not _save(item_id, ids, extra):
        return {"ok": False, "error": "접수하지 못했습니다. 잠시 후 다시 시도해 주세요."}

    _start(item_id, seller_id, queued, ids)
    return {"ok": True, "accepted": len(queued), "queued": queued, "skipped": skipped,
            "summary": istore.summarize(extra)}


def _start(item_id: str, seller_id: str, indices, seller_ids) -> None:
    with _LOCK:
        if _RUNNING.get(item_id):
            return
        _RUNNING[item_id] = True
    th = threading.Thread(target=_run, args=(item_id, seller_id, indices, seller_ids),
                          daemon=True, name=f"imgko-{item_id}")
    th.start()


def _run(item_id: str, seller_id: str, indices, seller_ids) -> None:
    """② 처리 — **한 장씩**. 장마다 저장한다(중간에 죽어도 앞선 장은 남게)."""
    from src.services import image_translate_store as istore
    from src.services import image_translate_tencent as tc
    from src.media.image_label import make_label, run_stamp
    done_entries = []
    # 0-b — 셀러 경로 번역본도 **이름표**를 단다(벤치와 같은 규칙). 한 번 누른 작업 = 한 run.
    run_id = run_stamp("sel")
    try:
        for i in indices:
            _row, extra = _load(item_id, seller_ids)
            images = [u for u in (extra.get("images") or []) if u]
            if not (0 <= i < len(images)):
                continue
            if istore.has_boxes(next((e for e in (extra.get("images_ko") or [])
                                      if isinstance(e, dict) and int(e.get("idx", -1)) == i), None)):
                continue                                         # Y11-F: 그 사이 상자 있는 번역본이 생겼다 — 보내지 않는다
            result = tc.translate_image(url=images[i])
            entry = istore.build_entry(i, result, item_id=item_id, seller_id=seller_id,
                                       label=make_label(run_id, item_id, i, "TENCENT", folder="seller"))
            done_entries.append(entry)
            extra["images_ko"] = istore.merge_images_ko(extra, [entry])
            _save(item_id, seller_ids, extra)
    except Exception as exc:                                   # pragma: no cover
        logger.warning("[이미지번역] 작업 중단 item=%s: %s", item_id, exc)
    finally:
        with _LOCK:
            _RUNNING.pop(item_id, None)
        if done_entries:
            istore.record_usage(seller_id, done_entries)
        logger.info("[이미지번역] item=%s 처리 %s장 완료 %s장", item_id, len(done_entries),
                    sum(1 for e in done_entries if e.get("status") == "done"))


def status(item_id: str, seller_ids) -> dict:
    """③ 조회 — 화면 폴링용. `{ok, entries, summary, running}`."""
    from src.services import image_translate_store as istore
    row, extra = _load(item_id, seller_ids)
    if not row:
        return {"ok": False, "error": "항목을 찾을 수 없습니다."}
    return {"ok": True, "entries": extra.get("images_ko") or [],
            "summary": istore.summarize(extra), "running": is_running(item_id)}
