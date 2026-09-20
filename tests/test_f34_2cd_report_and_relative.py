"""F34-2c·d 계약 — 결과가 어느 상품인지 말한다 · 상대 경로는 소스 페이지로 푼다.

## 실측 (오너 2026-09-20)

**c)** 「지금 올리기」 결과가 **「상세 1번째 · 올림」 ×3**이었다 — **어느 상품인지 알 수 없었다.**
   그리고 요약은 「올림 2」인데 **아래 표는 전부 「아직 없음」**이었다.

**d)** 「호스트 미상」으로 실패한 장이 있었다 — 사이트 상대 경로(`/img/a.jpg`)다.

## c) 두 가지

1. `item_id`는 결과에 실려 있었지만 **사람이 읽는 이름이 아니다.** 제목 앞 20자를 붙인다.
2. 표는 **페이지를 열 때 서버가 그린 것**이라 이 응답을 모른다 — 두 화면이 서로를 반박한다
   (F34-2의 모양). 올린 게 있으면 **표를 다시 그린다.**

## d) 발명과 참조는 다르다

F34-2b에선 상대 경로를 「호스트 미상」으로 뒀다 — 호스트를 **지어내면 안 되니까**.
그런데 **지어낼 필요가 없었다**: 그 이미지가 실려 있던 페이지 주소가 수집 시점에
저장돼 있다(행의 `url`). 브라우저가 그 페이지에서 하는 일과 **같은 계산**이다.

> ★ **호스트를 만들어 내는 건 발명이고, 그 이미지가 있던 페이지를 기준으로 푸는 건 참조다.**

소스 페이지 주소가 **없을 때만** 「못 편다」다 — 그땐 정말 모른다.

라이브 호출 0.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

CDN = "https://res.cloudinary.com/x/image/upload/v1/o.jpg"
PAGE = "https://detail.tmall.com/item.htm?id=617129397971"


# ---------------------------------------------------------------------------
# d) 상대 경로 — 소스 페이지 기준으로 편다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,base,expect", [
    ("/img/a.jpg", PAGE, "https://detail.tmall.com/img/a.jpg"),
    ("img/a.jpg", "https://x.example/p/1.html", "https://x.example/p/img/a.jpg"),
    ("../a.jpg", "https://x.example/p/q/1.html", "https://x.example/p/a.jpg"),
    # 절대·스킴상대는 base가 있어도 그대로다(기존 규칙 불변).
    ("//img.example.com/a.jpg", PAGE, "https://img.example.com/a.jpg"),
    ("https://img.example.com/a.jpg", PAGE, "https://img.example.com/a.jpg"),
])
def test_a_relative_path_resolves_against_the_source_page(raw, base, expect):
    """★★ **F34-2d의 판정 지점** — 브라우저가 그 페이지에서 하는 계산과 같다."""
    from src.services.image_cdn_backfill import normalize_outward
    assert normalize_outward(raw, base) == expect


def test_without_a_source_page_we_still_refuse():
    """★ 기준이 없으면 **정말 모른다** — 호스트를 지어내지 않는다(F34-2b 규율 유지)."""
    from src.services.image_cdn_backfill import normalize_outward
    assert normalize_outward("/img/a.jpg") == ""
    assert normalize_outward("/img/a.jpg", "not-a-url") == ""


def test_the_failure_sentence_says_what_was_missing():
    """못 폈으면 **무엇이 없어서**인지 말한다 — 「호스트 미상」만으론 손쓸 데를 모른다."""
    from src.services.image_cdn_backfill import fetch_original
    raw, err = fetch_original("/img/a.jpg")
    assert raw == b"" and "소스 페이지 주소도 없습니다" in err, err


def test_the_backfill_passes_the_rows_own_url():
    """★★ 기준은 **그 상품의** 페이지다 — 다른 상품 주소로 풀면 엉뚱한 이미지를 받는다."""
    from src.services import image_cdn_backfill as BF
    seen = {}

    def _fetch(url, *, timeout=15, base_url=""):
        seen["url"], seen["base"] = url, base_url
        return b"bytes", ""

    item = {"id": "it-1", "title": "수행방패", "url": PAGE,
            "extra_json": json.dumps({"images": [], "detail_images": ["/img/a.jpg"]})}
    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "fetch_original", side_effect=_fetch), \
         patch.object(BF, "_upload", return_value=(CDN, "")), \
         patch("src.seller_console.collect_history_store.update", return_value=True):
        out = BF.run_originals([item])
    assert seen["base"] == PAGE, seen
    assert out["uploaded"] == 1


def test_it_falls_back_to_the_draft_url_when_the_row_has_none():
    """행에 주소가 없으면 초안에서 꺼낸다 — `draft_url` 한 자리(F39/F40 규율)."""
    from src.services import image_cdn_backfill as BF
    seen = {}

    def _fetch(url, *, timeout=15, base_url=""):
        seen["base"] = base_url
        return b"b", ""

    item = {"id": "it-2", "title": "t", "url": "",
            "extra_json": json.dumps({"final_url": PAGE,
                                      "images": [], "detail_images": ["/img/a.jpg"]})}
    with patch.object(BF, "cdn_ready", return_value=True), \
         patch.object(BF, "fetch_original", side_effect=_fetch), \
         patch.object(BF, "_upload", return_value=(CDN, "")), \
         patch("src.seller_console.collect_history_store.update", return_value=True):
        BF.run_originals([item])
    assert seen["base"] == PAGE


# ---------------------------------------------------------------------------
# c) 결과가 어느 상품인지 말한다
# ---------------------------------------------------------------------------

def test_the_backfill_result_carries_the_product_title(monkeypatch):
    """★★ **F34-2c의 판정 지점** — 「상세 1번째 · 올림」이 어느 상품인지 보인다."""
    import src.seller_console.views as V

    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app

    LONG = "수행방패 접이식 차량용 책상 대형 원목 프레임 화이트"   # 20자보다 길다(컷이 실제로 걸린다)
    rows = [{"id": "it-1", "title": LONG, "extra_json": "{}"}]
    with patch.object(V, "_require_real_admin", lambda: None), \
         patch("src.services.image_cdn_backfill.run",
               return_value={"ok": True, "uploaded": 1, "failed": 0, "skipped": 0,
                             "results": [{"item_id": "it-1", "kind": "detail", "idx": 0,
                                          "ok": True, "error": ""}]}), \
         patch("src.services.image_cdn_backfill.run_originals",
               return_value={"ok": True, "uploaded": 0, "failed": 0, "results": []}), \
         patch("src.seller_console.collect_history_store.list_items",
               return_value=rows), \
         patch.object(V, "_seller_identities", lambda: {"u1"}):
        app.config["TESTING"] = True
        c = app.test_client()
        with c.session_transaction() as s:
            s["user_id"] = "u1"
            s["user_email"] = "a@b.c"
        r = c.post("/seller/admin/image-storage/backfill")
    body = r.get_json()
    assert body["results"][0]["title"] == LONG[:20], body
    assert len(body["results"][0]["title"]) == 20, "20자 컷이 안 걸렸다"


def test_an_unknown_item_gets_an_empty_title_not_a_guess(monkeypatch):
    """★ 제목을 못 찾으면 **빈 문자열**이다 — 「(제목 없음)」 같은 말을 지어내지 않는다."""
    import src.seller_console.views as V

    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app

    with patch.object(V, "_require_real_admin", lambda: None), \
         patch("src.services.image_cdn_backfill.run",
               return_value={"ok": True, "uploaded": 0, "failed": 1, "skipped": 0,
                             "results": [{"item_id": "없는id", "kind": "gallery",
                                          "idx": 0, "ok": False, "error": "x"}]}), \
         patch("src.services.image_cdn_backfill.run_originals",
               return_value={"ok": True, "uploaded": 0, "failed": 0, "results": []}), \
         patch("src.seller_console.collect_history_store.list_items",
               return_value=[]), \
         patch.object(V, "_seller_identities", lambda: {"u1"}):
        app.config["TESTING"] = True
        c = app.test_client()
        with c.session_transaction() as s:
            s["user_id"] = "u1"
            s["user_email"] = "a@b.c"
        r = c.post("/seller/admin/image-storage/backfill")
    assert r.get_json()["results"][0]["title"] == ""


def test_the_screen_prints_the_title():
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1]
           / "src/seller_console/templates/image_storage_diag.html").read_text(encoding="utf-8")
    assert "r.title ? r.title + ' · ' : ''" in tpl


def test_the_table_is_redrawn_after_a_successful_backfill():
    """★★ 요약은 「올림 2」인데 표는 「아직 없음」이었다 — 두 화면이 서로를 반박했다."""
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1]
           / "src/seller_console/templates/image_storage_diag.html").read_text(encoding="utf-8")
    assert "location.reload()" in tpl
    assert "(d.uploaded || 0) > 0" in tpl, "아무것도 안 올렸는데도 새로고침하면 사유를 잃는다"
