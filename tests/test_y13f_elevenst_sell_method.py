"""Y13-F F3(오너 2026-10-19) — 11번가 HTTP 500 「상품등록실패 : API로 이용할 수 없는 판매방식 입니다.0500」.

보낸 XML의 `selMthdCd`는 09-20 첫 구현부터 박힌 02였고, 사전검증은 도달(398ms)만 봤다.
"""
from src.uploaders import elevenst_uploader as E


def _xml(**kw):
    up = E.ElevenStUploader.__new__(E.ElevenStUploader)
    up.default_category = "1"
    return up._build_product_xml({"title": "t", "price": 1000, "images": [], **kw})


def test_default_sell_method_is_not_the_rejected_02(monkeypatch):
    monkeypatch.delenv("ELEVENST_SELL_METHOD", raising=False)
    assert "<selMthdCd>01</selMthdCd>" in _xml()
    assert E.sell_method_hold() == ""


def test_rejected_value_is_held_before_sending(monkeypatch):
    monkeypatch.setenv("ELEVENST_SELL_METHOD", "02")
    h = E.sell_method_hold()
    assert "02" in h and "API로 이용할 수 없는 판매방식" in h
    up = E.ElevenStUploader.__new__(E.ElevenStUploader)
    up.api_key = "k"
    out = up.upload_product({"sku": "s"})
    assert out["success"] is False and out["held"] is True


def test_precheck_holds_on_rejected_sell_method(monkeypatch):
    monkeypatch.setenv("ELEVENST_SELL_METHOD", "02")
    monkeypatch.setenv("ELEVENST_API_KEY", "k")
    from src.seller_console import upload_dispatcher as D
    reached = []
    import urllib.request as _ur
    from unittest.mock import MagicMock
    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: MagicMock())   # 이미지 HEAD(네트워크) 대신
    monkeypatch.setattr(D, "market_reach", lambda m: reached.append(m) or {"ok": True, "ms": 1, "detail": ""})
    pd = {"title": "블랙홀 무드등", "price": 30000, "currency": "KRW", "sell_price_krw": 30000,
          "images": ["https://img.example/a.jpg"], "description": "본문"}
    r = D.UploadDispatcher()._prevalidate_market(pd, "elevenst")
    assert r.ok is False and r.error_code == "elevenst_sell_method", (r.error_code, r.message)
    assert reached == []                                         # 도달 확인(398ms)만 보고 통과시키지 않는다
    monkeypatch.setenv("ELEVENST_SELL_METHOD", "01")
    r2 = D.UploadDispatcher()._prevalidate_market(pd, "elevenst")
    assert r2.error_code != "elevenst_sell_method"
