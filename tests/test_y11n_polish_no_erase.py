"""Y11-N(오너 2026-10-15) — 다듬기는 지우지 않는다 · 타일 최신 · 잔여 잉크 폴백 · 겹친 상자 묶음 · 외국어 번역 · 직역 금지.

운영 실측(VRSUK 4ebaf1b8, 10-15 00:28 UTC 다듬기):
- AI 「빈칸」 답을 지우기로 적용한 장 14개(쿠폰 상세 4 = 16상자, 6번 「톱1」 등) — 6번은 「톱」 윗부분만 지워져 「ㅂ1」이 남았다.
- 상세 타일·등록 페이로드: DB `url` = 다듬음 편집본 주소(전 장 일치) — 타일이 옛 렌더였던 건 서랍을 열 때 받은 판정표를 다듬기 뒤에 안 다시 읽어서.
- 22번 좌하단 세 줄: 텐센트 판이 겹친 자리에 원문 획(유령)이 남음.
"""
from __future__ import annotations

import io
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "y11m")
D4 = json.load(open(os.path.join(FIX, "vrsuk_d4_d6_polish.json"), encoding="utf-8"))
BOXES = json.load(open(os.path.join(FIX, "vrsuk_d21_d22_boxes.json"), encoding="utf-8"))


@pytest.fixture(autouse=True)
def _fresh():
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    yield
    q.reset_for_tests()


def _img(n):
    return open(os.path.join(FIX, f"vrsuk_d{n}_tencent.jpg"), "rb").read()


def _ai(monkeypatch, reply=lambda p: json.dumps({"boxes": []})):
    from src.ai import llm
    seen = []
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda prompt, **k: seen.append(prompt) or {"text": reply(prompt)})
    return seen


def _coupon_entry(i="3", exclude="판촉·스토어 문구(88VIP, 消费券, 优惠券, 加补券)"):
    """운영 그대로 — AI 「빈칸」 답을 지우기로 적용한 옛 다듬음 버전이 지금 버전."""
    d = D4[i]
    rows = [{"id": f"t{k}", "src": b["src"], "tgt": b["tgt"], "ai": d["ai"][f"t{k}"], "ko": b["tgt"],
             "from": "polish" if d["ai"][f"t{k}"] in ("",) or d["ai"][f"t{k}"] != b["tgt"] else "tencent", "why": ""}
            for k, b in enumerate(d["boxes"])]
    erase = [{"id": r["id"], "action": "erase"} for r in rows if r["ai"] == ""]
    e = {"idx": int(i), "kind": "detail", "status": "done", "use": True, "vendor": "tencent",
         "url": "https://res.cloudinary.com/x/edit/old.jpg", "translated_url": "https://res.cloudinary.com/x/t.jpg",
         "box_size": d["size"], "box_frame": "identity", "boxes": [dict(b) for b in d["boxes"]], "current": "edit:1",
         "edits": [{"n": 1, "url": "https://res.cloudinary.com/x/edit/old.jpg", "base_key": "translated", "by": "polish", "ready": True,
                    "render": "local", "render_v": 2, "ops": erase}],
         "polish": {"rows": rows, "pv": "y11l-1", "at": "2026-10-15T00:28:00+00:00"}}
    if exclude:
        e["exclude"] = exclude                                                   # 운영 그대로 — 판촉·스토어 문구로 등록 제외
    return {"title_ko": "VRSUK 리클라이너 오일 왁스 가죽", "detail_images": [f"https://img/d{k}.jpg" for k in range(28)],
            "detail_images_ko": [e]}


# ── 1. 다듬기는 지우지 않는다 — AI 「빈칸」은 지우기 제안 · 이미 지운 장은 번역본에서 다시(캐시) ─────────────────────

def test_polish_never_erases_blank_answer_is_a_suggestion(monkeypatch):
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = {"title_ko": "VRSUK 리클라이너", "images": ["https://img/g0.jpg"], "images_ko": [{
        "idx": 0, "status": "done", "use": True, "url": "https://res.cloudinary.com/x/t0.jpg", "translated_url": "https://res.cloudinary.com/x/t0.jpg",
        "box_size": [800, 800], "box_frame": "identity",
        "boxes": [{"x": 10, "y": 10, "w": 300, "h": 40, "src": "88VIP专属消费券", "tgt": "88VIP 전용 소비 쿠폰"},
                  {"x": 10, "y": 100, "w": 300, "h": 40, "src": "软糯Q弹", "tgt": "부드럽고 쫄깃한 식감"}]}]}
    _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t0", "ko": ""}, {"id": "t1", "ko": "부드럽고 탄탄한 쿠션감"}]}))
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    applied = []
    monkeypatch.setattr(IE, "apply", lambda extra, kind, idx, ops, by="user", small=None: applied.append(ops) or {"ok": True, "version": "edit:1"})
    r = P.polish_entry(ex, "gallery", 0)
    assert applied == [[{"id": "t1", "action": "text", "text": "부드럽고 탄탄한 쿠션감"}]]       # 지우기 op 0
    assert r["suggest_erase"] == 1
    row = ex["images_ko"][0]["polish"]["rows"][0]
    assert row["suggest_erase"] and row["ko"] == "88VIP 전용 소비 쿠폰" and row["from"] == "tencent"
    assert [x["tgt"] for x in IE._polish_view(ex["images_ko"][0])["rows"] if x.get("suggest_erase")] == ["88VIP 전용 소비 쿠폰"]
    assert "AI 지우기 제안 1(편집기에서 탭해야 지움)" in P.item_line("x", ex)


def test_old_erased_coupon_is_restored_from_translated_with_cache(monkeypatch):
    """쿠폰(상세 4): 옛 다듬음이 16상자를 지웠다 → 다시 누르면 그 버전을 빼고 번역본에서 다시 — 지우기 0.
    Y11N-1: 쿠폰은 **등록 제외**(판촉) — 옛 프롬프트 답도 캐시 그대로, AI 0회(안 나가는 그림에 돈 안 씀)."""
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = _coupon_entry()
    assert P.item_targets(ex) == [("detail", 3)]
    seen = _ai(monkeypatch)
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    applied = []

    def _apply(extra, kind, idx, ops, by="user", small=None):
        applied.append(ops)
        return {"ok": False, "error": "바꿀 상자가 없어요 — 기운 글자 1곳은 텐센트 글자 그대로 둬요"}
    monkeypatch.setattr(IE, "apply", _apply)
    r = P.polish_entry(ex, "detail", 3)
    e = ex["detail_images_ko"][0]
    assert seen == [] and r["calls"] == 0 and e["polish"]["outbound"] is False and e["polish"]["reask_old"] == 0
    assert not any(o["action"] == "erase" for o in applied[0])
    assert r["suggest_erase"] == 16
    assert [v["key"] for v in IE.versions(ex, "detail", 3)] == ["original", "translated"]   # 지운 버전은 빠지고 번역본(텐센트)
    assert IE.current_key(e) == "translated" and e["polish_rerender"][0]["dropped"] == ["edit:1"]


def test_outbound_photo_reasks_old_prompt_answers_and_line_says_so(monkeypatch):
    """Y11N-1: 등록에 나가는 장은 옛 프롬프트 답(6번 「모든 한 대는 편안한 의자」 같은 직역)을 새 프롬프트로 다시 묻는다."""
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = _coupon_entry("5", exclude="")
    seen = _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t1", "ko": "의자 하나하나가 편안함 그 자체"}]}))
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    applied = []
    monkeypatch.setattr(IE, "apply", lambda extra, kind, idx, ops, by="user", small=None: applied.append(ops) or {"ok": True, "version": "edit:2"})
    r = P.polish_entry(ex, "detail", 5)
    pl = ex["detail_images_ko"][0]["polish"]
    assert len(seen) == 1 and pl["outbound"] is True and pl["reask_old"] == 4 and r["cached"] == 0
    assert {"id": "t1", "action": "text", "text": "의자 하나하나가 편안함 그 자체"} in applied[0]
    assert "재질문 4상자(옛 프롬프트)" in P.item_line("x", ex)
    # 같은 판에서 답한 상자(t1)는 캐시 — 다시 안 묻는다(답 없던 상자만 다시)
    seen.clear()
    ex["detail_images_ko"][0].update(current="translated", edits=[])
    P.polish_entry(ex, "detail", 5)
    asked = [json.loads(line)["id"] for line in seen[0].splitlines() if line.startswith("{")]
    assert "t1" not in asked and ex["detail_images_ko"][0]["polish"]["reask_old"] == 0


def test_glossary_row_with_old_blank_answer_uses_glossary_without_ai(monkeypatch):
    """22번 AUTOPULENTE: 옛 답 「빈칸」(지움) → 용어집 「셀프 클리닝」(Y11M-1 결정), AI 안 부름."""
    from src.services import image_polish as P
    assert P.apply_glossary("AUTOPULENTE", "자기충전식") == "셀프 클리닝"
    seen = _ai(monkeypatch)
    box = {"id": "t10", "src": "AUTOPULENTE", "tgt": "자기충전식"}
    cache = {("AUTOPULENTE", "자기충전식"): {"ai": "", "pv": "y11l-1"}}
    r = P.polish_boxes([dict(box)], {"rule": {}}, cache=cache)
    assert not seen and r["rows"][0]["ko"] == "셀프 클리닝" and r["calls"] == 0


def test_prompt_translates_foreign_and_forbids_literal_style():
    from src.services import image_polish as P
    assert P.PROMPT_VER == "y11n-1"
    assert "중국어가 아닌 외국어" in P._SYSTEM and "AUTOPULENTE → 셀프 클리닝" in P._SYSTEM and "™®" in P._SYSTEM
    assert "직역 금지" in P._SYSTEM and "한국 쇼핑몰 상품 상세 카피체" in P._SYSTEM


# ── 3. 탭 지우기 뒤 잔여 잉크 > 15% → 상자 통째로 ─────────────────────────────────────────────

def test_residual_ink_over_15_percent_falls_back_to_whole_box(monkeypatch):
    import cv2
    import numpy as np
    from src.services import image_edit as IE
    img = np.full((200, 400, 3), 245, np.uint8)
    cv2.putText(img, "TOP1", (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 4, (40, 40, 40), 12)
    counts = iter([1000, 400])                                                 # 지우기 전 1000 · 뒤 400(40%)
    monkeypatch.setattr(IE, "_ink_px", lambda *a: next(counts))
    how = IE.erase_local(cv2, np, img, (20, 20, 380, 180), strict=True)
    assert how.startswith("fill-box") and "잔여 40%" in how
    assert int(np.abs(img[20:180, 20:380].astype(int) - 245).max()) <= 2      # 상자 통째로 바탕(한 색)
    counts2 = iter([1000, 100])
    monkeypatch.setattr(IE, "_ink_px", lambda *a: next(counts2))
    img2 = np.full((200, 400, 3), 245, np.uint8)
    cv2.putText(img2, "TOP1", (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 4, (40, 40, 40), 12)
    assert "잔여" not in IE.erase_local(cv2, np, img2, (20, 20, 380, 180), strict=True)   # 10%면 획 지우기 그대로


# ── 4. 겹친 상자 묶음 — 한 색 바탕(텐센트 판)에서만 · 큰 로고·기운 글자·사진 위는 안 묶음 ─────────────────────────

def test_d22_lines_merge_and_ghost_panel_cleared_but_d21_gradient_does_not_merge():
    from src.services import image_edit as IE
    B = BOXES["21"]
    r = IE.render_local(_img(22), 1.0, [], [(B[12], "TM 360° Sveglio")], others=B)
    assert r["merged"] == 2 and r["how"] == ["fill-ghost"] and r["drawn"] == 3   # 세 줄 한 번에 지우고 한 번에 그림
    B20 = BOXES["20"]
    r2 = IE.render_local(_img(21), 1.0, [], [(B20[2], "부드럽고 탄탄한 쿠션감")], others=B20)
    assert r2["merged"] == 0 and r2["drawn"] == 1                                # 그라데이션 위 — 이웃 제목 안 건드림


def test_tilted_text_is_detected_and_polish_skips_it():
    from PIL import Image, ImageDraw
    import cv2
    import numpy as np
    from src.services import image_edit as IE
    from src.services.image_render_font import load
    im = Image.new("RGB", (600, 300), (245, 245, 245))
    layer = Image.new("RGBA", (500, 120), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((10, 20), "회원 충전 혜택", font=load(60, "bold"), fill=(30, 30, 30, 255))
    im.paste(layer.rotate(14, expand=False), (40, 90), layer.rotate(14, expand=False))
    tilt = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    up = np.full((300, 600, 3), 245, np.uint8)
    up_pil = Image.fromarray(up)
    ImageDraw.Draw(up_pil).text((50, 110), "회원 충전 혜택", font=load(60, "bold"), fill=(30, 30, 30))
    assert IE._tilted(cv2, np, tilt, (30, 60, 580, 260)) and not IE._tilted(cv2, np, cv2.cvtColor(np.array(up_pil), cv2.COLOR_RGB2BGR), (30, 60, 580, 260))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    box = {"x": 30, "y": 60, "w": 550, "h": 200, "src": "会员充值享", "tgt": "회원 충전 혜택"}
    r = IE.render_local(buf.getvalue(), 1.0, [], [(box, "회원 충전 혜택!")], others=[box], skip_tilted=True)
    assert r["tilted"] == ["회원 충전 혜택!"] and r["drawn"] == 0


# ── 2. 타일 = 등록이 보내는 주소 = 지금 다듬음 버전 ───────────────────────────────────────────

def test_detail_plan_and_payload_point_at_current_polish_version():
    from src.services import image_translate_store as S
    url = "https://res.cloudinary.com/x/image/upload/v2/proxy-commerce/edit/new.jpg"
    ex = {"detail_images": ["https://img/d0.jpg"], "detail_images_ko": [{
        "idx": 0, "status": "done", "use": True, "url": url, "translated_url": "https://res.cloudinary.com/x/t0.jpg", "current": "edit:1",
        "edits": [{"n": 1, "url": url, "by": "polish", "render": "local", "render_v": 2}]}]}
    plan = S.effective_plan(ex, kind="detail")
    assert plan[0]["translated_url"] == url and plan[0]["url"] == url
    assert S.effective_images(ex, kind="detail") == [url]


# ── Y11-N2(오너 3번 메모): 사진 위 큰 글자는 통째 메움 안 함 — 경고 + 되돌리기 ─────────────────────────────

def test_photo_box_skips_whole_fill_and_warns(monkeypatch):
    import cv2
    import numpy as np
    from src.services import image_edit as IE
    rng = np.random.default_rng(7)
    img = rng.integers(40, 220, (200, 400, 3), dtype=np.uint8)               # 사진 성분(무늬·에지 많음)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    cv2.putText(img, "TOP1", (40, 150), cv2.FONT_HERSHEY_SIMPLEX, 4, (10, 10, 10), 14)
    before = img.copy()
    counts = iter([1000, 400])
    monkeypatch.setattr(IE, "_ink_px", lambda *a: next(counts))
    how = IE.erase_local(cv2, np, img, (20, 20, 380, 180), strict=True)
    assert "사진 위" in how and not how.startswith(("fill-box", "inpaint-box"))
    assert float(np.abs(img.astype(int) - before.astype(int)).mean()) < 30      # 상자 통째로 뭉개지 않았다
    assert IE.PHOTO_WARN.startswith("이 상자는 사진 위라 지우기 품질 보장 못 함")
