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

_STATE: dict = {"run_id": "", "running": False, "total": 0, "results": [],
                "mode": 0, "title": ""}
_LOCK = threading.Lock()


def reset_for_tests() -> None:
    with _LOCK:
        _STATE.update({"run_id": "", "running": False, "total": 0, "results": []})


def is_running() -> bool:
    with _LOCK:
        return bool(_STATE["running"])


def start(run_id: str, seller_id: str, fixtures, *, mode: int = 0,
          title: str = "", render_d3: bool = False) -> int:
    """접수 — 총 장수를 돌려주고 뒤에서 돈다. 이미 돌고 있으면 0.

    F33: `mode`(0=pro / 1=lite)를 실어 **같은 장을 두 번** 돌린다. 두 실행은 따로 저장되고
    화면이 나란히 세운다 — 한 번에 둘을 돌리면 초당 1장 한도를 어긴다.
    `title`은 **브랜드 사전의 출처**다(상품명에서 영문 대문자 토큰을 뽑는다).

    ## D3-3b — `render_d3=True`면 **한 장에 두 결과**가 난다

    공급사 렌더본(지금 쓰는 것)과 **우리 3단계 렌더본**을 같은 장으로 만들어 나란히 세운다.
    텐센트 호출은 **여전히 한 번**이다 — 우리는 그 응답의 `TransDetails`(박스+원문)를
    다시 쓸 뿐이다. 장당 과금이 두 배로 늘지 않는다.

    > ★ **이건 파이프라인 연결이 아니다.** 결과는 벤치 저장소(`kind="d3"`)에만 두고,
    > 등록·번역 경로는 이 값을 쳐다보지 않는다. 5축을 통과해야 연결을 논한다.
    """
    planned = [(fx, i, img) for fx in (fixtures or [])
               for i, img in enumerate(fx.get("images") or [])]
    with _LOCK:
        if _STATE["running"]:
            return 0
        _STATE.update({"run_id": run_id, "running": True, "mode": int(mode),
                       "title": str(title or ""), "total": len(planned), "results": [],
                       "render_d3": bool(render_d3)})
    threading.Thread(target=_run,
                     args=(run_id, seller_id, planned, int(mode), str(title or ""),
                           bool(render_d3)),
                     daemon=True, name=f"bench-{run_id}").start()
    return len(planned)


def _d3_translate_fn():
    """벤치가 2단계에 **주입할** 번역기 — 호출 수·글자 수를 같이 센다.

    ★ **토큰 수는 못 잰다.** 우리 번역 체인(`AITranslator`)이 공급사 응답의 `usage`를
    바깥으로 내주지 않는다(`choices`만 읽는다). 그래서 **호출 수와 글자 수**를 센다 —
    토큰을 추정해 적는 것은 지어내는 것이다. 토큰이 필요하면 체인이 `usage`를 실어야 한다.
    """
    stat = {"calls": 0, "chars": 0, "errors": 0}

    def _fn(text: str) -> str:
        stat["calls"] += 1
        stat["chars"] += len(text or "")
        from src.seller_console.ai.translator import AITranslator
        got = AITranslator().translate_product({"title": text, "description": ""})
        out = str((got or {}).get("title_ko") or "").strip()
        if not out:
            stat["errors"] += 1
        return out

    return _fn, stat


def _render_d3_for(raw: bytes, lines: list) -> dict:
    """2단계(용어집) + 3단계(지우고 그리기). 실패해도 **공급사 결과는 안 건드린다.**"""
    from src.services import image_text_glossary as glossary
    from src.services import image_text_render as render

    fn, stat = _d3_translate_fn()
    rows = glossary.translate_lines(lines or [], fn)
    out = render.render(raw, rows, method="telea")
    return {
        "ok": bool(out.get("ok")),
        "image_bytes": out.get("image_bytes") or b"",
        "erased": out.get("erased", 0),
        "drawn": out.get("drawn", 0),
        "skipped": out.get("skipped") or [],
        "error": out.get("error", ""),
        "glossary": glossary.summarize(rows),
        "rows": rows,
        "llm": stat,          # {calls, chars, errors} — 토큰은 위 설명 참조
    }


def _run_d3_stage(fx: dict, idx: int, img: dict, result: dict, seller_id: str) -> dict:
    """한 장의 D3 렌더 — 실패해도 **행 전체를 죽이지 않는다**(사유만 남긴다)."""
    import base64

    from src.services import image_translate_store as store
    from src.services import image_translate_tencent as tc

    lines = result.get("lines") or []
    if not lines:
        return {"ok": False, "error": "공급사가 줄(박스+원문)을 주지 않았습니다",
                "drawn": 0, "erased": 0, "skipped": [], "url": ""}
    try:
        raw, why = tc.fetch_image(img.get("url") or "")
    except Exception as exc:                                   # pragma: no cover
        return {"ok": False, "error": f"원본을 받지 못했습니다: {type(exc).__name__}",
                "drawn": 0, "erased": 0, "skipped": [], "url": ""}
    if not raw:
        return {"ok": False, "error": f"원본을 받지 못했습니다: {why}",
                "drawn": 0, "erased": 0, "skipped": [], "url": ""}

    try:
        out = _render_d3_for(raw, lines)
    except Exception as exc:                                   # pragma: no cover
        logger.warning("[벤치·D3] 렌더 실패: %s", exc)
        return {"ok": False, "error": f"렌더 오류: {type(exc).__name__}",
                "drawn": 0, "erased": 0, "skipped": [], "url": ""}

    # 벤치 저장소에만 둔다 — `kind="d3"`. 등록 경로가 보는 gallery/detail은 건드리지 않는다.
    stored = {"url": "", "stored_by": "", "note": ""}
    if out.get("image_bytes"):
        stored = store.store_translated(
            str(fx.get("item_id") or fx.get("item_no")), idx,
            base64.b64encode(out["image_bytes"]).decode("ascii"),
            seller_id=seller_id, kind="d3")
    return {
        "ok": bool(out.get("ok")) and bool(stored.get("url")),
        "url": stored.get("url", ""),
        "stored_by": stored.get("stored_by", ""),
        "store_note": stored.get("note", ""),
        "erased": out.get("erased", 0),
        "drawn": out.get("drawn", 0),
        "skipped": out.get("skipped") or [],
        "glossary": out.get("glossary") or {},
        "llm": out.get("llm") or {},
        "error": out.get("error", "") or (
            "" if stored.get("url") else (stored.get("note") or "저장하지 못했습니다")),
    }


def _run(run_id: str, seller_id: str, planned, mode: int = 0, title: str = "",
         render_d3: bool = False) -> None:
    from src.db import image_translate_usage_pg as usage
    from src.services import image_bench_axes as axes
    from src.services import image_translate_store as store
    from src.services import image_translate_tencent as tc

    tokens = axes.brand_tokens(title)
    entries = []
    try:
        for fx, i, img in planned:
            r = tc.translate_image(url=img["url"], mode=mode)
            e = store.build_entry(i, r, item_id=str(fx.get("item_id") or fx["item_no"]),
                                  seller_id=seller_id)
            entries.append(e)
            lines = r.get("lines") or []
            row = {"item_no": fx["item_no"], "kind": img.get("kind", ""),
                   "original": img["url"], "idx": i, "mode": mode,
                   # F33: 판정의 근거를 **그대로** 남긴다 — 표가 틀렸다는 말이 나오면
                   #   이 줄들로 다시 센다(우리가 고쳐 그린 것이 아니다).
                   "lines": lines,
                   "axes": axes.auto_scores(lines, tokens),
                   "box_hints": axes.box_hints(lines),
                   "brand_tokens": list(tokens),
                   **{k: e.get(k) for k in ("status", "url", "stored_by", "ms", "target_text",
                                            "warn", "error_class", "error_code",
                                            "error_message", "hint", "store_note")}}
            if render_d3:
                row["d3"] = _run_d3_stage(fx, i, img, r, seller_id)
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
        mode = _STATE.get("mode", 0)
    if run_id and run_id != cur:
        return {"ok": True, "run_id": run_id, "running": False,
                "total": 0, "done": 0, "results": [], "mode": 0}
    return {"ok": True, "run_id": cur, "running": running, "total": total, "mode": mode,
            "done": sum(1 for r in results if r.get("status") == "done"),
            "processed": len(results), "results": results}
