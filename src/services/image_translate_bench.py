"""src/services/image_translate_bench.py — 공급사 채점 벤치를 **요청 밖에서** 돈다 (F25).

12장 × 초당 1장 = 15초가 넘는다. 응답 안에서 돌리면 그만큼 워커를 잡는다 —
**F22에서 보강이 그렇게 502가 났다.** 접수하고, 뒤에서 돌리고, 화면이 물어본다.

결과는 장마다 저장한다. 중간에 프로세스가 죽어도 **앞선 장은 남는다** —
12장을 다 돌고 나서야 저장하면, 11장째에 죽었을 때 전부(그리고 그 청구까지) 날아간다.
"""
from __future__ import annotations

import json
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
          title: str = "", render_d3: bool = False, gen_remove: bool = False) -> int:
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

    ## D3-5 — `gen_remove=True`면 D3를 **두 번 그린다**(telea · gen_remove)

    번역(LLM)은 **한 번**이다 — 같은 줄을 두 인페인터로 그릴 뿐이다. gen_remove는
    Cloudinary 크레딧을 쓰므로(장당 51 tx ≈ 0.051 크레딧) **따로 켠다**.
    """
    planned = [(fx, i, img) for fx in (fixtures or [])
               for i, img in enumerate(fx.get("images") or [])]
    with _LOCK:
        if _STATE["running"]:
            return 0
        _STATE.update({"run_id": run_id, "running": True, "mode": int(mode),
                       "title": str(title or ""), "total": len(planned), "results": [],
                       "render_d3": bool(render_d3),
                       "gen_remove": bool(render_d3 and gen_remove)})
    threading.Thread(target=_run,
                     args=(run_id, seller_id, planned, int(mode), str(title or ""),
                           bool(render_d3), bool(render_d3 and gen_remove)),
                     daemon=True, name=f"bench-{run_id}").start()
    return len(planned)


def _d3_translate_fn():
    """벤치가 2단계에 **주입할** 번역기 — 호출 수·글자 수를 같이 센다.

    ★ **토큰 수는 못 잰다.** 우리 번역 체인(`AITranslator`)이 공급사 응답의 `usage`를
    바깥으로 내주지 않는다(`choices`만 읽는다). 그래서 **호출 수와 글자 수**를 센다 —
    토큰을 추정해 적는 것은 지어내는 것이다. 토큰이 필요하면 체인이 `usage`를 실어야 한다.
    """
    stat = {"calls": 0, "chars": 0, "errors": 0, "providers": {}, "styled": 0, "unstyled": 0}

    def _fn(text: str) -> str:
        stat["calls"] += 1
        stat["chars"] += len(text or "")
        from src.seller_console.ai.translator import AITranslator
        from src.services.image_text_glossary import STYLE_INSTRUCTION
        got = AITranslator().translate_product({"title": text, "description": ""},
                                               style=STYLE_INSTRUCTION) or {}
        # ★ D3-4 ④ — 「문체를 지시했다」가 아니라 **따를 수 있는 단이 받았나**를 센다.
        #   사전형 MT가 받았으면 지시는 아무 일도 하지 않았다. 그 사실이 표에 남아야
        #   카피가 여전히 평서문일 때 **어디를 봐야 하는지** 알 수 있다.
        stat["styled" if got.get("style_applied") else "unstyled"] += 1
        p = str(got.get("provider") or "?")
        stat["providers"][p] = stat["providers"].get(p, 0) + 1
        out = str(got.get("title_ko") or "").strip()
        if not out:
            stat["errors"] += 1
        return out

    return _fn, stat


def _render_d3_for(raw: bytes, lines: list, tokens=(), gen_remove: bool = False) -> dict:
    """2단계(용어집) + 3단계(지우고 그리기). 실패해도 **공급사 결과는 안 건드린다.**

    D3-5: 번역은 **한 번** 하고, 같은 줄로 telea를 그리고(항상), `gen_remove`면 한 번 더 그린다.
    두 결과 모두 **F축**(지운 자리 vs 주변 링)을 **지운 결과**에서 잰다 —
    지운 결과 바이트는 재고 나서 **버린다**(저장소·실행 기록에 싣지 않는다).
    """
    from src.services import image_bench_axes as axes
    from src.services import image_text_glossary as glossary
    from src.services import image_text_render as render

    fn, stat = _d3_translate_fn()
    rows = glossary.translate_lines(lines or [], fn)
    # ★★ D3-4 ⑤ — D3 열도 **텐센트 열과 같은 판정기**로 A·B·D를 자동 채점한다.
    #   다른 판정기를 쓰면 두 열의 점수를 나란히 놓을 수 없다(그게 비교의 전부다).
    #   C·E는 여전히 사람이 찍는다 — 박스는 **원문**의 자리라 자동으로 못 잰다(F33).
    text_axes = axes.auto_scores(d3_judgeable(rows), list(tokens or []))

    def _one(method: str) -> dict:
        out = render.render(raw, rows, method=method)
        erased = out.pop("erased_bytes", b"") or b""
        f = ({"score": None, "reason": out.get("error") or "지운 결과가 없습니다", "hits": []}
             if not (out.get("ok") and erased)
             else render.background_score(erased, raw, out.get("painted_boxes") or []))
        return {
            "ok": bool(out.get("ok")),
            "image_bytes": out.get("image_bytes") or b"",
            "erased": out.get("erased", 0),
            "drawn": out.get("drawn", 0),
            "skipped": out.get("skipped") or [],
            "error": out.get("error", ""),
            "axes": {**text_axes, "F": {"score": f["score"], "reason": f["reason"]}},
            "f_hits": f.get("hits") or [],
            "typography": out.get("typography") or [],
            "inpainter": out.get("inpainter", method),
            "inpaint_fallback": out.get("inpaint_fallback", ""),
            "cloud_tx": out.get("cloud_tx", 0),
            "cloud_credits": out.get("cloud_credits", 0.0),
        }

    tel = _one("telea")
    tel.update({"glossary": glossary.summarize(rows), "rows": rows,
                "llm": stat})     # {calls, chars, errors, providers, styled} — 토큰은 위 설명 참조
    if gen_remove:
        tel["gen_remove"] = _one("gen_remove")
    return tel


def d3_judgeable(rows: list) -> list:
    """우리 렌더 결과를 **판정기가 읽는 모양**(`{source, target}`)으로 바꾼다.

    ★ `target`은 **우리가 그린 글자**(`render_text`)다 — 공급사 번역이 아니다.
    두 열이 같은 판정기를 쓰되 **각자 자기 결과**를 채점해야 비교가 성립한다.
    """
    return [{"source": r.get("source") or "", "target": r.get("render_text") or ""}
            for r in (rows or [])]


def bench_label(run_id: str, fx: dict, idx: int, pipeline: str) -> dict:
    """D3-6 ⓪ — 벤치 산출물의 **이름표**. 주소(public_id)와 context에 그대로 박힌다."""
    return {"run_id": str(run_id or ""), "item_no": str(fx.get("item_no") or ""),
            "page": str(idx), "pipeline": pipeline}


def _run_d3_stage(fx: dict, idx: int, img: dict, result: dict, seller_id: str,
                  tokens=(), gen_remove: bool = False, run_id: str = "") -> dict:
    """한 장의 D3 렌더 — 실패해도 **행 전체를 죽이지 않는다**(사유만 남긴다).

    D3-5: `gen_remove`면 결과에 `gen_remove` 키로 **두 번째 렌더**가 붙는다(`kind="d3g"`).
    """
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
        out = _render_d3_for(raw, lines, tokens, gen_remove=gen_remove)
    except Exception as exc:                                   # pragma: no cover
        logger.warning("[벤치·D3] 렌더 실패: %s", exc)
        return {"ok": False, "error": f"렌더 오류: {type(exc).__name__}",
                "drawn": 0, "erased": 0, "skipped": [], "url": ""}

    item_id = str(fx.get("item_id") or fx.get("item_no"))

    def _store(one: dict, kind: str) -> dict:
        # 벤치 저장소에만 둔다 — `kind="d3"`/`"d3g"`. 등록 경로가 보는 gallery/detail은 안 건드린다.
        if not one.get("image_bytes"):
            return {"url": "", "stored_by": "", "note": ""}
        # D3-6 ⓪ — 이름표는 **실제로 쓴 인페인터**로 붙인다(폴백이면 TELEA — 이름을 속이지 않는다).
        pipe = "GEN_REMOVE" if one.get("inpainter") == "gen_remove" else "TELEA"
        got = store.store_translated(
            item_id, idx, base64.b64encode(one["image_bytes"]).decode("ascii"),
            seller_id=seller_id, kind=kind, label=bench_label(run_id, fx, idx, pipe))
        if got.get("stored_by") == "db":
            # ★ D3-5에서 찾은 구멍 — DB에 두면 저장소가 **셀러 경로**(`/collect/image-ko/…?kind=d3`)를
            #   준다. 그런데 그 라우트는 `detail`이 아닌 kind를 전부 **gallery로** 읽는다 —
            #   D3 칸에 **엉뚱한 그림(텐센트 번역본)이** 뜬다. 벤치 그림은 벤치 라우트로만 연다
            #   (D3-3b가 그 라우트를 만든 이유다 — 주소만 안 이어져 있었다).
            got = {**got, "url": f"/seller/admin/image-translate-bench/image/{item_id}/{idx}"
                                 f"?kind={kind}"}
        return got

    stored = _store(out, "d3")
    g_row = {}
    if out.get("gen_remove"):
        g = out["gen_remove"]
        gs = _store(g, "d3g")
        g_row = {
            "ok": bool(g.get("ok")) and bool(gs.get("url")),
            "url": gs.get("url", ""), "stored_by": gs.get("stored_by", ""),
            "store_note": gs.get("note", ""),
            "erased": g.get("erased", 0), "drawn": g.get("drawn", 0),
            "skipped": g.get("skipped") or [],
            "axes": g.get("axes") or {}, "f_hits": g.get("f_hits") or [],
            # ★ 폴백이면 **이름이 telea**다 — gen_remove 칸에 telea를 gen_remove로 올리지 않는다.
            "inpainter": g.get("inpainter", ""),
            "inpaint_fallback": g.get("inpaint_fallback", ""),
            "cloud_tx": g.get("cloud_tx"), "cloud_credits": g.get("cloud_credits"),
            "error": g.get("error", "") or (
                "" if gs.get("url") else (gs.get("note") or "저장하지 못했습니다")),
        }
    return {
        "gen_remove": g_row,
        "ok": bool(out.get("ok")) and bool(stored.get("url")),
        "url": stored.get("url", ""),
        "stored_by": stored.get("stored_by", ""),
        "store_note": stored.get("note", ""),
        "erased": out.get("erased", 0),
        "drawn": out.get("drawn", 0),
        "skipped": out.get("skipped") or [],
        "glossary": out.get("glossary") or {},
        "axes": out.get("axes") or {},
        "f_hits": out.get("f_hits") or [],
        "inpainter": out.get("inpainter", "telea"),
        "typography": out.get("typography") or [],
        "llm": out.get("llm") or {},
        "error": out.get("error", "") or (
            "" if stored.get("url") else (stored.get("note") or "저장하지 못했습니다")),
    }


def _run(run_id: str, seller_id: str, planned, mode: int = 0, title: str = "",
         render_d3: bool = False, gen_remove: bool = False) -> None:
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
                                  seller_id=seller_id,
                                  label=bench_label(run_id, fx, i, "TENCENT"))
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
            # D3-6 ④ — 「박스가 있었는데 버렸나, 애초에 없었나」를 **응답 원문으로** 가른다.
            #   파싱은 TransDetails를 하나도 거르지 않는다 → `lines`가 곧 응답의 박스 전부다.
            #   전체 OCR 문(`SourceText`)엔 있는데 어느 박스에도 없는 조각 = **텐센트가 박스를 안 준 것**.
            row["source_text"] = str(r.get("source_text") or "")
            row["unboxed"] = unboxed_fragments(row["source_text"], lines)
            logger.info("[벤치·텐센트] run=%s item=%s p%d 박스 %d개 · 박스 밖 OCR %s · 원문=%s",
                        run_id, fx["item_no"], i, len(lines), row["unboxed"] or "없음",
                        json.dumps([{"s": ln.get("source"), "b": ln.get("box")} for ln in lines],
                                   ensure_ascii=False)[:3000])
            # D3-5 ② — 텐센트의 F는 **잴 수 없다**(지운 중간본이 없다). 0이 아니라 측정 불가.
            row["axes"]["F"] = {"score": None, "reason": axes.F_UNMEASURABLE_TENCENT}
            if render_d3:
                d3 = _run_d3_stage(fx, i, img, r, seller_id, tokens, gen_remove=gen_remove,
                                   run_id=run_id)
                row["d3g"] = d3.pop("gen_remove", {}) or {}
                row["d3"] = d3
            # D3-5 ③ — 장마다 **최선**을 제안한다(사람이 뒤집을 수 있다).
            row["pick"] = axes.pick_best(pick_candidates(row))
            if render_d3:
                logger.info("[벤치·F] %s", f_log_line(run_id, fx["item_no"], i, row))
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


def unboxed_fragments(source_text: str, lines: list) -> list:
    """전체 OCR 문의 조각 중 **어느 박스 원문에도 없는 것** (D3-6 ④).

    조각 = 줄바꿈·공백으로 나눈 덩어리. 박스 원문들을 공백 없이 이어 붙인 문자열에
    안 들어 있으면 「박스 밖」이다. 응답에 `SourceText`가 없으면 빈 목록(판정 불가를 0으로 쓰지 않는다).
    """
    joined = "".join("".join(str(ln.get("source") or "").split()) for ln in (lines or []))
    out = []
    for frag in str(source_text or "").split():
        if frag and frag not in joined and frag not in out:
            out.append(frag)
    return out


def _f_of(col: dict) -> str:
    f = ((col or {}).get("axes") or {}).get("F") or {}
    sc = f.get("score")
    return "측정불가" if sc is None else str(sc)


def f_log_line(run_id: str, item_no, idx: int, row: dict) -> str:
    """장마다 F와 선택 — **왜 GEN_REMOVE가 안 뽑혔는지** 로그 한 줄로 (D3-6 ⑤)."""
    d3, g = row.get("d3") or {}, row.get("d3g") or {}
    pick = row.get("pick") or {}
    return (f"run={run_id} item={item_no} p{idx} "
            f"TELEA F={_f_of(d3)} · GEN_REMOVE F={_f_of(g)}"
            f"(인페인터={g.get('inpainter') or '-'}"
            f"{' 폴백: ' + str(g.get('inpaint_fallback')) if g.get('inpaint_fallback') else ''}) · "
            f"선택={pick.get('pick') or '-'} · 사유={pick.get('reason') or '-'}")


def pick_candidates(row: dict) -> dict:
    """이 장에서 **실제로 그림을 낸** 후보만 — `{name: axes}`.

    ★ gen_remove가 **telea로 폴백**했으면 후보가 아니다 — 같은 그림을 두 번 세게 된다.
    """
    out = {}
    if row.get("status") == "done" and row.get("url"):
        out["tencent"] = row.get("axes") or {}
    d3 = row.get("d3") or {}
    if d3.get("ok") and d3.get("url"):
        out["d3"] = d3.get("axes") or {}
    g = row.get("d3g") or {}
    if g.get("ok") and g.get("url") and g.get("inpainter") == "gen_remove":
        out["d3g"] = g.get("axes") or {}
    return out


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
