"""Z3-2(오너 2026-10-04) — 이미지 번역: 무료 로컬 OCR 사전판정 · 월 예산(계정 전체 $200) · 건당 16장 · 진단 한 줄.

실측: 지금 코드는 `ImageTranslateLLM` **Mode 0(pro, $0.04)**만 불렀다(SDK 3.1.129 문서: 0=pro · 1=lite).
운영 큐 20장 중 14장이 「그릴 줄 없음」 — 돈 내고 「글자 없음」을 들은 장이다.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def fresh(monkeypatch):
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    monkeypatch.delenv("TENCENT_TMT_MODE", raising=False)
    monkeypatch.delenv("TENCENT_IMAGE_MONTHLY_BUDGET_USD", raising=False)
    return monkeypatch


def _wire(monkeypatch, *, has_han, ok=True):
    monkeypatch.setenv("IMAGE_OCR_PRECHECK", "1")
    from src.services import image_text_precheck as P
    from src.services import image_translate_tencent as tc
    calls = []
    monkeypatch.setattr(tc, "fetch_image", lambda url: (b"jpgbytes", ""))
    monkeypatch.setattr(P, "han_text", lambda raw: (has_han, "加厚" if has_han else ""))

    def fake_translate(url="", data=b"", mode=0, **kw):
        calls.append(mode)
        return {"ok": ok, "lines": [], "ms": 10}
    monkeypatch.setattr(tc, "translate_image", fake_translate)
    return calls


def test_no_han_by_local_ocr_never_calls_tencent(fresh):
    from src.services import image_translate_auto as A, image_translate_budget as B
    calls = _wire(fresh, has_han=False)
    e = A.translate_page("https://img.alicdn.com/x.jpg", idx=0, kind="gallery", item_id="i", seller_id="u")
    assert calls == [] and e["status"] == "skipped" and "로컬 판정" in e["reason"]
    assert B.ledger()["skip_ocr"] == 1 and B.ledger()["calls"] == 0


def test_unknown_local_verdict_still_sends(fresh):
    """모르면(엔진 없음) 예전처럼 보낸다 — 「없음」으로 치면 한자가 남은 사진이 나간다."""
    from src.services import image_translate_auto as A, image_translate_budget as B
    calls = _wire(fresh, has_han=None)
    A.translate_page("https://img.alicdn.com/x.jpg", idx=0, kind="gallery", item_id="i", seller_id="u")
    assert calls == [0] and B.ledger()["calls"] == 1 and abs(B.ledger()["usd"] - 0.04) < 1e-9


def test_monthly_budget_stops_sending_but_not_registering(fresh):
    from src.services import image_translate_auto as A, image_translate_budget as B
    fresh.setenv("TENCENT_IMAGE_MONTHLY_BUDGET_USD", "0.05")
    calls = _wire(fresh, has_han=True)
    A.translate_page("u1", idx=0, kind="gallery", item_id="i", seller_id="u")           # $0.04
    e = A.translate_page("u2", idx=1, kind="gallery", item_id="i", seller_id="u")       # $0.08 > $0.05 → 안 보냄
    assert calls == [0] and e["status"] == "skipped" and "예산 소진" in e["reason"] and "원본으로 등록" in e["reason"]
    assert B.ledger()["skip_budget"] == 1


def test_lite_mode_is_cheaper_and_sent_as_mode_1(fresh):
    from src.services import image_translate_auto as A, image_translate_budget as B
    fresh.setenv("TENCENT_TMT_MODE", "1")
    calls = _wire(fresh, has_han=True)
    A.translate_page("u", idx=0, kind="gallery", item_id="i", seller_id="u")
    assert calls == [1] and abs(B.ledger()["usd"] - 0.02) < 1e-9 and B.ledger()["lite"] == 1


def test_per_item_cap_16(fresh):
    from src.services import image_translate_auto as A, image_translate_tencent as tc
    fresh.setattr(tc, "is_configured", lambda: True)
    fresh.setattr(A, "kick", lambda: None)
    extra = {"images": [f"g{i}" for i in range(9)], "detail_images": [f"d{i}" for i in range(14)]}
    n = A.enqueue_after_enrich("u", "item-cap", "https://item.taobao.com/item.htm?id=1", extra)
    assert n == 16                                        # 대표1+갤러리5(0~5) + 상세10


def test_status_line_for_diagnostics(fresh):
    from src.services import image_translate_budget as B
    B.record_call(0, True)
    B.record_call(0, True)
    B.record_skip("ocr")
    line = B.status_line()
    assert line.startswith("이미지 번역 이번 달(") and "2장 / $0.08" in line and "상한 $200" in line
    assert "로컬 판정으로 안 보냄 1장" in line and "청구서가 정본" in line


def test_diagnostics_pages_render(fresh):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics").get_data(as_text=True)
    assert 'data-role="image-budget"' in h and "이미지 번역 이번 달" in h
    h = c.get("/admin/diagnostics/ocr-precheck").get_data(as_text=True)
    assert 'data-role="ocr-summary"' in h and "글자 있는 장" in h
    h = c.get("/admin/diagnostics/image-mode-compare").get_data(as_text=True)
    assert "유료 약 $0.30" in h


def test_local_ocr_reads_han_from_bytes(monkeypatch):
    pytest.importorskip("rapidocr_onnxruntime")
    monkeypatch.setenv("IMAGE_OCR_PRECHECK", "1")
    import io
    from PIL import Image, ImageDraw, ImageFont
    from src.services import image_text_precheck as P
    font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    import os
    if not os.path.exists(font):
        pytest.skip("CJK 글꼴 없음")
    im = Image.new("RGB", (600, 300), "white")
    ImageDraw.Draw(im).text((20, 100), "加厚记忆棉", font=ImageFont.truetype(font, 48), fill="black")
    b = io.BytesIO(); im.save(b, "JPEG")
    assert P.han_text(b.getvalue())[0] is True
    b2 = io.BytesIO(); Image.new("RGB", (600, 300), "gray").save(b2, "JPEG")
    assert P.han_text(b2.getvalue())[0] is False
