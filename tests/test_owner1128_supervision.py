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
    for gone in ("sony", "소니", "garmin", "가민", "yeti", "예티", "xerjoff", "제르조프", "stanley", "스탠리", "staub", "bose"):   # 「그 밖」만 뺌
        assert gone not in act, gone
    # 오너 11-28 08:34: 골프·고가 의류는 브랜드째 계속 막고, 애매한 것(운동화·스포츠·아웃도어 용품)은 오너 답까지 그대로
    for stay in ("ping", "callaway", "titleist", "taylormade", "srixon", "cobra", "mizuno", "캘러웨이", "미즈노",
                 "moncler", "canada goose", "arcteryx", "lululemon", "the north face", "columbia", "몽클레르", "노스페이스",
                 "adidas", "아디다스", "new balance", "hoka", "salomon", "keen", "msr", "osprey", "fizik"):
        assert stay in act, stay
    assert RG.brand_group("Callaway") == "golf" and RG.brand_group("몽클레르") == "apparel" and RG.brand_group("adidas") == "ask"
    assert RG.brand_group("sony") == "" and RG.brand_group("casetify") == ""
    for stay in ("casetify", "케이스티파이", "peter millar", "피터밀러", "memo paris", "메모파리",                 # 브랜드 단위 근거 · 오너 판단
                 "laser pointer",                                                                             # 우리 정책 차단(청소년유해)
                 "hello kitty", "sanrio", "nintendo", "pokemon", "disney", "marvel", "포켓몬", "디즈니"):          # 범위 밖
        assert stay in act, stay
    assert RG.blacklist_words("Sony WH-1000XM5 헤드폰") == []
    assert RG.blacklist_words("CASETiFY 임팩트 케이스") == ["casetify"]
    toks = RG.tokens()
    assert set(t.lower() for t in toks["no_evidence"]) <= {t.lower() for t in PROD}       # 운영 목록에 있는 낱말만 뺀다(오타로 엉뚱한 낱말 0)
    assert not set(t.lower() for t in toks["no_evidence"]) & {"casetify", "peter millar", "memo paris", "hello kitty", "laser pointer"}
    groups = {t.lower() for ws in toks["brand_groups"].values() for t in ws}
    assert not groups & {t.lower() for t in toks["no_evidence"]}                       # 막는 묶음과 뺄 줄이 겹치지 않음
    assert groups <= {t.lower() for t in PROD}


def test_relist_skips_golf_and_apparel_brand_rows_with_their_own_locked_reason(monkeypatch):
    """오너 11-28 08:34: 셰고가·고코스모스 판매중지분 중 골프·고가 의류 브랜드 줄은 켤 후보에서 빼고 사유 「브랜드 차단(골프/고가 의류)」 — 오너도 못 고름."""
    from src.services import risk_gate as RG
    from src.services import smartstore_relist as SR
    monkeypatch.setattr(RG, "_blacklist", lambda: RG.brand_filter(PROD))
    brands = RG.active_blacklist()
    base = {"channel_no": "1", "origin_no": "2", "name": "", "sale_price": 100000, "category": "스포츠", "seller_code": ""}
    for name, want in (("Callaway 골프 장갑 남성", "brand_golf"), ("[해외직구] 몽클레르 패딩 조끼", "brand_apparel"),
                       ("adidas 러닝화", "brand"), ("Sony 이어폰 케이스", None)):
        j = SR._judge_row({**base, "name": name}, None, {"ss": 0, "cp": 0}, [], brands, [])
        got = [k for k in j["exclude"] if k.startswith("brand")]
        assert (got[0] if got else None) == want, (name, j["exclude"])
    assert SR.REASON_KO["brand_golf"] == "브랜드 차단(골프)" and SR.REASON_KO["brand_apparel"] == "브랜드 차단(고가 의류)"
    assert {"brand_golf", "brand_apparel"} <= set(SR.LOCKED)


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
        monkeypatch.setattr(AR, "run", lambda i, sids=None, **k: {"ok": False, "saved": True, "reason": "아마존 화면을 읽지 못했어요(막힘·빈 화면)"})
        iid2 = chs.append(source="extension", url="https://a.co/d/11ABC", title="tomtoc", seller_id="u-1128", extra={"images": []})
        iid2 = iid2[0] if isinstance(iid2, tuple) else iid2
        out2 = O._run({"op": "url_canon", "item_id": iid2})
        assert out2["changed"] and out2["refetch"]["reason"].startswith("아마존 화면을 읽지 못했어요")   # 실패 사유가 결과에 실린다
        chs.delete([iid2], seller_id="u-1128")
        again = O._run({"op": "url_canon", "item_id": iid})
        assert again["ok"] and again["changed"] is False and len(calls) == 1          # 이미 정본 — 다시 안 고침·다시 안 가져옴
    finally:
        chs.delete([iid], seller_id="u-1128")


def test_two_overseas_outbound_places_show_name_and_address_to_pick(monkeypatch):
    """오너 11-28 감독 4: 고가네 쿠팡 해외 출고지 2곳 — 보류 문장(카드)에 둘의 이름·주소·코드를 그대로 보여 고르기 쉽게(읽기만 · 저장 0)."""
    from src.uploaders import coupang_uploader as CU
    monkeypatch.setenv("COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE", "")
    monkeypatch.setenv("COUPANG_GOGANE_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE", "")
    rows = [{"outboundShippingPlaceCode": 31234567, "shippingPlaceName": "오리건 배대지", "addressType": "OVERSEA", "usable": True,
             "placeAddresses": [{"returnAddress": "12345 SW Example Rd", "returnAddressDetail": "Suite 9", "countryCode": "US"}]},
            {"outboundShippingPlaceCode": 31234568, "shippingPlaceName": "도쿄 창고", "addressType": "OVERSEA", "usable": True,
             "placeAddresses": [{"returnAddress": "1-2-3 Minato", "countryCode": "JP"}]}]
    CU._SHARED.clear()
    calls = []
    monkeypatch.setattr(CU.CoupangUploader, "_api_request",
                        lambda self, m, path, data=None, **k: (calls.append(m), {"code": "SUCCESS", "data": {"content": rows}})[1])
    up = CU.CoupangUploader(account="gogane", vendor_id="A01381223")
    up.delivery_method = "AGENT_BUY"
    code, why = up.outbound_for_delivery()
    assert code == "" and "2곳" in why
    assert "① 오리건 배대지(31234567) 12345 SW Example Rd Suite 9 [US]" in why and "② 도쿄 창고(31234568) 1-2-3 Minato [JP]" in why
    assert set(calls) == {"GET"}
    CU._SHARED.clear()


def test_brand_catalog_matches_exact_product_number_once_and_labels_name_matches(monkeypatch, tmp_path):
    """오너 11-28 감독 3: 원가 못 찾은 줄 → 브랜드 공식몰 **전체 목록**(블루호스트 · DB 쓰기 0)에서 품번이 정확히 하나로 맞으면 `code`,
    아니면 가게 제목 70%·3낱말 이름 일치 `name` · 품번이 여럿에 맞으면 못 정함. 오라클 넣기는 큐 덧붙이기 하나 · 품번 일치는 「품번 일치(공식몰)」(실측처럼),
    이름 일치는 「이름 일치(확인 필요)」."""
    import importlib.util
    import json as _j
    spec = importlib.util.spec_from_file_location("brand_catalog_1128", "ops/oracle_a1/brand_catalog_1128.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    assert m.codes_in("[해외직구] 포터 PORTER POTR / DISSECTION SHOULDER BAG 994-25002", "PT-994-25002") == {"994-25002"}
    assert m.codes_in("To Summer OSMANTHUS REED DIFFUSER 200ML", "TOSU-OSMANTHUSREEDDIF-47") == set()
    cat = {"products": [{"title": "Light Prismatic Cotton Rope Dog Leash", "handle": "light-prismatic-leash",
                         "variants": [{"price": "68.00", "available": True, "sku": "FMA-LP-01"}]},
                        {"title": "Wisteria Cotton Rope Dog Leash", "handle": "wisteria-leash", "variants": [{"price": "68.00", "available": False}]},
                        {"title": "Dissection Shoulder Bag 994-25002", "handle": "dissection-994-25002", "variants": [{"price": "300.00", "available": True}]},
                        {"title": "Tanker 622-19859 black", "handle": "tanker-a", "variants": [{"price": "200.00", "available": True}]},
                        {"title": "Tanker 622-19859 olive", "handle": "tanker-b", "variants": [{"price": "200.00", "available": True}]}]}

    def get(url, timeout=25):
        if url.endswith("cart.js"):
            return 200, {"currency": "USD"}
        return 200, (cat if "page=1" in url else {"products": []})
    monkeypatch.setattr(m, "get", get)
    (tmp_path / "vault" / "srv_snap" / "apply_out").mkdir(parents=True)
    (tmp_path / "vault" / "srv_snap" / "apply_out" / "relistledger_data_chezgoga.txt").write_text(_j.dumps({"unmatched": [
        {"channel_no": "1", "code": "FMA-FOUNDMYANI-0007", "name": "[해외직구] Found My Animal 파운드마이애니멀 Light Prismatic Cotton Rope Dog Leash by"},
        {"channel_no": "2", "code": "FMA-FOUNDMYANI-0012", "name": "[해외직구] Found My Animal Wisteria Cotton Rope Dog Leash | Bolt Snaps"},
        {"channel_no": "3", "code": "XX-1", "name": "PORTER DISSECTION SHOULDER BAG 994-25002", "domain": "shop.example.com"},
        {"channel_no": "4", "code": "XX-2", "name": "PORTER TANKER 622-19859", "domain": "shop.example.com"},
        {"channel_no": "5", "code": "PT-994-1", "name": "PORTER X 994-11111", "domain": "www.yoshidakaban.com"}],
        "prefix_domain": {"FMA": "foundmyanimal.com"}}))
    monkeypatch.setattr(m, "H", str(tmp_path))
    assert m.main(["chezgoga"]) == 0
    rows = {r["channel_no"]: r for r in _j.loads((tmp_path / "vault" / "srv_snap" / "apply_out" / "brandcat_data_chezgoga.txt").read_text())["rows"]}
    assert rows["1"]["kind"] == "name" and rows["1"]["cost"] == 68.0 and rows["1"]["currency"] == "USD"
    assert rows["2"]["src_state"] == "soldout"
    assert rows["3"]["kind"] == "code" and rows["3"]["url"].endswith("/dissection-994-25002") and "994-25002" in rows["3"]["via"]
    assert "4" not in rows                                              # 품번이 두 상품에 맞음 — 못 정함(틀린 원가 0)
    assert "5" not in rows                                              # 요시다카반은 Shopify 아님 — 오라클 따로
    spec2 = importlib.util.spec_from_file_location("brandcat_push_1128", "ops/oracle_a1/brandcat_push_1128.py")
    p = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(p)
    up = p.SQL.upper()
    assert up.count("UPDATE APP_STATE") == 1 and "'ops:oneshot:queue'" in p.SQL and "DELETE" not in up
    from src.services import relist_ledger as RL
    assert RL.SRC_KO["code_match"] == "품번 일치(공식몰)" and RL.src_label({"src": "품번 일치(공식몰)", "updated": "2026-11-28"}) == "품번 일치(공식몰 11-28)"
