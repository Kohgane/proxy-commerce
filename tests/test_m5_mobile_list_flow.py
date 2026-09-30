"""M5(오너 2026-09-30) — 폰: 담은 결과 화면에서 바로 미리보기 → 마켓 선택 → 사전검증 → 등록.

  ① 결과 화면에 카드(대표 이미지·상품명·SKU 요약·쿠팡 상품명 F53) + 마켓 선택(쿠팡 기본, 여럿) + 사전검증·등록
  ② 타오바오 초안(서버 fetch 불가)은 카드에 「PC 확장에서 보강 필요 — 가격·사진·SKU」, 가격 없으면 등록 막힘 문구
  ③ 등록은 데스크톱과 **같은 두 입구**(/collect/prevalidate · /collect/upload) — 캐너리 경로 두 벌 0
  ④ 화면이 싣는 상품 몸통으로 사전검증·등록이 실제로 돈다 → 성공 마켓만 「등록됨」 영속
  ⑤ /seller/m/item/<id>는 로그인 뒤 **그 자리로** 돌아온다(AUTH-1과 결합: 가입 → 바로 복귀)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import pytest

SHARE = ("【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt CZ356\n"
         "「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」\n"
         "点击链接直接打开 或者 淘宝搜索直接打开")


@pytest.fixture
def client(monkeypatch):
    from src.collectors import link_diag
    monkeypatch.setattr(link_diag, "resolve_short_link", lambda url: {"ok": False, "reason": "offline"})
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-m5"
    return c


def _item(seller="u-m5", **extra):
    from src.seller_console import collect_history_store as S
    ex = {"title": "원목 책상", "title_ko": "원목 책상", "price": "199", "currency": "CNY",
          "images": ["https://img.example/1.jpg", "https://img.example/2.jpg"],
          "skus": [{"spec": ["원목", "120cm"], "price": "199", "currency": "CNY"},
                   {"spec": ["원목", "140cm"], "price": "239", "currency": "CNY"}]}
    ex.update(extra)
    return S.append(source="share", url="https://detail.1688.com/offer/7788.html", title=ex["title_ko"],
                    price=ex["price"], currency=ex["currency"], extra=ex, seller_id=seller)


def _embedded_product(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="m5Product">(.*?)</script>', html, re.S)
    assert m, "화면이 등록에 쓸 상품 몸통을 싣지 않았다"
    return json.loads(m.group(1))


def test_share_result_shows_card_markets_and_steps(client):
    h = client.get("/seller/collect/share?src=share&text=" + quote(SHARE)).get_data(as_text=True)
    assert 'data-role="m5"' in h and 'data-role="m5-card"' in h and 'data-role="m5-coupang-name"' in h
    assert re.search(r'value="coupang" checked', h) and 'value="smartstore"' in h     # 쿠팡 기본 · 여럿
    assert 'data-role="m5-check"' in h and re.search(r'data-role="m5-register" disabled', h)   # 검증 전엔 등록 닫힘
    need = re.search(r'data-role="m5-needs-pc">(.*?)</div>', h, re.S).group(1)
    assert "PC 확장에서 보강 필요" in need and "SKU" in need and "사진" in need
    assert 'data-role="share-enrich"' in h and h.count('sd-btn"') == 2                  # 옛 계약 유지


def test_draft_without_price_says_register_is_blocked(client):
    iid = _item(price="", gate_ready=False, enrich_state="pending")
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-blocked="1"' in h and "가격이 없어 등록할 수 없어요" in h and "가격" in h


def test_same_two_endpoints_as_desktop():
    t = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert "'/seller/collect/prevalidate'" in t and "'/seller/collect/upload'" in t
    assert "item_id: itemId" in t and "confirm_warn" in t
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", t.split("<script>")[0])            # 토큰만(스타일에 hex 0)
    assert not re.search(r"[\U0001F300-\U0001FAFF]", t)
    assert 'id="rp-ledger"' in Path("src/seller_console/templates/dashboard.html").read_text(encoding="utf-8")


def test_embedded_product_prechecks_and_registers_end_to_end(client, monkeypatch):
    """화면이 싣는 몸통 그대로 → 사전검증 통과 → 등록 → 성공한 마켓만 영속."""
    import src.seller_console.views as V
    from src.seller_console.upload_dispatcher import DispatchResult, UploadResult

    seen = {}

    class _Disp:
        def prevalidate(self, product, markets):
            seen["pre"] = (product, list(markets))
            return [type("R", (), {"market": m, "ok": m == "coupang", "error_code": "" if m == "coupang" else "CRED",
                                   "message": "" if m == "coupang" else "자격 없음", "hint": "", "reach_ok": None,
                                   "reach_ms": None, "reach_detail": "", "details": [], "action_url": ""})()
                    for m in markets]

        def dispatch(self, product, markets):
            seen["up"] = (product, list(markets))
            return DispatchResult(product_url="", total=1, succeeded=1, results=[
                UploadResult(market="coupang", success=True, message="쿠팡 업로드 성공",
                             external_product_id="16400000001")])

    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _Disp())
    monkeypatch.setattr("src.services.image_reachability.check_all",
                        lambda urls, labels=None: {"ok": True, "bad": []})
    iid = _item()
    product = _embedded_product(client.get(f"/seller/m/item/{iid}").get_data(as_text=True))
    assert product["title"] == "원목 책상" and len(product["skus"]) == 2 and product.get("coupang_name")

    pre = client.post("/seller/collect/prevalidate", json={"product": product, "markets": ["coupang", "smartstore"]}).get_json()
    ok_markets = [r["market"] for r in pre["results"] if r["ok"]]
    assert ok_markets == ["coupang"]                                          # 통과한 곳만 등록 대상
    up = client.post("/seller/collect/upload", json={"product": product, "markets": ok_markets, "item_id": iid}).get_json()
    assert up["ok"] and up["result"]["results"][0]["external_product_id"] == "16400000001"
    assert seen["up"][1] == ["coupang"] and len(seen["up"][0]["skus"]) == 2   # SKU까지 같은 몸통
    from src.seller_console import collect_history_store as S
    ex = json.loads(S.get(iid, seller_ids={"u-m5"})["extra_json"])
    assert [u["market"] for u in ex.get("uploaded", [])] == ["coupang"]


def test_mobile_item_page_login_round_trip(monkeypatch):
    """로그인 전 → 로그인 화면(next=그 자리) → 가입하면 **바로 그 화면**(AUTH-1 결합)."""
    import src.seller_console.views as V
    from src.auth import password_accounts as accounts
    from src.db import user_identities_pg as ident
    accounts.reset_for_tests()
    ident.reset_for_tests()
    monkeypatch.setattr(accounts, "_legacy_sheet_account", lambda email: None)
    old = V._AUTH_ENABLED
    V._AUTH_ENABLED = True
    try:
        from src.order_webhook import app
        c = app.test_client()
        r = c.get("/seller/m/item/abc123")
        loc = r.headers.get("Location", "")
        from urllib.parse import unquote
        assert r.status_code == 302 and "/auth/login" in loc and "next=/seller/m/item/abc123" in unquote(loc)
        r = c.post("/auth/signup", data={"email": "m5@example.test", "password": "pass12345",
                                         "next": "/seller/m/item/abc123"})
        assert r.status_code == 302 and r.headers["Location"].endswith("/seller/m/item/abc123")
        assert c.get("/seller/m/item/abc123").status_code == 404           # 로그인은 됐고, 남의/없는 항목은 404
    finally:
        V._AUTH_ENABLED = old
        accounts.reset_for_tests()
        ident.reset_for_tests()
