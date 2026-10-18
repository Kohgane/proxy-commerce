"""Y13-A(오너 2026-10-18 15:43 BLACKHOLES) — 옵션 값의 브랜드 조각 · 라틴 값 표기 · 중복 판정 순서.

실측(item 301c02cd, 타오바오 1077964821879): 옵션은 축 하나(颜色分类: Yellow light · White light)인데 SKU 스펙은 두 칸
(「【BLACKHOLES】」, 「Yellow light」). 쿠팡 빌더가 축과 스펙을 자리로 짝지어 두 SKU 모두 색상 「【BLACKHOLES】」 → 「옵션 값이 같아집니다」.
규칙: 【브랜드】·브랜드 낱말은 옵션 값에서 뺀다(상품명 쪽으로) → 남은 라틴 값은 낱말이 전부 표에 있으면 한국어 표기 → 그 뒤 중복 판정.
"""
from __future__ import annotations

from src.collectors import ko_polish as KP
from src.collectors import option_ko as OK
from src.seller_console.upload_dispatcher import drop_brand_option_slots
from src.uploaders import coupang_options as CO
from src.uploaders import naver_options as NO

BLACKHOLES = {
    "title": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
    "title_ko": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
    "title_en": "【BLACKHOLES】黑洞小夜灯星际穿越电影周边摆件装饰模型手办宇宙",
    "brand": None,
    "options": [{"name": "颜色分类", "values": ["Yellow light", "White light"]}],
    "option_name_overrides": {"大小": "모델"},
    "skus": [
        {"spec": ["【BLACKHOLES】", "Yellow light"], "price": "69.90", "stock": 200, "sku_id": "6129730953948",
         "currency": "CNY", "sell_price_krw": 21900},
        {"spec": ["【BLACKHOLES】", "White light"], "price": "69.90", "stock": 200, "sku_id": "6129730953949",
         "currency": "CNY", "sell_price_krw": 21900},
    ],
}
META = [{"attributeTypeName": "색상", "required": "MANDATORY"}]


def test_latin_values_translated_only_when_every_word_known():
    assert KP.latin_option_ko("Yellow light") == "옐로 라이트"
    assert KP.latin_option_ko("White light") == "화이트 라이트"
    assert KP.latin_option_ko("Proprietary 20") == ""            # 모델명은 원문 그대로(런북 2호 체크 14)
    assert KP.latin_option_ko("Black Edition") == ""              # 모르는 낱말 하나 → 옮기지 않는다
    assert CO.resolve_option_value("Yellow light")["value"] == "옐로 라이트"
    assert CO.resolve_option_value("XL")["value"] == "XL"


def test_brand_tokens_and_strip():
    toks = KP.brand_tokens(BLACKHOLES)
    assert toks == ["BLACKHOLES"]
    assert KP.strip_brand_value("【BLACKHOLES】", toks) == ""
    assert KP.strip_brand_value("【BLACKHOLES】Yellow light", toks) == "Yellow light"
    assert KP.strip_brand_value("BLACKHOLES White light", toks) == "White light"
    assert KP.strip_brand_value("【超长3年质保】", toks) == "【超长3年质保】"   # 브랜드 아닌 묶음은 그대로(옵션 아님 판정이 따로 본다)


def test_brand_slot_dropped_from_specs_and_kept_out_of_saved_data():
    out = drop_brand_option_slots(BLACKHOLES)
    assert [k["spec"] for k in out["skus"]] == [["Yellow light"], ["White light"]]
    assert [k["spec_src"] for k in out["skus"]][0] == ["【BLACKHOLES】", "Yellow light"]
    assert BLACKHOLES["skus"][0]["spec"] == ["【BLACKHOLES】", "Yellow light"]          # 저장값(입력)은 그대로
    assert out["option_brand_removed"] == ["BLACKHOLES"]
    assert not out.get("brand")                                                         # 상품명에 이미 있다 — 옮길 필요 없음


def test_brand_moves_to_brand_field_when_title_lacks_it():
    p = dict(BLACKHOLES, title_ko="블랙홀 미니 벽등", title="블랙홀 미니 벽등")
    assert drop_brand_option_slots(p)["brand"] == "BLACKHOLES"


def test_blackholes_two_skus_split_into_yellow_and_white_light_on_coupang():
    pd = drop_brand_option_slots(BLACKHOLES)
    plan = CO.plan_sku_items(META, pd)
    assert [it["label"] for it in plan["items"]] == ["옐로 라이트", "화이트 라이트"]
    assert not [h for h in plan["holds"] if "같아집니다" in h]


def test_coupang_aligns_axis_by_value_even_with_extra_slot():
    """브랜드 조각을 못 뺀 경우에도(예: 표에 없는 모양) 축은 그 축의 값으로 짝짓는다 — 자리로 밀리지 않는다."""
    plan = CO.plan_sku_items(META, BLACKHOLES)
    assert [it["label"] for it in plan["items"]] == ["옐로 라이트", "화이트 라이트"]


def test_blackholes_naver_and_option_view_use_same_values():
    pd = drop_brand_option_slots(BLACKHOLES)
    p = NO.plan(pd)
    assert p["mode"] == "combo", p.get("why")
    assert [OK.spec_ko(pd, k["spec"]) for k in pd["skus"]] == [["옐로 라이트"], ["화이트 라이트"]]
    assert [v["ko"] for v in OK.options_view(pd)[0]["values"]] == ["옐로 라이트", "화이트 라이트"]


def test_prevalidate_uses_same_option_cleanup_as_register(monkeypatch):
    """#917 같은 재료 — 사전검증(`prevalidate`)도 등록 빌더와 같은 옵션 정리(`apply_outbound_options`)를 지난다."""
    from src.seller_console.upload_dispatcher import UploadDispatcher, PrevalidationResult
    seen = []

    def fake(self, pd, base):
        seen.append([k["spec"] for k in pd.get("skus") or []])
        return PrevalidationResult(market=base, ok=True, message="")
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market", fake)
    UploadDispatcher().prevalidate(dict(BLACKHOLES), ["coupang"])
    assert seen == [[["Yellow light"], ["White light"]]]


def test_oneshot_prevalidate_starts_same_job_under_item_account(monkeypatch):
    from src.seller_console import collect_history_store as S
    from src.seller_console import views as V
    from src.services import oneshot_ops as OO
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    import json
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id="u-y13a",
                   title=BLACKHOLES["title"], price="69.90", currency="CNY", extra=dict(BLACKHOLES))
    got = {}

    def fake_start(data, markets, dispatcher):
        from flask import jsonify, session
        got.update(uid=session.get("user_id"), markets=markets, item=data["item_id"], skus=len(data["product"].get("skus") or []))
        return jsonify({"ok": True, "job_id": "job-1"}), 202
    monkeypatch.setattr(V, "_pv_start_job", fake_start)
    out = OO._run({"op": "prevalidate", "item_id": iid})
    assert out == {"ok": True, "job_id": "job-1", "markets": list(OO.PREVALIDATE_MARKETS), "why": ""}
    assert got["uid"] == "u-y13a" and got["item"] == iid and got["skus"] == 2
    assert OO._run({"op": "prevalidate", "item_id": "nope"})["ok"] is False
    S._in_memory.clear()


def test_oneshot_image_probe_records_format_and_ocr_code(monkeypatch):
    import io
    from PIL import Image
    from src.seller_console import collect_history_store as S
    from src.services import image_translate_tencent as tc
    from src.services import ocr_tencent as O
    from src.services import oneshot_ops as OO
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    ex = {"detail_images": ["//img.alicdn.com/imgextra/i3/x.jpg_1200x1200q30.jpg_.webp", "https://g.alicdn.com/s.gif"]}
    iid = S.append(source="share", url="https://detail.tmall.com/item.htm?id=851803804374", seller_id="u-fish", title="피샹리",
                   price="1", currency="CNY", extra=ex)

    def img(fmt, w, h):
        b = io.BytesIO()
        Image.new("RGB", (w, h)).save(b, fmt)
        return b.getvalue()
    fetched = []
    monkeypatch.setattr(tc, "fetch_image", lambda u: fetched.append(u) or ((img("WEBP", 1200, 1200), "") if "x.jpg" in u else (img("GIF", 1, 1), "")))
    monkeypatch.setattr(O, "read", lambda raw, **k: {"ok": True, "lines": [("包邮", 99)], "code": ""})
    out = OO._run({"op": "image_probe", "item_id": iid, "kind": "detail", "idx": [0, 1]})
    r0, r1 = out["rows"]
    assert r0["scheme_fixed"] and r0["url"].startswith("https://img.alicdn.com/") and r0["fmt"] == "WEBP"
    assert r0["prepare"]["sent"] == "바꿈" and r0["ocr"]["ok"] and r0["ocr"]["lines"] == 1
    assert r1["excluded"].startswith("빈 칸 이미지") and r1["prepare"]["sent"] == "안 보냄" and "ocr" not in r1
    S._in_memory.clear()


def test_drawer_sku_table_shows_outbound_values(monkeypatch):
    """옵션 탭 SKU 조합표 = 나가는 값(브랜드 조각 뺀 「옐로 라이트」) + 뺀 브랜드 한 줄. 원문은 「원문 보기」 줄에 그대로."""
    from src.seller_console import collect_history_store as S
    monkeypatch.setattr(S, "_pg_backend", lambda: None)
    S._in_memory.clear()
    iid = S.append(source="share", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id="u-y13a-d",
                   title=BLACKHOLES["title"], price="69.90", currency="CNY", extra=dict(BLACKHOLES))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="u-y13a-d", user_email="u-y13a-d@example.com", user_role="seller")
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    tbl = html[html.index('data-role="sku-table"'):]
    tbl = tbl[:tbl.index("</table>")]
    assert '<span data-role="sku-ko">옐로 라이트</span>' in tbl and '<span data-role="sku-ko">화이트 라이트</span>' in tbl
    assert 'data-role="sku-brand-removed">브랜드 「BLACKHOLES」는 옵션 값에서 뺐어요' in tbl
    assert "원문 — 【BLACKHOLES】 / Yellow light" in tbl
    S._in_memory.clear()
