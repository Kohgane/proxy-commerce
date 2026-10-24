"""Y11X(오너 2026-10-17) — 한 장짜리 일회성 작업 줄: 「이 장만 다시 다듬기」 · 「이 장만 OCR 다시 판정」.

버튼(「번역 다듬기(이 상품)」·「OCR 다시 판정(이 상품)」)은 상품 전체를 돈다 — 오너가 **한 장만** 시킬 때(상세 13번만 재다듬,
상세 1번만 다시 판정) 다른 장의 캐시·과금을 건드리지 않으려고 둔다. 줄은 `app_state ops:oneshot:queue`, 결과는 `ops:oneshot:last`.
`/cron/translate-drain` 틱이 꺼내 **한 번만** 돌린다(꺼내자마자 줄에서 뺀다 — 실패해도 다시 돌지 않는다, 결과에 사유).
P0-운영(오너 2026-10-23): 꺼낸 줄은 `ops:oneshot:inflight:<인스턴스:pid>`에 적어 두고 끝나면 지운다 — 프로세스가 도중에 죽으면
(강제 종료·OOM) 다음 부팅의 `restart_recovery`가 시작 못 한 줄은 다시 넣고, 돌던 줄은 읽기 작업만 한 번 다시 넣고 나머지는 「중단됨」.

허용 작업은 둘뿐(그 밖의 줄은 「모르는 작업」으로 버린다):
- `polish_page` {item_id, kind, idx} — 그 장만 `image_polish.polish_job`(다시 만들 다듬음 버전일 때만 새로 그림)
- `ocr_recheck` {item_id, detail_idx:[…]} — 그 상세 장만 `ocr_compare_diag.run`(장당 OCR 4회)
- `attn_backfill` {} — Y12-A: 목록 정렬·「손댈 것」 열(`last_action_at`·`attn_n`)과 `extra.attn`을 등록 기록·등록 보류가 있는
  상품에만 한 번 채운다(그 밖의 칸은 손대지 않는다 · 한 번에 500건). Y12-B: 수집 실패 후보(보강 대기·막힘 · 보강 축 없이
  가격·갤러리 둘 다 빈 상품)도 — 「손댈 것 · 수집 실패」·「재수집 대기」 요약을 옛 행에도 붙인다
- `review_status` {item_id, market} — Y12-A(오너 23:31 Y11W-1): 그 상품·그 마켓 **상태만 1회 조회**(쿠팡 GET, 무료)하고
  성공 값만 등록 기록 `review`에 남긴다(막힌 조회는 덮지 않음 — 결정 8). 결과 원문 = `ops:oneshot:last`
- `prevalidate` {item_id, markets?} — Y13-A(오너 2026-10-18 「두 상품 사전검증 다시 돌려서 결과표」): 그 상품 계정으로
  화면과 **같은 사전검증 잡**을 띄운다(몸통 = 등록 빌더 `build_product`). 결과는 잡 기록 `prevalidate_job:<id>`(화면이 읽는 그것)
- `image_probe` {item_id, kind, idx:[…]} — Y13-A: 실제 주소를 서버에서 받아 형식·크기·base64·정규화 결과를 남기고 텐센트 OCR에
  한 번 보내 응답 코드를 남긴다(장당 OCR 1회 · 최대 6장 · 번역은 안 보냄). `InvalidParameterValue.Data` 재현 로그
- `carry_requeue` {item_ids:[…]} — Y13-A 9(오너 16:41 「12건 이월 대기열로 재투입」): 4013 분류(#45) 전에 `provider_fail`로 적힌
  공유 초안을 `provider_quota`로 바로잡고(5000 등 다른 사유는 사유 그대로) 이월 대기에 넣는다 — 한도가 풀리는 날 워커가 1회씩 부른다.
  수집 원본·다른 칸은 손대지 않는다(`auto_enrich.kind`·`carry_requeued_at`만)
- `retranslate` {item_id, pages:[[kind, idx], …]?} — Y13-C 1(오너 2026-10-18 「다시 번역 큐 투입 — 오너 안 누른다」): 화면 「다시 번역」과
  **같은 계획**(`translate_plan(retry=True)`)에서 `pages`에 적힌 장만 줄에 넣는다(없으면 계획 전부). 계획이 빼는 장(스페이서·아이콘·
  중복·상한)은 넣지 않고 사유를 남긴다 — 결과 = 접수·건너뜀·이미 대기
- `owner_decision` {item_id, rep:{candidates:[idx…], prefer}, strip:[라벨…], pixels:"restore"} — Y13-D 2(오너 2026-10-18 BLACKHOLES
  「권고안 채택」): 화면 버튼과 **같은 함수**로 오너 결정을 적용한다 — 대표 사진(후보 장마다 텐센트 OCR 상자 수를 재서 0상자 장 ·
  여럿이면 `prefer`)=「이 장을 대표로」, 위험 「빼고 등록」=`risk_gate.decide(strip)`(`pixels=restore`: 음차 상자만 원본 복원 ·
  원문에 상표가 남는 장은 사진째 뺌). 저장 뒤 같은 계정으로 사전검증 잡을 띄운다. 수집 원본(`images`·`skus`)은 손대지 않는다
- `owner_decision` … `option_overrides:{원문 값: 한국어}` — 순찰 42(오너 2026-10-23 d5af2185): 오너가 정한 옵션 값을 편집 화면과
  같은 칸(`option_value_overrides`)에 넣고 사전검증을 다시 띄운다. 원문 값은 손대지 않는다
- `undiscard` {item_id, why} — Y15(오너 2026-10-22): 「버리기」 되돌리기(`extra.discarded` 해제 · `discard_log`에 남김)
- `option_retry` {item_id} — Y15(오너 2026-10-22): 옵션 값 한국어 옮기기 1회(화면 「한국어로 번역」과 같은 `translate_now`) ·
  남은 값과 그 사유를 결과에
- `naver_find` {item_id, words:[…], stores?, max_pages?(기본 10 · 상한 30)} — 순찰 80: **읽기만** — 스마트스토어 전 상태(판매대기·승인대기·판매중지·반려 포함)에서
  상품명 검색. 스토어마다 다 훑었는지(`complete`)를 남긴다(다 못 훑었으면 「없음」이라 하지 않는다). `item_id`는 그 상품 주인 키로 돌리려고
- `register` … `via_job:true` — 순찰 80: 화면 「등록」과 같은 잡(`_upload_start_job`)으로 보내고 끝날 때까지 기다린다(측정 = `reg_job`)
- `thumb_probe` {item_id} — Y12-D(오너 15:32 리브러쉬·BLACKHOLES 썸네일 빈칸): 목록 대표 사진 주소를 **서버에서** 한 번 받아 본다
  (리퍼러 없이 = 목록 `<img referrerpolicy=no-referrer>`와 같은 조건). 상태 코드·형식·크기만 남긴다 — 기록은 바꾸지 않는다
"""
from __future__ import annotations

import contextvars
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

QUEUE_KEY = "ops:oneshot:queue"
PER_TICK = 5
#: 사전검증 잡을 띄우는 줄 — 한 틱에 `HEAVY_PER_TICK`개만(잡이 겹치면 메모리 상한에 걸린다 · Y14 10-21)
HEAVY_OPS = ("prevalidate", "owner_decision", "register", "coupang_relist", "dims_fetch", "check_item")
HEAVY_PER_TICK = 1
LAST_KEY = "ops:oneshot:last"
#: 순찰 62 — 끝난 줄 최근 기록(덮어쓰지 않고 덧붙임 · `LOG_MAX`줄) · 한 줄이 `LOG_ROW_MAX`자를 넘으면 마켓별 성공·사유만
LOG_KEY = "ops:oneshot:log"
LOG_MAX = 60
LOG_ROW_MAX = 4000
INFLIGHT_PREFIX = "ops:oneshot:inflight:"
INTERRUPTED_KEY = "ops:oneshot:interrupted"
#: 도중에 끊겨도 다시 돌려도 되는 줄(조회·사전검증만 — 마켓에 쓰지 않는다). 등록·전송·결정 적용은 다시 넣지 않는다(중복 등록 방지).
REQUEUE_SAFE_OPS = ("prevalidate", "check_item", "dims_fetch", "review_status", "image_probe", "thumb_probe", "coupang_inspect",
                    "naver_find")
_CURRENT_ROW: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar("oneshot_row", default=None)
OPS = ("polish_page", "ocr_recheck", "attn_backfill", "review_status", "prevalidate", "image_probe", "carry_requeue",
       "retranslate", "owner_decision", "register", "relist_fix", "coupang_refresh", "naver_resend", "coupang_inspect",
       "thumb_probe", "coupang_relist", "register_report", "discard", "dims_fetch", "check_item", "option_retry", "undiscard",
       "naver_find")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_row() -> Optional[dict]:
    """지금 이 스레드가 돌리는 일회성 작업 줄(없으면 None) — 사전검증 잡이 「어느 줄이 띄웠나」를 기록에 남긴다(재시작 회수용)."""
    return _CURRENT_ROW.get()


def _inflight_set(key: str, holder: str, rows: list) -> None:
    from src.db import image_translate_queue_pg as st
    try:
        st.state_set(key, {"holder": holder, "at": _now(), "rows": rows})
    except Exception as exc:                                     # noqa: BLE001 — 기록 실패가 작업을 막지 않는다
        logger.warning("[일회성 작업] 진행 기록 실패(계속): %s", exc)


def queue_rows() -> List[dict]:
    from src.db import image_translate_queue_pg as st
    return [r for r in (st.state_get(QUEUE_KEY) or {}).get("rows") or [] if isinstance(r, dict)]


@contextmanager
def _job_env(row: dict):
    """Y15 P0-2(fail-closed): 상품 줄은 **그 상품 주인**의 마켓 키로만 — 주인이 공유 목록(오너·가족)에 없으면 그 셀러 저장값만 보이는
    격리 안에서 돈다(오너 서버 자격 0). 주인을 못 읽으면 닫는다(빈 격리). 상품 없는 줄(백필 등)은 그대로."""
    from src.seller_console import market_credentials as mc
    iid = str(row.get("item_id") or "")
    if not iid:
        yield
        return
    try:
        from src.services import ocr_compare_diag as D
        got = D._item(iid)
        uid = str((got[1] if isinstance(got, tuple) and len(got) > 1 else "") or "")
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[일회성 작업] 상품 주인 조회 실패 — 격리로 닫음 item=%s: %s", iid[:8], exc)
        with mc.isolated_market_env({}):
            yield
        return
    with mc.job_market_env(uid):
        yield


def _run(row: dict) -> Dict:
    op = str(row.get("op") or "")
    item_id = str(row.get("item_id") or "")
    if op not in OPS:
        return {"ok": False, "why": f"모르는 작업({op[:30]})"}
    if op == "attn_backfill":
        return _attn_backfill()
    if op == "review_status":
        return _review_status(item_id, str(row.get("market") or ""))
    if op == "prevalidate":
        return _prevalidate(item_id, [str(m) for m in (row.get("markets") or []) if m])
    if op == "carry_requeue":
        return _carry_requeue([str(i) for i in (row.get("item_ids") or []) if i][:50])
    if op == "retranslate":
        return _retranslate(item_id, [(str(p[0]), int(p[1])) for p in (row.get("pages") or [])
                                      if isinstance(p, (list, tuple)) and len(p) == 2][:40])
    if op == "owner_decision":
        return _owner_decision(item_id, row.get("rep") if isinstance(row.get("rep"), dict) else {},
                               [str(x) for x in (row.get("strip") or []) if x][:5], str(row.get("pixels") or ""),
                               [str(m) for m in (row.get("markets") or []) if m],
                               fields=row.get("fields") if isinstance(row.get("fields"), dict) else None,
                               strip_keep=[str(x) for x in (row.get("strip_keep") or []) if x][:5],
                               exclude_images=[(str(p[0]), int(p[1])) for p in (row.get("exclude_images") or [])
                                               if isinstance(p, (list, tuple)) and len(p) == 2][:10],
                               exclude_why=str(row.get("exclude_why") or ""),
                               relist_only=[str(m) for m in (row.get("relist_only") or []) if m][:4],
                               option_overrides=(row.get("option_overrides")
                                                 if isinstance(row.get("option_overrides"), dict) else None))
    if op == "discard":
        return _discard(item_id, str(row.get("why") or ""))
    if op == "option_retry":
        return option_retry(item_id)
    if op == "undiscard":
        return _undiscard(item_id, str(row.get("why") or ""))
    if op == "dims_fetch":
        return dims_fetch(item_id, onebound=row.get("onebound", True) is not False)
    if op == "check_item":
        return check_item(item_id, [str(m) for m in (row.get("markets") or []) if m])
    if op == "naver_resend":
        return _naver_resend(item_id, [str(m) for m in (row.get("markets") or []) if m])
    if op == "coupang_refresh":
        return _coupang_refresh(item_id, [str(m) for m in (row.get("markets") or []) if m])
    if op == "coupang_inspect":
        return coupang_inspect(item_id, [str(m) for m in (row.get("markets") or []) if m])
    if op == "relist_fix":
        return _relist_fix(item_id, row)
    if op == "register":
        return register(item_id, [str(m) for m in (row.get("markets") or []) if m], via_job=bool(row.get("via_job")))
    if op == "naver_find":
        return naver_find([str(w) for w in (row.get("words") or []) if w][:5],
                          [str(s) for s in (row.get("stores") or []) if s][:4] or None,
                          max_pages=max(1, min(int(row.get("max_pages") or 10), NAVER_FIND_MAX_PAGES)))
    if op == "coupang_relist":
        return _coupang_relist(item_id, str(row.get("step") or "plan"), [str(m) for m in (row.get("markets") or []) if m],
                               mode=str(row.get("mode") or "category"))
    if op == "register_report":
        return register_report(item_id, [str(m) for m in (row.get("markets") or []) if m])
    if op == "image_probe":
        return _image_probe(item_id, str(row.get("kind") or "detail"), [int(i) for i in (row.get("idx") or [])][:6])
    if op == "thumb_probe":
        return _thumb_probe(item_id)
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    item_id = str(item.get("id") or item_id)
    if op == "polish_page":
        from src.services import image_polish as IP
        kind, idx = str(row.get("kind") or "detail"), int(row.get("idx"))
        res = IP.polish_job(item_id, uid, kind, idx) or {}
        return {"ok": bool(res.get("ok")), "changed": res.get("changed", 0), "version": res.get("version") or "",
                "calls": res.get("calls", 0), "why": str(res.get("why") or "")[:160],
                "rows": [{k: r.get(k) for k in ("id", "src", "tgt", "ko", "from", "why")} for r in res.get("rows") or []][:20]}
    idx = [int(i) for i in row.get("detail_idx") or []][:6]
    if not idx:
        return {"ok": False, "why": "판정할 장 번호가 없어요"}
    res = D.run(item_id, idx)
    from src.db import image_translate_queue_pg as st
    st.state_set(D.STATE_KEY, res)                               # 화면(진단·드로어 줄)이 이 결과를 읽는다
    st.state_set(D.item_key(item_id), res)
    return {"ok": not res.get("error"), "count": res.get("count"), "line": D.line(res), "at": res.get("at"),
            "pages": [{k: p.get(k) for k in ("no", "idx", "verdict", "why", "url")} for p in res.get("pages") or []]}


def _row_key(r: dict) -> tuple:
    return (str(r.get("op")), str(r.get("item_id")), tuple(sorted(r.get("markets") or [])))


def enqueue(row: dict) -> bool:
    """줄 하나를 **덧붙인다**(덮어쓰지 않음) — 같은 op·상품·마켓 줄이 이미 있으면 안 넣는다.
    순찰 57: 읽고-덧쓰기를 한 번에(`state_update`) — 두 인스턴스가 같은 순간 넣어도·꺼내는 중에 넣어도 줄이 안 사라진다."""
    from src.db import image_translate_queue_pg as st
    added = {"ok": False}

    def _fn(cur: dict) -> dict:
        rows = [r for r in cur.get("rows") or [] if isinstance(r, dict)]
        if any(_row_key(r) == _row_key(row) for r in rows):
            return dict(cur, rows=rows)
        added["ok"] = True
        return dict(cur, rows=rows + [dict(row, queued_at=_now())])

    st.state_update(QUEUE_KEY, _fn)
    return added["ok"]


def _pick(rows: List[dict]) -> tuple:
    """`(이번 틱에 돌 줄, 남길 줄)` — 한 틱 `PER_TICK`줄, 무거운 줄은 `HEAVY_PER_TICK`줄(순서 그대로)."""
    pick, keep, heavy = [], [], 0
    for r in rows:
        if len(pick) >= PER_TICK or (r.get("op") in HEAVY_OPS and heavy >= HEAVY_PER_TICK):
            keep.append(r)
            continue
        heavy += r.get("op") in HEAVY_OPS
        pick.append(r)
    return pick, keep


def drain() -> Dict:
    """줄을 통째로 꺼내(먼저 비운다 — 한 번만) 차례로 돌린다. `{picked, rows}`."""
    from src.db import image_translate_queue_pg as st
    if not queue_rows():
        return {"picked": 0, "rows": []}
    # 한 틱에 5줄 — 나머지는 줄에 **남긴다**(10-20 13:30 실측: 7줄 넣었더니 앞 5줄만 돌고 2줄이 조용히 사라졌다)
    # Y14(10-21 08:00·08:10 실측): 사전검증 5건을 두 틱에 몰아 돌렸더니 잡이 겹쳐 인스턴스 437·461MB(상한 420/460) —
    #   3건이 「메모리 여유가 없어요」로 검증 못 함. 무거운 줄(사전검증을 띄우는 줄)은 **한 틱에 하나**만, 나머지는 줄에 남긴다(순서 그대로).
    # 순찰 57: 고르기·남기기를 한 번에(`state_update`) — 꺼내는 사이에 들어온 줄도 남는다.
    got = {"pick": []}

    def _take(cur: dict) -> dict:
        pick, keep = _pick([r for r in cur.get("rows") or [] if isinstance(r, dict)])
        got["pick"] = pick
        return dict(cur, rows=keep)

    st.state_update(QUEUE_KEY, _take)
    pick = got["pick"]
    if not pick:
        return {"picked": 0, "rows": []}
    from src.utils.instance import holder as _holder
    me = _holder()
    inkey = INFLIGHT_PREFIX + me
    track = [dict(r, _state="pending") for r in pick]
    _inflight_set(inkey, me, track)                              # 꺼낸 바로 뒤 — 도중에 죽어도 다음 부팅이 안다
    out = []
    try:
        for i, r in enumerate(pick):
            track[i].update(_state="running", started_at=_now())
            _inflight_set(inkey, me, track)
            heavy_op = r.get("op") in HEAVY_OPS
            mem0 = _mem_mark() if heavy_op else None
            tok = _CURRENT_ROW.set(r)
            try:
                with _job_env(r):
                    res = _run(r)
            except Exception as exc:                             # noqa: BLE001 — 한 줄 실패가 다른 줄을 막지 않는다
                logger.warning("[일회성 작업] %s 실패: %s", r.get("op"), exc)
                res = {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
            finally:
                _CURRENT_ROW.reset(tok)
                if heavy_op:
                    _mem_after(r, mem0)
            track[i]["_state"] = "done"
            out.append({**{k: r.get(k) for k in ("op", "item_id", "kind", "idx", "detail_idx", "reason")}, "result": res, "at": _now()})
            logger.info("[일회성 작업] %s item=%s ok=%s why=%s", r.get("op"), str(r.get("item_id") or "")[:8], res.get("ok"),
                        str(res.get("why") or "")[:120])
        st.state_set(LAST_KEY, {"at": _now(), "rows": out})
        _log_append(out)
    finally:
        try:
            st.state_delete(inkey)                               # 정상으로 끝난 틱은 흔적을 남기지 않는다
        except Exception as exc:                                 # noqa: BLE001
            logger.warning("[일회성 작업] 진행 기록 지우기 실패(계속): %s", exc)
    return {"picked": len(out), "rows": out}


def _log_row(r: dict) -> dict:
    """기록 한 줄 — 결과가 크면(등록 뒤 표 등) 마켓별 성공·사유만 남긴다."""
    res = r.get("result") if isinstance(r.get("result"), dict) else {}
    if len(json.dumps(res, ensure_ascii=False, default=str)) > LOG_ROW_MAX:
        res = {"ok": res.get("ok"), "why": str(res.get("why") or "")[:300], "trimmed": True,
               "rows": [{k: x.get(k) for k in ("market", "success", "ok", "message", "error_code", "error", "no",
                                                "external_product_id", "status")}
                        for x in (res.get("rows") or []) if isinstance(x, dict)][:8]}
    return dict(r, result=res)


def _log_append(out: List[dict]) -> None:
    """순찰 62(10-24 df0f8a8c 스마트스토어 등록 사유 유실): `ops:oneshot:last`는 다음 틱이 덮는다 — 끝난 줄을 최근
    `LOG_MAX`줄 기록(`ops:oneshot:log`)에도 덧붙인다(실패 사유가 다음 틱에 사라지지 않게)."""
    from src.db import image_translate_queue_pg as st
    rows = [_log_row(r) for r in out]
    try:
        st.state_update(LOG_KEY, lambda cur: dict(cur, rows=([x for x in cur.get("rows") or [] if isinstance(x, dict)]
                                                             + rows)[-LOG_MAX:]))
    except Exception as exc:                                     # noqa: BLE001 — 기록 실패가 작업을 막지 않는다
        logger.warning("[일회성 작업] 기록 덧붙이기 실패(계속): %s", exc)


def _mem_mark() -> dict:
    """무거운 줄 시작 — 프로세스 MB · 살아 있는 스레드 수."""
    import threading
    try:
        from src.utils import rss as _rss
        mb = _rss.read_mb()[0]
    except Exception:                                            # noqa: BLE001
        mb = -1
    from src.utils import memprobe as _mp
    return {"mb": mb, "threads": threading.active_count(), "names": {t.name for t in threading.enumerate()},
            "probe": _mp.before()}


def _mem_after(row: dict, mem0: Optional[dict]) -> None:
    """Y15(오너 2026-10-22 「치수 수집 앞뒤 MB·스레드 수 따로」 — 밤새 잡마다 바닥 +8~34MB · 스레드 9→16):
    무거운 줄 하나가 끝난 자리 — 반환(gc+malloc_trim) 전·후 MB, 앞뒤 스레드 수, **새로 생겨 남은 스레드 이름**을 `rss:recent`(op_job)에.
    사전검증 줄은 잡을 띄우고 바로 돌아오므로 그 잡 스레드가 남은 것으로 보인다(잡 자체 기록은 pv_job)."""
    import threading
    try:
        from src.utils import rss as _rss
        from src.utils import render_worker as _rw
        from src.utils import memprobe as _mp
        rel = _rss.release("oneshot:" + str(row.get("op") or ""))
        now = {t.name for t in threading.enumerate()}
        new = sorted(n for n in now - set((mem0 or {}).get("names") or ()))[:8]
        _rw.record("op_job", op=str(row.get("op") or ""), item=str(row.get("item_id") or "")[:8],
                   start_mb=(mem0 or {}).get("mb"), rel_before_mb=rel[0], rel_after_mb=rel[1],
                   threads_before=(mem0 or {}).get("threads"), threads_after=threading.active_count(), new_threads=new,
                   **_mp.after((mem0 or {}).get("probe")))
    except Exception as exc:                                     # noqa: BLE001 — 기록 실패가 줄을 막지 않는다
        logger.debug("[일회성 작업] 메모리 기록 실패: %s", exc)


def _attn_backfill() -> Dict:
    import json
    from src.db import collect_history_pg as chp
    from src.seller_console.attention import _has, last_action, summarize, items as attn_items
    done = 0
    for item_id, uid in chp.ids_for_attention_backfill():
        row = chp.get(item_id, seller_ids={uid} if uid else None) or {}
        try:
            ex = json.loads(row.get("extra_json") or "{}") or {}
        except Exception:                                        # noqa: BLE001
            continue
        attn = summarize(ex, row.get("title") or "", row.get("collected_at") or "")
        n = len(attn_items(dict(ex, attn=attn), row.get("title") or ""))   # 적는 요약과 같은 것으로 센다(Y12-D: 수집 시각 기준 포함)
        la = last_action(ex, row.get("collected_at") or "")
        if chp.set_attention(item_id, la["at"] or row.get("collected_at"), n, attn if _has(attn) else None):
            done += 1
    return {"ok": True, "done": done}


def _review_status(item_id: str, market: str) -> Dict:
    """한 상품·한 마켓 상태 1회 조회 → 성공 값만 기록(`listing_status.remember`). 화면 팝업 「마켓 상태」와 같은 길."""
    import json
    from src.seller_console import collect_history_store as store
    from src.seller_console import listing_status as MS
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    item_id = str(item.get("id") or item_id)
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        return {"ok": False, "why": "상품 기록을 읽지 못했어요"}
    recs = [r for r in MS.records(ex) if r["market"] == market]
    if not recs:
        return {"ok": False, "why": f"등록 기록 없음({market[:30]})"}
    MS.reset_cache()
    row = MS.query(recs[-1])
    saved = False
    if MS.remember(ex, row):
        saved = store.merge_extra(item_id, lambda fresh: MS.remember(fresh, row), seller_ids={uid} if uid else None)
    return {"ok": not row.get("error"), "market": market, "state": row.get("state"), "label": row.get("label"),
            "status_raw": row.get("status_raw"), "comment": str(row.get("comment") or "")[:200],
            "checked_at": row.get("checked_at"), "stale": bool(row.get("stale")),
            "why": str(row.get("stale_note") or row.get("error") or "")[:200], "saved": bool(saved)}


PREVALIDATE_MARKETS = ("coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos")
#: Y13-F — 다시 등록 가능한 마켓(오너가 고른 줄·이월 줄만 — 화면 등록과 같은 입구 `collect_upload`)
REGISTER_MARKETS = PREVALIDATE_MARKETS + ("elevenst",)


def register(item_id: str, markets: List[str], *, confirm_duplicate: bool = False, relist: bool = False,
             via_job: bool = False) -> Dict:
    """화면 「마켓 등록」과 **같은 입구**(`collect_upload`) — 그 상품 계정 세션으로. 중복·위험·도달성 게이트도 그대로 지난다.

    확인 플래그(`confirm_duplicate`·`confirm_warn`)는 **붙이지 않는다** — 막히면 그 답(409 원문)을 그대로 돌려준다.
    Y14-f: 카테고리 바꾸기용 새로 등록(`coupang_relist` register 단계)만 `confirm_duplicate=True` — 옛 번호를 먼저 적은 뒤에.
    """
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    if not uid:
        return {"ok": False, "why": "상품 계정을 알 수 없어요(세션 없이 돌리지 않는다)"}
    mk = [m for m in markets if m in REGISTER_MARKETS]
    if not mk:
        return {"ok": False, "why": "보낼 마켓이 없어요"}
    from flask import session
    from src.order_webhook import app
    from src.seller_console import views as V
    from src.seller_console.product_builder import build_product
    body = {"product": build_product(item, edits={}, seller_id=uid), "markets": mk, "item_id": str(item.get("id") or item_id)}
    if confirm_duplicate:
        body["confirm_duplicate"] = True
    if relist:
        body["relist_register"] = True                   # relist 경로 — `relist_only` 마켓도 이 길로만 올린다
    if via_job:
        js, code = _register_via_job(body, uid)
    else:
        with app.test_request_context("/seller/collect/upload", method="POST", json=body):
            session["user_id"] = uid
            resp = V.collect_upload()
        r, code = (resp if isinstance(resp, tuple) else (resp, 200))
        js = r.get_json() or {}
    rows = [{k: x.get(k) for k in ("market", "success", "message", "error_code", "external_product_id", "channel_product_no")}
            for x in ((js.get("result") or {}).get("results") or []) if isinstance(x, dict)]
    # 빈 배열의 all()은 True다. 요청한 마켓마다 정확히 한 응답이 있어야 성공이라고 말한다.
    complete = len(rows) == len(mk) and sorted(str(x.get("market") or "") for x in rows) == sorted(mk)
    ok = bool(js.get("ok")) and complete and all(x.get("success") is True for x in rows)
    why = str(js.get("error") or "")[:300]
    if not complete and not why:
        why = "등록 결과가 빠져 있어 완료를 확인하지 못했어요"
    return {"ok": ok, "status": code, "markets": mk, "rows": rows, "why": why}


#: 순찰 80 — 화면 등록 잡을 기다리는 상한(초) · 묻는 간격
REG_JOB_WAIT_SEC = 600
REG_JOB_POLL_SEC = 2.0


def _register_via_job(body: dict, uid: str) -> tuple:
    """순찰 80(오너 2026-10-24 「새 등록 잡 경로(#968)로 — 첫 reg_job 측정 표도」): 화면 「등록」과 **같은 잡**(`_upload_start_job`)을
    띄우고 끝날 때까지 기다린다 — 몸통은 잡 스레드, 메모리 측정은 그 잡이 `reg_job`으로 남긴다. `(본문, 상태 코드)`."""
    import time as _t
    from flask import session
    from src.order_webhook import app
    from src.seller_console import views as V
    from src.db import image_translate_queue_pg as st
    with app.test_request_context("/seller/collect/upload", method="POST", json=dict(body, **{"async": True})):
        session["user_id"] = uid
        resp = V._upload_start_job(body)
    r = resp[0] if isinstance(resp, tuple) else resp
    job_id = str((r.get_json() or {}).get("job_id") or "")
    if not job_id:
        return {"ok": False, "error": "등록 잡을 띄우지 못했어요"}, 500
    t0 = _t.monotonic()
    while _t.monotonic() - t0 < REG_JOB_WAIT_SEC:
        cur = st.state_get(V._UP_JOB_KEY + job_id) or {}
        if cur.get("state") in ("done", "interrupted"):
            js = cur.get("body") if isinstance(cur.get("body"), dict) else {"ok": False, "error": "등록 결과가 비었어요"}
            return dict(js, job_id=job_id), int(cur.get("http_status") or 500)
        _t.sleep(REG_JOB_POLL_SEC)
    return {"ok": False, "job_id": job_id, "error": f"등록 잡이 {REG_JOB_WAIT_SEC}초 안에 끝나지 않았어요 — 마켓 상태를 먼저 확인"}, 504


#: 순찰 80(10-24 13:10 실측): 기본 10쪽(1,000개)으론 셰고가 1,466 · 고코스모스 1,187을 다 못 훑었다 — 줄에서 `max_pages`로 늘린다(상한)
NAVER_FIND_MAX_PAGES = 30


def naver_find(words: List[str], stores: Optional[List[str]] = None, max_pages: int = 10) -> Dict:
    """순찰 80 — **읽기만**: 스마트스토어 전 상태에서 상품명 검색(`find_by_name`). 스토어마다 다 훑었는지(`complete`)를 같이 남긴다."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as N
    out = []
    for stn in stores or ("chezgoga", "gocosmos"):
        try:
            res = N(account=stn).find_by_name(words, max_pages=max_pages)
        except Exception as exc:                                 # noqa: BLE001
            res = {"ok": False, "rows": [], "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        out.append({"store": stn, **{k: res.get(k) for k in ("ok", "rows", "total", "scanned", "complete", "error")}})
    return {"ok": all(s.get("ok") for s in out), "words": words, "stores": out,
            "found": sum(len(s.get("rows") or []) for s in out)}


def _sent_excluded(ex: dict, sent_urls: set) -> List[str]:
    """런북 9 — 「등록에서 뺀」 장(제외·판촉)의 주소가 보낸 사진에 끼었나."""
    bad = set()
    for k in ("images_ko", "detail_images_ko", "sku_images_ko"):
        for e in ex.get(k) or []:
            if isinstance(e, dict) and (str(e.get("status") or "") == "excluded" or e.get("use") is False):
                for f in ("url", "src", "orig"):
                    if e.get(f):
                        bad.add(str(e[f]))
    return sorted(bad & sent_urls)[:6]


def register_report(item_id: str, markets: List[str], make_up=None) -> Dict:
    """Y14-g — **등록 뒤 표**(읽기만, 런북 9·11·14): 마켓마다 상품번호(네이버는 채널 번호) · 상태(쿠팡 조회) · 보낸 판매가 ·
    쿠팡 정가 = 판매가 × (1+표시 할인율) 대조 · 상품명 · 카테고리(보낸 값 vs 조회 원문) · 상세 글자 수 · 보낸 사진 수 ·
    뺀 장이 끼었나 · 등록 기록 price/sent가 비지 않았나. 등록 성공 직후 줄로 들어온다(`views._queue_register_report`)."""
    from src.services import coupang_detail_refresh as CDR
    from src.services import ocr_compare_diag as D
    from src.seller_console import listing_status as MS
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    item, _uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        ex = {}
    make_up = make_up or CDR._uploader
    raw = {(str(u.get("market")), str(u.get("product_id") or "")): u for u in ex.get("uploaded") or [] if isinstance(u, dict)}
    rows = []
    for rec in MS.records(ex):
        m = rec["market"]
        if markets and m not in markets:
            continue
        u = raw.get((m, rec["product_id"])) or {}
        sent = u.get("sent") if isinstance(u.get("sent"), dict) else {}
        si = sent.get("sent_images") if isinstance(sent.get("sent_images"), dict) else {}
        urls = {str(x.get("url")) for x in si.get("images") or [] if isinstance(x, dict) and x.get("url")}
        r = {"market": m, "no": rec["shown_no"], "at": rec["at"], "sent_name": sent.get("name") or "",
             "sale_price": sent.get("sale_price"), "sent_category": str(sent.get("category") or ""),
             "detail_chars": sent.get("detail_chars"), "images_sent": si.get("n"),
             "excluded_sent": _sent_excluded(ex, urls), "price_record": bool(u.get("price")), "sent_record": bool(sent)}
        if m.startswith("coupang"):
            try:
                live = make_up(rec["account"]).get_product(rec["product_id"])
            except Exception as exc:                             # noqa: BLE001
                live = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
            if "error" in live:
                r["status"] = f"조회 실패 — {str(live['error'])[:120]}"
            else:
                it = next((x for x in live.get("items") or [] if isinstance(x, dict)), {})
                want = CU.list_price(it.get("salePrice"))
                r.update(status=str(live.get("statusName") or ""), live_name=str(live.get("sellerProductName") or ""),
                         live_category=str(live.get("displayCategoryCode") or ""), live_sale=it.get("salePrice"),
                         live_list=it.get("originalPrice"), list_ok=bool(want) and it.get("originalPrice") == want,
                         category_match=str(live.get("displayCategoryCode") or "") == r["sent_category"])
        else:
            r["status"] = rec.get("state_label") or ""
        rows.append(r)
    return {"ok": bool(rows), "rows": rows, "why": "" if rows else "등록 기록이 없어요"}


def _coupang_relist(item_id: str, step: str, markets: List[str], mode: str = "category") -> Dict:
    """Y14-f — 쿠팡 카테고리 바꾸기(새로 등록 → 승인 → 옛 상품 판매중지). `step` = plan(읽기만) | register | stop_old."""
    from src.seller_console import collect_history_store as store
    from src.services import coupang_relist as CR
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    iid = str(item.get("id") or item_id)
    save = lambda fn: store.merge_extra(iid, fn, seller_ids={uid} if uid else None)     # noqa: E731
    if step == "plan":
        return CR.plan(item, markets, mode=mode)
    if step == "register":
        return CR.register(item, markets, save=save, mode=mode)
    if step == "stop_old":
        return CR.stop_old(item, markets, save=save)
    return {"ok": False, "why": f"모르는 단계({step[:20]})"}


def carry_drain(now=None) -> Dict:
    """Y13-F F1 — 쿠팡 일일 옵션 한도 이월 줄: KST 00:10이 지나면 **한 줄씩** 같은 입구로 다시 등록, 결과는 이월 기록 `log`."""
    from src.services import coupang_option_quota as Q
    due = Q.carry_due(now)
    out = []
    for r in due[:3]:
        try:
            res = register(r["item_id"], [r["market"]])
        except Exception as exc:                                 # noqa: BLE001
            res = {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:160]}", "rows": []}
        row = next((x for x in res.get("rows") or [] if x.get("market") == r["market"]), {})
        Q.carry_done(r["item_id"], r["market"], {
            "success": bool(res.get("ok")) and row.get("success") is True,
            "error_code": row.get("error_code") or ("" if res.get("ok") else "carry_unconfirmed"),
            "message": row.get("message") or res.get("why") or "등록 결과를 확인하지 못했어요"})
        out.append({"item_id": r["item_id"], "market": r["market"], "result": res})
        logger.info("[쿠팡 옵션 이월] item=%s market=%s ok=%s why=%s", r["item_id"][:8], r["market"], res.get("ok"),
                    str(res.get("why") or row.get("message") or "")[:120])
    return {"picked": len(out), "rows": out}


def _login_email(uid: str) -> str:
    """그 계정의 로그인 이메일(정체성 표 첫 줄) — 못 찾으면 ""."""
    try:
        from src.db import user_identities_pg as U
        ems = U.emails_for(uid) or []
        return str(ems[0]) if ems else ""
    except Exception:                                            # noqa: BLE001
        return ""


def _prevalidate(item_id: str, markets: List[str]) -> Dict:
    """화면 「사전검증」과 같은 잡 — 그 상품 계정 세션으로(자격·마켓 키가 그 계정 것). 잡 id만 돌려준다(결과는 잡 기록)."""
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    if not uid:
        return {"ok": False, "why": "상품 계정을 알 수 없어요(세션 없이 돌리지 않는다)"}
    from flask import session
    from src.order_webhook import app
    from src.seller_console import views as V
    from src.seller_console.product_builder import build_product
    mk = [m for m in (markets or PREVALIDATE_MARKETS) if m in PREVALIDATE_MARKETS]
    data = {"product": build_product(item, edits={}, seller_id=uid), "markets": mk, "item_id": str(item.get("id") or item_id)}
    with app.test_request_context("/seller/collect/prevalidate", method="POST"):
        session["user_id"] = uid
        # Y15(야간 미등록 전부 사전검증 — 두 번째 로그인 계정 상품): 그 계정으로 로그인한 화면과 **같은 판정**이 나오게
        #   로그인 이메일도 싣는다(공유 마켓 = 관리자·FAMILY_EMAILS 판정이 이메일을 본다). 없으면 예전처럼 user_id만.
        _em = _login_email(uid)
        if _em:
            session["user_email"] = _em
        dispatcher = V._get_upload_dispatcher()
        if dispatcher is None:
            return {"ok": False, "why": "업로드 디스패처를 불러오지 못했어요"}
        resp = V._pv_start_job(data, mk, dispatcher)
    body = (resp[0] if isinstance(resp, tuple) else resp).get_json() or {}
    return {"ok": bool(body.get("job_id")), "job_id": body.get("job_id") or "", "markets": mk,
            "why": "" if body.get("job_id") else str(body.get("error") or "잡을 띄우지 못했어요")[:160]}


def _image_probe(item_id: str, kind: str, idxs: List[int]) -> Dict:
    """장마다: 저장 주소 → 정리 주소 → 받기(형식·크기·바이트·base64) → 텐센트 입력 정규화 → OCR 1회 응답 코드."""
    import json
    from src.collectors.image_norm import abs_image_url, image_head
    from src.services import ocr_compare_diag as D
    from src.services import detail_image_plan as P
    from src.services import image_translate_tencent as tc
    from src.services import ocr_tencent as O
    item, _uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        ex = {}
    src = {"detail": "detail_images", "gallery": "images"}.get(kind, "detail_images")
    urls = [u for u in (ex.get(src) or []) if isinstance(u, str)]
    rows = []
    for i in idxs:
        if not 0 <= i < len(urls):
            rows.append({"idx": i, "why": "그 번호의 사진이 없어요"})
            continue
        raw_url = urls[i]
        url = P.fix_url(raw_url)
        row = {"idx": i, "stored": raw_url[:160], "url": url[:160], "scheme_fixed": abs_image_url(raw_url) != raw_url.strip(),
               "excluded": P.url_exclusion(url)}
        data, why = tc.fetch_image(url)
        if why:
            row["fetch"] = why
            rows.append(row)
            continue
        fmt, w, h = image_head(data)[:3]
        row.update(fmt=fmt, w=w, h=h, bytes=len(data), b64=int(len(data) * 4 / 3))
        norm, info = P.prepare_for_tencent(data, url=url)
        row["prepare"] = {"sent": "원본 그대로" if norm is data else ("안 보냄" if norm is None else "바꿈"),
                          "note": str(info.get("note") or ""), "bytes": len(norm or b"")}
        if norm is not None:
            r = O.read(norm, max_side=O.AS_IS)
            row["ocr"] = {"ok": bool(r.get("ok")), "code": str(r.get("code") or ""), "why": str(r.get("why") or "")[:160],
                          "lines": len(r.get("lines") or [])}
        rows.append(row)
        data = norm = None
    return {"ok": True, "kind": kind, "rows": rows}


def _thumb_probe(item_id: str) -> Dict:
    """대표 사진(목록 썸네일) + 갤러리 앞 2장을 리퍼러 없이 받아 본다 — 「주소 없음 / 만료(404) / 차단(403) / 너무 큼」을 사실로 가른다."""
    import json
    import requests
    from src.services import ocr_compare_diag as D
    item, _uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        ex = {}
    rep = str(item.get("image_url") or "").strip()
    urls = [rep] + [str(u).strip() for u in (ex.get("images") or []) if str(u or "").strip() and str(u).strip() != rep][:2]
    if not rep:
        return {"ok": True, "why": "대표 사진 주소 없음", "rows": []}
    rows = []
    for u in [x for x in urls if x]:
        try:
            r = requests.get(u, timeout=15, stream=True, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"})
            size = int(r.headers.get("Content-Length") or 0)
            rows.append({"url": u[:200], "status": r.status_code, "type": str(r.headers.get("Content-Type") or "")[:40],
                         "bytes": size})
            r.close()
        except Exception as exc:                                 # noqa: BLE001 — 한 장 실패가 다른 장을 막지 않는다
            rows.append({"url": u[:200], "status": 0, "why": f"{type(exc).__name__}: {str(exc)[:120]}"})
    bad = [x for x in rows if x.get("status") != 200]
    return {"ok": True, "why": "대표 사진 받기 실패" if rows and rows[0].get("status") != 200 else ("일부 실패" if bad else "모두 받음"),
            "rows": rows}


def _carry_requeue(item_ids: List[str]) -> Dict:
    """옛 4013 기록 → `provider_quota` + 이월 대기. 보강 대기(`enrich_state=pending`) 공유 초안만 — 그 밖은 건너뛴 사유를 남긴다."""
    import json
    from src.seller_console import collect_history_store as store
    from src.services import ocr_compare_diag as D
    from src.services import onebound_carry as carry
    rows = []
    for iid in item_ids:
        item, uid = D._item(iid)
        if not item:
            rows.append({"item_id": iid[:8], "why": "상품 없음"})
            continue
        try:
            ex = json.loads(item.get("extra_json") or "{}") or {}
        except Exception:                                        # noqa: BLE001
            ex = {}
        ae = ex.get("auto_enrich") if isinstance(ex.get("auto_enrich"), dict) else {}
        if ex.get("enrich_state") != "pending":
            rows.append({"item_id": iid[:8], "why": f"보강 대기 아님({ex.get('enrich_state') or '없음'})"})
            continue
        reason = str(ae.get("reason") or "")
        kind = "provider_quota" if ("4013" in reason or "已超量" in reason) else str(ae.get("kind") or "")
        now = datetime.now(timezone.utc).isoformat()

        def _fix(fresh, kind=kind, now=now):
            a = fresh.get("auto_enrich") if isinstance(fresh.get("auto_enrich"), dict) else {}
            if a and a.get("kind") != kind:
                fresh["auto_enrich"] = dict(a, kind=kind)
            fresh["carry_requeued_at"] = now
            return True
        store.merge_extra(str(item.get("id") or iid), _fix, seller_ids={uid} if uid else None)
        pos = carry.add(uid, str(item.get("id") or iid), url=str(item.get("url") or ""),
                        share=str(ex.get("share_raw") or ""), kind=kind)
        rows.append({"item_id": iid[:8], "kind": kind, "position": pos})
    return {"ok": True, "queued": sum(1 for r in rows if r.get("position")), "rows": rows, "waiting": carry.count()}


def _retranslate(item_id: str, pages: List[tuple]) -> Dict:
    """「다시 번역」과 같은 계획 → 적힌 장만 접수(없으면 계획 전부). 계획 밖 장은 사유(스페이서·아이콘·중복·상한·이미 번역됨)."""
    import json
    from src.services import ocr_compare_diag as D
    from src.services import image_translate_auto as A
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        ex = {}
    plan = A.translate_plan(ex, retry=True)
    want = set(pages)
    send = [(k, i) for k, i, _w in plan["send"] if not want or (k, i) in want]
    why = {}
    for label, lst in plan["skip"].items():
        for k, i in lst:
            why[(k, i)] = A.SKIP_LABEL.get(label, label)
    for k, i in plan["no_text"]:
        why[(k, i)] = "글자 없음(텐센트)"
    q = A._q()
    new = q.enqueue(uid or str(item.get("seller_id") or ""), str(item.get("id") or item_id), send) if send else 0
    again = q.requeue_pages(str(item.get("id") or item_id), send) if send else 0
    if new or again:
        A.kick()
    rows = [{"kind": k, "idx": i, "sent": (k, i) in set(send), "why": "" if (k, i) in set(send) else why.get((k, i), "계획 밖")}
            for k, i in (sorted(want) if want else send)]
    return {"ok": True, "accepted": new + again, "waiting": max(0, len(send) - new - again), "rows": rows}


def _ocr_box_count(url: str):
    """그 장의 텐센트 OCR 글자 상자 수 — `(n | None, 사유)`. 큰 장은 축소 사본으로 보낸다(Y13-D 3 — 원본을 풀지 않는다)."""
    from src.services import image_edit as IE
    from src.services import ocr_tencent as O
    raw, why = IE.work_bytes(url)
    if not raw:
        return None, why or "사진을 받지 못했어요"
    got = O.read_boxes(raw)
    if not got.get("ok"):
        return None, str(got.get("why") or "OCR 실패")[:120]
    return len(got.get("boxes") or []), ""


def pick_rep(counts: Dict[int, object], prefer: int = -1) -> int:
    """0상자 장 중에서 — `prefer`가 그 안에 있으면 그것, 아니면 앞 번호. 0상자 장이 없으면 -1(대표를 바꾸지 않는다)."""
    zero = [i for i, n in sorted(counts.items()) if n == 0]
    if not zero:
        return -1
    return prefer if prefer in zero else zero[0]


#: Y14(오너 2026-10-21 SPORTLINK) — 오너 결정 줄이 바꿔 넣을 수 있는 칸(나가는 값만 · 수집 원문 `title`·`tags`는 안 건드림).
#: Y15(오너 2026-10-22 바퀴 의자 「아기 전용 의자」): `child_product` = 어린이제품 표시(사유 한 줄) — 등록 경로 보류 「오너 확인」.
#:   인증 규칙은 단정하지 않는다(무엇이 필요한지는 오너가 확인). 빈 값이면 표시를 푼다.
OWNER_FIELDS = ("title_ko", "coupang_name", "keywords", "detail_head_note", "child_product")


def dims_fetch(item_id: str, *, onebound: bool = True, ob_call=None, ocr=None) -> Dict:
    """Y14(오너 2026-10-21) — 치수 서버 수집(`dims_fetch` 모듈) → 상품 기록 `dims_auto` 칸만 덧대 저장. 표 한 줄을 돌려준다."""
    from src.seller_console import collect_history_store as store
    from src.services import dims_fetch as DF
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    res = DF.fetch(item, ob_call=ob_call, ocr=ocr, onebound=onebound)
    da = res["dims_auto"]

    def _fn(fresh):
        fresh["dims_auto"] = da
        return True
    saved = bool(store.merge_extra(str(item.get("id") or item_id), _fn, seller_ids={uid} if uid else None))
    return {"ok": saved, "dims_cm": da.get("dims_cm"), "confidence": da.get("confidence"), "label": da.get("label"),
            "line": DF.line(da), "ocr_pages": da.get("ocr_pages"), "onebound_calls": da.get("onebound_calls"),
            "sources": [{k: s.get(k) for k in ("label", "dims_cm", "seen", "why")} for s in da.get("sources") or []]}


def check_item(item_id: str, markets: List[str], *, fetch=None, prevalidate=None) -> Dict:
    """Y15(오너 2026-10-21 야간 「미등록 전부 3호 체크리스트 사전검증 · 한 틱에 하나」) — 한 틱에 무거운 일 **하나만**:
    가구·대형이라 치수 게이트에 걸리는데 서버 치수 수집이 아직이면 이번 틱엔 `dims_fetch`만 하고 사전검증 줄을 **맨 뒤에** 건다.
    아니면 바로 사전검증. 등록·전송은 하지 않는다."""
    import json
    from src.services import dims_fetch as DF
    from src.services import ocr_compare_diag as D
    item, _uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        ex = {}
    item_id = str(item.get("id") or item_id)
    if DF.should_fetch(ex):
        d = (fetch or dims_fetch)(item_id)
        queued = enqueue({"op": "prevalidate", "item_id": item_id, "markets": list(markets or PREVALIDATE_MARKETS),
                          "reason": "check_item — 치수 수집 뒤"})
        return {"ok": bool(d.get("ok")), "step": "dims_fetch", "dims": d, "prevalidate_queued": queued,
                "why": str(d.get("why") or "")[:160]}
    r = (prevalidate or _prevalidate)(item_id, markets)
    return dict(r, step="prevalidate")


def option_retry(item_id: str) -> Dict:
    """Y15(오너 2026-10-22 「왼쪽 마우스 스탠드 옵션 미해석 2개 번역 재시도 1회」) — 화면 「한국어로 번역」과 같은 함수
    (`option_translate_auto.translate_now`: 규칙 → 번역기, 일 상한 안) **한 번**. 못 옮긴 값은 그 값의 사유가 그대로 남는다."""
    from src.services import ocr_compare_diag as D
    from src.services import option_translate_auto as OT
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    iid = str(item.get("id") or item_id)
    res = OT.translate_now(uid, iid)
    left = {}
    try:
        _row, ex = OT._load(iid, uid)
        left = dict(((ex or {}).get("option_translate_diag") or {}).get("values") or {})
    except Exception:                                            # noqa: BLE001
        pass
    return {"ok": res.get("status") == "done", "status": res.get("status"), "why": str(res.get("reason") or "")[:240],
            "sent": res.get("sent", 0), "left": {k: str(v)[:160] for k, v in list(left.items())[:6]}}


def _undiscard(item_id: str, why: str) -> Dict:
    """Y15(오너 2026-10-22 순찰 32 KYLIA 15df5bbf 「되살리기」): `_discard`를 되돌린다 — `extra.discarded`를 빼고 그 기록은
    `discard_log`에 남긴다(언제·왜 버렸고 언제·왜 되살렸나). 수집 원본은 손대지 않는다."""
    from datetime import datetime as _dt, timezone as _tz
    from src.seller_console import collect_history_store as store
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    prev: Dict = {}

    def _fn(fresh):
        d = fresh.get("discarded")
        if not isinstance(d, dict):
            return False
        prev.update(d)
        fresh.pop("discarded", None)
        fresh.setdefault("discard_log", []).append({"discarded": d, "restored_at": _dt.now(_tz.utc).isoformat(),
                                                    "by": "owner-oneshot", "why": (why or "오너 결정")[:120]})
        return True
    ok = bool(store.merge_extra(str(item.get("id") or item_id), _fn, seller_ids={uid} if uid else None))
    return {"ok": ok, "why": "" if ok else "버린 기록이 없거나 저장하지 못했어요", "was": prev}


def _discard(item_id: str, why: str) -> Dict:
    """Y14(오너 2026-10-21 리브러쉬 「등록 안 함 · 목록 버리기」) — 화면 「버리기」와 같은 기록(`extra.discarded`) · DB 삭제 아님."""
    from datetime import datetime as _dt, timezone as _tz
    from src.seller_console import collect_history_store as store
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}

    def _fn(fresh):
        if isinstance(fresh.get("discarded"), dict):
            return False
        fresh["discarded"] = {"at": _dt.now(_tz.utc).isoformat(), "by": "owner-oneshot", "why": (why or "오너 결정")[:80]}
        return True
    ok = bool(store.merge_extra(str(item.get("id") or item_id), _fn, seller_ids={uid} if uid else None))
    return {"ok": ok, "why": "" if ok else "이미 버렸거나 저장하지 못했어요"}


#: Y14(오너 2026-10-21 SPORTLINK 「사진 3 제외」) — 오너가 뺀 장. `risk_exclude`와 같은 칸(등록 빌더·검사가 이미 보는 칸)에 적되
#   「위험 —」으로 시작하지 않게 — 자동 되살리기(`heal_prop_excludes`·`heal_retext_excludes`)는 「위험 —」만 푼다.
OWNER_EXCLUDE_PREFIX = "오너 결정 — 사진째 뺌"
_KIND_KEY = {"gallery": "images_ko", "detail": "detail_images_ko", "sku": "sku_images_ko"}


def _owner_exclude(ex: dict, pages: List[tuple], why: str, by: str) -> List[str]:
    out = []
    for kind, idx in pages:
        key = _KIND_KEY.get(kind)
        if not key:
            continue
        lst = ex.setdefault(key, [])
        e = next((x for x in lst if isinstance(x, dict) and int(x.get("idx", -1)) == idx), None)
        if e is None:
            e = {"idx": idx, "kind": kind}
            lst.append(e)
        e["risk_exclude"] = f"{OWNER_EXCLUDE_PREFIX}({(why or '오너 결정')[:60]})"
        e["owner_exclude"] = {"at": _now(), "by": by, "why": (why or "")[:80]}
        out.append(f"{kind} {idx + 1}")
    return out


def _owner_option_overrides(ex: dict, wanted: dict, uid: str) -> Dict:
    """순찰 42(오너 2026-10-23 d5af2185): 오너가 정한 옵션 값 — 편집 화면 옵션 탭과 **같은 칸**(`option_value_overrides`, 원문 값 → 한국어,
    `option_ko`의 1순위). 원문(`options[].values`·`skus[].spec`)은 손대지 않는다. 지금 옵션에 없는 원문 값은 넣지 않고 사유를 남긴다.
    앞 값은 `owner_fields_log`에(되돌리기 재료)."""
    have = {str(v) for o in (ex.get("options") or []) if isinstance(o, dict) for v in (o.get("values") or [])}
    ov = dict(ex.get("option_value_overrides") or {}) if isinstance(ex.get("option_value_overrides"), dict) else {}
    done, prev = [], {}
    for raw, ko in list(wanted.items())[:30]:
        raw, ko = str(raw or "").strip(), str(ko or "").strip()
        if not raw or not ko:
            continue
        if raw not in have:
            done.append({"value": raw[:40], "ok": False, "why": "지금 옵션에 없는 값"})
            continue
        prev[raw] = ov.get(raw)
        ov[raw] = ko
        done.append({"value": raw[:40], "ok": True, "set": ko})
    if prev:
        ex["option_value_overrides"] = ov
        ex.setdefault("owner_fields_log", []).append({"at": _now(), "by": uid, "set": ["option_value_overrides"],
                                                      "before": {"option_value_overrides": prev}})
    return {"set": sum(1 for d in done if d["ok"]), "rows": done}


def _owner_decision(item_id: str, rep: dict, strip: List[str], pixels: str, markets: List[str], *,
                    fields: Optional[dict] = None, strip_keep: Optional[List[str]] = None,
                    exclude_images: Optional[List[tuple]] = None, exclude_why: str = "",
                    relist_only: Optional[List[str]] = None, option_overrides: Optional[dict] = None) -> Dict:
    import json
    from src.services import ocr_compare_diag as D
    from src.services import risk_gate as R
    from src.seller_console import collect_history_store as store
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    if not uid:
        return {"ok": False, "why": "상품 계정을 알 수 없어요"}
    iid = str(item.get("id") or item_id)
    ex = json.loads(item.get("extra_json") or "{}") or {}
    out: Dict = {"ok": True}
    originals = [u for u in ex.get("images") or [] if u]
    if rep:
        cands = [int(i) for i in rep.get("candidates") or [] if 0 <= int(i) < len(originals)][:6]
        counts, whys = {}, {}
        for i in cands:
            n, why = _ocr_box_count(originals[i])
            counts[i] = n
            if why:
                whys[i] = why
        pick = pick_rep(counts, int(rep.get("prefer", -1)))
        if pick > 0:
            ex["rep_image"] = originals[pick]            # 「이 장을 대표로」와 같은 칸(원본 주소)
        elif pick == 0:
            ex.pop("rep_image", None)
        # Y14(오너 2026-10-21 SPORTLINK): 글자 0상자 장이 없으면 「대표 사진 바꾸기 필요」 보류(쿠팡) — 재지 못한 장만 있으면 말하지 않는다
        if pick < 0 and counts and all(isinstance(n, int) for n in counts.values()):
            ex["rep_need_change"] = (f"후보 {len(counts)}장 모두 글자가 있어요(상자 "
                                     + ", ".join(f"{int(k) + 1}번 {n}개" for k, n in sorted(counts.items())) + ")")
        elif pick >= 0:
            ex.pop("rep_need_change", None)
        out["rep"] = {"counts": {str(k): v for k, v in counts.items()}, "why": {str(k): v for k, v in whys.items()},
                      "picked": pick, "rule": "0상자 장 · 여럿이면 지정 장(prefer)"}
    if fields:
        # Y14: 오너가 정한 나가는 값 — 상품명(오너 초안) · 검색어 · 상세 첫 줄 고정 문구. 앞 값은 기록에 남긴다(되돌리기 재료)
        prev = {}
        for k in OWNER_FIELDS:
            if k not in fields:
                continue
            v = fields[k]
            v = [str(x).strip() for x in v if str(x).strip()][:20] if k == "keywords" and isinstance(v, list) else str(v or "").strip()
            prev[k] = ex.get(k)
            ex[k] = v
        ex.setdefault("owner_fields_log", []).append({"at": _now(), "by": uid, "set": sorted(prev), "before": prev})
        out["fields"] = sorted(prev)
    if option_overrides:
        out["option_overrides"] = _owner_option_overrides(ex, option_overrides, uid)
    done = []
    if strip or strip_keep:
        sc = R.scan(ex)
        for lab in strip:
            h = next((x for x in sc["hits"] if x["label"] == lab or x["key"] == lab), None)
            if h is None:
                done.append({"label": lab, "ok": False, "why": "지금 위험 항목에 없음"})
                continue
            res = R.decide(ex, h["key"], "strip", by=uid, pixels=pixels)
            done.append({"label": h["label"], "ok": bool(res.get("ok")), "why": res.get("error") or "",
                         "images": R.strip_image_line(ex, h), "where": R.where_line(h)})
        # Y14: 글자만 고칠 항목(블랙리스트 「애플」 — 사진은 앞 호환 표기 결정이 글자 고치기로 맡았다. 사진 쪽 원본 되살리기가
        #   방금 다시 그린 상자를 원문으로 돌리지 않게) — 앞 결정 뒤 다시 재서
        sc2 = R.scan(ex) if strip_keep else {"hits": []}
        for lab in strip_keep or []:
            h = next((x for x in sc2["hits"] if x["label"] == lab or x["key"] == lab), None)
            if h is None:
                done.append({"label": lab, "ok": True, "why": "앞 결정 뒤엔 남은 곳이 없음"})
                continue
            res = R.decide(ex, h["key"], "strip", by=uid, pixels="keep")
            done.append({"label": h["label"], "ok": bool(res.get("ok")), "why": res.get("error") or "", "text_only": True,
                         "where": R.where_line(h)})
        out["strip"] = done
    if exclude_images:
        out["excluded"] = _owner_exclude(ex, exclude_images, exclude_why, uid)
    if relist_only:
        # Y14(오너 2026-10-21 SPORTLINK 쿠팡 고가네 — 옛 16397045086): 이 마켓은 「마켓 등록」으로 올리지 않는다 — relist(새로 등록 →
        #   승인 → 옛 상품 판매중지) 경로로만. 등록 입구(`collect_upload`)가 막는다.
        ex["relist_only"] = sorted(set((ex.get("relist_only") or []) + list(relist_only)))
        out["relist_only"] = ex["relist_only"]
    ex.pop("pv_ready", None)                             # 바꿨으니 지난 「준비 완료」는 낡았다 — 아래 사전검증이 다시 적는다
    ok = bool(store.update(iid, seller_ids={uid}, extra_json=json.dumps(ex, ensure_ascii=False)))
    out["saved"] = ok
    if not ok:
        return dict(out, ok=False, why="저장하지 못했어요")
    out["prevalidate"] = _prevalidate(iid, markets)
    return out


def _relist_fix(item_id: str, row: dict) -> Dict:
    """Y13-G 3 — 등록본 상품명·카테고리 한 번에 고치기(`relist_fix`). 결과는 등록 기록 `uploaded[].relist_fix`."""
    from src.seller_console import collect_history_store as store
    from src.services import ocr_compare_diag as D
    from src.services import relist_fix as RF
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    iid = str(item.get("id") or item_id)
    name = str(row.get("name") or "").strip()
    if not name:
        return {"ok": False, "why": "새 상품명이 없어요"}
    return RF.run(item, [str(m) for m in (row.get("markets") or []) if m], name=name,
                  coupang_category=str(row.get("coupang_category") or ""), naver_category=str(row.get("naver_category") or ""),
                  detail_markets=[str(m) for m in (row.get("detail_markets") or []) if m],
                  save=lambda fn: store.merge_extra(iid, fn, seller_ids={uid} if uid else None))


def _coupang_refresh(item_id: str, markets: List[str]) -> Dict:
    """Y13-G 4 — 쿠팡 등록본 상세 다시 보내기(화면 「지금 갱신」과 같은 함수 `refresh_item` — 승인필요 PUT = 재심사)."""
    from src.services import coupang_detail_refresh as CDR
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    iid = str(item.get("id") or item_id)
    rows = CDR.refresh_item(item, seller_id=uid, markets=markets or None, save=CDR.store_save(iid, {uid} if uid else None))
    return {"ok": bool(rows) and all(r.get("ok") for r in rows),
            "rows": [{k: r.get(k) for k in ("market", "sid", "sent", "ok", "state", "error", "market_status")} for r in rows],
            "why": "" if rows else "쿠팡 등록 기록이 없어요"}


def coupang_inspect(item_id: str, markets: List[str], make_up=None) -> Dict:
    """Y13-H 2 — **읽기만**: 쿠팡 등록본 조회 원문에서 정가·판매가·상품명·카테고리·브랜드와 옵션의 바코드·속성 칸.
    GTIN 경고(「GTIN 속성이 유효하지 않습니다」 — 수정 PUT 응답 SUCCESS에 붙음)가 어느 칸에서 나는지 보려고. 아무것도 안 바꾼다."""
    from src.services import coupang_detail_refresh as CDR
    from src.services import ocr_compare_diag as D
    item, _uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        ex = {}
    make_up = make_up or CDR._uploader
    rows = []
    for u in CDR.coupang_uploads(ex):
        if markets and u["market"] not in markets:
            continue
        r = {"market": u["market"], "sid": u["sid"]}
        try:
            data = make_up(u["account"]).get_product(u["sid"])
        except Exception as exc:                                 # noqa: BLE001
            data = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        if not isinstance(data, dict) or data.get("error"):
            r["error"] = str((data or {}).get("error") if isinstance(data, dict) else data)[:300]
            rows.append(r)
            continue
        r.update(name=str(data.get("sellerProductName") or ""), category=str(data.get("displayCategoryCode") or ""),
                 brand=str(data.get("brand") or ""), status=str(data.get("statusName") or ""),
                 items=[{"name": str(it.get("itemName") or "")[:40], "originalPrice": it.get("originalPrice"),
                         "salePrice": it.get("salePrice"), "barcode": it.get("barcode"),
                         "emptyBarcode": it.get("emptyBarcode"), "emptyBarcodeReason": it.get("emptyBarcodeReason"),
                         "modelNo": it.get("modelNo"),
                         "attributes": [[str(a.get("attributeTypeName") or ""), str(a.get("attributeValueName") or "")]
                                        for a in it.get("attributes") or [] if isinstance(a, dict)][:40]}
                        for it in (data.get("items") or [])[:12] if isinstance(it, dict)])
        rows.append(r)
    return {"ok": bool(rows) and not any(r.get("error") for r in rows), "rows": rows,
            "why": "" if rows else "쿠팡 등록 기록이 없어요"}


def _naver_resend(item_id: str, markets: List[str]) -> Dict:
    """Y13-H — 네이버 등록본 상세 본문 다시 보내기(화면 「본문 다시 보내기」와 같은 입구 — 그 상품 계정 세션으로)."""
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    if not uid:
        return {"ok": False, "why": "상품 계정을 알 수 없어요(세션 없이 돌리지 않는다)"}
    from flask import session
    from src.order_webhook import app
    from src.seller_console import views as V
    iid = str(item.get("id") or item_id)
    rows = []
    for m in [x for x in markets if x.startswith("smartstore")]:
        with app.test_request_context(f"/seller/collect/{iid}/naver-resend-detail", method="POST", json={"market": m}):
            session["user_id"] = uid
            resp = V.collect_naver_resend_detail(iid)
        r, code = (resp if isinstance(resp, tuple) else (resp, 200))
        js = r.get_json() or {}
        rows.append({"market": m, "ok": bool(js.get("ok")), "status": code, "images": js.get("images"),
                     "text_chars": js.get("text_chars"), "error": str(js.get("error") or "")[:300]})
    return {"ok": bool(rows) and all(x["ok"] for x in rows), "rows": rows, "why": "" if rows else "네이버 마켓이 없어요"}
