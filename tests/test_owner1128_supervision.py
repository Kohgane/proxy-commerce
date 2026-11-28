"""오너 11-28 감독 계약.

1. 금지 브랜드 「근거 없음」 줄을 뺀다(반려 났던 제품만 · 핀포인트) — 브랜드 단위 근거·우리 정책 차단·범위 밖은 그대로.
   뺀 브랜드에 상표권 반려가 오면 반려 감시가 **그 상품만** 반려 상품 목록에 넣는다(등록 사전검증·판매 재개 같은 목록).
"""
from __future__ import annotations

import json
import os

import pytest

PROD = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "y11o_vrsuk_risk.json"),
                      encoding="utf-8"))["risk_decisions"]["blacklist"]["names"]


@pytest.fixture
def state(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    monkeypatch.delattr(st, "state_update", raising=False)
    from src.services import risk_gate as RG
    RG._rej_cache.update(at=0.0, rows=None)
    yield s
    RG._rej_cache.update(at=0.0, rows=None)


def test_no_evidence_brands_leave_the_list_but_evidence_policy_and_out_of_scope_stay(monkeypatch):
    """운영 목록 원문 151개 그대로 넣고 본다 — 근거 없는 브랜드(영문·한글)는 빠지고, 남는 건 근거·정책·범위 밖뿐."""
    from src.services import risk_gate as RG
    monkeypatch.setattr(RG, "_blacklist", lambda: RG.brand_filter(PROD))
    act = {t.lower() for t in RG.active_blacklist()}
    for gone in ("adidas", "아디다스", "sony", "소니", "garmin", "가민", "yeti", "예티", "moncler", "몽클레르", "the north face",
                 "노스페이스", "xerjoff", "제르조프", "ping", "keen", "msr", "stanley", "스탠리"):
        assert gone not in act, gone
    for stay in ("casetify", "케이스티파이", "peter millar", "피터밀러", "memo paris", "메모파리",                 # 브랜드 단위 근거 · 오너 판단
                 "laser pointer",                                                                             # 우리 정책 차단(청소년유해)
                 "hello kitty", "sanrio", "nintendo", "pokemon", "disney", "marvel", "포켓몬", "디즈니"):          # 범위 밖
        assert stay in act, stay
    assert RG.blacklist_words("Sony WH-1000XM5 헤드폰") == []
    assert RG.blacklist_words("CASETiFY 임팩트 케이스") == ["casetify"]
    toks = RG.tokens()
    assert set(t.lower() for t in toks["no_evidence"]) <= {t.lower() for t in PROD}       # 운영 목록에 있는 낱말만 뺀다(오타로 엉뚱한 낱말 0)
    assert not set(t.lower() for t in toks["no_evidence"]) & {"casetify", "peter millar", "memo paris", "hello kitty", "laser pointer"}


def test_trademark_rejection_blocks_that_product_only_and_other_kinds_do_not(state, monkeypatch):
    """반려 감시 1회전 — 상표권(담당자 검토) 반려만 그 상품을 반려 상품 목록에 넣는다. 이미지 규격 반려·판매중 전환은 안 넣는다."""
    from src.pipeline import reject_watch as RW
    from src.services import risk_gate as RG
    monkeypatch.setattr(RG, "_blacklist", lambda: [])
    items = [{"sid": "16500000001", "title": "Sony 헤드폰 거치대", "account": "gogane", "source_url": "https://shop.example.com/products/sony-stand"},
             {"sid": "16500000002", "title": "LED 스탠드", "account": "gogane", "source_url": "https://shop.example.com/products/led"},
             {"sid": "16500000003", "title": "Sony 케이블", "account": "gogane", "source_url": "https://shop.example.com/products/cable"}]
    hist = {"16500000001": "상표권 침해 소지가 있어 반려합니다(담당자 검토)",
            "16500000002": "대표이미지는 최대 10M, 최소 500*500",
            "16500000003": "상표권 침해 소지가 있어 반려합니다(담당자 검토)"}

    def classify(comment, title=""):
        return RW.classify_rejection(comment, title=title)

    def history(sid, acct):
        return {"sid": sid}
    monkeypatch.setattr(RW, "latest_rejection_comment", lambda h: hist[h["sid"]])
    monkeypatch.setattr(RW, "wing_state", lambda h: "approved" if h["sid"] == "16500000003" else "rejected")
    monkeypatch.setattr(RW, "was_selling", lambda h: False)
    monkeypatch.setattr(RW, "timeline", lambda h, limit=12: [])
    assert RW.classify_rejection(hist["16500000001"])["kind"] == "trademark"
    from src.pricing import cron as C
    out = RW.watch_registered(queue_fn=lambda n: items, history_fn=history, classify_fn=classify,
                              rejected_fn=C._rejected_recorder("gogane"))
    assert out["rejected_added"] == 1
    rows = RG.rejected_products()
    auto = [r for r in rows if r.get("auto")]
    assert [r["product_no"] for r in auto] == ["16500000001"] and auto[0]["market"] == "쿠팡(gogane)"
    assert "상표권" in auto[0]["reason"] and auto[0]["url"].endswith("/sony-stand")
    # 그 상품만 막는다 — 같은 소싱처 주소로 다시 등록하려 해도 막히고, 같은 브랜드 다른 상품은 통과
    hit = RG.scan({"title_ko": "Sony 헤드폰 거치대", "url": "https://shop.example.com/products/sony-stand?v=2"})
    assert any(h["key"] == "rejected_product" and h["grade"] == "block" for h in hit["hits"])
    other = RG.scan({"title_ko": "Sony 케이블 정리함", "url": "https://shop.example.com/products/organizer"})
    assert not any(h["key"] == "rejected_product" for h in other["hits"])
    # 같은 상품이 또 반려돼도 줄이 늘지 않는다(덮어씀)
    RW.watch_registered(queue_fn=lambda n: items[:1], history_fn=history, classify_fn=classify, rejected_fn=C._rejected_recorder("gogane"))
    assert len([r for r in RG.rejected_products() if r.get("auto")]) == 1
    # dry-run은 목록을 안 건드린다(cron이 dry_run이면 rejected_fn=None)
    out2 = RW.watch_registered(queue_fn=lambda n: items, history_fn=history, classify_fn=classify, dry_run=True)
    assert "rejected_added" not in out2


def test_record_rejected_needs_a_product_pointer(state):
    from src.services import risk_gate as RG
    assert RG.record_rejected(market="쿠팡(gogane)", reason="상표권")["ok"] is False
    assert RG.record_rejected(market="쿠팡(gogane)", product_no="16500000009", reason="상표권")["ok"] is True
    assert RG.rejected_match(codes=["16500000009"])["product_no"] == "16500000009"


def test_relist_marks_unmeasured_ledger_cost_and_puts_measured_may_june_rows_first(state, monkeypatch):
    """오너 11-28 감독 2: 원가 찾은 줄로 바로 목록 — 현재가를 못 잰 줄은 「원가: 장부(날짜) · 현재가 미확인」,
    5~6월 등록분은 같은 단계 안에서 잰 것(소싱처 실측)부터 앞에. 화면·진단 둘 다 같은 표시."""
    from tests.test_owner1126_relist import FakeUp, _env, _size
    from src.services import relist_ledger as RL
    SR = _env(monkeypatch)
    prods = [{"ch": "30000", "origin": "40000", "name": "램프 A", "price": 200000, "reg": "2026-05-10T00:00:00"},
             {"ch": "30001", "origin": "40001", "name": "램프 B", "price": 200000, "reg": "2026-06-02T00:00:00"},
             {"ch": "30002", "origin": "40002", "name": "램프 C", "price": 200000, "reg": "2026-10-01T00:00:00"}]
    up = FakeUp(prods, {"SALE": 400})
    real = up._api_request

    def api(method, path, data=None):
        res = real(method, path, data)
        if path == "/v1/products/search":
            for i, c in enumerate(res["contents"]):
                c["channelProducts"][0]["sellerManagementCode"] = f"CP-1500000000{i}"
        return res
    up._api_request = api
    RL.load_part("chezgoga", 1, 1, "sourcing_map", [{"code": f"CP-1500000000{i}", "cost": "40", "currency": "USD", "updated": "2026-05-20"}
                                                    for i in range(3)])
    RL.load_part("chezgoga", 1, 1, "source_live", [{"code": "CP-15000000001", "cost": "40", "currency": "USD", "updated": "2026-11-28",
                                                    "src_state": "ok", "via": "shopify products.json"}])
    p = SR.build("chezgoga", up=up, size_of=_size)
    by = {x["channel_no"]: x for x in p["rows"]}
    assert by["30000"]["cost_note"] == "원가: 볼트 소싱맵(2026-05-20) · 현재가 미확인" and not by["30000"]["cost_live"]
    assert by["30001"]["cost_note"] == "" and by["30001"]["cost_live"] and by["30001"]["cost_src"] == "소싱처 실측(11-28)"
    on = [x["channel_no"] for x in p["rows"] if x["action"] == "on"]
    assert on.index("30001") < on.index("30000")                       # 5~6월분: 잰 줄이 못 잰 줄보다 앞
    assert p["on_unmeasured"] == sum(1 for x in p["rows"] if x["action"] == "on" and not x["cost_live"]) >= 1


def test_url_canon_rewrites_short_link_keeps_raw_url_and_refetches(monkeypatch):
    """오너 11-28 감독 5(오너 확인됨): 아마존 짧은 링크로 저장된 행 → 정본 주소 · 원래 주소는 raw_url(되돌릴 수 있게) ·
    이어서 서버 「다시 가져오기」 · 이미 정본이면 그대로 · 마켓 전송 0(「사진 다시 보내기」는 누를 수 있는 마켓만 알려 줌)."""
    import json as _j
    from src.seller_console import collect_history_store as chs
    from src.services import oneshot_ops as O
    import src.collectors.link_diag as LD
    assert "url_canon" in O.OPS and "url_canon" in O.HEAVY_OPS and "url_canon" not in O.REQUEUE_SAFE_OPS
    iid = chs.append(source="extension", url="https://a.co/d/00RG5ThB", title="OKNIFE 접이식 칼 거치대", seller_id="u-1128", extra={"images": []})
    iid = iid[0] if isinstance(iid, tuple) else iid
    calls = []
    monkeypatch.setattr(LD, "resolve_share_link", lambda u, timeout=8: {"ok": True, "market": "amazon", "item_id": "B0CXYZ1234",
                                                                          "canonical_url": "https://www.amazon.com/dp/B0CXYZ1234"})
    import src.services.amazon_refetch as AR
    monkeypatch.setattr(AR, "run", lambda i, sids=None, **k: calls.append((i, sids)) or {"ok": True, "line": "사진 7장 · 옵션가 3"})
    try:
        out = O._run({"op": "url_canon", "item_id": iid[:8]})
        assert out["ok"] and out["changed"] and out["url"] == "https://www.amazon.com/dp/B0CXYZ1234" and out["raw_url"] == "https://a.co/d/00RG5ThB"
        row = chs.get(iid)
        assert row["url"] == "https://www.amazon.com/dp/B0CXYZ1234" and row["domain"] == "www.amazon.com"
        assert _j.loads(row["extra_json"])["raw_url"] == "https://a.co/d/00RG5ThB"
        assert calls == [(iid, {"u-1128"})] and out["refetch"]["ok"] and out["resend"] == []
        again = O._run({"op": "url_canon", "item_id": iid})
        assert again["ok"] and again["changed"] is False and len(calls) == 1          # 이미 정본 — 다시 안 고침·다시 안 가져옴
    finally:
        chs.delete([iid], seller_id="u-1128")
