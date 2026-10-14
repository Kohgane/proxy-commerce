"""Y11-H(오너 2026-10-14) — 텐센트가 사진을 180°로 오인해 한국어 머리글을 거꾸로 그린 장(휴대폰 거치대 3e72fadc 갤러리 2·3).

a. 회전 각도를 정하는 요청 칸이 있나 — SDK 요청 모델(`ImageTranslateLLMRequest`)에 Data·Target·Url·Mode뿐(없음, 아래 테스트로 고정).
b. 그래서 그 장은 원본으로 두고(`upside_down`) 편집 화면 「글자 고치기」 대상으로 표시 · 「다시 번역」은 다시 보내지 않고 결과줄에
   「거꾸로 번역 n장 — 글자 고치기로」 한 줄.
"""
from __future__ import annotations

import json

import pytest


def test_sdk_request_has_no_rotation_angle_field():
    from tencentcloud.tmt.v20180321 import models
    req = models.ImageTranslateLLMRequest()
    fields = {k.lstrip("_") for k in vars(req)}
    assert fields == {"Data", "Target", "Url", "Mode"}
    assert not {f for f in fields if "angle" in f.lower() or "rotat" in f.lower()}


def _ex():
    return {"title_ko": "핸들바 자석 휴대폰 거치대 360도 회전",
            "images": [f"https://img.alicdn.com/p{i}.jpg" for i in range(4)],
            "images_ko": [{"idx": 0, "kind": "gallery", "status": "done", "use": True, "url": "https://res.cloudinary.com/x/p0.jpg",
                           "boxes": [{"x": 1, "y": 1, "w": 500, "h": 80, "src": "强磁吸附", "tgt": "강력 자석"}], "box_size": [1600, 1600]},
                          {"idx": 1, "kind": "gallery", "status": "skipped", "use": True, "upside_down": True, "box_frame": "rot180",
                           "reason": "거꾸로 번역(텐센트가 사진을 180°로 오인) — 원본 그대로 · 머리글은 「글자 고치기」로"},
                          {"idx": 2, "kind": "gallery", "status": "skipped", "use": True, "upside_down": True, "box_frame": "rot180",
                           "reason": "거꾸로 번역(텐센트가 사진을 180°로 오인) — 원본 그대로 · 머리글은 「글자 고치기」로"},
                          {"idx": 3, "kind": "gallery", "status": "failed", "error_message": "timeout"}]}


def test_retry_does_not_resend_upside_down_and_says_so_in_one_line():
    from src.services import image_translate_auto as A
    p = A.translate_plan(_ex(), retry=True)
    assert [(k, i) for k, i, _w in p["send"]] == [("gallery", 3)]
    assert p["skip"]["upside"] == [("gallery", 1), ("gallery", 2)]
    assert A.plan_line(p, 1) == "접수 1장 · 건너뜀 1장(이미 번역 1) · 글자 없음 0장 · 거꾸로 번역 2장 — 글자 고치기로"


def test_editor_marks_upside_down_photo_as_fix_text_and_reads_original(monkeypatch):
    from src.services import image_edit as E
    seen = []
    monkeypatch.setattr(E, "_ocr_version", lambda url: seen.append(url) or {"ok": True, "size": [1600, 1600], "angle": 0.0, "boxes": [
        {"x": 300, "y": 60, "w": 1000, "h": 90, "src": "强磁吸附 稳固不掉", "tgt": "", "conf": 98.0}]})
    p = E.plan(_ex(), "gallery", 1, small=None, fetch=True)
    assert p["fix_text"] and "글자 고치기" in p["fix_note"] and not p["need_translate"]
    assert seen == ["https://img.alicdn.com/p1.jpg"] and [b["src"] for b in p["boxes"]] == ["强磁吸附 稳固不掉"]


def test_queue_worker_does_not_resend_upside_down(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.seller_console import collect_history_store as S
    from src.services import image_translate_auto as A
    q.reset_for_tests()
    monkeypatch.setattr(A, "kick", lambda: None)
    monkeypatch.setattr(A, "daily_cap", lambda: 320)
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=3", seller_id="y11h", title="x",
                   price="1", currency="CNY", extra=_ex())
    iid = iid[0] if isinstance(iid, tuple) else iid
    q.enqueue("y11h", iid, [("gallery", 1)])                                  # 예전에 줄에 선 장(낡은 줄)
    sent = []
    monkeypatch.setattr(A, "translate_page", lambda *a, **k: sent.append(k.get("idx")) or {})
    A._drain(5)
    assert sent == []
    row = next(r for r in q._MEM_Q if r["item_id"] == iid)
    assert row["status"] == "skipped" and row["reason"] == A.UPSIDE_REASON
    e1 = next(e for e in json.loads(S.get(iid, seller_ids={"y11h"})["extra_json"])["images_ko"] if e["idx"] == 1)
    assert e1["upside_down"] and e1["status"] == "skipped"
    q.reset_for_tests()


def test_ocr_failure_on_upside_down_photo_never_offers_paid_retranslation(monkeypatch):
    """캡처에서 잡힘 — OCR을 못 읽으면 「번역하고 글자 상자 받기」(1장 요금 · 또 거꾸로)를 권했다. 직접 작업 접수도 거절."""
    from src.services import image_edit as E
    from src.services import image_translate_job as job
    from src.services import image_translate_tencent as tc
    from src.seller_console import collect_history_store as S
    monkeypatch.setattr(E, "_ocr_version", lambda url: {"ok": False, "why": "텐센트 키 미설정", "boxes": [], "size": [0, 0]})
    p = E.plan(_ex(), "gallery", 1, small=None, fetch=True)
    assert not p["need_translate"] and p["fix_text"] and "읽지 못했어요" in p["why"]
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=4", seller_id="y11h-j", title="x",
                   price="1", currency="CNY", extra=_ex())
    iid = iid[0] if isinstance(iid, tuple) else iid
    monkeypatch.setattr(tc, "_cap_full", lambda: None)
    started = []
    monkeypatch.setattr(job, "_start", lambda *a: started.append(a))
    r = job.accept(iid, "y11h-j", [1, 2], seller_ids={"y11h-j"})
    assert not r["ok"] and started == [] and all("거꾸로" in s["reason"] for s in r["skipped"])
