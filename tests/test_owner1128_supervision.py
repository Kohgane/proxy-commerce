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
