"""오너 11-27 감독 1 — 운영 진단을 CC가 스스로 읽는 길. 계약.

이 길로 절대 안 나가는 것: 쓰기(상품 행 저장·등록·재개·사진 다시 보내기) · 마켓 전송 · 개인정보(주문자·수령인·주소·전화·이메일·통관부호).
적는 곳은 `app_state diag:snap:*` 하나뿐 · 모르는 진단 이름은 거부 · 사전검증 진단은 드라이(행에 쓰지 않음).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def state(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    writes = []

    def _set(k, v):
        writes.append(k)
        s[k] = v
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", _set)
    s["_writes"] = writes
    return s


@pytest.fixture
def no_writes(monkeypatch):
    """상품 행·마켓 쓰기 함수가 불리면 바로 실패한다."""
    def boom(*a, **k):
        raise AssertionError("진단이 쓰기를 불렀다")
    from src.seller_console import collect_history_store as chs
    for f in ("update", "merge_extra", "append", "delete_ids", "delete"):
        monkeypatch.setattr(chs, f, boom)
    from src.services import smartstore_relist as SR
    for f in ("start", "stop", "start_build", "_resume_one"):
        monkeypatch.setattr(SR, f, boom)
    from src.seller_console import upload_dispatcher as UD
    monkeypatch.setattr(UD.UploadDispatcher, "upload", boom, raising=False)
    from src.services import taobao_reenrich_batch as TB
    monkeypatch.setattr(TB, "start", boom)
    return boom


def test_sanitize_drops_personal_fields_and_patterns():
    from src.services.diag_export import sanitize
    out = sanitize({"name": "OKNIFE 칼", "buyer_name": "홍길동", "receiver": {"name": "김철수"}, "shipping_address": "서울시 …",
                    "phone": "010-1234-5678", "rows": [{"note": "연락 010 9876 5432 · kim@example.com · P123456789012", "주소": "부산"}],
                    "price": 36372})
    assert out == {"name": "OKNIFE 칼", "rows": [{"note": "연락 <가림> · <가림> · <가림>"}], "price": 36372}


def test_unknown_name_refused_and_only_snap_key_written(state):
    from src.services import diag_export as DX
    assert DX.snapshot("orders_raw")["ok"] is False and not state["_writes"]
    with pytest.raises(ValueError):
        DX.build("register")


@pytest.mark.parametrize("name,arg", [("restarts", ""), ("reenrich", ""), ("relist", "chezgoga"), ("jobs", ""), ("sources", "90")])
def test_db_backed_snapshots_are_read_only(state, no_writes, monkeypatch, name, arg):
    from src.services import diag_export as DX
    from src.utils import restart_log as RL
    monkeypatch.setattr(RL, "rows", lambda: [{"at": "2026-11-26T09:10:02+00:00", "kind": "boot", "pid": 637, "reason": "x"}])
    state["smartstore_relist:plan:chezgoga"] = {"at": "t", "on": 1, "skip": 1, "rows": [
        {"channel_no": "1", "name": "켤 것", "action": "on", "exclude": []},
        {"channel_no": "2", "name": "뺄 것", "action": "skip", "exclude": ["knife"], "exclude_detail": ["사시미칼"]}]}
    out = DX.snapshot(name, arg)
    assert out["ok"], out
    assert [k for k in state["_writes"]] == [DX.key_for(name, arg)]                    # 적는 곳은 진단 칸 하나
    snap = state[DX.key_for(name, arg)]
    assert snap["ok"] and snap["name"] == name
    if name == "relist":
        assert snap["data"]["samples"]["knife"][0]["name"] == "뺄 것" and snap["data"]["plan"]["on"] == 1


def test_market_reads_are_stubbed_and_prevalidate_is_dry(state, no_writes, monkeypatch):
    from src.services import diag_export as DX
    from src.services import admin_diag as AD
    monkeypatch.setattr(AD, "store_audit", lambda nos: {"stores": [{"store": "chezgoga", "buyer_phone": "010-1111-2222"}]})
    monkeypatch.setattr(AD, "store_verdict", lambda d: "ok")
    assert DX.snapshot("stores", "123")["ok"] and "buyer_phone" not in str(state[DX.key_for("stores", "123")])
    import src.seller_console.collect_history_store as chs
    monkeypatch.setattr(chs, "get", lambda iid, **k: {"id": iid, "title": "OKNIFE", "url": "https://www.amazon.com/dp/B0C38WV1F6",
                                                      "seller_id": "s", "extra_json": "{}"} if iid == "it1" else None)
    from src.seller_console import views as V
    seen = {}

    def prep(data, pd):
        from flask import g
        seen["dry"] = bool(getattr(g, "kgp_pv_dry", False))
        return pd, None
    monkeypatch.setattr(V, "_pv_prepare", prep)
    import src.seller_console.product_builder as PB
    monkeypatch.setattr(PB, "build_product", lambda item, **k: {"title": "OKNIFE", "images": [], "skus": [], "options": []})
    from src.seller_console.upload_dispatcher import UploadDispatcher, PrevalidationResult
    monkeypatch.setattr(UploadDispatcher, "prevalidate", lambda self, pd, ms: [PrevalidationResult(market=m, ok=False, hold=True,
                                                                                                  error_code="coupang_hold") for m in ms])
    out = DX.snapshot("prevalidate", "it1|coupang:gogane")
    assert out["ok"] and seen["dry"] is True                                               # 사전검증은 드라이로만
    snap = state[DX.key_for("prevalidate", "it1|coupang:gogane")]
    assert snap["data"]["rows"][0]["code"] == "coupang_hold" and "coupang:gogane 보류" in snap["data"]["verdict"]
    assert DX.snapshot("prevalidate", "nope")["ok"] is True and "못 찾았어요" in str(state[DX.key_for("prevalidate", "nope")])


def test_oneshot_op_routes_to_snapshot(state, no_writes, monkeypatch):
    from src.services import oneshot_ops as O
    from src.utils import restart_log as RL
    monkeypatch.setattr(RL, "rows", lambda: [])
    assert "diag_snapshot" in O.OPS and "diag_snapshot" in O.REQUEUE_SAFE_OPS
    out = O._run({"op": "diag_snapshot", "item_id": "restarts:"})
    assert out["ok"] and out["key"] == "diag:snap:restarts" and "diag:snap:restarts" in state
    assert O._run({"op": "diag_snapshot", "item_id": "orders:"})["ok"] is False             # 목록 밖 이름은 거부


def _diagro():
    import importlib.util
    spec = importlib.util.spec_from_file_location("diagro", "ops/oracle_a1/diagro.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_oracle_reader_writes_only_one_queue_append_and_reads_only_snaps():
    """볼트 오라클 작업(diagro)의 쓰기는 `ops:oneshot:queue` 덧붙이기 하나 · 읽기는 `diag:snap:*`만 · 이름은 앱 목록과 같다."""
    from src.services.diag_export import NAMES
    m = _diagro()
    assert tuple(m.NAMES) == tuple(NAMES)
    ask = m.ask_sql("prevalidate:abc|coupang:gogane")
    up = ask.upper()
    assert up.count("UPDATE APP_STATE") == 1 and "'ops:oneshot:queue'" in ask and "diag_snapshot" in ask
    for bad in ("DELETE", "DROP", "TRUNCATE", "ALTER", "COLLECT_HISTORY", "ORDERS", "USER_TOKENS", "MARKET_LINKS"):
        assert bad not in up, bad
    rd = m.read_sql("restarts")
    assert rd.startswith("BEGIN READ ONLY;") and "'diag:snap:restarts'" in rd and "UPDATE" not in rd.upper()
    assert m.LIST_SQL.startswith("BEGIN READ ONLY;") and "diag:snap:" in m.LIST_SQL
    for bad in ("orders:x", "item:1';drop table x;--", "register:abc"):
        with pytest.raises(SystemExit):
            m.parse(bad)
    assert m.mask("연락 010-1234-5678 kim@x.com") == "연락 <가림> <가림>"
