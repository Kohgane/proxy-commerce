"""0-b(오너 실측 2026-09-26) — 이름표는 벤치만이 아니라 **셀러 경로에도** 붙는다.

오너가 받은 결과 2장(`xyazoygebncalnyewnxu.jpg` · `prgyknh91xdd8gxblvde.webp`)엔 이름표가 없었다.
D3-6이 벤치에만 붙였기 때문이다 — **오너가 보는 건 늘 이름 없는 쪽이었다.**

여기서는 Cloudinary로 올리는 셀러 경로를 **하나씩 실제로 돌려서** 이름표가 실리는지 잰다:
  ① 편집 화면 → 이미지 번역(텐센트)          TENCENT
  ② 크론 — 원본 저장본(내려받아 WebP로)      ORIGINAL   (← `.webp`는 여기서 나온다)
  ③ 백필 — DB에 있던 번역본을 CDN으로       TENCENT / TELEA / GEN_REMOVE(kind별)
  ④ 백필 — 원본 CDN 사본                    ORIGINAL
  ⑤ 편집 화면 「이미지 정제」                 CLEAN
"""
from __future__ import annotations

import base64
import io
import json

import pytest

from src.media.image_label import make_label, public_id, upload_opts


def test_the_label_shape_is_one_rule():
    lab = make_label("sel-20260926-010203", "it9", 2, "TENCENT", folder="seller")
    assert public_id(lab) == "sel-20260926-010203_it9_p2_TENCENT"
    assert upload_opts(lab)["folder"] == "seller"
    with pytest.raises(ValueError):
        make_label("r", "i", 0, "MYSTERY", folder="seller")


def _jpeg() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 50, 50)).save(b, format="JPEG")
    return b.getvalue()


@pytest.fixture
def captured(monkeypatch):
    """`upload_bytes`를 목으로 — **받은 이름표**를 기록하고, 이름표로 만든 주소를 돌려준다."""
    seen = []

    def _up(raw, **kw):
        seen.append(kw.get("label"))
        pid = public_id(kw["label"]) if kw.get("label") else "random"
        return {"ok": True, "secure_url": f"https://res.cloudinary.com/x/image/upload/v1/pc/{pid}.jpg"}

    monkeypatch.setattr("src.media.image_pipeline.upload_bytes", _up)
    monkeypatch.setattr("src.media.image_pipeline._cloudinary_configured", lambda: True)
    monkeypatch.setattr("src.media.image_pipeline._CDN_UPLOAD_ENABLED", True)
    return seen


def test_seller_translation_job_labels_each_page_tencent(monkeypatch, captured):
    from src.services import image_translate_job as J
    from src.services import image_translate_tencent as tc
    state = {"extra": {"images": ["https://img/a.jpg", "https://img/b.jpg"]}}
    monkeypatch.setattr(J, "_load", lambda item_id, ids: ({"id": item_id}, state["extra"]))
    monkeypatch.setattr(J, "_save", lambda item_id, ids, extra: state.update(extra=extra) or True)
    monkeypatch.setattr(tc, "translate_image",
                        lambda **kw: {"ok": True, "image_b64": base64.b64encode(_jpeg()).decode(),
                                      "lines": [], "target_text": "", "vendor": "tencent"})
    monkeypatch.setattr("src.services.image_translate_store.record_usage", lambda *a, **k: True)
    J._run("it9", "s", [0, 1], {"s"})
    assert [l["pipeline"] for l in captured] == ["TENCENT", "TENCENT"]
    assert [l["page"] for l in captured] == ["0", "1"] and all(l["item_no"] == "it9" for l in captured)
    assert all(l["folder"] == "seller" and l["run_id"].startswith("sel-") for l in captured)
    assert len({l["run_id"] for l in captured}) == 1                      # 한 번 누름 = 한 run
    urls = [e.get("url") for e in state["extra"]["images_ko"]]
    assert all("_it9_p" in u and u.endswith("_TENCENT.jpg") for u in urls), urls


def test_original_copies_are_labelled_original(monkeypatch, captured):
    """`.webp`의 출처 — 크론이 원본을 내려받아 WebP로 저장본을 만든다(`process_image`)."""
    import src.api.extension_api as ext
    from src.media import image_pipeline as P
    monkeypatch.setattr(ext, "_cdn_configured", lambda: True)
    monkeypatch.setattr(P, "_download_image", lambda url, *a, **k: _jpeg(), raising=False)
    got = []

    def _proc(url, label=None, **kw):
        got.append(label)
        from types import SimpleNamespace
        return SimpleNamespace(cdn_uploaded=True, processed_url=f"https://cdn/{public_id(label)}.webp")

    monkeypatch.setattr(P, "process_image", _proc)
    out = ext._store_image_copies(["https://img/a.jpg", "https://img/b.jpg"], item_id="it7", budget_sec=5)
    assert [l["pipeline"] for l in got] == ["ORIGINAL", "ORIGINAL"] and got[1]["page"] == "1"
    assert all(u.endswith("_ORIGINAL.webp") and "_it7_p" in u for u in out["images_stored"])


def test_process_image_passes_the_label_to_the_upload(monkeypatch, captured):
    from src.media import image_pipeline as P
    import contextlib
    monkeypatch.setattr(P, "_PIPELINE_ENABLED", True, raising=False)
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: contextlib.nullcontext(io.BytesIO(_jpeg())))
    lab = make_label("copy-x", "it7", 0, "ORIGINAL", folder="seller")
    P.process_image("https://img/a.jpg", label=lab)
    assert captured and captured[-1] == lab


def test_backfill_labels_by_kind(monkeypatch, captured):
    from src.services import image_cdn_backfill as B
    from src.db import image_ko_blobs_pg as blobs
    monkeypatch.setattr(B, "cdn_ready", lambda: True)
    monkeypatch.setattr(blobs, "pending_cdn", lambda limit=50: [
        {"item_id": "it1", "idx": 0, "kind": "gallery"}, {"item_id": "it1", "idx": 1, "kind": "d3g"}])
    monkeypatch.setattr(blobs, "get_cdn", lambda *a, **k: "")
    monkeypatch.setattr(blobs, "get", lambda *a, **k: (_jpeg(), "image/jpeg"))
    monkeypatch.setattr(blobs, "set_cdn", lambda *a, **k: True)
    monkeypatch.setattr(B, "_point_entry_at_cdn", lambda *a, **k: True)
    B.run(limit=10)
    assert [(l["pipeline"], l["folder"]) for l in captured] == [("TENCENT", "seller"), ("GEN_REMOVE", "bench")]


def test_clean_button_labels_clean_with_item_and_page(monkeypatch):
    from src.order_webhook import app
    got = []

    def _proc(url, channel="default", label=None, **kw):
        got.append(label)
        from types import SimpleNamespace
        return SimpleNamespace(to_dict=lambda: {"processed_url": url, "cdn_uploaded": False})

    monkeypatch.setattr("src.media.image_pipeline.process_image", _proc)
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-clean"
        c.post("/seller/media/process-image", json={"image_url": "https://img/a.jpg", "item_id": "it5", "idx": 3})
    assert got[0]["pipeline"] == "CLEAN" and got[0]["item_no"] == "it5" and got[0]["page"] == "3"


# ---------------------------------------------------------------------------
# 0-c — 인보이스 올린 뒤 칸이 채워지고, 다시 열어도 남는다
# ---------------------------------------------------------------------------

def test_invoice_url_is_in_the_field_after_upload_and_after_reload(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(mc, "_path", lambda sid: str(tmp_path / f"{sid}.json"))
    url = "https://res.cloudinary.com/demo/image/upload/v1/proxy-commerce/coupang-invoice/inv.pdf"
    monkeypatch.setattr("src.media.image_pipeline.upload_bytes", lambda raw, **kw: {"ok": True, "secure_url": url})
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-inv-reload"
        r = c.post("/seller/markets/connect/coupang/invoice",
                   data={"file": (io.BytesIO(b"%PDF-1.4\nx"), "inv.pdf")}, content_type="multipart/form-data")
        assert r.get_json()["secure_url"] == url
        html = c.get("/seller/markets/connect/coupang").get_data(as_text=True)
    i = html.index('name="COUPANG_INVOICE_DOCUMENT_URL"')
    field = html[html.rfind("<input", 0, i):html.index(">", i)]
    assert f'value="{url}"' in field                    # 다시 열어도 칸에 그 주소


def test_invoice_failure_shows_the_original_error_under_the_field(monkeypatch, tmp_path):
    """실패하면 **원문 오류**가 응답에 — 화면은 그걸 칸 아래(`invoice-result`)에 그대로 쓴다."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(mc, "_path", lambda sid: str(tmp_path / f"{sid}.json"))
    monkeypatch.setattr("src.media.image_pipeline.upload_bytes",
                        lambda raw, **kw: {"ok": False, "error": "Error: Invalid api_key 1234"})
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-inv-fail"
        d = c.post("/seller/markets/connect/coupang/invoice",
                   data={"file": (io.BytesIO(b"%PDF-1.4\nx"), "inv.pdf")}, content_type="multipart/form-data").get_json()
    assert d["ok"] is False and "Invalid api_key 1234" in d["error"]
