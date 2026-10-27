"""오너 지시 2026-10-27 22:20 ① — 「각 유저의 서류/등록증/허가증을 받으면 가능하게」.

- 셀러별 서류함 `user_docs:{sid}` (종류·번호·발급기관·유효기간 · 지우기는 소프트).
- `cert:` 보류는 그 셀러의 유효한 서류(그 품목이 받는 종류)가 있으면 주의(통과) · 결정 근거 `{"by": "user_doc", "doc_id": …}`.
- 서류 없음·만료·지움·남의 서류 → 보류 그대로 + 「서류 추가하면 자동 통과」 링크.
- 의약품(block)은 서류로 안 풀린다(⑤ 차단 유지).
"""
import pytest


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    yield


def _food_item():
    return {"title_ko": "수입 원두 커피 식품 선물세트", "description": "커피 원두 식품"}


def _food_hit(sc):
    return next(h for h in sc["hits"] if h["key"] == "cert:food")


def test_store_add_list_soft_delete_and_expiry():
    from src.seller_console import user_docs as UD
    d = UD.add_doc("u1", kind="import_license", number="2026-서울-0001", issuer="식약처", valid_until="2099-12-31")
    rows = UD.list_docs("u1")
    assert [r["id"] for r in rows] == [d["id"]] and rows[0]["status"] == "valid" and rows[0]["kind_label"]
    assert UD.valid_doc_for({"u1"}, ["import_license"])["id"] == d["id"]
    assert UD.valid_doc_for({"u2"}, ["import_license"]) is None                 # 남의 서류는 안 본다
    old = UD.add_doc("u1", kind="cosmetic", number="C-1", valid_until="2020-01-01")
    assert UD.valid_doc_for({"u1"}, ["cosmetic"]) is None                       # 만료
    assert [r["status"] for r in UD.list_docs("u1") if r["id"] == old["id"]] == ["expired"]
    assert UD.delete_doc("u1", d["id"]) is True and UD.valid_doc_for({"u1"}, ["import_license"]) is None
    assert UD.list_docs("u1", include_deleted=True)[-1]["status"] in ("deleted", "expired")   # 기록은 남는다
    assert UD.delete_doc("u2", old["id"]) is False                              # 남의 서류는 못 지운다


def test_store_rejects_bad_input():
    from src.seller_console import user_docs as UD
    with pytest.raises(ValueError):
        UD.add_doc("u1", kind="nope", number="1")
    with pytest.raises(ValueError):
        UD.add_doc("u1", kind="kc", number="")
    with pytest.raises(ValueError):
        UD.add_doc("u1", kind="kc", number="1", valid_until="31-12-2099")


def test_cert_hold_passes_with_a_valid_doc_and_comes_back_without_it():
    from src.services import risk_gate as R
    from src.seller_console import user_docs as UD
    h = _food_hit(R.scan(_food_item(), owner={"u1"}))
    assert h["grade"] == "hold" and h["doc_hint"]["link"] == R.DOC_LINK and "자동 통과" in h["why"]
    assert any("수입식품" in x["short"] for x in R.holds(R.scan(_food_item(), owner={"u1"})))
    d = UD.add_doc("u1", kind="import_license", number="2026-서울-0001", valid_until="2099-12-31")
    sc = R.scan(_food_item(), owner={"u1", "u1@example.com"})
    h = _food_hit(sc)
    assert h["grade"] == "caution" and h["passed_by"] == {"by": "user_doc", "doc_id": d["id"], "kind": "import_license",
                                                          "number": "2026-서울-0001"}
    assert not [x for x in R.holds(sc) if "수입식품" in x["short"]]             # 등록을 막지 않는다
    card = R.card(sc)
    assert next(x for x in card["hits"] if x["key"] == "cert:food")["passed_by"]["doc_id"] == d["id"]
    assert _food_hit(R.scan(_food_item(), owner={"u2"}))["grade"] == "hold"     # 남의 서류로는 안 풀린다
    UD.delete_doc("u1", d["id"])
    assert _food_hit(R.scan(_food_item(), owner={"u1"}))["grade"] == "hold"     # 지우면 다시 보류
    assert _food_hit(R.scan(_food_item()))["grade"] == "hold"                   # 셀러 모름 = 보류(통과시키지 않는다)


def test_blocked_items_are_not_unlocked_by_documents():
    from src.services import risk_gate as R
    from src.seller_console import user_docs as UD
    for k in UD.KINDS:
        UD.add_doc("u1", kind=k, number="X-1")
    h = next(x for x in R.scan({"title_ko": "의료기기 마사지기"}, owner={"u1"})["hits"] if x["key"] == "cert:drug")
    assert h["grade"] == "block" and "passed_by" not in h


def test_me_page_card_and_routes(monkeypatch):
    from src.order_webhook import app
    from src.auth import user_store as US

    class _U(dict):                                                          # me.html은 사용자 레코드가 있어야 본문을 그린다
        __getattr__ = dict.get
    monkeypatch.setattr(US, "get_store", lambda: type("S", (), {"find_by_id": staticmethod(
        lambda uid: _U(email=f"{uid}@test.local", name="테스트", role="seller", email_verified=True, social_accounts=[],
                       created_at="2026-10-01", last_login_at="2026-10-27", avatar_url=""))})())
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-doc"
        s["user_email"] = "u-doc@test.local"
        s["user_role"] = "seller"
    r = c.get("/seller/me")
    assert r.status_code == 200 and 'data-role="docs-card"' in r.get_data(as_text=True)
    r = c.post("/seller/me/docs", json={"kind": "mfds_food", "number": "제2026-0001호", "issuer": "식약처", "valid_until": ""})
    assert r.status_code == 200 and r.get_json()["ok"]
    doc_id = r.get_json()["doc"]["id"]
    body = c.get("/seller/me").get_data(as_text=True)
    assert "제2026-0001호" in body and "기한 없음" in body
    assert c.post("/seller/me/docs", json={"kind": "mfds_food", "number": ""}).status_code == 400
    assert c.post(f"/seller/me/docs/{doc_id}/delete").get_json()["ok"] is True
    assert "제2026-0001호" not in c.get("/seller/me").get_data(as_text=True)
    assert c.post("/seller/me/docs/nope/delete").status_code == 404
