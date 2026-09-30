"""T4(오너 2026-09-30-H) — 모바일 「쿠팡에서 보이는 모습」 + 등록 몸통 서버 빌더 하나.

  ① 빌더 키 집합 = 데스크톱 `buildProductData()`가 보내는 키(템플릿과 대조) — 두 벌 금지
  ② 데스크톱 등록: 폼 값이 빌더 위에 얹혀 **결과가 폼 그대로**(캐너리 경로 무변경)
  ③ 미리보기 = 등록과 같은 사슬(`option_form`) · **전송 0회** · 카테고리 기준 못 받으면 「예상 모습」이라고 말함
  ④ 배지 요약: 미해석 값 n · 프로모션 이미지 n장 제외 · 표시광고 위험 · 판매가만(할인 전 가격 없음)
  ⑤ 순서: 카드 → 마켓 선택 → 쿠팡 미리보기 → 사전검증 → 등록
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FIX = json.loads(Path("tests/fixtures/ko_polish/recent48_2026-09-30.json").read_text(encoding="utf-8"))
VRSUK = FIX["vrsuk_values"]


@pytest.fixture
def client():
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-t4"
    return c


def _item(**extra):
    from src.seller_console import collect_history_store as S
    ex = {"title": "VRSUK椅", "title_ko": "임스 라운지 의자 재고 있음", "price": "6995.00", "currency": "CNY",
          "images": ["https://img.example/1.jpg", "https://img.example/2.jpg"],
          "detail_images": ["https://img.example/d1.jpg"],
          "options": [{"name": "颜色分类", "values": VRSUK[:3]}],
          "skus": [{"spec": [v], "price": "6995.00", "currency": "CNY", "stock": 5} for v in VRSUK[:3]]}
    ex.update(extra)
    return S.append(source="extension", url="https://detail.tmall.com/item.htm?id=999", title=ex["title_ko"],
                    price=ex["price"], currency="CNY", extra=ex, seller_id="u-t4")


def test_builder_keys_match_desktop_buildproductdata():
    from src.seller_console.product_builder import PRODUCT_KEYS
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    body = t.split("function buildProductData()", 1)[1].split("\n  };\n}", 1)[0]
    ret = body.split("return {", 1)[1]
    ret = re.sub(r"//[^\n]*", "", ret)                                     # 주석 제외
    named = set(re.findall(r"\b([a-z_]+)\s*:", ret))                       # key: value
    short = set(re.findall(r"(?:^|,|\{)\s*([a-z_]+)\s*(?=,)", ret, re.M))  # 단축 key(title, price, …)
    missing = set(PRODUCT_KEYS) - (named | short)
    assert not missing, missing                                           # 빌더 키 ⊆ 서랍이 보내는 키
    assert len(PRODUCT_KEYS) == len(set(PRODUCT_KEYS))


def test_desktop_form_values_win_so_canary_payload_is_unchanged():
    from src.seller_console import collect_history_store as S
    from src.seller_console.product_builder import PRODUCT_KEYS, build_product
    iid = _item()
    item = S.get(iid, seller_ids={"u-t4"})
    form = {k: f"폼-{k}" for k in PRODUCT_KEYS}
    out = build_product(item, edits=form)
    assert all(out[k] == form[k] for k in PRODUCT_KEYS)                   # 폼이 준 키는 전부 폼 값
    plain = build_product(item)
    assert plain["title"] == "임스 라운지 의자" and plain["coupang_name"]   # 폰: 저장값 + 정리 + F53 규칙안


def test_preview_uses_the_same_chain_and_sends_nothing(client, monkeypatch):
    from src.channel_sync import coupang_uploader as cu
    import src.seller_console.views as V
    seen = {}

    def fake_form(product):
        seen["product"] = product
        return {"ok": True, "category": "78293", "meta_ok": True, "holds": [], "notes": [],
                "items": [{"label": "브라운레드 오일왁스 반가죽 / 발받침 포함", "sell_price_krw": 1690000, "stock": 5,
                           "confirm": True}, {"label": "딥 블랙 오일왁스 반가죽 / 발받침 포함", "sell_price_krw": 1690000,
                                              "stock": 5, "confirm": True}]}

    monkeypatch.setattr(cu, "option_form", fake_form)
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: (_ for _ in ()).throw(AssertionError("전송 금지")))
    iid = _item()
    d = client.get(f"/seller/m/item/{iid}/coupang-preview").get_json()
    assert d["ok"] and not d["estimated"] and d["category"] == "78293"
    assert d["price_min"] == 1690000 and "original_price" not in d                # 판매가만
    assert d["items"][0]["label"].startswith("브라운레드") and d["unresolved"] == 0
    assert "재고 있음" not in d["name"] and d["images"][0] == "https://img.example/1.jpg"
    assert "해외구매대행" in d["shipping"] and seen["product"]["skus"]           # 같은 빌더 몸통이 사슬로


def test_preview_says_estimated_when_meta_is_unreachable(client, monkeypatch):
    from src.channel_sync import coupang_uploader as cu
    monkeypatch.setattr(cu, "option_form", lambda p: (_ for _ in ()).throw(OSError("relay down")))
    iid = _item()
    d = client.get(f"/seller/m/item/{iid}/coupang-preview").get_json()
    assert d["ok"] and d["estimated"] and any("예상 모습" in n for n in d["notes"])
    assert [i["label"] for i in d["items"]][0] == "브라운레드 오일왁스 반가죽 / 발받침 포함"


def test_badges_summarise_promo_and_ad_claims(client, monkeypatch):
    from src.channel_sync import coupang_uploader as cu
    monkeypatch.setattr(cu, "option_form", lambda p: {"ok": True, "items": [], "holds": [
        "옵션 값 1개를 한국어로 옮기지 못했습니다 — …: 莫奈色"], "notes": []})
    promo = {"idx": 0, "status": "done", "url": "https://cdn.example/p0.jpg", "use": True,
             "source_text": FIX["vrsuk_image0"]["source_text"], "target_text": FIX["vrsuk_image0"]["target_text"]}
    iid = _item(images_ko=[promo], coupang_name="임스 의자 최저가")
    d = client.get(f"/seller/m/item/{iid}/coupang-preview").get_json()
    assert d["promo_excluded"] == 1 and "https://cdn.example/p0.jpg" not in d["images"]
    assert d["unresolved"] == 1 and any("최저가" in a for a in d["ad_claims"])


def test_flow_order_card_market_preview_check_register(client):
    iid = _item()
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    order = [h.index(f'data-role="{r}"') for r in ("m5-card", "m5-markets", "m5-coupang-preview", "m5-check",
                                                   "m5-register")]
    assert order == sorted(order)
    t = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert "/coupang-preview'" in t and "할인" not in t.split("function loadCoupang")[1].split("function ")[0]
