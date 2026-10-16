"""Y11-V(오너 2026-10-16 19:12~19:16) — 네이버 본문 자동 다시 보내기 큐 · 「ISURE에」 렌더 · 옵션 사진 편집기 문구 · 티몰 입점 배너."""
import json

import pytest


# ── 2. 「M … ISURE에」 — 한국어로 그린 상자를 한글 없는 원문으로 덧그리지 않는다 ─────────────────────────────────

def test_foreign_revert_rule():
    from src.services import image_polish as P
    assert P.foreign_revert("ISURE", {"src": "ISURE", "tgt": "이수에"})          # 운영 상세 14 t2
    assert not P.foreign_revert("65 cm", {"src": "65cm", "tgt": "65cm"})          # 숫자·단위 띄어쓰기 — 한글 없는 곳끼리
    assert not P.foreign_revert("정품 보장", {"src": "正品保障", "tgt": "정품 보장"})
    assert not P.foreign_revert("", {"tgt": "이수에"})


def test_old_polish_with_foreign_revert_is_redone():
    """운영 VRSUK 상세 14: 다듬은 버전(edit:1)이 「이수에」 상자에 「ISURE」를 덧그렸다 — 다시 다듬을 장으로 잡힌다."""
    from src.services import image_edit as IE
    from src.services import image_polish as P
    e = {"status": "done", "current": "edit:1", "translated_url": "https://x/t.jpg",
         "boxes": [{"src": "M", "tgt": "M"}, {"src": "ISURE", "tgt": "이수에"}],
         "edits": [{"n": 1, "by": P.POLISH_BY, "render": "local", "render_v": IE.RENDER_V, "base_key": "translated",
                    "url": "https://x/e.jpg", "ready": True, "ops": [{"id": "t1", "action": "text", "text": "ISURE"}]}]}
    assert P._redo_polish(e["edits"][0], e["boxes"])
    e2 = json.loads(json.dumps(e))
    e2["edits"][0]["ops"] = [{"id": "t1", "action": "text", "text": "이스레"}]
    assert not P._redo_polish(e2["edits"][0], e2["boxes"])


# ── 1. 네이버 본문 자동 다시 보내기 큐 ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def qstate(monkeypatch):
    from src.db import image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "state_get", lambda k: box.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: box.__setitem__(k, v))
    monkeypatch.setattr(st, "counts", lambda item_id: {"queued": 0, "running": 0}, raising=False)
    return box


EX = {"uploaded": [{"market": "smartstore:chezgoga", "product_id": "13752236154", "channel_product_no": "13813465384"},
                   {"market": "smartstore:gocosmos", "product_id": "13752236263", "channel_product_no": "13813465493"},
                   {"market": "coupang:gogane", "product_id": "16415921785"}]}


def test_enqueue_one_row_per_naver_store(qstate):
    from src.services import naver_detail_refresh as N
    assert N.enqueue_item("it", EX, "u1") == 2
    assert N.enqueue_item("it", EX, "u1") == 0
    assert {r["market"] for r in N.queue_rows()} == {"smartstore:chezgoga", "smartstore:gocosmos"}


class _Up:
    def __init__(self, sent):
        self.sent = sent

    def update_detail_content(self, pid, html):
        self.sent.append((pid, html))
        return {"success": True, "raw": '{"originProductNo": %s}' % pid}


def _patch_body(monkeypatch, html):
    from src.services import naver_detail_refresh as N
    import src.uploaders.naver_detail as ND
    monkeypatch.setattr(N, "body_payload", lambda item, seller_id="": {"description_html": html, "sku": "s"})
    monkeypatch.setattr(ND, "judge", lambda h, up, sku: {"ok": True, "html": h, "dropped": [], "cached": 0})
    import contextlib
    import src.seller_console.upload_dispatcher as UD
    monkeypatch.setattr(UD, "_for_market", lambda m: (None, contextlib.nullcontext()))


def test_drain_sends_only_when_selling_and_dedupes_by_hash(qstate, monkeypatch):
    from src.services import naver_detail_refresh as N
    _patch_body(monkeypatch, '<img src="https://a/1.jpg"><p>본문</p>')
    item = {"id": "it", "extra_json": json.dumps(EX)}
    saved, sent = {}, []
    N.enqueue_item("it", EX, "u1")
    status = {"smartstore:chezgoga": "approved", "smartstore:gocosmos": "pending"}
    out = N.drain(lambda i, s: {"id": "it", "extra_json": json.dumps(saved.get("ex") or EX)},
                  lambda i, s: (lambda ex: saved.__setitem__("ex", ex)), make_up=lambda: _Up(sent),
                  status_of=lambda rec: {"state": status[rec["market"]], "label": "판매대기"})
    assert out["sent"] == 1 and out["ok"] == 1 and sent == [("13752236154", '<img src="https://a/1.jpg"><p>본문</p>')]
    assert [r["market"] for r in N.queue_rows()] == ["smartstore:gocosmos"]          # 판매대기 — 기다린다(시도 0)
    assert N.queue_rows()[0]["tries"] == 0
    ds = next(u for u in saved["ex"]["uploaded"] if u["market"] == "smartstore:chezgoga")["detail_sync"]
    assert ds["ok"] and ds["hash"] == N._hash('<img src="https://a/1.jpg"><p>본문</p>') and "originProductNo" in ds["raw"]
    # 같은 본문 → 다시 보내지 않는다
    N.enqueue_item("it", saved["ex"], "u1")
    status["smartstore:gocosmos"] = "approved"
    sent.clear()
    out = N.drain(lambda i, s: {"id": "it", "extra_json": json.dumps(saved["ex"])},
                  lambda i, s: (lambda ex: saved.__setitem__("ex", ex)), make_up=lambda: _Up(sent),
                  status_of=lambda rec: {"state": status[rec["market"]]})
    assert [p for p, _h in sent] == ["13752236263"]                                   # 셰고가는 같은 본문 — 안 보냄
    assert not N.queue_rows()


def test_drain_waits_while_item_images_are_busy(qstate, monkeypatch):
    from src.services import naver_detail_refresh as N
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "counts", lambda item_id: {"queued": 3, "running": 1}, raising=False)
    N.enqueue_item("it", EX, "u1")
    out = N.drain(lambda i, s: {"id": "it", "extra_json": json.dumps(EX)}, lambda i, s: (lambda ex: None),
                  make_up=lambda: pytest.fail("보내면 안 됨"), status_of=lambda rec: {"state": "approved"})
    assert out["sent"] == 0 and len(N.queue_rows()) == 2 and all(r.get("waiting") for r in out["rows"])


# ── 3. 옵션 사진 편집기 — 「번역하고 글자 상자 받기」가 **그 종류의** 번역본을 본다 ────────────────────────────────

def test_translate_route_uses_sku_kind(monkeypatch):
    from src.order_webhook import app
    import src.seller_console.views as V
    from src.services import image_translate_tencent as tc
    from src.services import image_translate_auto as A
    ex = {"detail_images_ko": [{"idx": 0, "status": "done", "boxes": [{"src": "x"}]}],      # 상세 0번은 상자 있음
          "skus": [{"sku_id": "s1", "image": "https://a/s.jpg"}]}
    monkeypatch.setattr(V, "_check_auth", lambda: True)
    monkeypatch.setattr(V, "_image_edit_item", lambda item_id: ({"id": item_id}, ex))
    monkeypatch.setattr(tc, "is_configured", lambda: True)
    got = []

    class Q:
        def requeue_pages(self, item_id, pages):
            got.append(pages)
            return 0

        def enqueue(self, uid, item_id, pages):
            got.append(pages)
            return 1
    monkeypatch.setattr(A, "_q", lambda: Q())
    monkeypatch.setattr(A, "kick", lambda: None)
    r = app.test_client().post("/seller/collect/it/image-edit/sku/0/translate")
    assert r.status_code == 202, r.get_json()                       # 예전: 상세 0번 상자를 보고 409 「이미 번역됨」
    assert got[-1] == [("sku", 0)]
    ex["sku_images_ko"] = [{"idx": 0, "status": "done", "boxes": [{"src": "正品"}]}]
    r = app.test_client().post("/seller/collect/it/image-edit/sku/0/translate")
    assert r.status_code == 409 and r.get_json()["protected"]


# ── 1. 티몰 입점 배너 ────────────────────────────────────────────────────────────────────────────────────────

def test_tmall_invite_banner_is_store_ui():
    from src.services import detail_image_plan as D
    assert D.text_exclusion("天猫国际邀请入驻 /2021年 致力于把「好品质」 送入1000+家")
    assert D.text_exclusion("品牌入驻 旗舰店")
