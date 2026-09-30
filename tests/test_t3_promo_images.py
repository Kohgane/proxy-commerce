"""T3(오너 2026-09-30-H) — 프로모션 이미지: OCR 글에 판촉 어휘 → 「프로모션 의심」 배지 + 등록에서 기본 제외.

캡처 좌표: VRSUK 이미지 번역 결과 「88VIP 세일 235」「국경절 축제 9.28-10.05 55% 할인」「1원에 88원 상당+증정품」.
텐센트(수동 경로)는 **그려진 이미지**를 돌려준다 — 글자는 못 고친다. 그래서 빼는 쪽으로 간다(인페인팅은 후순위).

  ① 판정은 어휘(원문·번역문 둘 다) — 「折叠(접이식)」 같은 일반어 오탐 0(운영 실측으로 잡은 결함)
  ② 등록에 나갈 배열(`effective_images`)에서 기본 제외 · 오너 「그래도 넣기」면 넣음 · 전부 판촉이면 빼지 않음
  ③ 화면 plan·요약이 같은 판정 · 토글 라우트 · 서랍 배지
  ④ 배너 모양(글자 면적·상하 띠)은 이번부터 적는다 — 기준은 실측이 쌓인 뒤
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import pytest

from src.services import image_translate_store as store

FIX = json.loads(Path("tests/fixtures/ko_polish/recent48_2026-09-30.json").read_text(encoding="utf-8"))
PROMO = {"idx": 0, "status": "done", "url": "https://cdn.example/p0.jpg", "use": True,
         "source_text": FIX["vrsuk_image0"]["source_text"], "target_text": FIX["vrsuk_image0"]["target_text"]}
PLAIN = {"idx": 1, "status": "done", "url": "https://cdn.example/p1.jpg", "use": True,
         "source_text": "十八纸风琴纸凳 折叠如书 承重 300KG", "target_text": "접이식 의자 책처럼 접힘 하중 300KG"}


@pytest.fixture(autouse=True)
def _fresh():
    from src.collectors import ko_polish as kp
    kp.reset_cache()
    yield


def _extra(*entries, n=3):
    return {"images": [f"https://img.example/{i}.jpg" for i in range(n)], "images_ko": [dict(e) for e in entries]}


def test_vocabulary_hits_and_no_folding_false_positive():
    hits = store.promo_of(PROMO)
    assert {"88VIP", "新客", "国庆", "天猫国际"} <= set(hits) and any("할인" in h or "쿠폰" in h for h in hits)
    assert store.promo_of(PLAIN) == []                                     # 折叠 = 접이식(판촉 아님)
    assert store.promo_of({"source_text": "荣登沙发椅热销榜/回购榜TOP1"})       # 순위 표기


def test_promo_page_is_excluded_by_default_and_owner_can_include():
    ex = _extra(PROMO, PLAIN)
    out = store.effective_images(ex)
    assert len(out) == 2 and "https://cdn.example/p0.jpg" not in out and out[0] == "https://cdn.example/p1.jpg"
    ex["images_ko"] = store.set_promo_include(ex, 0, True)
    assert store.effective_images(ex)[0] == "https://cdn.example/p0.jpg"
    only = _extra(PROMO, n=1)
    assert store.effective_images(only) == ["https://cdn.example/p0.jpg"]  # 전부 판촉이면 빼지 않는다


def test_plan_and_summary_say_the_same_thing():
    ex = _extra(PROMO, PLAIN)
    plan = store.effective_plan(ex)
    assert plan[0]["promo"] and plan[0]["promo_excluded"] and not plan[1]["promo"]
    sm = store.effective_summary(ex)
    assert [x["idx"] for x in sm["promo_excluded"]] == [0] and sm["promo_included"] == []


def test_toggle_route_and_drawer_badge():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=1", title="의자", price="10",
                   currency="CNY", seller_id="u-t3", extra=_extra(PROMO, PLAIN))
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-t3"
    d = c.post(f"/seller/collect/{iid}/image-promo", json={"kind": "gallery", "idx": 0, "include": True}).get_json()
    assert d["ok"] and d["plan"][0]["promo_include"] and d["summary"]["promo_included"][0]["idx"] == 0
    assert c.post(f"/seller/collect/{iid}/image-promo", json={"idx": "x"}).status_code == 400
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'data-role="imgko-promo"' in t and "그래도 넣기" in t and "kgpImgPromo(" in t and "alert(" not in t.split("function kgpImgPromo")[1].split("function ")[0]


def test_banner_geometry_is_recorded_from_now_on():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (800, 800), "white").save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    lines = [{"box": {"x": 0, "y": 0, "w": 800, "h": 100}}, {"box": {"x": 0, "y": 60, "w": 800, "h": 80}}]
    g = store.text_geometry({"lines": lines, "image_b64": b64})
    assert g == {"text_area": 0.225, "band": "top"}
    assert store.text_geometry({"lines": [], "image_b64": b64}) == {}      # 못 재면 비움(추정 0)
