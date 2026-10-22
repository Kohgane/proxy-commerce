"""Y15 순찰 32(오너 2026-10-22) — KYLIA 되살리기 · 메모리 측정(gc type 증가·모듈 캐시) · 리뷰 보상 옵션 · 괄호 단위 치수."""
import json

import pytest


@pytest.fixture(autouse=True)
def _probe_on(monkeypatch):
    monkeypatch.setenv("MEMPROBE", "1")                           # conftest는 꺼 둔다 — 이 파일은 측정 자체를 본다


# ── 1. 되살리기(undiscard) ──────────────────────────────────────────────────────

def test_undiscard_clears_discarded_and_keeps_log(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "KYLIA 흔들의자", "discarded": {"at": "2026-10-22T07:50:00+00:00", "by": "owner-oneshot",
                                                   "why": "오너 결정 10-22 — 등록 안 함(중고)"}}
    saved = {}
    monkeypatch.setattr(D, "_item", lambda iid: ({"id": "15df5bbf-full"}, "u2"))

    def _merge(iid, fn, seller_ids=None):
        fresh = json.loads(json.dumps(ex))
        if not fn(fresh):
            return False
        saved.update(iid=iid, ex=fresh, sids=seller_ids)
        return True
    monkeypatch.setattr(S, "merge_extra", _merge)
    r = O._run({"op": "undiscard", "item_id": "15df5bbf", "why": "中古 오역으로 인한 오판 — 오너 되살리기"})
    assert r["ok"] and r["was"]["why"].endswith("(중고)")
    assert "discarded" not in saved["ex"] and saved["sids"] == {"u2"}
    log = saved["ex"]["discard_log"][0]
    assert log["discarded"]["why"].endswith("(중고)") and "中古 오역" in log["why"]
    ex.pop("discarded")                                           # 버린 기록이 없으면 아무것도 안 바꾼다
    assert O._run({"op": "undiscard", "item_id": "15df5bbf"})["ok"] is False


# ── 2. 메모리 측정만 ─────────────────────────────────────────────────────────────

class _StayedBehind:                                              # 이 테스트만 만드는 type — 다른 객체가 풀려도 개수가 흔들리지 않는다
    def __init__(self, i):
        self.i = i


def test_memprobe_type_growth_names_what_stayed():
    from src.utils import memprobe as M
    snap = M.before()
    kept = [_StayedBehind(i) for i in range(30000)]               # 잡 뒤에도 남는 것(상위 10에 들 만큼)
    rows = M.type_growth(snap)
    top = {r[0]: r for r in rows}
    assert top["_StayedBehind"][1] == 30000 and top["_StayedBehind"][2] > 0
    assert len(rows) <= 10
    del kept


def test_memprobe_module_caches_lists_unbounded_dicts_and_lru(monkeypatch):
    import functools
    import sys
    import types
    from src.utils import memprobe as M
    mod = types.ModuleType("src._probe_fake")
    mod.__file__ = "src/_probe_fake.py"
    mod._BIG = {i: "x" * 100 for i in range(500)}

    @functools.lru_cache(maxsize=64)
    def _f(x):
        return x
    for i in range(3):
        _f(i)
    mod._f = _f
    monkeypatch.setitem(sys.modules, "src._probe_fake", mod)
    rows = {r["name"]: r for r in M.module_caches()}
    big = rows["src._probe_fake._BIG"]
    assert big["kind"] == "dict" and big["len"] == 500 and big["kb"] > 50 and big["maxsize"] is None   # 상한 없음 = 후보
    lru = rows["src._probe_fake._f"]
    assert lru["kind"] == "lru_cache" and lru["len"] == 3 and lru["maxsize"] == 64


def test_memprobe_trace_only_when_env(monkeypatch):
    from src.utils import memprobe as M
    monkeypatch.delenv("MEM_TRACE", raising=False)
    assert "trace" not in M.after(M.before())
    monkeypatch.setenv("MEM_TRACE", "1")
    s = M.before()
    blob = [bytearray(10000) for _ in range(50)]
    out = M.after(s)
    assert out.get("trace") and isinstance(out["trace"][0][0], str)
    import tracemalloc
    assert not tracemalloc.is_tracing()                           # 켠 것은 끄고 나온다(이후 테스트·잡이 느려지지 않게)
    del blob


def test_op_job_record_carries_type_growth_and_caches(monkeypatch):
    from src.services import oneshot_ops as O
    from src.db import image_translate_queue_pg as st
    from src.utils import rss, render_worker
    store = {O.QUEUE_KEY: {"rows": [{"op": "dims_fetch", "item_id": "x1"}]}}
    monkeypatch.setattr(st, "state_get", lambda k: store.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(rss, "release", lambda reason="": (200, 190))
    recs = []
    monkeypatch.setattr(render_worker, "record", lambda kind, **kw: recs.append(dict(kw, kind=kind)))
    monkeypatch.setattr(O, "_run", lambda row: {"ok": True})
    O.drain()
    assert recs and "types" in recs[0] and "caches" in recs[0]


# ── 4. 리뷰 보상 옵션(晒美图奖励10元) ───────────────────────────────────────────

def test_review_reward_sku_is_not_an_option_and_axis_rebuilds():
    """운영 10-22 08:00 사전검증: 옵션 값 「晒美图奖励10元」(리뷰 사진 보상)이 「미해석」 보류 — 옵션 값이 아니다."""
    from src.collectors import ko_polish as kp
    from src.seller_console.upload_dispatcher import drop_non_option_values, unresolved_option_values
    for v in ("晒美图奖励10元", "好评返现5元", "晒单返红包", "好评有礼"):
        assert kp.non_option(v), v
    assert kp.non_option("白色") == []
    pd = {"options": [{"name": "颜色分类", "values": ["白色", "黑色", "晒美图奖励10元"], "values_ko": ["화이트", "블랙", ""]}],
          "skus": [{"spec": ["白色"], "price": 10}, {"spec": ["黑色"], "price": 10}, {"spec": ["晒美图奖励10元"], "price": 1}]}
    out = drop_non_option_values(pd)
    assert out["options"][0]["values"] == ["白色", "黑色"] and out["options"][0]["values_ko"] == ["화이트", "블랙"]
    assert [k["spec"] for k in out["skus"]] == [["白色"], ["黑色"]]
    assert unresolved_option_values(pd) == []                       # 미해석으로 세지 않는다


# ── 5. 괄호 단위 치수 「485X300X580(mm)」 ───────────────────────────────────────

def test_parenthesized_mm_unit_is_read_as_mm():
    """운영 10-22 08:30 온풍기 e14acd34: 「机身尺寸(长X宽X高) 485X300X580(mm)」 → 485×300×580cm로 읽어 「한 변 580cm 대형화물」."""
    from src.seller_console import shipping_ratio as S
    from src.services import dims_fetch as D
    t = "机身尺寸(长X宽X高) 485X300X580(mm)"
    assert S._read_size({"title": "x", "description": t})["dims_cm"] == [48.5, 30.0, 58.0]
    assert D.parse(t)["dims_cm"] == [48.5, 30.0, 58.0]
    assert S._read_size({"title": "x", "description": "485X300X580 MM"})["dims_cm"] == [48.5, 30.0, 58.0]
    assert S._read_size({"title": "x", "description": "100×114×74（毫米）"})["dims_cm"] == [10.0, 11.4, 7.4]
    assert S._read_size({"title": "x", "description": "尺寸 60x50x45cm"})["dims_cm"] == [60.0, 50.0, 45.0]   # 그대로


def test_module_caches_never_calls_foreign_objects(monkeypatch):
    """전체 스위트 실측: `hasattr(x, "cache_info")`는 Mock에도 참 → 측정이 테스트가 끼운 Mock을 **불러** 호출 횟수 계약(「AI 두 번째 호출 없음」)이
    깨졌다. 진짜 lru 래퍼·순수 컨테이너만 본다."""
    import sys
    import types
    from unittest.mock import MagicMock
    from src.utils import memprobe as M
    mod = types.ModuleType("src._probe_mock")
    mod.__file__ = "src/_probe_mock.py"
    mod.call_ai = MagicMock()
    monkeypatch.setitem(sys.modules, "src._probe_mock", mod)
    M.module_caches()
    M.after(M.before())
    assert mod.call_ai.call_count == 0 and mod.call_ai.mock_calls == []


def test_memprobe_off_switch(monkeypatch):
    from src.utils import memprobe as M
    monkeypatch.setenv("MEMPROBE", "0")
    assert M.before() == {"off": True} and M.after(M.before()) == {}
