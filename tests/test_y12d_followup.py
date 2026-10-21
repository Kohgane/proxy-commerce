"""Y12-D(오너 2026-10-18) — 백필 후속 계약.

1. 「돌아가는 것 · 재수집 대기」에 「n일째」(마지막으로 움직인 날부터). 7일 넘으면 「손댈 것 · 수집기 안 돎 — PC에서 콘솔 탭 열기」.
   반례: 3주째 안 움직이는 걸 「돌아가는 것」이라 부르지 않는다 — 날이 지나 바뀌는 판정이라 **읽을 때 잰다**(저장 뒤에 낡아도 옮겨진다).
2. 수집 실패 줄 「다시 수집」(보강 큐 재투입 · 시도 상한 리셋) · 「버리기」(목록에서 숨김 · DB 삭제 아님 · 드로어 「되살리기」).
   버리면 손댈 것에서 빠진다. 수집기 안 돎 줄엔 「버리기」만(다시 넣으면 날 수만 0이 되고 수집기는 여전히 안 돈다).
4. 시험 계정(QA-TEST·dev)은 셀러를 안 정한 전체 집계에서 뺀다(그 계정으로 보면 그대로 보인다).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from src.seller_console import attention as A
from src.seller_console import collect_history_store as S
from src.seller_console import home_bundles as H


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    yield
    S._in_memory.clear()


def _client(uid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=f"{uid}@example.com", user_role="seller")
    return c


def _ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _wait(days_ago):
    """온바운드 자동 수집이 실패해 PC 고가수집기 보강 큐에 남은 초안 — 마지막으로 움직인 날 = `days_ago`일 전."""
    return {"mode": "share", "enrich_state": "pending", "gate_ready": True, "price": "189", "title_ko": "원목 식탁 의자",
            "auto_enrich": {"state": "manual", "kind": "provider_fail", "at": _ago(days_ago)}}


FAIL = {"title": "Vintage brass desk lamp"}                       # 가격·갤러리 둘 다 못 읽은 완전 수집(자동 재수집 없음)


def _add(uid, extra, url="https://item.taobao.com/item.htm?id=1", title="상품"):
    iid = S.append(source="share", url=url, seller_id=uid, title=title, price="", currency="CNY", extra=extra)
    for r in S._in_memory:
        if r.get("id") == iid:
            r["collected_at"] = _ago(30)
    return iid


# ── 1. n일째 · 7일 넘으면 수집기 안 돎 ────────────────────────────────────────────────────────────────
def test_refetch_day_count_and_seven_day_line():
    a = A.summarize(_wait(3))
    assert A.refetch_days(a) == 4 and not A.refetch_stale(a)       # 3일 전 움직임 = 4일째
    assert A.refetch_days(A.summarize(_wait(6))) == 7 and not A.refetch_stale(A.summarize(_wait(6)))
    assert A.refetch_stale(A.summarize(_wait(7)))                    # 8일째부터 손댈 것
    its = A.items(dict(_wait(21), attn=A.summarize(_wait(21))))
    assert [i["kind"] for i in its] == ["collector_down"]
    assert its[0]["text"] == "수집기 안 돎 — PC에서 콘솔 탭 열기 · 재수집 대기 22일째"


def test_three_weeks_not_running_is_attention_not_running():
    """반례: 3주째 안 움직이면 돌아가는 게 아니다 — 대시보드 「돌아가는 것」에서 빠지고 「손댈 것」에 「수집기 안 돎」."""
    uid = "u-y12d-3w"
    old = _add(uid, _wait(21), url="https://item.taobao.com/item.htm?id=11")
    _add(uid, _wait(2), url="https://item.taobao.com/item.htm?id=12")
    rows = S.dashboard_rows(seller_ids={uid})
    run = H._running({uid}, rows)
    # Y12-D 7: 재수집 대기가 있으면 PC 수집기 신호 줄이 같이 붙는다(여기선 신호 기록 없음)
    assert run["lines"] == ["재수집 대기 1건 · 3일째", "PC 수집기 · 신호 기록 없음"]
    att = H._attention({uid}, rows)
    assert att["n"] == 1 and att["todo"][0]["id"] == old and att["todo"][0]["kind"] == "collector_down"
    assert [r["id"] for r in S.list_items(days=3650, seller_ids={uid}, attn_only=True)] == [old]
    assert S.count_items(days=3650, seller_ids={uid}, refetch_only=True) == 1


def test_stale_judged_at_read_time_after_save():
    """저장 땐 6일째(손댈 것 아님 · attn_n 0) — 날이 지나 8일째가 되면 저장 없이도 손댈 것으로 옮겨진다."""
    uid = "u-y12d-age"
    iid = _add(uid, _wait(5), url="https://item.taobao.com/item.htm?id=21")
    row = next(r for r in S._in_memory if r["id"] == iid)
    assert int(row.get("attn_n") or 0) == 0
    ex = json.loads(row["extra_json"])
    ex["attn"]["refetch_since"] = _ago(9)                          # 시간이 흘렀다(저장은 없었다)
    row["extra_json"] = json.dumps(ex, ensure_ascii=False)
    assert [r["id"] for r in S.list_items(days=3650, seller_ids={uid}, attn_only=True)] == [iid]
    assert S.count_items(days=3650, seller_ids={uid}, refetch_only=True) == 0
    assert H._products(S.dashboard_rows(seller_ids={uid}))["attn"] == 1


def test_running_and_drawer_show_day_count():
    uid = "u-y12d-dash"
    iid = _add(uid, _wait(2), url="https://item.taobao.com/item.htm?id=31")
    c = _client(uid)
    html = c.get("/seller/").get_data(as_text=True)
    run = html[html.index('data-role="hb-running"'):]
    assert "재수집 대기 1건 · 3일째" in run[:run.index("</section>")]
    drawer = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    flags = drawer[drawer.index('data-role="item-flags"'):]
    assert "재수집 대기 · PC 고가수집기가 켜지면 차례로 엽니다 · 시도 0/3 · 3일째" in flags[:flags.index("</p>")]


# ── 2. 다시 수집 · 버리기 ─────────────────────────────────────────────────────────────────────────────
def test_dashboard_buttons_by_kind():
    uid = "u-y12d-btn"
    f = _add(uid, dict(FAIL), url="https://item.taobao.com/item.htm?id=41")
    d = _add(uid, _wait(21), url="https://item.taobao.com/item.htm?id=42")
    html = _client(uid).get("/seller/").get_data(as_text=True)
    rows = re.findall(r'<li class="hb-todo-row" data-kind="(\w+)">(.*?)</li>', html, re.S)
    by = {k: body for k, body in rows}
    assert f'data-role="hb-recollect" data-id="{f}"' in by["collect_fail"] and f'data-role="hb-discard" data-id="{f}"' in by["collect_fail"]
    assert f'data-role="hb-discard" data-id="{d}"' in by["collector_down"] and "hb-recollect" not in by["collector_down"]


def test_recollect_requeues_and_resets_attempts():
    uid = "u-y12d-re"
    iid = _add(uid, {"mode": "share", "enrich_state": "blocked", "enrich_attempts": 3, "enrich_blocked_reason": "로그인 벽"},
               url="https://item.taobao.com/item.htm?id=51")
    c = _client(uid)
    assert S.count_items(days=3650, seller_ids={uid}, attn_only=True) == 1
    r = c.post(f"/seller/collect/{iid}/recollect", json={"mode": "queue"})
    assert r.status_code == 200 and r.get_json()["queued"]
    ex = json.loads(S.get(iid, seller_ids={uid})["extra_json"])
    assert ex["enrich_attempts"] == 0 and ex["enrich_state"] == "pending"
    assert S.count_items(days=3650, seller_ids={uid}, attn_only=True) == 0      # 손댈 것 → 재수집 대기
    assert S.count_items(days=3650, seller_ids={uid}, refetch_only=True) == 1


def test_discard_hides_and_restore_brings_back():
    uid = "u-y12d-disc"
    iid = _add(uid, dict(FAIL), url="https://item.taobao.com/item.htm?id=61")
    keep = _add(uid, {"title_ko": "멀쩡한 상품", "price": "10", "images": ["https://img.alicdn.com/a.jpg"]},
                url="https://item.taobao.com/item.htm?id=62")
    c = _client(uid)
    assert c.post(f"/seller/collect/{iid}/discard", json={}).status_code == 200
    assert c.post(f"/seller/collect/{iid}/discard", json={}).status_code == 409          # 이미 버림(가짜 성공 금지)
    raw = S.get(iid, seller_ids={uid})
    assert raw is not None and json.loads(raw["extra_json"])["discarded"]                # DB에서 지우지 않았다
    lst = c.get("/seller/collect/history?days=3650").get_data(as_text=True)
    assert f'data-item-id="{iid}"' not in lst and f'data-item-id="{keep}"' in lst
    only = c.get("/seller/collect/history?discarded=1&days=3650").get_data(as_text=True)
    assert f'data-item-id="{iid}"' in only and f'data-item-id="{keep}"' not in only and 'data-role="discarded-banner"' in only
    dash = c.get("/seller/").get_data(as_text=True)
    assert 'data-role="hb-attention-none"' in dash                                        # 버리면 손댈 것에서 빠진다
    assert re.search(r'data-role="hb-tile-collected"[^>]*>\s*<span[^>]*>[^<]*</span><b class="hb-tile-v">1<', dash)
    drawer = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert 'data-role="discarded-note"' in drawer and 'data-restore="1"' in drawer and "되살리기" in drawer
    assert c.post(f"/seller/collect/{iid}/discard", json={"restore": True}).status_code == 200
    assert f'data-item-id="{iid}"' in c.get("/seller/collect/history?days=3650").get_data(as_text=True)
    assert S.count_items(days=3650, seller_ids={uid}, attn_only=True) == 1                # 되살리면 다시 손댈 것


def test_drawer_offers_discard_only_for_failures():
    uid = "u-y12d-dr"
    f = _add(uid, dict(FAIL), url="https://item.taobao.com/item.htm?id=71")
    ok = _add(uid, {"title_ko": "멀쩡", "price": "10", "images": ["https://img.alicdn.com/a.jpg"]}, url="https://item.taobao.com/item.htm?id=72")
    c = _client(uid)
    assert 'data-role="discard-btn" data-restore=""' in c.get(f"/seller/collect/preview/{f}?drawer=1").get_data(as_text=True)
    assert 'data-role="discard-btn"' not in c.get(f"/seller/collect/preview/{ok}?drawer=1").get_data(as_text=True)


# ── 4. 시험 계정 ─────────────────────────────────────────────────────────────────────────────────────
def test_test_accounts_out_of_unscoped_totals_but_visible_to_themselves():
    from src.utils.test_accounts import is_test_account
    assert is_test_account("QA-TEST-seller") and is_test_account("dev")
    assert not is_test_account("f275b60d-9728-4349-9f44-00cedb037516") and not is_test_account("developer")
    real = _add("u-real", dict(FAIL), url="https://item.taobao.com/item.htm?id=81")
    qa = _add("QA-TEST-seller", dict(FAIL), url="https://qa.example/1")
    dev = _add("dev", dict(FAIL), url="https://dev.example/1")
    every = {r["id"] for r in S.list_items(days=3650)}
    assert real in every and qa not in every and dev not in every
    assert {r["id"] for r in S.dashboard_rows()} == {real}
    assert S.summary(days=3650)["total"] == 1
    assert [r["id"] for r in S.list_items(days=3650, seller_ids={"QA-TEST-seller"})] == [qa]    # 그 계정으로 보면 그대로
    from src.public_site import stats as PS
    assert PS._collected() == 1


def test_market_cell_links_to_its_products(monkeypatch):
    """Y12-D 5 — 「고가네 승인대기 1」 칸을 누르면 그 상품만. 표와 같은 판정(`_bucket`)."""
    wait = {"uploaded": [{"market": "coupang:gogane", "product_id": "1", "review": {"state": "pending"}}]}
    sold = {"uploaded": [{"market": "coupang:gogane", "product_id": "2", "review": {"state": "approved"}},
                         {"market": "smartstore:gocosmos", "product_id": "3"}]}
    a = S.append(source="share", url="https://item.taobao.com/item.htm?id=91", seller_id="u-mk", title="대기 상품",
                 price="1", currency="CNY", extra=wait)
    b = S.append(source="share", url="https://item.taobao.com/item.htm?id=92", seller_id="u-mk", title="판매 상품",
                 price="1", currency="CNY", extra=sold)
    a, b = (a[0] if isinstance(a, tuple) else a), (b[0] if isinstance(b, tuple) else b)
    assert H.in_market_cell({"extra_json": json.dumps(wait)}, "coupang:gogane", "wait")
    assert not H.in_market_cell({"extra_json": json.dumps(sold)}, "coupang:gogane", "wait")
    assert H.in_market_cell({"extra_json": json.dumps(sold)}, "smartstore:gocosmos", "wait")     # 조회 전 = 승인대기(표와 같음)
    c = _client("u-mk")
    html = c.get("/seller/collect/history?mk=coupang:gogane&mst=wait&days=3650").get_data(as_text=True)
    assert "대기 상품" in html and "판매 상품" not in html and "고가네 쿠팡 · 승인대기" in html
    dash = c.get("/seller/").get_data(as_text=True)
    assert "mk=coupang%3Agogane&amp;mst=wait" in dash                      # 숫자 칸 → 그 칸 목록
    assert dash.count('data-role="hb-mcell"') == 3                              # 0인 칸엔 링크 없음(고가네 판매중·대기 · 고코스모스 대기)


def test_pc_collector_heartbeat_line_and_todo(monkeypatch):
    """Y12-D 7 — 확장 heartbeat: 1분 신호(1.5.167~) · 보강 폴링도 신호(1.5.151~) · 끊긴 채 재수집 대기면 손댈 것."""
    from src.db import image_translate_queue_pg as st
    from src.services import ext_heartbeat as HB
    st.reset_for_tests()
    now = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
    assert HB.status(["u-hb"], now=now)["line"] == "PC 수집기 · 신호 기록 없음"
    HB.beat("u-hb", "1.5.167", "beat", now=now - timedelta(minutes=2))
    s = HB.status(["u-hb", "x@y"], now=now)
    assert s["connected"] is True and s["line"] == "PC 수집기 · 연결 11:58 · v1.5.167"
    HB.beat("u-hb", "", "poll", now=now - timedelta(hours=3))                   # 옛 확장 폴링은 버전을 지우지 않는다
    s = HB.status(["u-hb"], now=now)
    assert s["connected"] is False and s["line"] == "PC 수집기 · 끊김 3시간 · v1.5.167"
    HB.beat("u-hb", "<script>", "beat", now=now)
    assert HB.status(["u-hb"], now=now)["version"] == "1.5.167"                 # 이상한 버전 문자열은 안 받는다
    st.reset_for_tests()


def test_beat_endpoint_and_poll_record(monkeypatch):
    from src.db import image_translate_queue_pg as st
    from src.api import extension_api as E
    from src.services import ext_heartbeat as HB
    st.reset_for_tests()
    monkeypatch.setattr(E, "_require_token", lambda scopes=None: {"user_id": "u-hb2"})
    from src.order_webhook import app
    c = app.test_client()
    r = c.post("/api/v1/collect/ext/beat", json={"version": "1.5.167"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert HB.status(["u-hb2"])["version"] == "1.5.167" and HB.status(["u-hb2"])["connected"] is True
    st.reset_for_tests()
    r = c.get("/api/v1/collect/enrich/pending", headers={"X-KGP-Ext-Version": "1.5.160"})
    assert r.status_code == 200 and HB.status(["u-hb2"])["version"] == "1.5.160"   # 폴링도 신호
    st.reset_for_tests()


def test_extension_sends_beat_only_with_console_tab():
    from pathlib import Path
    js = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
    assert "/api/v1/collect/ext/beat" in js and "periodInMinutes: 1" in js
    i = js.index("async function _kgpBeat")
    body = js[i:js.index("\n}\n", i)]
    assert "_kgpIsConsoleUrl" in body and "if (!open) return;" in body                 # 콘솔 탭 없으면 안 보낸다
    assert '"X-KGP-Ext-Version": _kgpExtVersion()' in js[js.index("enrich/pending?limit"):][:300]


def test_disconnected_pc_with_refetch_waiting_is_todo():
    from src.db import image_translate_queue_pg as st
    from src.services import ext_heartbeat as HB
    st.reset_for_tests()
    uid = "u-y12d-pc"
    _add(uid, _wait(2), url="https://item.taobao.com/item.htm?id=71")
    h = H.build({uid})
    assert not any(t["kind"] == "collector_off" for t in h["attention"]["todo"])     # 신호 기록 없음 → 단정 안 함
    assert "PC 수집기 · 신호 기록 없음" in h["running"]["lines"]
    HB.beat(uid, "1.5.160", "poll", now=datetime.now(timezone.utc) - timedelta(hours=5))
    h = H.build({uid})
    t = h["attention"]["todo"][0]
    assert t["kind"] == "collector_off" and t["text"].startswith("PC에서 콘솔 탭 열기 — 재수집 대기 1건 · 끊김 5시간")
    HB.beat(uid, "1.5.167", "beat")
    assert not any(t["kind"] == "collector_off" for t in H.build({uid})["attention"]["todo"])
    st.reset_for_tests()


def test_oneshot_drain_keeps_rows_beyond_five(monkeypatch):
    """10-20 13:30 실측: 7줄 → 앞 5줄만 돌고 2줄이 사라졌다. 나머지는 다음 틱으로 남는다."""
    from src.db import image_translate_queue_pg as st
    from src.services import oneshot_ops as O
    st.reset_for_tests()
    ran = []
    monkeypatch.setattr(O, "_run", lambda r: ran.append(r["item_id"]) or {"ok": True})
    st.state_set(O.QUEUE_KEY, {"rows": [{"op": "review_status", "item_id": str(i)} for i in range(7)]})
    assert O.drain()["picked"] == 5 and ran == ["0", "1", "2", "3", "4"]
    assert [r["item_id"] for r in O.queue_rows()] == ["5", "6"]
    O.drain()
    assert ran[-2:] == ["5", "6"] and O.queue_rows() == []
    st.reset_for_tests()


def test_thumb_probe_reports_status_without_writing(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    import requests
    item = {"id": "t", "image_url": "https://img.example/a.jpg", "extra_json": json.dumps({"images": ["https://img.example/a.jpg", "https://img.example/b.jpg"]})}
    monkeypatch.setattr(D, "_item", lambda iid: (item, "u"))

    class _R:
        def __init__(self, code):
            self.status_code, self.headers = code, {"Content-Type": "image/jpeg", "Content-Length": "10"}

        def close(self):
            pass
    monkeypatch.setattr(requests, "get", lambda u, **k: _R(200 if u.endswith("a.jpg") else 404))
    out = O._run({"op": "thumb_probe", "item_id": "t"})
    assert out["ok"] and [r["status"] for r in out["rows"]] == [200, 404] and out["why"] == "일부 실패"
    monkeypatch.setattr(D, "_item", lambda iid: (dict(item, image_url=""), "u"))
    assert O._run({"op": "thumb_probe", "item_id": "t"})["why"] == "대표 사진 주소 없음"


@pytest.mark.parametrize("version_changed,expect", [(False, 0), (True, 2)])
def test_editor_get_resends_only_when_outbound_version_changes(monkeypatch, version_changed, expect):
    """Y12-D 추가 1 — 15:28 「전부 넘김」 뒤 15:30 쿠팡·네이버 재전송: 편집기를 **열기(GET)만** 해도 OCR 상자 기록을 저장하며
    마켓 갱신 줄을 걸었다. 이제 나가는 버전(`current_key`)이 바뀐 때만 다시 보낸다."""
    from src.services import image_edit as IE
    from src.services import naver_detail_refresh as NDR
    from src.services import coupang_detail_refresh as CDR
    uid = "u-y12d-ed"
    iid = _add(uid, {"detail_images_ko": [{"idx": 0, "kind": "detail", "status": "done", "url": "https://img.example/0.jpg"}]},
               url="https://item.taobao.com/item.htm?id=81")
    sent = []
    monkeypatch.setattr(NDR, "enqueue_item", lambda *a, **k: sent.append("naver"))
    monkeypatch.setattr(CDR, "enqueue_item", lambda *a, **k: sent.append("coupang"))
    monkeypatch.setattr(IE, "drop_legacy_edits", lambda ex: [])
    keys = iter(["v1", "v2" if version_changed else "v1"])
    monkeypatch.setattr(IE, "current_key", lambda e: next(keys))

    def refresh(ex, kind, idx):
        IE._entry(ex, kind, idx)["vboxes"] = [{"id": "t0"}]           # OCR로 새로 읽은 상자 — 기록은 바뀐다
        return True
    monkeypatch.setattr(IE, "refresh_pending", refresh)
    monkeypatch.setattr(IE, "plan", lambda ex, kind, idx, **k: {"boxes": []})
    monkeypatch.setattr(IE, "_original", lambda ex, kind, idx: "")
    r = _client(uid).get(f"/seller/collect/{iid}/image-edit/detail/0")
    assert r.status_code == 200 and len(sent) == expect


def test_oneshot_drain_runs_one_prevalidate_per_tick(monkeypatch):
    """Y14(10-21 08:00·08:10 실측): 사전검증 5건을 두 틱에 몰았더니 잡이 겹쳐 인스턴스 437·461MB — 3건 「메모리 여유가 없어요」.
    사전검증을 띄우는 줄은 한 틱에 하나만, 가벼운 줄은 그 틱에 같이 돈다 · 남은 줄은 순서 그대로."""
    from src.db import image_translate_queue_pg as st
    from src.services import oneshot_ops as O
    st.reset_for_tests()
    ran = []
    monkeypatch.setattr(O, "_run", lambda r: ran.append(r["item_id"]) or {"ok": True})
    rows = [{"op": "prevalidate", "item_id": "p1"}, {"op": "prevalidate", "item_id": "p2"},
            {"op": "coupang_inspect", "item_id": "i1"}, {"op": "owner_decision", "item_id": "d1"},
            {"op": "review_status", "item_id": "r1"}]
    st.state_set(O.QUEUE_KEY, {"rows": rows})
    O.drain()
    assert ran == ["p1", "i1", "r1"] and [r["item_id"] for r in O.queue_rows()] == ["p2", "d1"]
    O.drain()
    assert ran[-1] == "p2" and [r["item_id"] for r in O.queue_rows()] == ["d1"]
    O.drain()
    assert ran[-1] == "d1" and O.queue_rows() == []
    st.reset_for_tests()
