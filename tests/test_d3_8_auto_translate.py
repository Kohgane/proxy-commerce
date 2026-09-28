"""D3-8 — 수집 시 이미지 번역 자동(퍼센티 방식) + 비용 가드(오너 2026-09-27).

  ① 중국 소싱처 초안의 보강이 끝나면(`/enrich`) 갤러리+상세 이미지가 장 단위로 **자동 큐** → 번역본이 장별로 놓인다
  ② 파이프라인 = 벤치 D3 최신(Tencent 박스+원문 → 용어집 → telea / gen_remove → F축이 나은 쪽 자동 선택)
     · 글자 없는 장은 원본(skipped) · 이름표 `<run>_<product>_p<page>_<pipeline>`
  ③ 일일 상한 `IMAGE_TRANSLATE_DAILY_CAP`(기본 200) = **시작한 장 수**(실패 포함), KST 자정 리셋 → 넘으면 대기
  ④ 실패 누적 20장 → 큐 자동 일시정지 + 화면 경고 → 「재개」로만 계속
  ⑤ 소싱처 토글(기본 켬) · 드로어·설정 화면 「오늘 N/200」
  ⑥ 등록 페이로드는 번역본 우선(effective_images — 기존 단일 규칙)
공급사·렌더는 **테스트 대역**(키·GPU 없음) — 큐·상한·정지·저장·등록 배열은 실제 코드로 돈다.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

TB = "https://item.taobao.com/item.htm?id=617129397971"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


@pytest.fixture
def auto(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.services import image_translate_auto as A
    from src.services import image_translate_bench as bench
    from src.services import image_translate_tencent as tc
    q.reset_for_tests()
    monkeypatch.setenv("IMAGE_TRANSLATE_AUTO_SYNC", "1")
    calls = {"tc": 0, "fail_urls": set(), "no_text": set()}

    def _tc(url="", **k):
        calls["tc"] += 1
        if url in calls["fail_urls"]:
            return {"ok": False, "vendor": "tencent", "error_class": "TencentCloudSDKException",
                    "error_message": "FailedOperation.RequestTimeout", "ms": 5}
        lines = [] if url in calls["no_text"] else [{"source": "三合一", "target": "3-in-1", "box": [0, 0, 10, 10]}]
        return {"ok": True, "vendor": "tencent", "ms": 7, "lines": lines, "image_b64": ""}

    def _render(raw, lines, tokens=(), gen_remove=False):
        rows = [{"source": "三合一", "render_text": "3in1"}]
        tel = {"ok": True, "image_bytes": PNG, "axes": {"F": {"score": 0.4}}, "rows": rows, "inpainter": "telea"}
        tel["gen_remove"] = {"ok": True, "image_bytes": PNG, "axes": {"F": {"score": 0.7}}, "inpainter": "gen_remove",
                             "cloud_credits": 0.02}
        return tel

    monkeypatch.setattr(tc, "is_configured", lambda: True)
    monkeypatch.setattr(tc, "translate_image", _tc)
    monkeypatch.setattr(tc, "fetch_image", lambda url: (PNG, ""))
    monkeypatch.setattr(bench, "_render_d3_for", _render)
    yield A, q, calls
    q.reset_for_tests()


def _client(monkeypatch, seller):
    import src.api.extension_api as ext
    from src.order_webhook import app
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def _draft(c, url=TB, gallery=3, detail=2):
    iid = c.post("/api/v1/collect/extension", json={
        "url": url, "title": "随行盾 SPORTLINK", "price": "29.9", "currency": "CNY", "mode": "simple",
        "images": ["https://img.alicdn.com/list.jpg"], "translate": False}).get_json()["item_id"]
    r = c.post("/api/v1/collect/enrich", json={
        "item_id": iid, "gallery": [f"https://img.alicdn.com/g{i}.jpg" for i in range(gallery)],
        "detail_images": [f"https://img.alicdn.com/d{i}.jpg" for i in range(detail)],
        "gallery_expected": gallery, "field_sources": {"images": "ice_context"}}).get_json()
    assert r["ok"], r
    return iid


def _extra(iid, seller):
    from src.seller_console import collect_history_store as S
    return json.loads(S.get(iid, seller_id=seller)["extra_json"])


# ① + ② + ⑥
def test_enriched_cn_draft_is_translated_gallery_and_detail(monkeypatch, auto):
    A, q, calls = auto
    seller = "u-d38-flow"
    c = _client(monkeypatch, seller)
    iid = _draft(c)
    ex = _extra(iid, seller)
    g, d = ex.get("images_ko") or [], ex.get("detail_images_ko") or []
    assert len(g) == 3 and len(d) == 2 and calls["tc"] == 5
    assert all(e["status"] == "done" and e["url"] and e["pipeline"] == "GEN_REMOVE" for e in g + d)
    from src.services.image_translate_store import effective_images
    assert all(u.startswith("/seller/collect/image-ko/") for u in effective_images(ex, kind="gallery"))
    assert all("kind=detail" in u for u in effective_images(ex, kind="detail"))
    assert q.counts(iid)["done"] == 5
    st = c.get(f"/seller/image-translate/auto?item={iid}").get_json()
    assert st["today"] == 5 and st["cap"] == 200 and st["env"] == "IMAGE_TRANSLATE_DAILY_CAP"


def test_telea_wins_when_gen_remove_fell_back(monkeypatch, auto):
    A, _q, _calls = auto
    tel = {"ok": True, "image_bytes": PNG, "axes": {"F": {"score": 0.4}}}
    g = {"ok": True, "image_bytes": PNG, "axes": {"F": {"score": 0.9}}, "inpainter": "telea"}   # 폴백 = 후보 아님
    assert A._pick_render({**tel, "gen_remove": g})[1] == "TELEA"
    g2 = {**g, "inpainter": "gen_remove", "axes": {"F": {"score": 0.2}}}
    assert A._pick_render({**tel, "gen_remove": g2})[1] == "TELEA"                  # F가 낮으면 telea
    assert A._pick_render({**tel, "gen_remove": {**g2, "axes": {"F": {"score": 0.4}}}})[1] == "GEN_REMOVE"


def test_page_without_text_keeps_the_original(monkeypatch, auto):
    A, q, calls = auto
    calls["no_text"].add("https://img.alicdn.com/g1.jpg")
    seller = "u-d38-notext"
    c = _client(monkeypatch, seller)
    iid = _draft(c, gallery=2, detail=0)
    g = _extra(iid, seller)["images_ko"]
    assert g[1]["status"] == "skipped" and "글자가 없습니다" in g[1]["reason"]


# ③ 일일 상한
def test_daily_cap_counts_starts_and_waits(monkeypatch, auto):
    A, q, calls = auto
    monkeypatch.setenv("IMAGE_TRANSLATE_DAILY_CAP", "4")
    seller = "u-d38-cap"
    c = _client(monkeypatch, seller)
    iid = _draft(c, gallery=3, detail=3)
    assert calls["tc"] == 4 and q.counts(iid)["queued"] == 2 and q.counts(iid)["done"] == 4
    st = c.get(f"/seller/image-translate/auto?item={iid}").get_json()
    assert st["today"] == 4 and st["waiting_cap"] is True and st["item"]["queued"] == 2
    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    assert 'data-role="imgko-auto"' in html and "번역 대기" in html


def test_cap_resets_at_kst_midnight(auto):
    A, _q, _c = auto
    # 2026-09-27 14:59 UTC = 09-27 23:59 KST · 15:00 UTC = 09-28 00:00 KST
    assert A.kst_day(datetime(2026, 9, 27, 14, 59, tzinfo=timezone.utc)) == "2026-09-27"
    assert A.kst_day(datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)) == "2026-09-28"


def test_failures_count_toward_the_cap(monkeypatch, auto):
    A, q, calls = auto
    calls["fail_urls"].update({"https://img.alicdn.com/g0.jpg", "https://img.alicdn.com/g1.jpg"})
    seller = "u-d38-failcap"
    c = _client(monkeypatch, seller)
    iid = _draft(c, gallery=2, detail=1)
    assert q.counts(iid)["failed"] == 2 and A.status()["today"] == 3


# ④ 실패 20장 → 일시정지 → 재개
def test_twenty_failures_pause_until_owner_resumes(monkeypatch, auto):
    A, q, calls = auto
    calls["fail_urls"].update({f"https://img.alicdn.com/g{i}.jpg" for i in range(25)})
    seller = "u-d38-pause"
    c = _client(monkeypatch, seller)
    iid = _draft(c, gallery=25, detail=0)
    st = c.get(f"/seller/image-translate/auto?item={iid}").get_json()
    assert st["paused"] is True and st["failed_since_resume"] == 20 and "20장" in st["pause_reason"]
    assert q.counts(iid)["queued"] == 5 and calls["tc"] == 20                     # 20장에서 멈췄다
    calls["fail_urls"].clear()
    r = c.post("/seller/image-translate/auto/resume").get_json()
    assert r["ok"] and r["paused"] is False
    assert q.counts(iid)["done"] == 5 and q.counts(iid)["queued"] == 0


# ⑤ 토글 · 설정 화면
def test_source_toggle_off_skips_queue(monkeypatch, auto):
    A, q, calls = auto
    seller = "u-d38-toggle"
    c = _client(monkeypatch, seller)
    assert c.post("/seller/image-translate/auto/settings", json={"taobao": False}).get_json()["settings"]["taobao"] is False
    iid = _draft(c)
    assert calls["tc"] == 0 and q.counts(iid)["queued"] == 0
    assert A.settings(seller) == {"taobao": False, "tmall": True, "1688": True}


def test_settings_screen_shows_today_and_toggles():
    """설정(내 작업공간) 카드 — 사용자 레코드가 있어야 본문이 그려지므로 템플릿 자리로 잰다(드로어는 실렌더로 잰다)."""
    html = open("src/seller_console/templates/me.html", encoding="utf-8").read()
    i = html.index("{% if not user %}")
    assert html.index('data-role="imgko-auto"') > i and "이미지 자동 번역" in html
    assert "const withToggles = true" in html and "오늘 ${d.today}/${d.cap}장" in html


def test_non_cn_sources_are_not_queued(monkeypatch, auto):
    A, q, calls = auto
    assert A.enqueue_after_enrich("u", "x1", "https://www.amazon.com/dp/B0X", {"images": ["a"]}) == 0
    assert calls["tc"] == 0


def test_unconfigured_vendor_is_not_queued(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.services import image_translate_auto as A
    from src.services import image_translate_tencent as tc
    q.reset_for_tests()
    monkeypatch.setattr(tc, "is_configured", lambda: False)
    assert A.enqueue_after_enrich("u", "x2", TB, {"images": ["a", "b"]}) == 0 and q.counts()["queued"] == 0


def test_shield_recollect_triggers_translation_of_gallery_and_detail(monkeypatch, auto):
    """회귀(오너): 수행방패 **재수집**(상세 페이지 ICE 페이로드 — 오너 진단 파일 실추출값) → 번역 큐 → 갤러리 3 + 상세 N 번역본."""
    import re
    from pathlib import Path
    A, q, calls = auto
    t = Path("fixtures/realpages/diag/kgp-diagnostic-detail-tmall-com-item-htm-id-617129397971.html").read_text(encoding="utf-8")
    e = json.loads(re.search(r'<script type="application/json" id="kgp-diagnostic">(.*?)</script>', t, re.S).group(1))["extracted"]
    seller = "u-d38-shield"
    c = _client(monkeypatch, seller)
    iid = c.post("/api/v1/collect/extension", json={"url": "https://detail.tmall.com/item.htm?id=617129397971",
                                                    "title": e["title"], "price": e["price"], "currency": "CNY",
                                                    "images": e["images"], "detail_images": e.get("detail_images") or [],
                                                    "field_sources": e["field_sources"], "translate": False}).get_json()["item_id"]
    r = c.post("/api/v1/collect/extension", json={"url": "https://detail.tmall.com/item.htm?id=617129397971",
                                                  "title": e["title"], "price": e["price"], "currency": "CNY",
                                                  "images": e["images"], "detail_images": e.get("detail_images") or [],
                                                  "field_sources": e["field_sources"], "force": True,
                                                  "translate": False}).get_json()
    assert r.get("updated"), r
    ex = _extra(iid, seller)
    n_detail = len([u for u in (ex.get("detail_images") or []) if u])
    assert len(ex.get("images_ko") or []) == len(e["images"]) == 5          # 재업로드 진단: 갤러리 5장
    assert len(ex.get("detail_images_ko") or []) == n_detail
    assert all(x["status"] == "done" for x in (ex.get("images_ko") or []) + (ex.get("detail_images_ko") or []))
