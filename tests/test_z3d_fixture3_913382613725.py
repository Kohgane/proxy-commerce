"""Z3-D 픽스처 3호(오너 2026-10-07) — 티몰 913382613725 중고풍 티테이블·TV장. 운영 보관본 = 진단 「내려받기」 원문.

특징: tmall · 축 2(安装方式 1값 + 颜色分类 8값 — 값 안에 [50cm]/[60cm]/[80cm] 사이즈와 茶几/电视柜 종류 혼합) ·
brand 亮妆（家俱） · 规格 毛重 40kg · 包装体积 0.36 · 尺寸 60x60x62m(오타 m) · desc_img ~crop~ 접미 · total_sold "10"(str) ·
video.url 있음 · cache 0인데 data_update 2026-08-25.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

FX = Path(__file__).parent.parent / "fixtures" / "providers" / "onebound_item_get_913382613725.json"
NOW = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)          # 운영 실측 날(베이징 11:00)
COLOR_VALUES = ["杏纹圆形中古风升降茶几[50cm]", "黑纹圆形中古风升降茶几[50cm]", "杏纹圆形中古风升降茶几[60cm]",
                "黑纹圆形中古风升降茶几[60cm]", "杏纹椭圆中古风伸缩电视柜亮面雪山白岩板", "黑纹椭圆中古风伸缩电视柜亮面雪山白岩板",
                "杏纹圆形中古风升降茶几[80cm]", "黑纹圆形中古风升降茶几[80cm]"]


@pytest.fixture
def item(monkeypatch):
    """공유 담기 1건 → 온바운드(픽스처 응답) → 자동 체인. `(seller, item_id)`."""
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    from src.seller_console import collect_history_store as S
    from src.services import taobao_auto as A
    monkeypatch.setenv("ONEBOUND_KEY", "kkk_test_key_1234")
    monkeypatch.setenv("ONEBOUND_SECRET", "sss_test_secret_5678")
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    monkeypatch.delenv("TAOBAO_MTOP_AUTO", raising=False)
    monkeypatch.setattr(T, "fetch", lambda *a, **k: pytest.fail("onebound면 mtop을 부르지 않는다"))
    monkeypatch.setattr(O, "_get", lambda params, transport=None: (200, FX.read_text(encoding="utf-8")))
    st.state_set(O._RAW + "913382613725", {})
    iid = S.append(source="share_text", url="https://item.taobao.com/item.htm?id=913382613725", seller_id="fx3",
                   title="중고풍 티테이블", price="", currency="",
                   extra={"title": "中古风茶几电视柜客厅家用小户型可移动升降2026年新款茶几桌", "item_id_taobao": "913382613725",
                          "enrich_state": "pending", "images": []})
    assert A.run("fx3", iid)["state"] == "done"
    return "fx3", iid


def _ex(seller, iid):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_ids={seller})["extra_json"])


def _pd(seller, iid):
    from src.seller_console import collect_history_store as S
    from src.seller_console.product_builder import build_product
    return build_product(S.get(iid, seller_ids={seller}), seller_id=seller)


def test_parses_as_owner_counted():
    from src.collectors import taobao_provider_onebound as O
    raw = json.loads(FX.read_text(encoding="utf-8"))
    assert raw["error_code"] == "0000" and raw["cache"] == 0 and not O.item_id_mismatch(raw, "913382613725")
    p = O.normalize(raw, now=NOW)
    pv = p["provider"]
    assert pv["is_tmall"] is True and pv["brand"] == "亮妆（家俱）" and pv["total_sold"] == 10
    assert pv["video_url"].endswith("517479432146.mp4?appKey=38829")
    assert [(o["name"], len(o["values"])) for o in p["options"]] == [("安装方式", 1), ("颜色分类", 8)]
    assert len(p["skus"]) == 8 and sorted({k["price"] for k in p["skus"]}) == [1150.0, 1250.0, 1500.0, 1650.0]
    specs = dict((k, v) for k, v in p["detail_specs"])
    assert specs["毛重"] == "40kg" and specs["包装体积"] == "0.36" and specs["尺寸"] == "60x60x62m"


def test_price_asof_by_data_update_not_cache_flag():
    """cache 0인데 data_update가 한 달 전 → 「가격 기준 2026-08-25 …」 — 날짜로 판단한다."""
    from src.collectors import taobao_provider_onebound as O
    raw = json.loads(FX.read_text(encoding="utf-8"))
    assert O.normalize(raw, now=NOW)["provider"]["price_asof"] == "2026-08-25 19:37:14"


def test_crop_suffix_urls_are_normal_images(item):
    """Y1: `~crop,0,0,750,1500~` 접미 주소는 정상 이미지 — 필터(아이콘·픽셀·쓰레기)에 걸리지 않는다. 픽셀(o0b.cn)만 빠진다."""
    ex = _ex(*item)
    crops = [u for u in ex["detail_images"] if "~crop," in u]
    assert len(ex["detail_images"]) == 24 and len(crops) == 6 and not any("o0b.cn" in u for u in ex["detail_images"])
    assert len(ex["images"]) == 5 and any("~crop,0,94,750,750~" in u for u in ex["images"])
    from src.collectors.collect_status import real_detail_images
    assert len(real_detail_images(ex["detail_images"])) == 24


def test_y8_bracket_size_to_axis_color_axis_types_kept_in_value(item):
    ex = _ex(*item)
    axes = {o["name"]: o["values"] for o in ex["options"]}
    assert axes["색상"] == ["아프리콧 무늬", "블랙 무늬"]
    assert axes["사이즈"] == ["50cm", "60cm", "기본", "80cm"]
    assert axes["종류"] == ["圆形中古风升降茶几", "椭圆中古风伸缩电视柜亮面雪山白岩板"]   # 茶几·电视柜는 떼지 않고 값에 남김
    rec = ex["option_split"]
    assert rec["state"] == "split" and rec["mixed_types"] == ["茶几", "电视柜"]
    # SKU 1:1 — 8개 · 가격 그대로 · 조합 서로 다름
    src = {tuple(k["spec"]): k["price"] for k in ex["skus_src"]}
    new = [(tuple(k["spec"]), k["price"]) for k in ex["skus"]]
    assert len(new) == 8 and len({s for s, _p in new}) == 8 and sorted(p for _s, p in new) == sorted(src.values())
    tv = [s for s, _p in new if "椭圆中古风伸缩电视柜亮面雪山白岩板" in s]
    assert len(tv) == 2 and all("기본" in s for s in tv)


def test_card_warns_mixed_products(item):
    seller, iid = item
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    seg = h.split('data-role="m5-mixed-types"')[1][:400]
    assert "옵션에 서로 다른 상품이 섞여 있어요" in seg and "茶几 · 电视柜" in seg
    assert "가격 기준 2026-08-25 19:37:14" in h


def test_coupang_axes_drop_single_value_axis(item):
    """安装方式(값 1개 「整装」)는 SKU를 가르지 않는다 — 쿠팡 3축 제한에선 먼저 빠진다(나머지 3축 그대로)."""
    from src.collectors.option_split import cap_axes
    pd = _pd(*item)
    assert [o["name"] for o in pd["options"]][:1] == ["安装方式"] and len(pd["options"]) == 4
    out = cap_axes(pd)
    assert [o.get("name_ko") or o["name"] for o in out["options"]] == ["색상", "사이즈", "종류"]
    assert all(len(k["spec"]) == 3 for k in out["skus"]) and len({tuple(k["spec"]) for k in out["skus"]}) == 8


def test_z5_reads_gross_weight_and_package_volume(item, monkeypatch):
    from src.seller_console import shipping_ratio as SR
    pd = _pd(*item)
    monkeypatch.delenv("SHIPPING_RATE_KRW_PER_KG_CN", raising=False)
    for r in SR.ROUTES:
        monkeypatch.delenv(f"SHIPPING_RATE_KRW_PER_KG_CN_{r.upper()}", raising=False)
    e = SR.estimate(pd, "fx3")
    assert e["state"] == "unknown" and e["line"] == "요율 미설정 — 비율 판정 생략(SHIPPING_RATE_KRW_PER_KG_CN)"   # 요율이 비면 그 사유
    monkeypatch.setenv("SHIPPING_RATE_KRW_PER_KG_CN", "6000")
    monkeypatch.setattr(SR, "_fx", lambda c: 190.0 if c == "CNY" else None)
    e = SR.estimate(pd, "fx3")
    # 毛重 40kg · 치수 60×60×62(오타 m → cm) 부피무게 37.2kg · 包装体积 0.36㎥ → 부피무게 60kg → 청구 60kg
    assert e["state"] == "ok" and e["chargeable_kg"] == 60.0 and e["pkg_m3"] == 0.36
    assert e["ship_krw"] == 360000 and e["cost_krw"] == 218500 and e["ratio_pct"] == 165   # 1150元 대비 실제 숫자
    assert "무게 40kg" in e["line"] and "포장 부피 0.36㎥(부피무게 60.0kg)" in e["line"] and "요율 미설정" not in e["line"]
    assert SR.hold(pd, "fx3")["short"] == "배송비 비율 초과 165%"


def test_brand_passes_y6_and_never_reaches_coupang_fields(item):
    """亮妆（家俱） — 한국 상표 아님(Y6 레플리카·IP 게이트 통과). 쿠팡 칸엔 한자 브랜드가 가지 않는다(정본: brand 빈 칸)."""
    from src.collectors import ko_polish as K
    from src.channel_sync._channel_bridge import to_collected
    from src.channel_sync.coupang_uploader import prepared_input
    from src.uploaders.coupang_uploader import CoupangUploader
    ex = _ex(*item)
    text = " ".join([ex["title"], ex["provider_detail"]["brand"]])
    assert K.replica_hits(text) == [] and K.ip_hits(text) == []
    pd = _pd(*item)
    prep = CoupangUploader(access_key="a", secret_key="b", vendor_id="v").prepare_product(to_collected(prepared_input(pd)))
    assert prep["brand"] == "" and not K.has_foreign(prep["brand"])
