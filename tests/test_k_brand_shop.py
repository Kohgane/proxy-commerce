"""K(오너 2026-10-01) — 쿠팡 옵션명 25자 · 브랜드·가게 이름 **재료** 수집(지뢰 「규칙은 들어갔는데 재료가 0이다」).

  ① 실페이지(티몰 617129397971 스냅샷)에서 확장 추출기가 brand=SportLink · shop_name=sportlink旗舰店를 낸다.
     경로는 파이썬 쪽에서 **독립적으로** 같은 JSON을 읽어 대조한다(JS와 같은 구현 금지).
  ② ICE에 그 필드가 없는 픽스처는 키 자체를 안 싣는다(빈 값으로 덮어쓰기 금지).
  ③ 서버: 수집 시 shop_name 저장 · 보강은 비어 있을 때만 채움(fill-only).
  ④ 브랜드 규칙(오너 역질문안): 브랜드 필드가 있으면 그것만 · 가게 이름은 브랜드가 비었을 때만 ·
     접미(旗舰店·专卖店·官方…) 떼고 2자 미만이면 브랜드 없음.
  ⑤ 옵션명 25자 초과는 자르지 않고 보류(「미해석」) — 계획·전송 두 자리.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_f49t2_tmall_ice_sku import F_106, F_617, REAL, _extract, res_of


def test_real_tmall_snapshot_gives_brand_and_shop():
    res = res_of(REAL)
    shop = res["seller"]["shopName"]
    brand = [p["valueName"] for p in res["plusViewVO"]["industryParamVO"]["enhanceParamList"]
             if p["propertyName"] == "品牌"][0]
    assert (shop, brand) == ("sportlink旗舰店", "SportLink")                  # 실물 값(파이썬 독립 판독)
    out = _extract(REAL.read_text(encoding="utf-8"))
    assert out["brand"] == brand and out["shop_name"] == shop
    assert len(out["skus"]) == 10                                            # SKU 추출은 그대로(회귀 0)


@pytest.mark.parametrize("fx", [F_617, F_106])
def test_minimal_fixtures_without_fields_send_no_keys(fx):
    out = _extract(Path(fx).read_text(encoding="utf-8"))
    # undefined(= 메시지 직렬화에서 키가 빠짐, Playwright에선 None) — 빈 문자열로 싣지 않는다(stock_status와 같은 규약)
    assert out.get("brand") is None and out.get("shop_name") is None


def test_server_stores_shop_on_collect_and_fills_on_enrich(monkeypatch):
    from src.api import extension_api as ext
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-k", "scopes": ["collect.write"]})
    c = app.test_client()
    r = c.post("/api/v1/collect/extension", json={
        "url": "https://detail.tmall.com/item.htm?id=881", "title": "sportlink三合一充电支架", "price": "29.90",
        "currency": "CNY", "images": [], "translate": False, "brand": "SportLink", "shop_name": "sportlink旗舰店"})
    iid = r.get_json()["item_id"]
    ex = json.loads(S.get(iid, seller_ids={"u-k"})["extra_json"])
    assert ex["brand"] == "SportLink" and ex["shop_name"] == "sportlink旗舰店"
    # 목록 카드 초안(브랜드 없음) → 상세 보강이 채움 · 이미 있는 값은 안 덮음
    iid2 = S.append(source="extension", url="https://item.taobao.com/item.htm?id=882", title="椅", price="",
                    currency="CNY", extra={"title": "椅", "mode": "simple", "enrich_state": "pending"}, seller_id="u-k")
    c.post("/api/v1/collect/enrich", json={"item_id": iid2, "brand": "懒小姐", "shop_name": "懒小姐旗舰店"})
    c.post("/api/v1/collect/enrich", json={"item_id": iid2, "brand": "다른값", "shop_name": "다른가게"})
    ex2 = json.loads(S.get(iid2, seller_ids={"u-k"})["extra_json"])
    assert ex2["brand"] == "懒小姐" and ex2["shop_name"] == "懒小姐旗舰店"


def test_brand_rule_uses_shop_only_when_brand_empty():
    from src.collectors import ko_polish as kp
    assert kp.brand_prefix("懒小姐懒人沙发", {"shop_name": "懒小姐官方旗舰店"})["latin"] == "LANXIAOJIE"
    assert kp.brand_prefix("懒小姐懒人沙发", {"brand": "SportLink", "shop_name": "懒小姐旗舰店"}) is None
    assert kp.brand_prefix("懒懒人沙发", {"shop_name": "懒旗舰店"}) is None           # 뗀 뒤 1자 → 브랜드 없음
    assert kp.brand_prefix("旗舰店沙发", {"shop_name": "旗舰店"}) is None             # 접미만 → 브랜드 없음


def test_option_name_over_25_is_held_not_cut():
    from src.uploaders import coupang_options as O
    from src.uploaders.coupang_uploader import CoupangUploader
    long_name = "가" * 26
    r = O.resolve_option_name(long_name, [long_name, "색상"])
    assert r["meta"] == "" and "미해석" in r["why"] and "25자" in r["why"]
    assert O.resolve_option_name("颜色分类", [long_name, "색상"])["meta"] == "색상"     # 짧은 이름은 그대로
    out = CoupangUploader.attr_safe([{"attributeTypeName": long_name, "attributeValueName": "1"},
                                     {"attributeTypeName": "색상", "attributeValueName": "블랙"}], "의자", None)
    names = [a["attributeTypeName"] for a in out]
    assert long_name not in names and not any(len(n) == 25 and n == long_name[:25] for n in names)
    assert "색상" in names
