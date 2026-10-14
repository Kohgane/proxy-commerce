"""Y9(오너 2026-10-13) — 상세 이미지 번역을 갤러리와 같은 텐센트 본선으로 · 입력 정규화 · 판촉/스토어 UI 제외 · 순서·상한 · IP.

재현 상품: VRSUK 라운지체어 `4ebaf1b8` 운영 저장값(`tests/fixtures/y9_4ebaf1b8_extra.json` — 상세 28장 · 옛 D3 결과).
흉내 낸 것: 텐센트 호출(`tc.translate_image`)·원본 받기(`tc.fetch_image`)·OCR 사전판정. 정규화(Pillow)·분류·배열은 실제 코드.
"""
from __future__ import annotations

import io
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "y9_4ebaf1b8_extra.json")


def _ex():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


def _img(fmt="JPEG", size=(400, 400), color=(200, 30, 30), **kw):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt, **kw)
    return buf.getvalue()


# ── 8. 28장 분류표 ─────────────────────────────────────────────────────────────────────────

def test_8_table_of_28_from_stored_values():
    from src.services import detail_image_plan as P
    rows = P.table(_ex())
    assert len(rows) == 28
    ex = {r["no"]: r["reason"] for r in rows if r["use"] == "excluded"}
    assert set(ex) == {2, 5, 7, 10, 11, 12, 18, 28}
    assert ex[2] == "작은 아이콘·로고(120×60)" and ex[28] == "빈 칸 이미지(스페이서 1px)"
    assert ex[5].startswith("판촉·스토어 문구(88VIP") and "天猫国际" in ex[11] and "好评率" in ex[18]
    # 옛 D3 결과(글자만 지운 그림)는 여기선 아직 「번역」으로 남는다 — 텐센트 본선이 다시 돌면 바뀐다(아래 enqueue 테스트)
    assert [r["no"] for r in rows if r["use"] == "translated"] == [8, 17, 21, 24]
    assert sum(1 for r in rows if r["outbound_pos"]) == 20                       # 28 − 제외 8 = 20(상한과 같음)
    assert rows[0]["url"].startswith("https://img.alicdn.com/") and rows[0]["url"].endswith(".jpg")   # `//…jpg_1200x1200q30.jpg_.webp`


def test_5_order_story_back_and_cap_20():
    from src.services import image_translate_store as S
    ex = {"detail_images": [f"https://img.alicdn.com/imgextra/d{i}.jpg" for i in range(25)],
          "detail_images_ko": [{"idx": 1, "status": "done", "use": True, "url": "https://cdn/x1.jpg",
                                "source_text": "设计团队 致敬 品牌故事", "target_text": "디자인 팀"},
                               {"idx": 2, "status": "done", "use": True, "url": "https://cdn/x2.jpg",
                                "source_text": "尺寸 63 cm 82 cm 材质", "target_text": "치수"}]}
    out = S.effective_images(ex, kind="detail")
    assert len(out) == 20                                                         # 상한 20 — 뒤에서 자름
    assert out[0].endswith("d0.jpg") and out[1] == "https://cdn/x2.jpg"           # 치수표는 제자리(앞)
    assert "https://cdn/x1.jpg" not in out                                        # 브랜드 이야기는 맨 뒤로 → 20장 밖으로


def test_8_pleats_unchanged():
    """대조 — 판촉·스토어 글자 없는 평범한 상세(옛 계약): 나가는 목록 = 원본 그대로."""
    from src.services import image_translate_store as S
    urls = [f"https://img.alicdn.com/imgextra/i1/ae9cee70/p{i}.jpg" for i in range(8)]
    assert S.effective_images({"detail_images": list(urls)}, kind="detail") == urls


# ── 2. 입력 정규화 ───────────────────────────────────────────────────────────────────────────

def test_2_webp_and_gif_become_jpeg():
    from PIL import Image
    from src.services import detail_image_plan as P
    data, info = P.prepare_for_tencent(_img("WEBP"))
    assert data[:2] == b"\xff\xd8" and info["converted"] and info["fmt"] == "WEBP"
    frames = [Image.new("RGB", (300, 300), c) for c in ((0, 200, 0), (0, 0, 200))]
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    data, info = P.prepare_for_tencent(buf.getvalue())
    im = Image.open(io.BytesIO(data))
    r, g, b = im.convert("RGB").getpixel((150, 150))
    assert im.format == "JPEG" and g > 150 and b < 80                           # 첫 프레임(초록)
    raw = _img()
    assert P.prepare_for_tencent(raw)[0] is raw                                   # 이미 한도 안 JPEG는 그대로(재인코딩 0)


def test_2_long_side_and_4mb_limits():
    from PIL import Image
    from src.services import detail_image_plan as P
    data, info = P.prepare_for_tencent(_img("PNG", size=(5000, 600)))
    assert max(Image.open(io.BytesIO(data)).size) <= 4096 and info["converted"]
    noise = Image.frombytes("RGB", (2400, 2400), os.urandom(2400 * 2400 * 3))
    buf = io.BytesIO()
    noise.save(buf, "PNG")
    assert len(buf.getvalue()) > P.TENCENT_MAX_BYTES
    data, info = P.prepare_for_tencent(buf.getvalue())
    assert data and len(data) <= P.TENCENT_MAX_BYTES and data[:2] == b"\xff\xd8"


def test_2_url_fixes():
    from src.services import detail_image_plan as P
    assert P.fix_url("//img.alicdn.com/a/O1!!1.jpg_1200x1200q30.jpg_.webp") == "https://img.alicdn.com/a/O1!!1.jpg"
    assert P.fix_url("https://gw.alicdn.com/i1/x-2-tps-120-60.png_.webp") == "https://gw.alicdn.com/i1/x-2-tps-120-60.png"
    assert P.fix_url("https://example.com/a.jpg_x.webp") == "https://example.com/a.jpg_x.webp"   # 알리 CDN만


# ── 1·3. 텐센트 본선 한 장 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def tencent(monkeypatch):
    from src.services import image_translate_tencent as tc
    from src.services import image_text_precheck as precheck
    from src.services import image_translate_store as istore
    monkeypatch.delenv("IMAGE_TRANSLATE_D3", raising=False)
    calls = {"fetch": [], "send": [], "answer": None}
    raw = {"data": _img("WEBP")}
    monkeypatch.setattr(tc, "fetch_image", lambda url: (calls["fetch"].append(url) or raw["data"], ""))
    monkeypatch.setattr(precheck, "han_text", lambda b: (None, ""))

    def fake(*, url="", data=b"", mode=0, **kw):
        calls["send"].append(data)
        return calls["answer"] or {"ok": True, "vendor": "tencent", "ms": 900, "image_b64": "aGk=", "lines": [{"source": "加厚", "target": "두꺼운"}],
                                   "source_text": "加厚", "target_text": "두꺼운"}
    monkeypatch.setattr(tc, "translate_image", fake)
    monkeypatch.setattr(istore, "store_translated", lambda *a, **k: {"url": "https://res.cloudinary.com/x/p.jpg", "stored_by": "cdn", "bytes": 10})
    return calls, raw


def test_1_detail_goes_to_tencent_mainline_with_jpeg(tencent):
    from src.services import image_translate_auto as A
    calls, _raw = tencent
    e = A.translate_page("//img.alicdn.com/a/O1!!1.jpg_1200x1200q30.jpg_.webp", idx=0, kind="detail", item_id="i", seller_id="u")
    assert calls["fetch"] == ["https://img.alicdn.com/a/O1!!1.jpg"]               # 스킴·webp 꼬리 고친 주소로 받는다
    assert calls["send"][0][:2] == b"\xff\xd8"                                    # webp → JPEG로 보낸다(InvalidParameterValue.Data 원인)
    assert e["status"] == "done" and e["vendor"] == "tencent" and e["use"] is True and e["input_note"].startswith("WEBP → JPEG")
    assert e["target_text"] == "두꺼운"                                             # 한국어가 들어간 결과(글자 지우기만 아님)


def test_3_picture_without_text_is_original_not_failure(tencent):
    from src.services import image_translate_auto as A
    calls, _ = tencent
    calls["answer"] = {"ok": False, "vendor": "tencent", "ms": 600, "error_class": "TencentCloudSDKException",
                       "error_code": "UnsupportedOperation.PictureWithoutText", "error_message": "翻译失败，输入为无文本图片。"}
    e = A.translate_page("https://img.alicdn.com/p.jpg", idx=3, kind="detail", item_id="i", seller_id="u")
    assert e["status"] == "skipped" and e["use"] is True and "원본 그대로" in e["reason"]


def test_4_promo_text_marks_exclusion_and_spacer_never_sent(tencent):
    from src.services import image_translate_auto as A
    calls, _ = tencent
    calls["answer"] = {"ok": True, "vendor": "tencent", "ms": 900, "image_b64": "aGk=", "lines": [{}] * 3,
                       "source_text": "天猫国际权威认可 新锐品牌奖 VRSUK海外旗舰店", "target_text": "티몰 국제"}
    e = A.translate_page("https://img.alicdn.com/award.jpg", idx=10, kind="detail", item_id="i", seller_id="u")
    assert e["status"] == "done" and e["exclude"].startswith("스토어·수상 배너(")
    n = len(calls["fetch"])
    e2 = A.translate_page("https://g.alicdn.com/s.gif", idx=27, kind="detail", item_id="i", seller_id="u")
    assert e2["status"] == "excluded" and len(calls["fetch"]) == n                # 스페이서는 받지도 보내지도 않는다


def test_1_stored_d3_results_are_requeued_for_tencent(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.services import image_translate_auto as A
    from src.services import image_translate_tencent as tc
    q.reset_for_tests()
    monkeypatch.delenv("IMAGE_TRANSLATE_D3", raising=False)
    monkeypatch.setattr(tc, "is_configured", lambda: True)
    monkeypatch.setattr(A, "kick", lambda: None)
    ex = _ex()
    ex["images"] = [f"https://img.alicdn.com/g{i}.jpg" for i in range(5)]
    n = A.enqueue_after_enrich("u", "4ebaf1b8", "https://detail.tmall.com/item.htm?id=1", ex)
    jobs = [(r["kind"], r["idx"]) for r in q._MEM_Q if r["item_id"] == "4ebaf1b8"]
    detail = sorted(i + 1 for k, i in jobs if k == "detail")
    # Y11-C(오너 2026-10-14): 판촉·스토어 배너로 읽힌 장(5·7·10·11·12·18)과 옛 D3 「그릴 줄 없음」도 **보낸다**(번역 → 상자 → 편집 대상,
    #   등록 제외는 편집 뒤 Y10 결정). 빼는 건 아이콘·스페이서(2·28)·중복뿐 — 그래서 상세 26장.
    assert detail == [i for i in range(1, 29) if i not in (2, 28)]
    assert {5, 7, 10, 11, 12, 18} <= set(detail)
    assert n == len(detail) + 5
    q.reset_for_tests()


def test_3_old_d3_no_draw_record_is_a_translation_failure_not_no_text():
    """Y11-C(오너 2026-10-14): 「글자 없는 사진」은 텐센트 PictureWithoutText일 때만. 옛 D3 「그릴 줄이 없습니다」는 글자가 있어도
    났다(VRSUK 상세 4번 쿠폰 — 다시 보내니 상자 34개) → 「번역 실패 — 원본으로」(등록은 원본 사진으로, 막지 않음)."""
    from src.services import detail_image_plan as P
    ex = _ex()
    rows = {r["no"]: r for r in P.table(ex)}
    assert rows[3]["use"] == "failed" and "그릴 줄이 없습니다" in rows[3]["reason"] and "글자 없는 사진" not in rows[3]["reason"]
    pwt = {"idx": 2, "status": "failed", "error_code": "UnsupportedOperation.PictureWithoutText", "error_message": "翻译失败，输入为无文本图片。"}
    assert P.verdict(pwt, "https://img.alicdn.com/x.jpg") == {"use": "original", "reason": "글자 없는 사진 — 원본 그대로",
                                                               "section": P.verdict(pwt, "https://img.alicdn.com/x.jpg")["section"]}
    ocr = {"status": "skipped", "reason": "글자 없는 사진(OCR 판정 — 한자 0) — 원본 그대로 · 읽은 글자 「VRSUK」"}
    assert P.verdict(ocr, "https://img.alicdn.com/x.jpg")["reason"].startswith("중국어 글자 없음(OCR 판정")   # 옛 문구도 바로잡아 보여 준다


def test_4_include_anyway_queues_that_detail_page(monkeypatch):
    """판촉 배너라 번역을 안 보냈던 장 — 「그래도 넣기」면 번역 줄에 들어간다(그 장만)."""
    from src.db import image_translate_queue_pg as q
    from src.services import image_translate_auto as A
    from src.services import image_translate_tencent as tc
    from src.seller_console import collect_history_store as S
    from src.order_webhook import app
    q.reset_for_tests()
    monkeypatch.delenv("IMAGE_TRANSLATE_D3", raising=False)
    monkeypatch.setattr(tc, "is_configured", lambda: True)
    monkeypatch.setattr(A, "kick", lambda: None)
    ex = _ex()
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=4", seller_id="y9-inc", title="x",
                   price="1", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "y9-inc"
    d = c.post(f"/seller/collect/{iid}/image-promo", json={"kind": "detail", "idx": 4, "include": True}).get_json()
    assert d["ok"] and d["queued"] >= 1
    sent = sorted(i + 1 for r in q._MEM_Q if r["item_id"] == iid for i in [r["idx"]] if r["kind"] == "detail")
    assert 5 in sent                                                            # 켠 5번이 번역 줄에 있다(Y11-C부터 다른 배너도 번역은 보낸다)
    q.reset_for_tests()


# ── 6. 사전검증 카드 진행 ─────────────────────────────────────────────────────────────────────

def test_6_progress_line_counts_pending(monkeypatch):
    from src.db import image_translate_queue_pg as q
    import src.seller_console.views as V
    q.reset_for_tests()
    ex = _ex()
    q.enqueue("u", "it-p", [("detail", i) for i in range(5)])
    p = V._detail_translate_progress("it-p", ex)
    assert p["total"] == 28 and p["pending"] == 5 and p["done"] == 4              # 옛 D3 장은 안 셈 · 텐센트 실패 2장 + 주소로 뺀 2장
    q.reset_for_tests()


# ── 7. IP·상표: 본문·사진 속 글자까지 ─────────────────────────────────────────────────────────

def test_7_replica_in_image_ocr_and_body_holds():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    import src.seller_console.views as V
    ex = _ex()
    pd = {"title": "라운지 체어", "title_ko": "라운지 체어", "price": 100, "images": ["https://img.alicdn.com/a.jpg"],
          "image_ocr_text": V._ocr_text_of(ex), "description": "Vitra 스타일 라운지 체어"}
    h = [x for x in UploadDispatcher.readiness_holds(pd, "elevenst") if x["fix"] == "trademark"]
    assert h and "임스" in h[0]["short"] and "비트라" in h[0]["short"]
    assert "사진 속 글자(임스)" in h[0]["line"] and "본문(비트라)" in h[0]["line"]
    clean = {**pd, "image_ocr_text": "", "description": "북유럽 라운지 체어"}
    assert not [x for x in UploadDispatcher.readiness_holds(clean, "elevenst") if x["fix"] == "trademark"]
