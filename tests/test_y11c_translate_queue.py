"""Y11-C(오너 2026-10-14) — 번역 큐가 「제외 예정」 사진을 건너뛰어 편집 대상이 번역을 못 받던 것.

실측 16:07:27 KST VRSUK 4ebaf1b8 「다시 번역」: 「등록에서 빠질 8장(스페이서·아이콘·판촉 배너) 안 보냄 · 접수 4장」 → 화면은
「26장을 다시 넣었어요 · 오늘 0/320」(26 = 큐의 옛 실패 줄 수 — 그중 갤러리 1~3은 이미 번역된 장이라 덮어썼다).
재현 입력 = 운영 저장값 `tests/fixtures/y10_4ebaf1b8_extra.json`(16:07 이전 상태 — 상세 28장 · 갤러리 5장).
번호: 오너가 말한 「5·7·8번」은 화면 번호(1부터) = 상세 idx 4(88VIP 판촉)·6(热销榜 배너)·7(Eames).
"""
from __future__ import annotations

import base64
import io
import json
import os
from unittest.mock import patch

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "y10_4ebaf1b8_extra.json")


def _ex():
    with open(FIX, encoding="utf-8") as f:
        d = json.load(f)
    d.pop("_doc", None)
    return d


@pytest.fixture
def mem(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.services import image_translate_auto as A
    q.reset_for_tests()
    monkeypatch.setattr(A, "kick", lambda: None)
    yield q
    q.reset_for_tests()


def _post_retry(iid, seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c.post(f"/seller/collect/{iid}/image-translate/retry").get_json()


def _store(seller, ex):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", seller_id=seller, title="VRSUK",
                   price="7183", currency="CNY", extra=ex)
    return iid[0] if isinstance(iid, tuple) else iid


# ── 5. VRSUK 「다시 번역」 접수 목록 ──────────────────────────────────────────────────────────

def test_vrsuk_retry_accepts_main_photo_and_promo_eames_pages_and_skips_only_spacer_icon(mem):
    iid = _store("y11c", _ex())
    d = _post_retry(iid, "y11c")
    got = {(p["kind"], p["idx"]) for p in d["pages"]}
    assert ("gallery", 0) in got                                               # 대표사진(쿠폰) — 상자 없는 옛 번역본 → 다시
    assert {("detail", 4), ("detail", 6), ("detail", 7)} <= got                 # 5·7·8번(판촉·스토어 배너·Eames)
    assert ("detail", 1) not in got and ("detail", 27) not in got               # 120×60 아이콘 · 스페이서
    assert d["skipped"] == {"icon": [{"kind": "detail", "idx": 1}], "spacer": [{"kind": "detail", "idx": 27}]}
    assert d["no_text"] == [{"kind": "gallery", "idx": 4}]                      # 텐센트 PictureWithoutText만 「글자 없음」
    queued = {(r["kind"], int(r["idx"])) for r in mem._MEM_Q if r["item_id"] == iid and r["status"] == "queued"}
    assert queued == got and d["accepted"] == len(got) == 30
    assert d["message"] == "접수 30장 · 건너뜀 2장(스페이서 1 · 아이콘 1) · 글자 없음 1장 · 오늘 텐센트 호출 0/200장"
    d2 = _post_retry(iid, "y11c")                                              # 다시 눌러도 두 번 보내지 않는다
    assert d2["accepted"] == 0 and d2["waiting"] == 30 and d2["message"].startswith("접수 0장 · 이미 대기 중 30장")


def test_automatic_enqueue_no_longer_cuts_promo_banners(mem, monkeypatch):
    """1번: 자동 접수(보강 직후)도 판촉·스토어 배너로 읽힌 장을 뺐다(「8장 안 보냄」의 6장) — 이제 보낸다."""
    from src.services import image_translate_auto as A
    from src.services import image_translate_tencent as tc
    monkeypatch.setattr(tc, "is_configured", lambda: True)
    monkeypatch.delenv("IMAGE_TRANSLATE_D3", raising=False)
    plan = A.translate_plan(_ex())
    sent = {i for k, i, _w in plan["send"] if k == "detail"}
    assert {4, 6, 9, 10, 11, 17} <= sent                                       # 예전 「판촉 배너」로 잘린 6장
    assert plan["skip"]["icon"] == [("detail", 1)] and plan["skip"]["spacer"] == [("detail", 27)]


def test_duplicate_page_is_skipped_and_done_with_boxes_is_not_overwritten(mem):
    """중복 주소는 한 번만 · 이미 상자까지 받은 번역본은 「다시 번역」이 덮어쓰지 않는다(16:07 갤러리 1~3 덮어쓰기 재발 방지)."""
    from src.services import image_translate_auto as A
    ex = {"images": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/a.jpg_1200x1200q30.jpg_.webp",
                     "https://img.alicdn.com/b.jpg"],
          "images_ko": [{"idx": 2, "status": "done", "url": "https://res.cloudinary.com/x/b.jpg", "use": True,
                         "boxes": [{"x": 1, "y": 1, "w": 5, "h": 5, "src": "满减", "tgt": "할인"}], "box_size": [800, 800]}]}
    p = A.translate_plan(ex, retry=True)
    assert [(k, i) for k, i, _w in p["send"]] == [("gallery", 0)]
    assert p["skip"]["dup"] == [("gallery", 1)] and p["skip"]["done"] == [("gallery", 2)]
    assert A.plan_line(p, 1) == "접수 1장 · 건너뜀 2장(중복 1 · 이미 번역 1)"


# ── 3. 「오늘 n/상한」 = 텐센트에 실제로 보낸 수(PictureWithoutText 포함) ─────────────────────────────

class _Box:
    def __init__(self, x, y, w, h):
        self.X, self.Y, self.Width, self.Height = x, y, w, h


class _Detail:
    def __init__(self, src, tgt, box):
        self.SourceLineText, self.TargetLineText, self.BoundingBox = src, tgt, box
        self.LineHeight, self.LinesCount = 20, 1


def _jpeg(w=800, h=800):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (240, 240, 240)).save(b, "JPEG")
    return b.getvalue()


class _Pwt(Exception):
    code = "UnsupportedOperation.PictureWithoutText"
    message = "翻译失败，输入为无文本图片。"


def _cli(pwt_urls, seen):
    class _Resp:
        Source, Target, Angle, RequestId = "zh", "ko", 0, "req"

    class _Cli:
        def ImageTranslateLLM(self, req):
            seen.append(1)
            if seen and len(seen) in pwt_urls:
                raise _Pwt()
            r = _Resp()
            r.Data = base64.b64encode(_jpeg()).decode()
            r.SourceText, r.TargetText = "88VIP SALE 235 消费券", "88VIP 세일 235 쿠폰"
            r.TransDetails = [_Detail("88VIP SALE", "88VIP 세일", _Box(620, 20, 160, 40)),
                              _Detail("235 RMB 消费券", "235 위안 쿠폰", _Box(620, 62, 160, 40))]
            return r
    return _Cli()


def test_daily_counter_counts_real_calls_including_picture_without_text(mem, monkeypatch):
    from src.services import image_translate_auto as A
    from src.services import image_translate_tencent as tc
    from src.services import image_text_precheck as precheck
    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")
    monkeypatch.setattr(tc, "MIN_INTERVAL_SEC", 0.0)
    seen = []
    with patch.object(tc, "_client", lambda *_a, **_k: _cli({2}, seen)), patch.object(tc, "fetch_image", lambda u: (_jpeg(), "")):
        assert tc.translate_image(url="https://img.alicdn.com/1.jpg")["ok"]
        r = tc.translate_image(url="https://img.alicdn.com/2.jpg")                   # 두 번째 = PictureWithoutText
        assert not r["ok"] and r["error_code"] == "UnsupportedOperation.PictureWithoutText"
    assert A.status()["today"] == 2                                              # 글자 없음도 과금 — 1회로 센다
    # 보내지 않은 장(OCR 한자 0 · 스페이서)은 세지 않는다
    monkeypatch.setattr(precheck, "han_text", lambda raw: (False, "IS THAT YOU"))
    with patch.object(tc, "fetch_image", lambda u: (_jpeg(), "")):
        e = A.translate_page("https://img.alicdn.com/3.jpg", idx=3, kind="gallery", item_id="i", seller_id="u")
        x = A.translate_page("https://g.alicdn.com/s.gif", idx=27, kind="detail", item_id="i", seller_id="u")
    assert e["status"] == "skipped" and e["reason"].startswith("중국어 글자 없음(OCR 판정") and "글자 없는 사진" not in e["reason"]
    assert x["status"] == "excluded" and A.status()["today"] == 2


def test_drain_counts_like_the_vendor_and_retranslated_main_photo_has_boxes(mem, monkeypatch):
    """끝까지: 「다시 번역」 → 큐 → 텐센트(가짜 클라이언트, 실제 `translate_image`) → `images_ko[0]`에 상자 좌표가 남는다.
    큐가 상한을 세는 수 = 공급사에 보낸 수(OCR 「한자 0」으로 안 보낸 장은 0회)."""
    from src.services import image_translate_auto as A
    from src.services import image_translate_tencent as tc
    from src.services import image_text_precheck as precheck
    from src.services import image_translate_store as istore
    from src.seller_console import collect_history_store as S
    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")
    monkeypatch.setattr(tc, "MIN_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(istore, "store_translated", lambda *a, **k: {"url": "https://res.cloudinary.com/x/new.jpg", "stored_by": "cdn", "bytes": 9})
    monkeypatch.setattr(precheck, "han_text", lambda raw: (True, "消费券"))
    ex = _ex()
    ex["detail_images"], ex["detail_images_ko"] = [], []                        # 이 테스트는 갤러리만(대표사진)
    iid = _store("y11c-drain", ex)
    d = _post_retry(iid, "y11c-drain")
    assert [(p["kind"], p["idx"]) for p in d["pages"]] == [("gallery", i) for i in range(4)]
    seen = []
    with patch.object(tc, "_client", lambda *_a, **_k: _cli(set(), seen)), patch.object(tc, "fetch_image", lambda u: (_jpeg(), "")):
        n = A.run_until_idle(10)
    assert n == 4 and len(seen) == 4 and A.status()["today"] == 4
    e0 = json.loads(S.get(iid, seller_ids={"y11c-drain"})["extra_json"])["images_ko"][0]
    assert e0["status"] == "done" and e0["box_size"] == [800, 800]
    assert e0["boxes"][:2] == [{"x": 620, "y": 20, "w": 160, "h": 40, "src": "88VIP SALE", "tgt": "88VIP 세일"},
                               {"x": 620, "y": 62, "w": 160, "h": 40, "src": "235 RMB 消费券", "tgt": "235 위안 쿠폰"}]


# ── 4. 「글자 없는 사진」 = PictureWithoutText만 ─────────────────────────────────────────────────

def test_no_text_label_is_picture_without_text_only():
    from src.db import image_translate_queue_pg as q
    from src.services import detail_image_plan as P
    assert q.is_no_text("UnsupportedOperation.PictureWithoutText") and q.is_no_text("翻译失败，输入为无文本图片。")
    assert not q.is_no_text("그릴 줄이 없습니다(원본 그대로)") and not q.is_no_text("输入Data无效，请参考Data参数说明。")
    assert q.is_benign("그릴 줄이 없습니다(원본 그대로)")                         # 차단기는 예전처럼 멈추지 않는다(Y4)
    u = "https://img.alicdn.com/x.jpg"
    coupon = {"idx": 3, "status": "failed", "vendor": "d3", "error_message": "그릴 줄이 없습니다(원본 그대로)"}
    data = {"idx": 18, "status": "failed", "error_code": "InvalidParameterValue.Data", "error_message": "输入Data无效，请参考Data参数说明。"}
    assert P.verdict(coupon, u)["use"] == "failed" and P.verdict(data, u)["use"] == "failed"     # 「번역 실패 — 원본으로」
    assert "글자 없는 사진" not in P.verdict(coupon, u)["reason"]
