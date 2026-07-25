"""tests/test_v72b_recollect.py — v72b STEP3: 목록 벌크바 [다시 수집] 재추출.

구버전 수집분('-' 가격·잔재)을 최신 추출기로 세탁하는 통로. 선택 상품을 force로 재수집 →
서버가 기존 레코드를 덮어씀(신규 행 생성 0) + 보강 큐 재투입(enrichTargets). 추출기 로직은
동결(이 배치는 저장·표시 계층만) — force는 서버 덮어쓰기 경로(이미 존재)를 벌크바에 연결만.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
EXT_API = Path("src/api/extension_api.py").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.123"


# ── source-contract: 벌크바 [다시 수집] 버튼 + force 배선 ──
def test_recollect_button_and_handler_source():
    # 벌크바에 '다시 수집' 버튼(data-act=recollect).
    assert 'data-act="recollect"' in CS
    assert "다시 수집" in CS
    # 핸들러가 선택분을 force로 재수집.
    assert re.search(r'act === "recollect"', CS)
    assert "kgpCollect(sel, { force: true })" in CS
    # kgpCollect/kgpRunBulk가 opts.force → item.force 부착.
    assert "function kgpCollect(urls, opts)" in CS
    assert "function kgpRunBulk(items, opts)" in CS
    assert "if (opts && opts.force) items.forEach(it => { if (it) it.force = true; });" in CS


def test_server_force_overwrites_not_creates_source():
    # 서버가 force일 때 기존 항목 갱신(신규 행 금지) + updated 회신.
    assert 'bool(payload.get("force") or payload.get("overwrite"))' in EXT_API
    assert "if _force:" in EXT_API
    assert '"updated": True' in EXT_API
    # 갱신은 update(신규 append 아님).
    seg = EXT_API.split("if _force:")[1].split('"ok": True, "updated": True')[0]
    assert "_hist_update" in seg and "append" not in seg


# ── behavioral: '-'(빈) 가격 항목을 force로 세탁 → 같은 id·새 가격·행 수 불변 ──
def _force_inmemory(monkeypatch):
    from src.seller_console import collect_history_store as store
    monkeypatch.setattr(store, "pg_enabled", lambda: False, raising=False)
    if hasattr(store, "_in_memory"):
        store._in_memory.clear()
    return store


def _session(flask_client):
    with flask_client.session_transaction() as s:
        s["user_id"] = "u_recollect"
        s["user_email"] = "recollect@example.com"


def test_recollect_updates_existing_no_new_row(flask_client, monkeypatch):
    store = _force_inmemory(monkeypatch)
    _session(flask_client)
    url = "https://www.amazon.com/dp/B00RECOL01"
    hdr = {"X-KGP": "1"}

    # 1차 수집: 가격 '-'(빈값) — 구버전 아마존 '-' 재현.
    r1 = flask_client.post("/api/v1/collect/extension",
                           json={"url": url, "title": "재추출 대상", "price": "", "currency": ""},
                           headers=hdr)
    assert r1.status_code == 200, r1.get_data(as_text=True)
    d1 = r1.get_json()
    assert d1.get("ok") is True
    item_id = d1.get("item_id")
    assert item_id

    ids_before = {row.get("id") for row in store.list_items(seller_ids={"u_recollect", "recollect@example.com"})}
    assert item_id in ids_before
    n_before = len(ids_before)

    # 2차 '다시 수집'(force): 같은 URL + 실제 가격 → 기존 항목 덮어씀(신규 행 0).
    r2 = flask_client.post("/api/v1/collect/extension",
                           json={"url": url, "title": "재추출 대상", "price": "12000",
                                 "currency": "KRW", "force": True},
                           headers=hdr)
    assert r2.status_code == 200, r2.get_data(as_text=True)
    d2 = r2.get_json()
    assert d2.get("ok") is True
    assert d2.get("updated") is True                 # 덮어쓰기(중복 아님)
    assert d2.get("item_id") == item_id              # 같은 레코드

    rows_after = store.list_items(seller_ids={"u_recollect", "recollect@example.com"})
    ids_after = {row.get("id") for row in rows_after}
    assert len(ids_after) == n_before                # 신규 행 0
    row = next(r for r in rows_after if r.get("id") == item_id)
    extra = json.loads(row.get("extra_json") or "{}")
    assert extra.get("recollected") is True          # 재수집 마킹
    assert (row.get("price") or extra.get("price") or "").replace(",", "") == "12000"  # 가격 채워짐


def test_force_returns_item_id_for_enrich(flask_client, monkeypatch):
    # 재수집 응답 item_id → 벌크 배경이 enrichTargets로 재투입(보강 큐).
    _force_inmemory(monkeypatch)
    _session(flask_client)
    url = "https://www.amazon.com/dp/B00RECOL02"
    hdr = {"X-KGP": "1"}
    flask_client.post("/api/v1/collect/extension",
                      json={"url": url, "title": "T", "price": "", "currency": ""}, headers=hdr)
    r = flask_client.post("/api/v1/collect/extension",
                          json={"url": url, "title": "T", "price": "9900", "currency": "KRW", "force": True},
                          headers=hdr)
    assert (r.get_json() or {}).get("item_id")       # background enrichTargets 재투입 조건(item_id 존재)


# ── node 하네스: kgpRunBulk({force:true})가 각 항목에 force 부착 ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_recollect_force_flag_node():
    # kgpRunBulk가 opts.force일 때 collectBulk items 각각에 force:true를 붙이는지 실증.
    body = CS.split("function kgpRunBulk(items, opts) {")[1].split("kgpSendMessage")[0]
    # opts.force 부착 라인만 격리 검증(sendMessage 이전).
    harness = (
        "var sent=null;\n"
        "var document={querySelectorAll:function(){return {forEach:function(){}};},"
        "getElementById:function(){return null;}};\n"
        "function kgpSetStatus(){}\n"
        "function kgpRunBulk(items, opts){\n"
        + body +
        "  sent=items;\n"
        "}\n"
        "kgpRunBulk([{url:'a',price:''},{url:'b',price:''}], {force:true});\n"
        "var forced = sent.every(function(i){return i.force===true;});\n"
        "kgpRunBulk([{url:'c'}], {});\n"
        "var noForce = (sent[0].force===undefined);\n"
        "console.log(JSON.stringify({forced:forced, noForce:noForce}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["forced"] is True                     # force:true 배치엔 전부 부착
    assert out["noForce"] is True                    # 일반 배치엔 미부착(회귀 방지)
