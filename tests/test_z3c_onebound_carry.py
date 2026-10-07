"""Z3-C(오너 2026-10-07): 온바운드 하루 한도에 막힌 상품 → 「이월 대기」 → 한도가 풀리면 자동 수집.

- 4013(provider_quota) → 대기 등록(상품 ID·공유 원문·사용자·시각) · 카드 「상품정보 일일 한도 — 내일 자동으로 채워져요 (대기 N번째)」
- 우리 상한(provider_cap — #845 이후 키 max로 내려가 4013보다 먼저 걸림)도 같은 대기
- 베이징 자정 뒤: 유효 상한 10 · 대기 12 → 10 처리 · 2 이월(다음 날)
- 「사진 추가」로 직접 채운 건 → 대기에서 빠짐(자동으로 다시 부르지 않음)
- 「새로 받기」가 막음을 풀면 곧바로 비우기 시작
- 진단 /taobao-provider 「이월 대기 N건 · 다음 실행 …」 · 텔레그램은 대기 20건 초과 때만 오너에게 하루 한 번
- 비운 상품은 기존 자동 체인(같은 병합)을 지나 쿠팡 등록 준비까지 — 회귀 없음
네트워크 0(대역 transport).
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_onebound_quota import QUOTA_BODY, _Tr, _ok_body


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from src.collectors import taobao_mtop as T
    monkeypatch.setenv("ONEBOUND_KEY", "kkk_test_key_1234")
    monkeypatch.setenv("ONEBOUND_SECRET", "sss_test_secret_5678")
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", "60")
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    monkeypatch.delenv("TAOBAO_MTOP_AUTO", raising=False)
    monkeypatch.setattr(T, "fetch", lambda *a, **k: pytest.fail("onebound면 mtop을 부르지 않는다"))


def _route(monkeypatch, body_for):
    """`O.call`이 쓰는 transport를 상품번호별 응답으로 — `body_for(num_iid) -> dict`. 호출 기록을 돌려준다."""
    from src.collectors import taobao_provider_onebound as O
    calls = []
    real = getattr(O.call, "_orig", O.call)                # 두 번 감싸도 진짜 call 위에

    def tr(url, params):
        calls.append(params["num_iid"])
        return 200, json.dumps(body_for(params["num_iid"]), ensure_ascii=False)

    def fake(iid, refresh=False, no_cache=False, transport=None):
        return real(iid, refresh=refresh, no_cache=no_cache, transport=tr)
    fake._orig = real
    monkeypatch.setattr(O, "call", fake)
    return calls


def _item(seller, num_iid):
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    from src.seller_console import collect_history_store as S
    st.state_set(O._RAW + num_iid, {})
    ex = {"title": "格斯潘懒人沙发单人", "title_ko": "격스판 빈백 소파", "item_id_taobao": num_iid, "enrich_state": "pending",
          "images": [], "uncollected": ["images", "options", "price"],
          "share_raw": f"【淘宝】https://e.tb.cn/h.TEST{num_iid} 「格斯潘懒人沙发单人」"}
    return S.append(source="share_text", url=f"https://item.taobao.com/item.htm?id={num_iid}", seller_id=seller,
                    title="격스판 빈백 소파", price="", currency="", extra=ex)


def _new_beijing_day():
    """베이징 자정 흉내 — 새 날짜 키는 비어 있다: 오늘 막음 · 우리 호출 수 0."""
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    from src.db import option_translate_queue_pg as oq
    st.state_set(O._QUOTA + O._cst_day(), {})
    with oq._LOCK:
        oq._MEM_DAY.pop(O._day_key(), None)
    if oq._enabled():
        st.state_set(O._day_key(), {"n": 0})


def _ex(seller, iid):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_ids={seller})["extra_json"])


def test_4013_goes_to_carry_queue_with_share_user_time(monkeypatch):
    from src.services import onebound_carry as C
    from src.services import taobao_auto as A
    _route(monkeypatch, lambda n: QUOTA_BODY)
    iid = _item("carry-a", "8801")
    rec = A.run("carry-a", iid)
    assert rec["kind"] == "provider_quota"
    q = C.items()
    assert len(q) == 1 and q[0]["item_id"] == iid and q[0]["user_id"] == "carry-a" and q[0]["kind"] == "provider_quota"
    assert "e.tb.cn/h.TEST8801" in q[0]["share"] and q[0]["url"].endswith("id=8801") and q[0]["at"]
    iid2 = _item("carry-b", "8802")                     # 막음 뒤 다음 담기 — 부르지 않고 대기 2번째
    assert A.run("carry-b", iid2)["kind"] == "provider_quota" and C.position(iid2) == 2
    A.run("carry-a", iid)                               # 같은 상품 또 막혀도 두 번 들어가지 않는다
    assert C.count() == 2


def test_card_line_shows_queue_position(monkeypatch):
    import src.seller_console.views as V
    from src.services import taobao_auto as A
    _route(monkeypatch, lambda n: QUOTA_BODY)
    a, b = _item("carry-c", "8811"), _item("carry-c", "8812")
    A.run("carry-c", a), A.run("carry-c", b)
    assert V._m5_auto(_ex("carry-c", b), b)["line"] == "상품정보 일일 한도 — 내일 자동으로 채워져요 (대기 2번째)"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "carry-c"
    d = c.get(f"/seller/collect/{a}/auto-enrich").get_json()
    assert d["state"] == "carry" and d["line"].endswith("(대기 1번째)")
    h = c.get(f"/seller/m/item/{a}").get_data(as_text=True)
    assert 'data-state="carry"' in h and "내일 자동으로 채워져요 (대기 1번째)" in h
    assert 'data-role="m5-needs-pc"' not in h            # 「PC 크롬만 자동」 문구와 겹치지 않는다


def test_our_cap_also_carries(monkeypatch):
    """#845 이후 상한이 키 max로 내려가 4013보다 우리 가드(provider_cap)가 먼저 걸린다 — 그 건도 대기."""
    from src.collectors import taobao_provider_onebound as O
    from src.services import onebound_carry as C
    from src.services import taobao_auto as A
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", "1")
    _route(monkeypatch, lambda n: _ok_body(n))
    first, second = _item("carry-d", "8821"), _item("carry-d", "8822")
    assert A.run("carry-d", first)["state"] == "done" and C.count() == 0
    assert A.run("carry-d", second)["kind"] == "provider_cap" and C.position(second) == 1
    assert O.used_today() == 1


def test_after_midnight_cap10_queue12_does_10_and_carries_2(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    from src.services import onebound_carry as C
    from src.services import taobao_auto as A
    from src.db import image_translate_queue_pg as st
    calls = _route(monkeypatch, lambda n: QUOTA_BODY)
    ids = [_item("carry-e", f"88{30 + i}") for i in range(12)]
    for iid in ids:
        A.run("carry-e", iid)
    assert C.count() == 12 and len(calls) == 1          # 첫 건만 불렀고(4013) 나머지 11건은 부르지 않고 대기
    assert C.drain()["stopped"] == "quota_block" and C.count() == 12 and len(calls) == 1   # 오늘은 그대로

    # 베이징 자정 → 오늘 막음 키·호출 수가 새 날로(= 새 날짜 키는 비어 있음). 키 max 10을 배운 상태.
    _new_beijing_day()
    st.state_set(O._LIMITS, {"max": 10, "expires": "2099-12-31"})
    calls = _route(monkeypatch, lambda n: _ok_body(n, "today:1 max:10 all[];expires:2099-12-31"))
    res = C.drain()
    assert res["done"] == 10 and res["left"] == 2 and res["stopped"] == "cap" and len(calls) == 10
    assert O.used_today() == 10 and [r["item_id"] for r in C.items()] == ids[10:]   # 오래된 순 10건, 나머지 2건 이월
    for iid in ids[:10]:
        assert _ex("carry-e", iid)["auto_enrich"]["state"] == "done"
    for iid in ids[10:]:
        assert _ex("carry-e", iid)["auto_enrich"]["kind"] == "provider_quota"  # 아직 안 부름(한도 0에서 멈춤)
    assert C.next_run_text().endswith("(베이징 자정 — 한도 리셋) 뒤 첫 틱") and "01:00 KST" in C.next_run_text()


def test_manual_photos_removes_from_queue(monkeypatch):
    from src.media import image_pipeline
    from src.services import onebound_carry as C
    from src.services import taobao_auto as A
    _route(monkeypatch, lambda n: QUOTA_BODY)
    iid, other = _item("carry-f", "8851"), _item("carry-f", "8852")
    A.run("carry-f", iid), A.run("carry-f", other)
    monkeypatch.setattr(image_pipeline, "upload_bytes",
                        lambda raw, folder="": {"ok": True, "secure_url": "https://res.cloudinary.com/x/manual/1.jpg"})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "carry-f"
    r = c.post(f"/seller/collect/{iid}/manual-photos",
               data={"photos": (io.BytesIO(b"\xff\xd8\xff\xe0" + b"0" * 64), "a.jpg", "image/jpeg")},
               content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["ok"]
    assert C.position(iid) == 0 and C.position(other) == 1        # 직접 채운 건만 빠지고 순번이 당겨진다


def test_drain_skips_manually_filled_even_if_still_listed(monkeypatch):
    """대기에 남아 있어도 비울 때 다시 본다 — 사진을 직접 넣은 상품은 부르지 않고 뺀다."""
    from src.services import onebound_carry as C
    from src.seller_console import collect_history_store as S
    iid = _item("carry-g", "8861")
    C.add("carry-g", iid, kind="provider_quota")
    ex = _ex("carry-g", iid)
    ex.update(manual_photos=2, manual_fields={"images": "2026-10-07T00:00:00+00:00"})
    S.update(iid, seller_ids={"carry-g"}, extra_json=json.dumps(ex, ensure_ascii=False))
    called = []
    res = C.drain(runner=lambda *a, **k: called.append(a) or {"state": "done", "kind": "ok"})
    assert res["manual_skip"] == 1 and not called and C.count() == 0


def test_refresh_clearing_block_kicks_drain(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    from src.services import onebound_carry as C
    O.call("8871", transport=_Tr(QUOTA_BODY))
    kicked = []
    monkeypatch.setattr(C, "kick", lambda: kicked.append(1) or True)
    assert O.call("8871", refresh=True, no_cache=True, transport=_Tr(_ok_body("8871")))["ok"]
    assert kicked == [1] and not O.quota_block().get("code")


def test_kick_runs_drain_in_background(monkeypatch):
    from src.services import onebound_carry as C
    import threading
    done = threading.Event()
    C.add("carry-h", "it-1", kind="provider_quota")
    monkeypatch.setattr(C, "drain", lambda runner=None: done.set() or {"done": 1, "left": 0})
    assert C.kick() is True and done.wait(5)


def test_telegram_only_over_20_once_a_day(monkeypatch):
    from src.notifications import telegram
    from src.services import onebound_carry as C
    sent = []
    monkeypatch.setattr(telegram, "send_telegram", lambda msg, urgency="info": sent.append(msg) or True)
    for i in range(20):
        C.add("carry-i", f"t-{i}", kind="provider_quota")
    assert sent == []                                   # 20건까지는 조용
    C.add("carry-i", "t-20", kind="provider_quota")
    C.add("carry-i", "t-21", kind="provider_quota")
    assert len(sent) == 1 and "대기 21건(20건 초과)" in sent[0] and "kkk_" not in sent[0] and "sss_" not in sent[0]


def test_diag_shows_count_and_next_run(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    from src.services import onebound_carry as C
    O.call("8881", transport=_Tr(QUOTA_BODY))
    C.add("carry-j", "diag-1", kind="provider_quota")
    C.add("carry-j", "diag-2", kind="provider_quota")
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-provider").get_data(as_text=True)
    seg = h.split('data-role="provider-carry"')[1][:600]
    assert "이월 대기 2건" in seg and "다음 실행" in seg and "베이징 자정" in seg and "diag-1(" in seg and "KST)" in seg


def test_day_counter_is_beijing_date():
    """온바운드 한도는 베이징 자정 리셋 — 우리 호출 수도 같은 날짜로 센다(KST 00:00~01:00 어긋남 제거)."""
    from src.collectors import taobao_provider_onebound as O
    kst_0030 = datetime(2026, 10, 8, 0, 30, tzinfo=timezone(timedelta(hours=9)))
    assert O._day_key(kst_0030) == "onebound_calls:2026-10-07"          # 베이징은 아직 10-07 23:30
    assert O._day_key(kst_0030 + timedelta(hours=1)) == "onebound_calls:2026-10-08"


def test_drained_item_goes_through_chain_to_coupang_ready(monkeypatch):
    """비운 상품은 같은 자동 체인(병합·번역 큐)을 지나 쿠팡 등록 준비까지 — 사진·옵션 보류가 풀린다."""
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    from src.seller_console import collect_history_store as S
    from src.seller_console.product_builder import build_product
    from src.seller_console.upload_dispatcher import UploadDispatcher
    from src.services import onebound_carry as C
    from src.services import taobao_auto as A
    from src.uploaders.coupang_uploader import CoupangUploader
    _route(monkeypatch, lambda n: QUOTA_BODY)
    iid = _item("carry-k", "8891")
    A.run("carry-k", iid)
    before = UploadDispatcher.readiness_holds(build_product(S.get(iid, seller_ids={"carry-k"}), seller_id="carry-k"), "coupang")
    assert before                                       # 사진·옵션이 비어 등록 보류
    _new_beijing_day()
    _route(monkeypatch, lambda n: _ok_body(n))
    assert C.drain()["done"] == 1 and C.count() == 0
    ex = _ex("carry-k", iid)
    assert ex["auto_enrich"]["state"] == "done" and len(ex["images"]) == 3 and len(ex["skus"]) == 2
    pd = build_product(S.get(iid, seller_ids={"carry-k"}), seller_id="carry-k")
    after = UploadDispatcher.readiness_holds(pd, "coupang")
    assert len(after) < len(before)
    assert not any(h.get("fix") == "pc" for h in after)  # 「PC로 보강」 보류(사진·옵션 없음)는 풀림
    prep = CoupangUploader(access_key="a", secret_key="b", vendor_id="v").prepare_product(pd)
    assert prep["images"] and len(prep["skus"]) == 2


def test_boot_starts_only_on_onebound_worker_service(monkeypatch):
    from src.services import onebound_carry as C
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "mtop")
    assert C.start_if_enabled().startswith("꺼짐 — TAOBAO_DETAIL_PROVIDER")
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    monkeypatch.setenv("WORKERS_ENABLED", "0")
    assert C.start_if_enabled().startswith("꺼짐 — 이 서비스는 워커 아님")
    from src.services import workers as W
    assert "onebound-carry" in W.WORKERS
