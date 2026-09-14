"""src/services/image_translate_bench.py — 공급사 채점 벤치를 **요청 밖에서** 돈다 (F25).

12장 × 초당 1장 = 15초가 넘는다. 응답 안에서 돌리면 그만큼 워커를 잡는다 —
**F22에서 보강이 그렇게 502가 났다.** 접수하고, 뒤에서 돌리고, 화면이 물어본다.

결과는 장마다 저장한다. 중간에 프로세스가 죽어도 **앞선 장은 남는다** —
12장을 다 돌고 나서야 저장하면, 11장째에 죽었을 때 전부(그리고 그 청구까지) 날아간다.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_STATE: dict = {"run_id": "", "running": False, "total": 0, "results": []}
_LOCK = threading.Lock()


def reset_for_tests() -> None:
    with _LOCK:
        _STATE.update({"run_id": "", "running": False, "total": 0, "results": []})


def is_running() -> bool:
    with _LOCK:
        return bool(_STATE["running"])


def start(run_id: str, seller_id: str, fixtures) -> int:
    """접수 — 총 장수를 돌려주고 뒤에서 돈다. 이미 돌고 있으면 0."""
    planned = [(fx, i, img) for fx in (fixtures or [])
               for i, img in enumerate(fx.get("images") or [])]
    with _LOCK:
        if _STATE["running"]:
            return 0
        _STATE.update({"run_id": run_id, "running": True,
                       "total": len(planned), "results": []})
    threading.Thread(target=_run, args=(run_id, seller_id, planned),
                     daemon=True, name=f"bench-{run_id}").start()
    return len(planned)


def _run(run_id: str, seller_id: str, planned) -> None:
    from src.db import image_translate_usage_pg as usage
    from src.services import image_translate_store as store
    from src.services import image_translate_tencent as tc

    entries = []
    try:
        for fx, i, img in planned:
            r = tc.translate_image(url=img["url"])
            e = store.build_entry(i, r, item_id=str(fx.get("item_id") or fx["item_no"]),
                                  seller_id=seller_id)
            entries.append(e)
            row = {"item_no": fx["item_no"], "kind": img.get("kind", ""),
                   "original": img["url"], "idx": i,
                   **{k: e.get(k) for k in ("status", "url", "stored_by", "ms", "target_text",
                                            "warn", "error_class", "error_code",
                                            "error_message", "hint", "store_note")}}
            with _LOCK:
                _STATE["results"].append(row)
                snapshot = list(_STATE["results"])
            # 장마다 저장 — 중간에 죽어도 앞선 장(과 그 청구의 결과)은 남는다.
            try:
                usage.save_run(run_id, seller_id, snapshot)
            except Exception as exc:
                logger.warning("[벤치] 중간 저장 실패(계속): %s", exc)
    except Exception as exc:                                   # pragma: no cover
        logger.warning("[벤치] 실행 중단 %s: %s", run_id, exc)
    finally:
        with _LOCK:
            _STATE["running"] = False
        if entries:
            store.record_usage(seller_id, entries)
        ok = sum(1 for e in entries if e.get("status") == "done")
        logger.info("[벤치] %s — %d장 중 %d장 성공", run_id, len(entries), ok)


def status(run_id: str = "") -> dict:
    """`{ok, run_id, running, total, done, results}`. 다른 run을 물으면 진행은 비운다."""
    with _LOCK:
        cur, running = _STATE["run_id"], _STATE["running"]
        total, results = _STATE["total"], list(_STATE["results"])
    if run_id and run_id != cur:
        return {"ok": True, "run_id": run_id, "running": False,
                "total": 0, "done": 0, "results": []}
    return {"ok": True, "run_id": cur, "running": running, "total": total,
            "done": sum(1 for r in results if r.get("status") == "done"),
            "processed": len(results), "results": results}
