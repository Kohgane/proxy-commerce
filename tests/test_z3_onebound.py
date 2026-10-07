"""Z3-B(오너 2026-10-05) — 온바운드(万邦) item_get 공급자: 파서 · 실패 원문 · 한도 · 24시간 재사용 · api_info · 자동 담기 · 진단.

네트워크 0(대역 transport). 픽스처 출처는 `fixtures/providers/README.md`:
  - `onebound_item_get_652874751412.json` = 오너 실측 응답(2026-10-05 [Z3-B 후속]으로 투입 — 원문 그대로).
  - `onebound_item_get_reconstructed.json` = 오너 지시 필드 매핑대로 만든 재구성(값은 지어낸 것).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_z3_mtop_auto import _share_item

FX = Path(__file__).parent.parent / "fixtures" / "providers"
REAL = FX / "onebound_item_get_652874751412.json"
RECON = FX / "onebound_item_get_reconstructed.json"


def _recon_text(num_iid: str = ""):
    """재구성 응답 — `num_iid`를 주면 응답 item.num_iid를 그 번호로(요청·응답 상품번호 일치 검사를 통과하게)."""
    t = RECON.read_text(encoding="utf-8")
    if num_iid:
        raw = json.loads(t)
        raw["item"]["num_iid"] = num_iid
        t = json.dumps(raw, ensure_ascii=False)
    return t


def _keys(monkeypatch, cap="60"):
    monkeypatch.setenv("ONEBOUND_KEY", "kkk_test_key_1234")
    monkeypatch.setenv("ONEBOUND_SECRET", "sss_test_secret_5678")
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", cap)


def _fresh_store(num_iid):
    from src.collectors import taobao_provider_onebound as O
    from src.db import image_translate_queue_pg as st
    st.state_set(O._RAW + num_iid, {})


# ── 실측 응답(오너 첨부) ──────────────────────────────────────────────────────────

def test_real_652874751412_parses_as_owner_counted():
    """오너 실측 응답(원문 그대로) — 오너가 센 기대값과 1:1."""
    from src.collectors import taobao_provider_onebound as O
    raw = json.loads(REAL.read_text(encoding="utf-8"))
    assert raw["error_code"] == "0000" and len(raw["item"]["desc_img"]) == 20 and not O.item_id_mismatch(raw, "652874751412")
    p = O.normalize(raw)
    pv = p["provider"]
    assert p["title"].startswith("奶油风布艺沙发") and pv["price_cny"] == 480.0 == p["price"]
    assert len(p["images"]) == 5 and all(u.startswith("https://img.alicdn.com/") for u in p["images"])
    assert len(p["detail_images"]) == 19 and not any("o0b.cn" in u for u in p["detail_images"])   # 20 − 추적 픽셀 1
    axes = {o["name"]: o["values"] for o in p["options"]}
    assert list(axes) == ["几人坐", "颜色分类"] and len(axes["几人坐"]) == 8 and axes["颜色分类"] == ["乳白色 尺寸颜色可定制"]
    assert len(p["skus"]) == 8 and p["skus"][0] == {"spec": ["脚踏90*60*48cm", "乳白色 尺寸颜色可定制"], "price": 480.0,
                                                   "stock": 200, "sku_id": "4881047531343"}
    assert p["skus"][1]["stock"] == 135 and all(k["sku_id"] for k in p["skus"])
    assert pv["is_tmall"] is False and pv["shop_name"] == "佑安居" and pv["stock_total"] == 1527
    assert pv["cache"] is True and pv["data_update"] == "2026-10-04 20:54:24"
    assert pv["api_info"]["max"] == 10 and pv["api_info"]["expires"] == "2026-10-08"
    assert pv["option_images"] == {"乳白色 尺寸颜色可定制":
                                   "https://img.alicdn.com/imgextra/i1/2568161054/O1CN017GTZ4h1Jem9Qra1ap_!!2568161054.jpg"}  # http → https
    assert pv["origin_city"] == "江苏南通" and pv["video_url"].startswith("https://cloud.video.taobao.com/")
    assert len(p["detail_specs"]) == 22 and p["detail_specs"][0] == ["品牌", "#0 工厂"] and pv["parse_notes"] == []


def test_real_via_call_reuses_and_keeps_raw(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("652874751412")
    calls = []

    def tr(url, params):
        calls.append(params["num_iid"])
        raw = json.loads(REAL.read_text(encoding="utf-8"))
        raw["cache"] = 0             # 실측 원문은 cache=1(10-04 데이터) — 하루 지나면 cache=no 재호출이 맞게 돈다(시계에 묶이지 않게)
        return 200, json.dumps(raw, ensure_ascii=False)
    r = O.fetch_detail("652874751412", transport=tr)
    assert r["state"] == "ok" and len(r["payload"]["skus"]) == 8 and calls == ["652874751412"]
    assert O.fetch_detail("652874751412", transport=tr)["reused"] is True and calls == ["652874751412"]


def test_num_iid_mismatch_fails_and_is_not_stored(monkeypatch):
    """요청 상품번호와 응답 item.num_iid가 다르면 실패(캐시 오염 방어) — 보관도 안 한다."""
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("999000111")
    r = O.fetch_detail("999000111", transport=lambda u, p: (200, REAL.read_text(encoding="utf-8")))
    assert r["state"] == "manual" and r["kind"] == "provider_fail"
    assert r["reason"] == "온바운드 응답 상품번호 불일치(요청 999000111 ≠ 응답 652874751412) — 캐시 오염 의심, 쓰지 않음"
    assert not O.stored("999000111").get("raw")
    raw = json.loads(REAL.read_text(encoding="utf-8"))
    del raw["item"]["num_iid"]
    assert O.item_id_mismatch(raw, "652874751412").startswith("온바운드 응답에 상품번호 없음")


def test_props_img_dict_and_http_to_https():
    """props_img = {"pid:vid": url}만 와도 옵션값 사진을 읽는다 · http:// → https://."""
    from src.collectors import taobao_provider_onebound as O
    raw = json.loads(REAL.read_text(encoding="utf-8"))
    del raw["item"]["prop_imgs"]
    assert O.normalize(raw)["provider"]["option_images"] == {
        "乳白色 尺寸颜色可定制": "https://img.alicdn.com/imgextra/i1/2568161054/O1CN017GTZ4h1Jem9Qra1ap_!!2568161054.jpg"}
    assert O._https("http://a.b/c.jpg") == "https://a.b/c.jpg" and O._https("//a.b/c.jpg") == "https://a.b/c.jpg"


# ── 파서(재구성 픽스처) ──────────────────────────────────────────────────────────

def test_parser_maps_owner_fields_and_keeps_pipeline_keys():
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider_onebound as O
    p = O.normalize(json.loads(_recon_text()))
    assert set(T.enrich_payload({"data": {}}).keys()) <= set(p.keys())          # 뒤 파이프라인 키 그대로
    pv = p["provider"]
    assert p["price"] == 128.0 and pv["price_cny"] == 128.0 and pv["original_price_cny"] == 168.0 and p["currency"] == "CNY"
    assert p["images"] == ["https://img.alicdn.com/imgextra/i1/0/O1CN01main.jpg",
                           "https://img.alicdn.com/imgextra/i2/0/O1CN01side.jpg",
                           "https://img.alicdn.com/imgextra/i3/0/O1CN01back.jpg"]       # 「//」 보정 · pic_url 중복 제거
    assert p["detail_images"] == ["https://img.alicdn.com/imgextra/i4/0/O1CN01desc1.jpg",
                                  "https://img.alicdn.com/imgextra/i4/0/O1CN01desc2.jpg"]    # o0b.cn 픽셀 제외
    assert p["options"] == [{"name": "几人坐", "values": ["单人", "双人"]}, {"name": "颜色分类", "values": ["灰色"]}]
    assert [k["spec"] for k in p["skus"]] == [["单人", "灰色"], ["双人", "灰色"]]          # properties → props_list
    assert p["skus"][1] == {"spec": ["双人", "灰色"], "price": 198.0, "stock": 0, "sku_id": "5100000002"}
    assert p["detail_specs"] == [["品牌", "格斯潘"], ["面料", "科技布"]] == pv["spec_table"]
    assert pv["option_images"] == {"灰色": "https://img.alicdn.com/imgextra/i5/0/O1CN01gray.jpg"}
    assert pv["video_url"].startswith("https://cloud.video.taobao.com/") and pv["origin_city"] == "浙江 金华"
    assert pv["is_tmall"] is False and pv["shop_name"] == "示例家居店" == p["shop_name"] and pv["stock_total"] == 200
    assert pv["cache"] is True and pv["price_asof"] == "2026-10-01 09:00:00"              # 캐시 + 하루 넘음 → 기준일 표기
    assert pv["parse_notes"] == []


def test_properties_name_is_not_used():
    """SKU 조합은 properties + props_list로만 — properties_name이 어긋나도 따라가지 않는다."""
    from src.collectors import taobao_provider_onebound as O
    raw = json.loads(_recon_text())
    for k in raw["item"]["skus"]["sku"]:
        k["properties_name"] = "x:y:엉뚱:값"
    assert [k["spec"] for k in O.normalize(raw)["skus"]] == [["单人", "灰色"], ["双人", "灰色"]]


def test_api_info_parse():
    from src.collectors import taobao_provider_onebound as O
    a = O.parse_api_info("today: max:10 all[=++];expires:2026-10-08")
    assert a["max"] == 10 and a["expires"] == "2026-10-08"
    assert O.parse_api_info("이상한 값")["max"] is None


def test_fresh_cache_has_no_price_asof():
    from datetime import datetime, timezone, timedelta
    from src.collectors import taobao_provider_onebound as O
    raw = json.loads(_recon_text())
    raw["data_update"] = (datetime.now(timezone(timedelta(hours=9))) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    assert O.normalize(raw)["provider"]["price_asof"] == ""
    raw["cache"] = 0
    raw["data_update"] = "2026-01-01 00:00:00"
    assert O.normalize(raw)["provider"]["price_asof"] == ""


# ── 호출 · 실패 · 한도 · 재사용 ─────────────────────────────────────────────────

def test_call_params_and_lang_fixed(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("733241700286")
    seen = {}

    def tr(url, params):
        seen.update(params, url=url)
        return 200, _recon_text()
    r = O.fetch_detail("733241700286", transport=tr)
    assert r["state"] == "ok" and seen["url"] == "https://api-gw.onebound.cn/taobao/item_get/"
    assert seen["num_iid"] == "733241700286" and seen["is_promotion"] == "1" and seen["lang"] == "zh-CN"


def test_error_code_passes_reason_verbatim_no_retry(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("111")
    calls = []

    def tr(url, params):
        calls.append(1)
        return 200, '{"error":"item-not-found","reason":"商品不存在或已下架","error_code":"1001"}'
    r = O.fetch_detail("111", transport=tr)
    assert r["state"] == "manual" and r["kind"] == "provider_fail" and r["reason"] == "온바운드 1001: 商品不存在或已下架"
    assert calls == [1]                                               # error_code≠0000 → 재시도 0


def test_retry_once_on_5xx_only(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("222")
    seq = [(502, "bad gateway"), (200, _recon_text("222"))]
    r = O.fetch_detail("222", transport=lambda u, p: seq.pop(0))
    assert r["state"] == "ok" and seq == []
    _fresh_store("223")
    seq4 = [(403, "forbidden"), (200, _recon_text("223"))]
    r4 = O.fetch_detail("223", transport=lambda u, p: seq4.pop(0))
    assert r4["state"] == "manual" and len(seq4) == 1                # 4xx는 재시도 안 함


def test_daily_cap_holds_before_calling(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    monkeypatch.setenv("ONEBOUND_DAILY_CAP", str(O.used_today()))
    _fresh_store("333")
    r = O.fetch_detail("333", transport=lambda u, p: pytest.fail("한도 넘으면 호출 안 함"))
    assert r["state"] == "manual" and r["kind"] == "provider_cap" and r["reason"].startswith("온바운드 일일 한도")


def test_default_cap_is_60(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    monkeypatch.delenv("ONEBOUND_DAILY_CAP", raising=False)
    assert O.daily_cap() == 60


def test_same_item_within_24h_reuses_stored_raw(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("444")
    calls = []

    def tr(url, params):
        calls.append(1)
        return 200, _cache_raw(params["num_iid"], 0, 0)          # 캐시 아님(하루 넘은 캐시 재호출과 섞이지 않게)
    assert O.fetch_detail("444", transport=tr)["reused"] is False
    again = O.fetch_detail("444", transport=tr)
    assert again["state"] == "ok" and again["reused"] is True and calls == [1]     # 24시간 재담기 → 호출 0
    assert O.fetch_detail("444", refresh=True, transport=tr)["reused"] is False and calls == [1, 1]   # 「새로 받기」만
    assert O.stored("444")["raw"]["item"]["num_iid"] == "444"                       # 원문 보관(상품당 최신 1건)


def test_keys_missing_is_its_own_failure_and_boot_warning(monkeypatch):
    from src.collectors import taobao_provider as P
    from src.services import taobao_auto as A
    monkeypatch.delenv("ONEBOUND_KEY", raising=False)
    monkeypatch.delenv("ONEBOUND_SECRET", raising=False)
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    _fresh_store("555")
    assert "공급자 키 미설정" in A.startup_check() and A.enabled() and A.effective_route() == "onebound"
    r = P.fetch_detail("555", transport=lambda u, p: pytest.fail("키 없으면 호출 안 함"))
    assert r["state"] == "manual" and r["reason"].startswith("공급자 키 미설정")


# ── 자동 담기 ───────────────────────────────────────────────────────────────────

def _auto_env(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    monkeypatch.setenv("TAOBAO_DETAIL_PROVIDER", "onebound")
    monkeypatch.delenv("TAOBAO_MTOP_AUTO", raising=False)
    monkeypatch.setattr(T, "fetch", lambda *a, **k: pytest.fail("onebound면 mtop을 부르지 않는다"))
    _fresh_store("733241700286")
    return O


def test_share_auto_collects_price_options_images_specs(monkeypatch):
    """완료 조건: 공급자 onebound + 키 → 담기 1건이 가격·옵션(축)·사진·규격표까지(같은 병합) → 카드 「채웠어요」."""
    from src.services import taobao_auto as A
    from src.services import mtop_stats as MS
    from src.seller_console import collect_history_store as S
    O = _auto_env(monkeypatch)
    real_call = O.call
    monkeypatch.setattr(O, "call", lambda iid, refresh=False, no_cache=False, transport=None:
                        real_call(iid, refresh=refresh, no_cache=no_cache, transport=lambda u, p: (200, _recon_text())))
    before = MS.summary(3)["routes"].get("onebound", {}).get("ok", 0)
    seller = "owner-onebound"
    iid = _share_item(seller)
    rec = A.run(seller, iid)
    assert rec["state"] == "done" and rec["route"] == "onebound" and rec["kind"] == "ok"
    assert rec["counts"] == {"images": 3, "skus": 2, "detail_images": 2} and rec["price_asof"] == "2026-10-01 09:00:00"
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert ex["price"] and len(ex["images"]) == 3 and len(ex["skus"]) == 2 and len(ex["options"]) == 2
    assert ex["detail_specs"] == [["品牌", "格斯潘"], ["面料", "科技布"]]
    assert ex["provider_detail"]["is_tmall"] is False and ex["provider_detail"]["origin_city"] == "浙江 金华"
    assert "provider" not in ex and MS.summary(3)["routes"]["onebound"]["ok"] - before == 1
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"] = seller
    d = c.get(f"/seller/collect/{iid}/auto-enrich").get_json()
    assert d["state"] == "done" and "가격 기준 2026-10-01 09:00:00" in d["line"]


def test_share_auto_failure_card_carries_raw_reason(monkeypatch):
    from src.services import taobao_auto as A
    O = _auto_env(monkeypatch)
    real_call = O.call
    monkeypatch.setattr(O, "call", lambda iid, refresh=False, no_cache=False, transport=None: real_call(
        iid, refresh=refresh, transport=lambda u, p: (200, '{"error_code":"4005","reason":"授权已过期","error":"key"}')))
    seller = "owner-onebound-fail"
    iid = _share_item(seller)
    rec = A.run(seller, iid)
    assert rec["state"] == "manual" and rec["kind"] == "provider_fail"
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"] = seller
    d = c.get(f"/seller/collect/{iid}/auto-enrich").get_json()
    assert d["line"].startswith("자동 수집 실패(provider_fail) — 온바운드 4005: 授权已过期")


def test_unresolved_item_id_reason(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.services import taobao_auto as A
    from src.seller_console import collect_history_store as S
    _auto_env(monkeypatch)
    seller = "owner-onebound-noid"
    iid = S.append(source="share_text", url="https://e.tb.cn/h.xxxx", seller_id=seller, title="x", price="", currency="",
                   extra={"title": "x", "enrich_state": "pending"})
    monkeypatch.setattr(T, "item_id_from", lambda arg, s=None: ("", "못 폄"))
    rec = A.run(seller, iid)
    assert rec["state"] == "manual" and rec["reason"] == "상품번호 해석 실패"


def test_spec_table_cn_plug_blocks_like_title():
    """五孔/国标插座 소싱 제외 — 규격표 값도 본다(제목·옵션과 같은 판정)."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title": "멀티탭", "title_src": "排插", "options": [], "detail_specs": [["插座类型", "国标插座"]],
          "price": "10", "currency": "CNY", "images": ["https://a/1.jpg"]}
    assert any("중국 표준 콘센트" in h.get("short", "") for h in UploadDispatcher.readiness_holds(pd, "coupang"))
    pd["detail_specs"] = [["插座类型", "USB"]]
    assert not any("중국 표준 콘센트" in h.get("short", "") for h in UploadDispatcher.readiness_holds(pd, "coupang"))


# ── 진단 ───────────────────────────────────────────────────────────────────────

def test_diag_provider_page(monkeypatch):
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("733241700286")
    raw = json.loads(_recon_text())
    raw["echo"] = "secret=sss_test_secret_5678"                     # 응답에 시크릿이 섞여 와도
    monkeypatch.setattr(T, "item_id_from", lambda arg, s=None: ("733241700286", "e.tb.cn 펴기"))
    real_call = O.call
    monkeypatch.setattr(O, "call", lambda iid, refresh=False, no_cache=False, transport=None:
                        real_call(iid, refresh=refresh, no_cache=no_cache, transport=lambda u, p: (200, json.dumps(raw))))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-provider", query_string={"q": "https://e.tb.cn/h.abc"}).get_data(as_text=True)
    assert 'data-role="provider-norm"' in h and "옵션 축 几人坐(2): 单人 / 双人" in h and "SKU 2개" in h
    assert "일일 한도 10 · 만료 2026-10-08" in h and "data_update 2026-10-01 09:00:00" in h and "가격 기준 2026-10-01" in h
    assert "sss_test_secret_5678" not in h and "kkk_test_key_1234" not in h and 'data-role="provider-refresh"' in h
    h2 = c.get("/admin/diagnostics/taobao-provider", query_string={"q": "733241700286"}).get_data(as_text=True)
    assert "보관본 재사용 — 호출 0" in h2
    d = c.get("/admin/diagnostics/taobao-provider/raw/733241700286.json")
    assert d.status_code == 200 and "sss_test_secret_5678" not in d.get_data(as_text=True)
    m = c.get("/admin/diagnostics/taobao-mtop").get_data(as_text=True)
    assert 'href="/admin/diagnostics/taobao-provider"' in m


def test_diag_refresh_button_sends_cache_no(monkeypatch):
    """진단 「새로 받기」(POST) → 실제 요청 params에 cache=no · REFRESH_STALE 상태 한 줄."""
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    monkeypatch.setenv("ONEBOUND_REFRESH_STALE", "0")
    _fresh_store("733241700287")
    seen = []
    monkeypatch.setattr(T, "item_id_from", lambda arg, s=None: ("733241700287", "숫자"))
    real_call = O.call

    def tr(u, p):
        seen.append(dict(p))
        return 200, _cache_raw("733241700287", 0, 0)
    monkeypatch.setattr(O, "call", lambda iid, refresh=False, no_cache=False, transport=None:
                        real_call(iid, refresh=refresh, no_cache=no_cache, transport=tr))
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics/taobao-provider", query_string={"q": "733241700287"}).get_data(as_text=True)
    assert "cache" not in seen[-1] and "ONEBOUND_REFRESH_STALE): 끔" in h
    # Z3-D: 주소의 refresh=1(GET)은 무시 — 새로고침마다 유료 재호출이 나가던 길(운영 4013 중 33회)
    h = c.get("/admin/diagnostics/taobao-provider", query_string={"q": "733241700287", "refresh": "1"}).get_data(as_text=True)
    assert len(seen) == 1 and 'data-role="provider-legacy-refresh"' in h
    r = c.post("/admin/diagnostics/taobao-provider/refresh", data={"q": "733241700287"})
    assert r.status_code == 303 and "refresh" not in r.headers["Location"]
    assert seen[-1]["cache"] == "no" and len(seen) == 2


def test_docs_memo_exists():
    doc = (Path(__file__).parent.parent / "docs" / "z3-onebound.md").read_text(encoding="utf-8")
    for w in ("0.023", "ONEBOUND_KEY", "ONEBOUND_SECRET", "TAOBAO_DETAIL_PROVIDER", "ONEBOUND_DAILY_CAP", "login_required"):
        assert w in doc


def test_app_boot_does_not_import_site_adapters():
    """#835 CI 실측: 부팅 startup_check가 `src.collectors` 패키지를 import하면 `__init__`이 사이트 어댑터 전부를 끌고 와
    어댑터의 import 시점 ADAPTER_DRY_RUN이 굳어 dry-run 계약 4건이 실네트워크로 돌았다 — 부팅은 env만 본다."""
    import subprocess
    import sys
    code = ("import sys, src.order_webhook; "
            "print(int('src.collectors.adapters.yoshida_kaban_adapter' in sys.modules))")
    for env_extra in ({}, {"TAOBAO_DETAIL_PROVIDER": "mtop", "TAOBAO_MTOP_AUTO": "0"}):
        import os
        env = {k: v for k, v in os.environ.items() if k not in ("TAOBAO_DETAIL_PROVIDER", "TAOBAO_MTOP_AUTO", "ADAPTER_DRY_RUN")}
        env.update(env_extra)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                             cwd=str(Path(__file__).parent.parent), timeout=120)
        assert out.stdout.strip().splitlines()[-1] == "0", out.stderr[-600:]


# ── 실측 2호(667810641388 · 운영 Render 내려받기) · 타입 관용 · cache=no ─────────────────────────

REAL2 = FX / "onebound_item_get_667810641388.json"


def test_real2_667810641388_parses_as_owner_counted():
    from src.collectors import taobao_provider_onebound as O
    raw = json.loads(REAL2.read_text(encoding="utf-8"))
    assert raw["error_code"] == "0000" and raw["client_ip"] == "74.220.52.131" and not O.item_id_mismatch(raw, "667810641388")
    p = O.normalize(raw)
    pv = p["provider"]
    assert pv["price_cny"] == 298.0 and len(p["images"]) == 5 and all(u.startswith("https://") for u in p["images"])
    assert len(p["detail_images"]) == 17 and not any("o0b.cn" in u for u in p["detail_images"])   # 픽셀은 desc(html)에만
    assert [(o["name"], len(o["values"])) for o in p["options"]] == [("颜色分类", 8)]
    assert len(p["skus"]) == 8 and {k["price"] for k in p["skus"]} == {298.0}
    assert all(45 <= k["stock"] <= 50 for k in p["skus"])
    assert pv["is_tmall"] is False and pv["shop_name"] == "110V家电商贸城" and pv["cache"] is False and pv["price_asof"] == ""
    assert pv["api_info"]["today"] == 1 and pv["api_info"]["max"] == 10 and pv["api_info"]["expires"] == "2026-10-08"
    assert len(pv["option_images"]) == 8 and pv["parse_notes"] == []


def test_type_tolerance_real2_vs_real1():
    """실측 차이: total_sold int↔str · video.url null · 배송비·무게 null/""/0 → 「미기재」 · brand other/其他 → 없음."""
    from src.collectors import taobao_provider_onebound as O
    p1 = O.normalize(json.loads(REAL.read_text(encoding="utf-8")))["provider"]
    p2 = O.normalize(json.loads(REAL2.read_text(encoding="utf-8")))["provider"]
    assert p1["total_sold"] == 0 and p2["total_sold"] == 6 and p2["sales"] == 6
    assert p2["video_url"] is None and p1["video_url"].startswith("https://")
    for pv in (p1, p2):
        assert pv["post_fee"] == pv["express_fee"] == pv["item_weight"] == O.UNLISTED == "미기재"
    assert p2["freight"] == "미기재" and p2["brand"] is None and p1["brand"] == "#0 工厂"
    assert O._listed("12.5") == 12.5 and O._brand("其他") is None and O._brand("other") is None


def test_missing_keys_never_raise_and_fallbacks():
    """키 누락에 KeyError 없음 · desc_img 비면 desc(html) <img>에서(o0b.cn 제외) · prop_imgs 없으면 props_imgs."""
    from src.collectors import taobao_provider_onebound as O
    raw = json.loads(REAL2.read_text(encoding="utf-8"))
    raw["item"]["desc_img"] = []
    del raw["item"]["prop_imgs"]
    del raw["item"]["props_img"]
    p = O.normalize(raw)
    assert len(p["detail_images"]) == 17 and not any("o0b.cn" in u for u in p["detail_images"])
    assert len(p["provider"]["option_images"]) == 8                              # props_imgs(복수형)에서
    assert "desc(html)에서 상세 사진 17장" in p["provider"]["parse_notes"][0]
    for bare in ({}, {"item": {}}, {"item": None}, {"item": {"num_iid": "1", "skus": None, "props_list": None, "video": None}}):
        q = O.normalize(bare)
        assert q["title"] == "" and q["skus"] == [] and q["options"] == []


def test_unknown_keys_kept_in_stored_raw(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("667810641388")
    assert O.fetch_detail("667810641388", transport=lambda u, p: (200, REAL2.read_text(encoding="utf-8")))["state"] == "ok"
    kept = O.stored("667810641388")["raw"]["item"]
    assert kept["_ddf"] == "ykn1" and "suggestive_price" in kept and "url_log" in kept


def _cache_raw(num_iid, cache, hours_old):
    from datetime import datetime, timedelta, timezone
    raw = json.loads(_recon_text(num_iid))
    raw["cache"] = cache
    raw["data_update"] = (datetime.now(timezone(timedelta(hours=8))) - timedelta(hours=hours_old)).strftime("%Y-%m-%d %H:%M:%S")
    return json.dumps(raw, ensure_ascii=False)


@pytest.mark.parametrize("cache,hours_old,calls,second_no_cache", [
    (0, 100, 1, None),          # 캐시 아님 → 1회, cache=no 안 붙음
    (1, 2, 1, None),            # 캐시 + 신선(24h 안) → 1회
    (1, 30, 2, True),           # 캐시 + 하루 초과 → cache=no로 1회 더(한도도 2회)
])
def test_auto_cache_bypass_only_when_cached_and_stale(monkeypatch, cache, hours_old, calls, second_no_cache):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    iid = f"77{cache}{hours_old}"
    _fresh_store(iid)
    seen = []

    def tr(url, params):
        seen.append(dict(params))
        if params.get("cache") == "no":
            return 200, _cache_raw(iid, 0, 0)
        return 200, _cache_raw(iid, cache, hours_old)
    before = O.used_today()
    r = O.fetch_detail(iid, transport=tr)
    assert r["state"] == "ok" and len(seen) == calls and O.used_today() - before == calls
    assert "cache" not in seen[0]                                               # 첫 호출엔 안 붙인다
    if second_no_cache:
        assert seen[1]["cache"] == "no" and r["bypassed"] is True and r["payload"]["provider"]["price_asof"] == ""
    else:
        assert r["bypassed"] is False


def test_bypass_failure_keeps_cached_value_with_price_asof(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("880001")

    def tr(url, params):
        if params.get("cache") == "no":
            return 200, '{"error_code":"4000","reason":"busy"}'
        return 200, _cache_raw("880001", 1, 40)
    r = O.fetch_detail("880001", transport=tr)
    assert r["state"] == "ok" and r["bypassed"] is False and r["payload"]["provider"]["price_asof"]


@pytest.mark.parametrize("env", ["0", "false", "off"])
def test_refresh_stale_off_skips_auto_recall(monkeypatch, env):
    """ONEBOUND_REFRESH_STALE=0 — 하루 넘은 캐시여도 자동 cache=no 재호출 0(체험 기간 오너 설정), 「가격 기준」 표시.
    「새로 받기」(refresh)는 이 값과 무관하게 cache=no."""
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    monkeypatch.setenv("ONEBOUND_REFRESH_STALE", env)
    iid = "8800" + str(len(env)) + "9"
    _fresh_store(iid)
    seen = []

    def tr(url, params):
        seen.append(dict(params))
        return 200, _cache_raw(iid, 1, 30)
    before = O.used_today()
    r = O.fetch_detail(iid, transport=tr)
    assert r["state"] == "ok" and len(seen) == 1 and "cache" not in seen[0] and O.used_today() - before == 1
    assert r["bypassed"] is False and r["payload"]["provider"]["price_asof"]          # 캐시 값 그대로 + 기준 시각
    r2 = O.fetch_detail(iid, refresh=True, transport=tr)
    assert seen[-1]["cache"] == "no" and r2["bypassed"] is True and len(seen) == 2


def test_refresh_stale_default_on(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    monkeypatch.delenv("ONEBOUND_REFRESH_STALE", raising=False)
    assert O.refresh_stale() is True
    monkeypatch.setenv("ONEBOUND_REFRESH_STALE", "1")
    assert O.refresh_stale() is True
    monkeypatch.setenv("ONEBOUND_REFRESH_STALE", "0")
    assert O.refresh_stale() is False


def test_refresh_sends_cache_no_and_overwrites_store(monkeypatch):
    from src.collectors import taobao_provider_onebound as O
    _keys(monkeypatch)
    _fresh_store("880002")
    seen = []

    def tr(url, params):
        seen.append(dict(params))
        return 200, _cache_raw("880002", 0, 0)
    O.fetch_detail("880002", transport=tr)
    assert O.fetch_detail("880002", transport=tr)["reused"] is True and len(seen) == 1   # 24h 재사용 그대로
    r = O.fetch_detail("880002", refresh=True, transport=tr)
    assert r["reused"] is False and r["bypassed"] is True and seen[-1]["cache"] == "no" and len(seen) == 2
