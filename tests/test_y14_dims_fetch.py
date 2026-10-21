"""Y14(오너 2026-10-21 「가구 4건 치수 서버에서 수집」) — 온바운드 규격 · 사진 OCR · 규격 블록 대조 · 수집 단계 자동 · 배송비 엔진 반영.

운영 실측(10-21): 바퀴 의자·접이식 의자·발판·허리 보호 소파 4건이 「치수 확인 필요」 — 상세 사진은 번역 실패(글자 없음),
규격 블록 없음, 온바운드 보관본 없음. 사람 손으로 넘어오지 않게 서버가 모은다.
"""
import json

from src.services import dims_fetch as DF


def _item(extra, url="https://item.taobao.com/item.htm?id=616118458070&ns=1"):
    return {"id": "805773b6", "url": url, "extra_json": json.dumps(extra, ensure_ascii=False)}


def _ob(props=None, plist=None, ok=True):
    def call(iid):
        assert iid == "616118458070"
        return {"ok": ok, "raw": {"item": {"props": props or [], "props_list": plist or {}}}, "why": "" if ok else "4013"}
    return call


def test_parse_reads_cross_and_labeled_dims():
    assert DF.parse("尺寸: 60x50x45cm")["dims_cm"] == [60.0, 50.0, 45.0]
    assert DF.parse("宽60cm 长50cm 高41cm")["dims_cm"] == [60.0, 50.0, 41.0]
    assert DF.parse("坐高41cm") is None                            # 한 축만 — 치수 아님
    assert DF.parse("600*500*450mm")["dims_cm"] == [60.0, 50.0, 45.0]


def test_two_sources_agree_is_confirmed_one_is_estimate():
    ex = {"images": ["https://img/g0.jpg"], "detail_images": ["https://img/d0.jpg"],
          "detail_images_ko": [{"idx": 0, "status": "failed"}]}
    ocr_calls = []

    def ocr(url):
        ocr_calls.append(url)
        return "产品尺寸 宽61cm 长50cm 高45cm"
    r = DF.fetch(_item(ex), ob_call=_ob(props=[{"name": "尺寸", "value": "60*50*45cm"}]), ocr=ocr)["dims_auto"]
    assert r["confidence"] == "확정" and r["agree"] == ["onebound", "photo"] and r["dims_cm"] == [61.0, 50.0, 45.0]
    assert "온바운드 규격·사진 글자 일치" in r["label"]
    assert ocr_calls == ["https://img/d0.jpg", "https://img/g0.jpg"]   # 글자 없는 장만 · 상세부터
    # 둘째 실행 — OCR 결과는 기록에서 다시 쓴다(텐센트 0회)
    ex2 = dict(ex, dims_auto=r)
    ocr_calls.clear()
    DF.fetch(_item(ex2), ob_call=_ob(), ocr=ocr)
    assert ocr_calls == []
    # 온바운드만 — 추정
    r1 = DF.fetch(_item({}), ob_call=_ob(props=[{"name": "规格", "value": "80x70x75cm"}]), ocr=lambda u: "")["dims_auto"]
    assert r1["confidence"] == "추정" and r1["label"] == "추정(온바운드 규격)"


def test_option_dims_take_biggest_and_disagreement_is_estimate():
    plist = {"1:1": "尺寸:40x40x41cm", "1:2": "尺寸:50x50x45cm"}
    r = DF.fetch(_item({"detail_specs": [["尺寸", "90x80x70cm"]]}), ob_call=_ob(plist=plist), ocr=lambda u: "")["dims_auto"]
    ob = next(s for s in r["sources"] if s["src"] == "onebound")
    assert ob["dims_cm"] == [50.0, 50.0, 45.0]                     # 옵션별이면 가장 큰 것
    assert r["confidence"] == "추정" and "불일치" in r["label"] and r["dims_cm"] == [90.0, 80.0, 70.0]


def test_nothing_found_says_why_per_source():
    r = DF.fetch(_item({}), ob_call=_ob(ok=False), ocr=lambda u: "")["dims_auto"]
    assert r["dims_cm"] is None and r["confidence"] == "없음"
    assert DF.line(r).startswith("치수 못 찾음 — 온바운드 규격: 4013")


def test_shipping_engine_uses_dims_auto_but_owner_input_wins():
    from src.seller_console.shipping_ratio import _size_for
    pd = {"title_ko": "허리 보호 소형 소파 1인용 소파", "title_src": "护腰小沙发", "currency": "CNY", "price": "589",
          "dims_auto": {"dims_cm": [60.0, 50.0, 45.0], "confidence": "추정", "label": "추정(사진 글자)"}}
    s = _size_for(pd)
    assert s["dims_cm"] == [60.0, 50.0, 45.0] and "서버 수집 치수 — 추정(사진 글자)" in s["basis"] and not s.get("need_dims")
    s2 = _size_for(dict(pd, ship_input={"l": "70", "w": "60", "h": "50"}))
    assert s2["dims_cm"] == [70.0, 60.0, 50.0] and s2["basis"] == "직접 입력한 무게·치수"


def test_collect_stage_queues_dims_fetch_only_for_furniture(monkeypatch):
    from src.services import oneshot_ops as O
    rows = []
    monkeypatch.setattr(O, "enqueue", lambda row: rows.append(row) or True)
    sofa = {"title": "护腰小沙发人体工学懒人沙发", "title_ko": "허리 보호 소형 소파"}
    assert DF.maybe_queue("805773b6", sofa) and rows[-1]["op"] == "dims_fetch"
    assert not DF.maybe_queue("x1", {"title": "手机壳", "title_ko": "휴대폰 케이스"})               # 가구 아님
    assert not DF.maybe_queue("x2", dict(sofa, dims_auto={"dims_cm": None}))                  # 이미 돌았음
    assert not DF.maybe_queue("x3", dict(sofa, ship_input={"l": 1, "w": 1, "h": 1}))           # 오너 값
    assert len(rows) == 1


def test_dims_fetch_op_saves_only_dims_auto(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    from src.seller_console import collect_history_store as store
    ex = {"title": "护腰小沙发", "ship_input": {"weight_kg": "3"}}
    monkeypatch.setattr(D, "_item", lambda iid: (_item(ex), "u1"))
    box = json.loads(json.dumps(ex))
    monkeypatch.setattr(store, "merge_extra", lambda iid, fn, seller_ids=None: fn(box))
    r = O.dims_fetch("805773b6", ob_call=_ob(props=[{"name": "尺寸", "value": "60x50x45cm"}]), ocr=lambda u: "")
    assert r["ok"] and r["dims_cm"] == [60.0, 50.0, 45.0] and r["confidence"] == "추정"
    assert box["ship_input"] == {"weight_kg": "3"} and box["dims_auto"]["dims_cm"] == [60.0, 50.0, 45.0]


def test_relist_only_market_is_blocked_at_upload_and_legacy_record_counts_as_duplicate(monkeypatch):
    from src.seller_console import views as V
    item = {"id": "a3a35e92", "extra_json": json.dumps({"relist_only": ["coupang:gogane"], "uploaded": [
        {"market": "coupang", "external_url": "https://www.coupang.com/vp/products/16397045086"}]})}
    assert V._relist_only(item, ["coupang:gogane", "smartstore:chezgoga"]) == ["coupang:gogane"]
    dup = V._already_registered(item, ["coupang:woojoo"])
    assert dup and dup[0]["shown_no"] == "16397045086"            # 예전 기록 — 쿠팡 계정 마켓 중복 후보
    monkeypatch.setattr(V, "_get_owned_item", lambda iid: item)
    monkeypatch.setattr(V, "_account_codes_forbidden", lambda markets: None)      # 계정 권한 판정은 이 계약 밖
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="u1", user_email="u1@example.com", user_role="seller")
    r = c.post("/seller/collect/upload", json={"product": {"title": "x"}, "markets": ["coupang:gogane"], "item_id": "a3a35e92"})
    js = r.get_json()
    assert r.status_code == 409 and js["relist_only"] == ["coupang:gogane"] and "relist" in js["error"]


def test_rep_need_change_holds_coupang(monkeypatch):
    """오너(10-21 SPORTLINK): 글자 0상자 장을 대표로 자동 — 없으면 「대표 사진 바꾸기 필요」 보류(쿠팡)."""
    from src.seller_console.upload_dispatcher import UploadDispatcher as UD
    monkeypatch.setattr("src.services.coupang_image_check.hold", lambda pd, m, cached_only=True: None)
    monkeypatch.setattr("src.services.coupang_image_check.kick", lambda pd, m: None)
    base = {"title": "스탠드", "title_ko": "스탠드", "images": ["https://img/a.jpg"], "images_effective": ["https://img/a.jpg"],
            "price": "10", "currency": "CNY"}
    h = UD.readiness_holds(dict(base, rep_need_change="후보 4장 모두 글자가 있어요"), "coupang:gogane")
    assert any(x["short"] == "대표 사진 바꾸기 필요" and x["fix"] == "rep_image" for x in h)
    h2 = UD.readiness_holds(dict(base), "coupang:gogane")
    assert not any(x["short"] == "대표 사진 바꾸기 필요" for x in h2)


def test_owner_decision_rep_sets_or_clears_need_change(monkeypatch):
    from src.services import oneshot_ops as O
    from src.services import ocr_compare_diag as D
    from src.seller_console import collect_history_store as store
    imgs = ["https://img/0.jpg", "https://img/1.jpg", "https://img/2.jpg"]
    box = {}

    def run(counts):
        ex = {"images": imgs}
        monkeypatch.setattr(D, "_item", lambda iid: ({"id": "a3a35e92", "extra_json": json.dumps(ex)}, "u1"))
        monkeypatch.setattr(O, "_ocr_box_count", lambda url: (counts[imgs.index(url)], ""))
        monkeypatch.setattr(O, "_prevalidate", lambda iid, m: {"ok": True})
        monkeypatch.setattr(store, "update", lambda iid, seller_ids=None, extra_json="": box.update(json.loads(extra_json)) or True)
        return O._owner_decision("a3a35e92", {"candidates": [0, 1, 2]}, [], "", [])
    run({0: 4, 1: 2, 2: 7})
    assert "후보 3장 모두 글자가 있어요" in box["rep_need_change"] and "rep_image" not in box
    box.clear()
    run({0: 4, 1: 0, 2: 7})
    assert box["rep_image"] == imgs[1] and "rep_need_change" not in box


def test_rep_need_change_wins_over_text_hold_single_line(monkeypatch):
    """운영 10-21 13:00 SPORTLINK: 후보 4장 모두 글자(9·9·4·9상자) — 지금 대표 「텍스트 있음」 판정이 있어도 오너 이름 하나로."""
    from src.seller_console.upload_dispatcher import UploadDispatcher as UD
    rh = {"short": "대표 사진 텍스트 있음", "fix": "rep_image", "line": "쿠팡 대표 사진: 텍스트 있음 — 반려 가능(읽은 글자 「스포츠링크」)"}
    monkeypatch.setattr("src.services.coupang_image_check.hold", lambda pd, m, cached_only=True: rh)
    monkeypatch.setattr("src.services.coupang_image_check.kick", lambda pd, m: None)
    base = {"title": "스탠드", "title_ko": "스탠드", "images": ["https://img/a.jpg"], "images_effective": ["https://img/a.jpg"],
            "price": "10", "currency": "CNY", "rep_need_change": "후보 4장 모두 글자가 있어요"}
    h = [x for x in UD.readiness_holds(base, "coupang:woojoo") if x.get("fix") == "rep_image"]
    assert len(h) == 1 and h[0]["short"] == "대표 사진 바꾸기 필요" and "스포츠링크" in h[0]["line"]
    base.pop("rep_need_change")
    h2 = [x for x in UD.readiness_holds(base, "coupang:woojoo") if x.get("fix") == "rep_image"]
    assert h2 == [rh]


def test_prevalidate_registered_rows_skip_unselected_legacy_market(monkeypatch):
    """운영 10-21 13:00 SPORTLINK 잡: 계정 없는 예전 「coupang」 기록이 고르지 않은 「coupang」 줄로 카드에 따로 붙었다."""
    from src.seller_console import views as V
    item = {"id": "a3a35e92", "extra_json": json.dumps({"uploaded": [
        {"market": "coupang", "external_url": "https://www.coupang.com/vp/products/16397045086"},
        {"market": "smartstore:chezgoga", "product_id": "111", "channel_product_no": "222"}]})}
    monkeypatch.setattr(V, "_get_owned_item", lambda iid: item)
    rows = V._pv_registered_rows("a3a35e92", ["coupang:gogane", "coupang:woojoo", "smartstore:chezgoga"])
    assert "coupang" not in rows and set(rows) <= {"coupang:gogane", "coupang:woojoo", "smartstore:chezgoga"}
    assert V._already_registered(item, ["coupang:woojoo"])          # 업로드 입구 중복 확인은 그대로
