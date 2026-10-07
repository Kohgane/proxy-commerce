"""Z3-D(오너 2026-10-07) — 4013 막음 중 호출 폭주.

운영 실측(14:3x KST): 진단 「오늘 25/10회」 → 수 분 뒤 「58/10회」, 온바운드 all[56=10+1+45]. 운영 DB 기록으로 특정:
자동 수집 집계(mtop_auto)는 12:54 이후 0건 · 이월 워커 실행 기록 0 · 막음 키는 마지막 호출(14:39:13)마다 다시 써짐 —
상한 10을 넘겨 셀 수 있는 길은 「새로 받기」(막음 무시 · env 상한 60)뿐이고, 진단 폼이 GET ?refresh=1이라
그 주소가 새로고침·뒤로가기·탭 복원마다 다시 나갔다(58 < 60에서 멈춘 것도 같은 상한).

계약: 막음 중엔 「새로 받기」 외 어떤 길도 온바운드로 나가지 않는다 · 「새로 받기」는 POST만(PRG), 막음 중엔 쿨다운에 1회 ·
막음 판정은 매 호출 직전 공유 저장소(app_state)에서 읽는다 · 나간 호출은 출처별·실패를 따로 센다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_onebound_quota import QUOTA_BODY, _ok_body


@pytest.fixture
def wire(monkeypatch):
    """온바운드 HTTP 대역 — 나간 요청을 센다. 응답은 `wire.body`."""
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider_onebound as O
    monkeypatch.setenv("ONEBOUND_KEY", "kkk_test_key_1234")
    monkeypatch.setenv("ONEBOUND_SECRET", "sss_test_secret_5678")
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", "60")
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    monkeypatch.delenv("TAOBAO_MTOP_AUTO", raising=False)
    monkeypatch.setattr(T, "fetch", lambda *a, **k: pytest.fail("onebound면 mtop을 부르지 않는다"))
    monkeypatch.setattr(T, "item_id_from", lambda arg, s=None: (str(arg).strip()[-12:], "숫자"))

    class W:
        sent: list = []
        body = QUOTA_BODY
    W.sent = []

    def fake_get(params, transport=None):
        W.sent.append(params["num_iid"])
        return 200, json.dumps(W.body if not callable(W.body) else W.body(params["num_iid"]), ensure_ascii=False)
    monkeypatch.setattr(O, "_get", fake_get)
    return W


def _block():
    """다른 프로세스·서비스가 막음을 써 둔 상태 — 같은 공유 저장소(app_state) 키를 직접 쓴다."""
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    st.state_set(O._QUOTA + O._cst_day(), {"code": "4013", "reason": "已超量", "at": datetime.now(timezone.utc).isoformat()})


def _items(seller, n, base=7700):
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    from src.seller_console import collect_history_store as S
    out = []
    for i in range(n):
        num = f"9{base + i:011d}"
        st.state_set(O._RAW + num, {})
        out.append(S.append(source="share_text", url=f"https://item.taobao.com/item.htm?id={num}", seller_id=seller,
                            title="x", price="", currency="",
                            extra={"title": "x", "item_id_taobao": num, "enrich_state": "pending", "images": []}))
    return out


def _admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    return c


def test_block_zero_calls_on_every_path(wire):
    """막음 상태: 공유 10건 · 이월 워커 틱 10회 · 진단 조회 10회 · 옛 refresh=1 주소 10회 → 온바운드 호출 0."""
    from src.services import onebound_carry as C
    from src.services import taobao_auto as A
    from src.order_webhook import app
    _block()
    ids = _items("storm", 10)
    for iid in ids:                                     # 폰 공유 → 서버 자동 수집(백그라운드 본체)
        A._safe_run("storm", iid)
    assert C.count() == 10                              # 막혀서 이월 대기로
    for _ in range(10):                                 # 이월 워커 틱
        C._tick()
    c = _admin(app)
    for i in range(10):                                 # 진단 「조회」 · 새로고침된 옛 주소(refresh=1)
        c.get("/admin/diagnostics/taobao-provider", query_string={"q": f"9{7700 + i:011d}"})
        c.get("/admin/diagnostics/taobao-provider", query_string={"q": f"9{7700 + i:011d}", "refresh": "1"})
    assert wire.sent == []


def test_block_written_elsewhere_is_read_right_before_each_call(wire):
    """막음은 프로세스 메모리 캐시가 아니라 매 호출 직전 공유 저장소에서 읽는다 — 다른 서비스가 쓰면 바로 멈춘다."""
    from src.collectors import taobao_provider_onebound as O
    wire.body = lambda n: _ok_body(n)
    assert O.call("900000000001")["ok"] and len(wire.sent) == 1
    _block()                                            # 다른 서비스가 4013을 받아 막음을 씀
    r = O.call("900000000002")
    assert r["kind"] == "provider_quota" and len(wire.sent) == 1


def test_refresh_is_post_only_and_cooldown_while_blocked(wire):
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    from src.order_webhook import app
    _block()
    c = _admin(app)
    q = "900000007777"
    r = c.post("/admin/diagnostics/taobao-provider/refresh", data={"q": q})
    assert r.status_code == 303 and "refresh" not in r.headers["Location"] and len(wire.sent) == 1   # 충전 확인 1회
    h = c.get(r.headers["Location"]).get_data(as_text=True)                                         # 리다이렉트 화면
    assert len(wire.sent) == 1 and 'data-role="provider-last-refresh"' in h and "provider_quota" in h
    for _ in range(5):                                  # 연타 · 새로고침
        c.post("/admin/diagnostics/taobao-provider/refresh", data={"q": q})
        c.get(r.headers["Location"])
    assert len(wire.sent) == 1
    h = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "분 뒤 다시(연타 방지 · 호출 0)" in h
    # 쿨다운이 지나면 한 번 더(충전 뒤 확인 길은 열어 둔다)
    st.state_set(O._REFRESH_TRY + O._cst_day(),
                 {"at": (datetime.now(timezone.utc) - timedelta(seconds=O.refresh_cooldown() + 1)).isoformat()})
    c.post("/admin/diagnostics/taobao-provider/refresh", data={"q": q})
    assert len(wire.sent) == 2


def test_refresh_success_after_recharge_clears_block(wire, monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    from src.order_webhook import app
    from src.services import onebound_carry as C
    monkeypatch.setattr(C, "kick", lambda: True)
    _block()
    wire.body = lambda n: _ok_body(n, "today:1 max:500 all[1=1+0+0];expires:2027-10-07")
    _admin(app).post("/admin/diagnostics/taobao-provider/refresh", data={"q": "900000008888"})
    assert len(wire.sent) == 1 and not O.quota_block().get("code") and O.daily_cap() == 60


def test_sent_counts_by_source_and_failures(wire):
    from src.collectors import taobao_provider_onebound as O
    from src.services import taobao_auto as A
    from src.order_webhook import app
    wire.body = lambda n: _ok_body(n)
    (iid,) = _items("src", 1, base=7800)
    A.run("src", iid)                                   # 자동 1 성공
    wire.body = QUOTA_BODY
    c = _admin(app)
    c.get("/admin/diagnostics/taobao-provider", query_string={"q": "900000007801"})   # 진단 조회 1 → 4013(실패)
    c.post("/admin/diagnostics/taobao-provider/refresh", data={"q": "900000007802"})   # 막음 첫 새로 받기 1(실패)
    sent = O.sent_today()
    assert sent == {"auto": 1, "diag": 1, "refresh": 1, "fail": 2}
    h = c.get("/admin/diagnostics/taobao-provider").get_data(as_text=True)
    seg = h.split('data-role="provider-sent"')[1][:400]
    assert "자동 수집 1" in seg and "진단 조회 1" in seg and "새로 받기 1" in seg and "이월 대기 0" in seg and "실패 2" in seg


def test_carry_drain_counts_as_carry(wire, monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    from src.services import onebound_carry as C
    wire.body = lambda n: _ok_body(n)
    (iid,) = _items("src-c", 1, base=7900)
    C.add("src-c", iid, kind="provider_quota")
    assert C.drain()["done"] == 1
    assert O.sent_today() == {"carry": 1}


def test_no_other_module_calls_onebound_directly():
    """온바운드로 나가는 길은 `taobao_provider_onebound.call` 하나 — 다른 모듈이 엔드포인트를 직접 부르지 않는다."""
    import pathlib
    hits = [str(p) for p in pathlib.Path("src").rglob("*.py")
            if "api-gw.onebound.cn" in p.read_text(encoding="utf-8", errors="ignore")]
    assert hits == ["src/collectors/taobao_provider_onebound.py"]
