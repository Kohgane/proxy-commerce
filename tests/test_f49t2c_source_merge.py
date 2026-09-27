"""F49-T 2부-c — 확장 페이로드는 정상인데 초안에 안 들어갔다(2026-09-27 03:21Z, ext 1.5.156, 617129397971).

실측: payload_echo has_price true · skus_n 10 · options_n 1 · field_sources 전부 ice_context. 화면 초안은
옵션 17/13/12/11 · 가격 없음 · SKU 표 없음 그대로. 원인 — 그 행은 이미 보강이 끝난(`enrich_state=done`) 초안이라
수집 라우트가 「이미 수집한 상품」으로 돌려보내며 **아무것도 쓰지 않았고**, `/enrich`도 「빈 칸만 채움」이었다.

이 파일이 못박는 것(입력 = 오너가 올린 **1.5.156 진단 파일의 실제 추출값**):
  ① tier2 잡음 옵션이 든 초안 + ice_context 페이로드 → 옵션 1그룹 · SKU 10 · 가격 29.90, 드로어 SKU 10줄
  ② 오너가 손으로 고친 필드는 어떤 출처가 와도 그대로
  ③ 낮은 출처(tier2)는 높은 출처(ice_context)를 못 덮는다 · 같은 값이면 예전처럼 「이미 수집한 상품」
  ④ 드로어 「원본에서 다시 수집」 = 서버는 원본을 안 열고 표시만 → 그 뒤 수집은 재수집 규칙(같은 순위도 덮음)
  ⑤ 드로어 각 필드 옆에 출처, 마지막 병합 결과(바뀐 것·남긴 것)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

TMALL = "https://detail.tmall.com/item.htm?id=617129397971"
DIAG = Path("fixtures/realpages/diag/kgp-diagnostic-detail-tmall-com-item-htm-id-617129397971.html")
JUNK = [{"name": f"옵션{i}", "values": [f"잡음{i}-{j}" for j in range(n)]}
        for i, n in enumerate((17, 13, 12, 11))]


def _real_payload() -> dict:
    t = DIAG.read_text(encoding="utf-8")
    d = json.loads(re.search(r'<script type="application/json" id="kgp-diagnostic">(.*?)</script>', t, re.S).group(1))
    e = d["extracted"]
    assert d["ext_version"] == "1.5.156" and len(e["skus"]) == 10 and e["price"] == "29.90"
    return {k: e.get(k) for k in ("title", "price", "currency", "images", "gallery_images", "options", "skus",
                                  "description", "detail_images", "field_sources", "page_diag")}


def _client(monkeypatch, seller):
    import src.api.extension_api as ext
    from src.order_webhook import app
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def _junk_draft(c, seller):
    """오너 화면 그대로: 붙여넣기 초안 → 옛 확장(tier2)이 잡음 옵션 4그룹·이미지로 보강(가격 없음) → done."""
    from src.collectors.share_collect import collect_input
    r = collect_input(TMALL, seller_id=seller, source="preview", translate=False)
    iid = r["item_id"]
    e = c.post("/api/v1/collect/enrich", json={
        "item_id": iid, "options": JUNK, "gallery": ["https://img.alicdn.com/tps/icon-a.png"],
        "field_sources": {"options": "tier2", "images": "tier2"}}).get_json()
    assert e["ok"] and c.get(f"/seller/collect/{iid}/state").get_json()["enrich_state"] == "done"
    return iid


def _extra(iid):
    from src.seller_console import collect_history_store as S
    row = S.get(iid, seller_ids=None) if "seller_ids" in S.get.__code__.co_varnames else S.get(iid)
    return json.loads(row.get("extra_json") or "{}"), row


def _post(c, body, **kw):
    return c.post("/api/v1/collect/extension", json={"url": TMALL, "translate": False, **body, **kw}).get_json()


# ① 오너 실측 재현
def test_ice_payload_replaces_tier2_junk_on_an_enriched_draft(monkeypatch):
    seller = "u-2c-junk"
    c = _client(monkeypatch, seller)
    iid = _junk_draft(c, seller)
    d = _post(c, _real_payload())
    assert d["ok"] and d["updated"] and d["item_id"] == iid, d
    assert set(d["changed"]) >= {"options", "sku", "price", "images"}
    ex, row = _extra(iid)
    assert [o["name"] for o in ex["options"]] == ["颜色分类"] and len(ex["options"][0]["values"]) == 10
    assert len(ex["skus"]) == 10 and ex["price"] == "29.90" and ex["currency"] == "CNY"
    assert row["price"] == "29.90" and ex["gate_ready"] is True
    assert ex["field_sources"]["options"] == "ice_context" and ex["field_sources"]["sku"] == "ice_context"
    assert not any("icon-a" in u for u in ex["images"])          # tier2 아이콘 이미지가 대표로 남지 않는다
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    table = html[html.index('data-role="sku-table"'):]
    table = table[:table.index("</table>")]
    assert table.count("<tr") == 11                                # 머리 1 + SKU 10줄
    assert "잡음0-0" not in html
    assert 'data-field="options"' in html and "티몰 상태(ICE)" in html
    assert 'data-role="merge-log"' in html and "화면 읽기→티몰 상태(ICE)" in html


# ② 직접 수정은 유지
def test_owner_edits_survive_a_better_source(monkeypatch):
    seller = "u-2c-manual"
    c = _client(monkeypatch, seller)
    iid = _junk_draft(c, seller)
    s = c.post(f"/seller/collect/preview/{iid}/save", json={
        "title": "오너가 고친 제목", "price": "", "options": [{"name": "색상", "values": ["블랙", "화이트"]}]}).get_json()
    assert s["ok"]
    ex, _ = _extra(iid)
    assert set(ex["manual_fields"]) == {"title", "options"}          # 가격은 비워 보냄 → 수정 아님
    d = _post(c, _real_payload())
    ex, _ = _extra(iid)
    assert ex["options"] == [{"name": "색상", "values": ["블랙", "화이트"]}]
    assert ex["title"] == "오너가 고친 제목"
    assert ex["price"] == "29.90" and len(ex["skus"]) == 10          # 안 고친 필드는 갱신
    assert "options" in d["kept"] and "직접 수정" in d["kept"]["options"]
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert re.search(r'data-field="options"[^>]*>직접 수정<', html)


# ③ 낮은 출처는 못 덮는다 · 같은 값이면 예전 그대로
def test_lower_source_cannot_overwrite_and_same_payload_is_plain_duplicate(monkeypatch):
    seller = "u-2c-lower"
    c = _client(monkeypatch, seller)
    iid = _junk_draft(c, seller)
    p = _real_payload()
    assert _post(c, p)["updated"]
    again = _post(c, p)
    assert again["duplicate"] is True and not again.get("updated")   # 바꿀 게 없으면 「이미 수집한 상품」
    lower = dict(p, options=JUNK, field_sources={**p["field_sources"], "options": "tier2"})
    d = _post(c, lower)
    ex, _ = _extra(iid)
    assert [o["name"] for o in ex["options"]] == ["颜色分类"]
    assert "options" in (d.get("kept") or {})


def test_enrich_uses_the_same_rule(monkeypatch):
    """목록 카드 → 상세 보강(`/enrich`)으로 와도 같은 규칙 — ice_context가 tier2를 덮는다."""
    seller = "u-2c-enrich"
    c = _client(monkeypatch, seller)
    iid = _junk_draft(c, seller)
    p = _real_payload()
    r = c.post("/api/v1/collect/enrich", json={"item_id": iid, "options": p["options"], "skus": p["skus"],
                                                "price": p["price"], "currency": "CNY", "gallery": p["images"],
                                                "field_sources": p["field_sources"]}).get_json()
    assert r["ok"] and {"options", "skus", "price"} <= set(r["changed"])
    ex, _ = _extra(iid)
    assert len(ex["options"]) == 1 and len(ex["skus"]) == 10 and ex["price"] == "29.90"


# ④ 드로어 「원본에서 다시 수집」
def test_drawer_recollect_marks_and_the_next_collect_overwrites_same_rank(monkeypatch):
    seller = "u-2c-recollect"
    c = _client(monkeypatch, seller)
    iid = _junk_draft(c, seller)
    p = _real_payload()
    _post(c, p)
    newer = dict(p, price="31.50")                                   # 같은 ice_context — 평소엔 안 덮는다
    assert not _post(c, newer).get("updated")
    r = c.post(f"/seller/collect/{iid}/recollect").get_json()
    assert r["ok"] and r["open_url"].startswith("https://") and "id=617129397971" in r["open_url"]
    d = _post(c, newer)
    assert d["updated"] and "price" in d["changed"]
    ex, _ = _extra(iid)
    assert ex["price"] == "31.50"
    st = c.get(f"/seller/collect/{iid}/state").get_json()
    assert st["recollected_at"] >= st["recollect_requested_at"] and "price" in st["last_merge"]["changed"]
    assert not _post(c, dict(p, price="33.00")).get("updated")      # 표시는 한 번 쓰면 끝


def test_recollect_button_is_in_the_drawer_and_server_never_fetches(monkeypatch):
    import requests
    seller = "u-2c-nofetch"
    c = _client(monkeypatch, seller)
    iid = _junk_draft(c, seller)
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(a) or pytest.fail("서버 fetch"))
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert 'id="btnRecollect"' in html and "원본에서 다시 수집" in html
    assert c.post(f"/seller/collect/{iid}/recollect").get_json()["ok"] and not calls


def test_merge_rule_unit():
    from src.collectors.source_merge import merge_by_source, rank
    assert rank("ice_context") > rank("tier1") > rank("tier2") > rank("") > rank("none")
    ex = {"options": JUNK, "field_sources": {"options": "tier2"}}
    ex, ch, kept = merge_by_source(ex, {"options": [{"name": "颜色分类", "values": ["黑"]}]}, {"options": "ice_context"})
    assert ex["options"][0]["name"] == "颜色分类" and "options" in ch and ex["merge_log"][-1]["changed"]
    ex2, ch2, _ = merge_by_source({"price": "10"}, {"price": ""}, {"price": "ice_context"})
    assert ex2["price"] == "10" and not ch2                          # 빈 값은 절대 안 덮는다
