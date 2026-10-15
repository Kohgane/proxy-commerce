"""Y11-M(오너 2026-10-14 02:12 캡처) — 다듬기 렌더 품질.

운영 실측(VRSUK 4ebaf1b8, 16:22~16:25 UTC 다듬기):
- 21번(상세 idx 20) 큰 제목·아랫줄: Cloudinary 변환(gen_remove + 글자 오버레이)이 텐센트 글자 위에 겹쳐 그려 번졌다 · 글자색 회보라(원래 연보라/흰색).
- 진행줄 「(24/23장)」 — 13:23에 다듬은 상세 28번 기록까지 셌다.
- 22번(idx 21) 한자 상자: AI 답 「중력+ 고탄성 정형면 자체 개발 「힐딩 체감 시스템」」(한자 0)인데 「길어서 유지」로 버려 「못 고친 1」.
- 「AI 결과 버림 18」 = 길어서 유지 16 + 금지어·과장(88VIP) 1 + 다른 품목 표현(「의식감」 속 「식감」 오탐) 1 — 숫자 탈락 0.
- 「길어서 유지 16」 — 옛 기준(상자 높이의 45%)은 텐센트 자기 글자도 못 넘었다.

사진은 운영 텐센트 번역본(상세 21·22, JPEG 82로 다시 저장), 상자는 운영 DB 값.
"""
from __future__ import annotations

import io
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "y11m")
BOXES = json.load(open(os.path.join(FIX, "vrsuk_d21_d22_boxes.json"), encoding="utf-8"))


def _img(n):
    return open(os.path.join(FIX, f"vrsuk_d{n}_tencent.jpg"), "rb").read()


def _diff(a: bytes, b: bytes, box, thr=40):
    """그 상자 안에서 크게 바뀐 픽셀 비율."""
    from PIL import Image, ImageChops
    A, B = (Image.open(io.BytesIO(x)).convert("L").crop((box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"])) for x in (a, b))
    d = ImageChops.difference(A, B).point(lambda v: 255 if v > thr else 0)
    return sum(1 for v in d.getdata() if v) / float(d.size[0] * d.size[1])


@pytest.fixture(autouse=True)
def _fresh():
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    yield
    q.reset_for_tests()


# ── 1. 우리 쪽에서 지우고 그린다 — 21번(그라데이션 바탕) · 22번(흰 바탕·이웃 줄) ─────────────────────────────

def test_d21_title_is_erased_and_redrawn_in_tencent_colour_neighbours_untouched():
    from src.services import image_edit as IE
    B = BOXES["20"]
    raw = _img(21)
    r = IE.render_local(raw, 1.0, [], [(B[2], "부드럽고 탄탄한 쿠션감"), (B[7], "1:0.618 구름감 부드러움")], others=B)
    assert r["ok"] and r["drawn"] == 2 and not r["skipped"]
    assert r["how"] == ["inpaint", "inpaint"]                         # 그라데이션 바탕 — 상자를 통째 칠하지 않는다(네모 자국 방지)
    title = tuple(int(r["colors"][0][i:i + 2], 16) for i in (0, 2, 4))
    assert min(title) > 140 and title[2] > title[1]                   # 텐센트 글자색(연보라) 그대로 — 옛 렌더는 회보라 79,6d,84
    assert _diff(raw, r["bytes"], B[3]) < 0.01 and _diff(raw, r["bytes"], B[5]) < 0.01   # 「과학적 체감 지지」·「황금 과학적 배합」 그대로
    assert _diff(raw, r["bytes"], B[2]) > 0.02


def test_d22_erasing_one_box_does_not_eat_the_next_line_or_logo():
    """반례(실측): 지울 자리를 넓히다 이웃 줄 「전방위 1」 윗획·「EHILÀ」 아랫단을 먹었다.
    Y11-N: 붙은 줄(TM 360° / 전방위 1 / 자기 순환…)은 묶어서 지우고 다시 그린다 — 「전방위 1」은 사라지지 않고 다시 그려진다.
    큰 로고(EHILÀ, 원문 그대로)는 묶지도 건드리지도 않는다."""
    from src.services import image_edit as IE
    B = BOXES["21"]
    raw = _img(22)
    r = IE.render_local(raw, 1.0, [], [(B[12], "TM 360° Sveglio"), (B[6], "끊김 없음")], others=B)
    assert r["ok"] and r["merged"] >= 2
    assert _diff(raw, r["bytes"], B[1]) < 0.005                       # 「EHILÀ」
    assert _ink_ratio(r["bytes"], B[13]) > 0.6 * _ink_ratio(raw, B[13])   # 「전방위 1」 다시 그려짐(지워져 사라지지 않음)


def _ink_ratio(raw: bytes, box, thr=120):
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("L").crop((box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]))
    return sum(1 for v in im.getdata() if v < thr) / float(im.size[0] * im.size[1])


def test_d22_han_box_redrawn_without_han():
    from src.services import image_edit as IE
    B = BOXES["21"]
    r = IE.render_local(_img(22), 1.0, [B[0]], [(B[7], "중력+ 고탄성 정형면 자체 개발 「힐딩 체감 시스템」")], others=B)
    assert r["ok"] and r["drawn"] == 1 and r["how"][0] in ("fill", "fill-ghost")   # 흰 바탕 — 획(또는 판·유령째) 바탕색으로
    assert r["sizes"][0] >= 60                                         # 텐센트 글자(약 80px)와 같은 급


# ── 5. 「길어서 유지 16」 — 기준 = 텐센트가 같은 상자에 그린 글자 ─────────────────────────────────────

TOO_LONG_16 = [  # (상자 w, h, 텐센트 한국어, AI 다듬은 한국어) — 운영 16:22 기록 그대로
    (386, 170, "모든 한 대는 편안한 챔피언입니다", "모든 한 대는 편안한 의자"),
    (1101, 332, "Natura에 대한 지속적인 혁신을 경의를 표하며, 80+가 원작을 위해 태어난 디자인 팀에 감사드립니다.", "Natura에 경의를 표하며 지속적인 혁신\n80+년 원창 디자인팀"),
    (682, 159, "혁신은 끝이 없으며, 우리는 사용자에게 최첨단, 패션적이고 섬세한 디자인 제품을 제공하기 위해 노력합니다. 이 중 해조 소파, Isabella 침대, Elisir Lounge 랩 의자는 Muse 디자인상, 미국 좋은",
     "혁신은 끝이 없으며, 사용자에게 선진적이고 세련된 디자인 제품을 제공합니다. 해조 소파, Isabella 침대, Elisir Lounge 흔들 의자는 Muse 디자인상, 미국 좋은 디자인상, 프랑스 디자인상 수상"),
    (1255, 138, "평균적으로 팀 구성원은 12년 이상의 경험을 보유하고 있습니다. 일부는 가구 제작 전문가 가족 출신이며, 다른 이들은 인체공학을 깊이 공부했고, 또 다른 이들은 직물과 그들이 빛과 어떻게 상호작용하는지를 사랑하고 있",
     "평균적으로 팀 구성원은 12년 이상의 경험을 보유합니다. 가구 제작 전문가 가족 출신이거나, 인체공학을 깊이 있게 연구했거나, 직물과 빛의 상호작용을 전문으로 합니다"),
    (335, 117, "선구자의 원초적인 디자인, 디자인의 영혼.", "선구자의 원초적 디자인, 디자인의 영혼."),
    (561, 104, "국제 가정용품 트렌드를 깊이 조사하여 각 제품에 맞는 색상을 정합니다. 원단의 질감부터 색상의 밝기와 어두움까지, 조금씩 반복적으로 다듬어 완벽한 질감을 선사합니다.",
     "국제 가정용품 트렌드를 깊이 조사하여 각 제품에 맞는 색상을 정합니다. 원단의 질감부터 색상의 밝기까지, 차근차근 다듬어 우수한 질감을 선사합니다."),
    (182, 159, "호두나무 무늬 실목 곡선 판", "호두나무 무늬 실목 곡목 합판"),
    (182, 61, "그리고 이는 둘 다를 가지고 있습니다", "그리고 이는 둘 다를 갖추고 있습니다"),
    (42, 119, "82cm", "82 cm"),
    (669, 259, "예술을 삶에 전달하세요 3,200명 이상의 사용자 평판 실증 가구 달인/디자이너 추천", "예술을 삶에 전달하다 3,200명 이상의 사용자 호평 가구 전문가·디자이너 추천"),
    (402, 63, "VRSUK은 직업적인 섬유 연구 및 개발 팀을 결성하고, 이탈리아 디자인 섬유 실험실과 전략적 협력을 시작했습니다.", "VRSUK은 전문 섬유 연구개발팀을 구성하고 이탈리아 디자인 섬유 랩과 전략적 협력을 시작했습니다."),
    (155, 82, "모든 세부 사항은 당신을 위해 계획되었습니다", "모든 세부 사항, 당신을 위해 설계"),
    (268, 63, "당신이 앉을 때, 그것을 보는 곳에서 잘 이해하고, 보이지 않는 곳에서는 단단히 느껴집니다. 모든 세부 사항은 고안된 것입니다.", "앉는 순간, 보는 곳은 아름답고 보이지 않는 곳은 단단함. 모든 세부, 정성스럽게 설계"),
    (917, 243, "O중력+]고탄성 정형면 자研「希尔丁体感系统」", "중력+ 고탄성 정형면 자체 개발 「힐딩 체감 시스템」"),
    (438, 78, "전체 앉은 자세에 맞는 자동 적응 지지, 자체 개발된 순환 통기 및 습기 배출 기능, 구름을 품는 듯한 감촉 모델링", "전체 앉은 자세에 자동 적응 지지. 자체 개발 순환 통기 및 습기 배출. 구름 같은 포용감"),
    (569, 375, "세노 에스테티카", "Senso Estetica"),
]


def test_owner_16_too_long_boxes_now_fit():
    from src.services import image_edit as IE
    fits = [IE.text_fit(ai, {"w": w, "h": h}, ref=tgt)["fits"] for w, h, tgt, ai in TOO_LONG_16]
    assert sum(fits) == 16


# ── 4. 버린 사유 — 숫자는 집합 · 「의식감」은 식감이 아니다 · 결과줄은 사유별(길어서 유지와 따로) ──────────────────

def test_number_set_rule_and_category_word_boundary():
    from src.services import image_polish as P
    rule = P.category_rule({"title_ko": "VRSUK 리클라이너"})
    assert P.check("1:0.618云感软度", "1:0.618 구름 감각의 부드러움", "1:0.618 구름감 부드러움", rule) == ""
    assert P.check("3,200+用户口碑", "3,200명 이상의 사용자", "3200명 넘는 사용자 호평", rule) == ""
    assert P.check("82 cm", "82cm", "8 cm", rule) == "숫자 누락(82)"
    assert P.check("[K] 偏爱仪式感 Senso Estetica", "[K] 선호하는 의식감 Senso Estetica", "[K] 의식감을 선호하다 Senso Estetica", rule) == ""
    assert P.check("软糯Q弹", "부드럽고 쫄깃한 식감", "쫄깃한 식감", rule) == "다른 품목 표현(식감)"


def test_result_line_drop_reasons_and_running_count():
    from src.db import image_translate_queue_pg as q
    from src.services import image_polish as P
    rows = [{"why": "길어서 유지(상자에 안 들어감)"}] * 3 + [{"why": "금지어·과장(88VIP)"}, {"why": "다른 품목 표현(식감)"}]
    ex = {"detail_images_ko": [{"idx": 5, "polish": {"changed": 2, "calls": 1, "too_long": 3, "rows": rows, "at": "2026-10-14T16:22:00+00:00"}},
                               {"idx": 27, "polish": {"changed": 1, "calls": 1, "rows": [], "at": "2026-10-14T13:23:00+00:00"}}]}
    line = P.item_line("x", ex)
    assert "길어서 유지 3" in line and "AI 결과 버림 2(" in line and "금지어·과장 1" in line and "다른 품목 표현 1" in line
    q.state_set(P._item_key("x"), {"running": True, "n": 1, "at": "2026-10-14T16:21:00+00:00"})
    assert P.item_line("x", ex) == "번역 다듬기 중… (1/1장)"            # 13:23에 다듬은 28번은 이번 실행이 아니다(옛 「24/23」)


# ── 3. 한자 남은 상자 — AI 두 번 → 그래도 남으면 한자만 텍스트 번역해 끼운다 · 다시 눌러도 AI·번역 0 ──────────────────

def _ai(monkeypatch, reply):
    from src.ai import llm
    seen = []
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda prompt, **k: seen.append(prompt) or {"text": reply(prompt)})
    return seen


def test_han_left_twice_then_text_translate_splice_and_cache(monkeypatch):
    from src.services import image_polish as P
    from src.services import image_translate_tencent as T
    box = {"id": "t7", "src": "O重力+]高弹定型绵自研「希尔丁体感系统」", "tgt": "O중력+]고탄성 정형면 자研「希尔丁体感系统」"}
    seen = _ai(monkeypatch, lambda p: json.dumps({"boxes": [{"id": "t7", "ko": "고탄성 정형면 자研「希尔丁」"}]}))
    sent = []
    tr = {"研": "연구", "希尔丁体感系统": "힐딩 체감 시스템"}
    monkeypatch.setattr(T, "translate_text", lambda t, **k: sent.append(t) or {"ok": True, "text": tr[t], "why": ""})
    ctx = {"title": "VRSUK 리클라이너", "rule": P.category_rule({"title_ko": "VRSUK 리클라이너"}), "materials": []}
    r = P.polish_boxes([dict(box)], ctx)
    row = r["rows"][0]
    assert len(seen) == 2 and r["calls"] == 2 and sent == ["研", "希尔丁体感系统"]
    assert row["from"] == "tmt" and row["ko"] == "O중력+]고탄성 정형면 자연구「힐딩 체감 시스템」" and not P.han_left(row["ko"])
    cache = {(row["src"], row["tgt"]): {"ai": row["ai"], "pv": P.PROMPT_VER, "tries": row["tries"], "tmt": row["tmt"]}}
    r2 = P.polish_boxes([dict(box)], ctx, cache=cache)
    assert len(seen) == 2 and len(sent) == 2 and r2["calls"] == 0 and r2["rows"][0]["ko"] == row["ko"]


# ── 1-b. 옛 렌더로 만든 다듬음은 다시 그린다(사람 편집·새 렌더는 그대로) ─────────────────────────────────

def _entry_with_old_polish(user_on_top=False):
    e = {"idx": 20, "kind": "detail", "status": "done", "use": True, "vendor": "tencent",
         "url": "https://res.cloudinary.com/x/image/upload/e_gen_remove:region_((x_1;y_1;w_2;h_2))/v1/edit/old.jpg",
         "translated_url": "https://res.cloudinary.com/x/t20.jpg", "box_size": [1440, 1209], "box_frame": "identity",
         "boxes": [dict(b) for b in BOXES["20"]], "current": "edit:1",
         "edits": [{"n": 1, "url": "https://res.cloudinary.com/x/image/upload/e_gen_remove:region_((x_1;y_1;w_2;h_2))/v1/edit/old.jpg",
                    "base_key": "translated", "by": "polish", "ready": True, "transform": "e_gen_remove:…"}],
         "vboxes": {"edit:1": {"boxes": [], "size": [1440, 1209]}},
         "polish": {"rows": [{"id": f"t{i}", "src": b["src"], "tgt": b["tgt"], "ai": b["tgt"], "ko": b["tgt"], "from": "tencent", "why": ""}
                             for i, b in enumerate(BOXES["20"]) if i != 2]
                    + [{"id": "t2", "src": "软糯Q弹", "tgt": "부드럽고 쫄깃한 식감", "ai": "부드럽고 탄탄한 쿠션감", "ko": "부드럽고 탄탄한 쿠션감",
                        "from": "polish", "why": ""}], "pv": "y11l-1", "at": "2026-10-14T16:24:00+00:00"}}
    if user_on_top:
        e["edits"].append({"n": 2, "url": "https://res.cloudinary.com/x/u.jpg", "base_key": "edit:1", "by": "user", "ready": True})
        e["current"] = "edit:2"
    return {"title_ko": "VRSUK 리클라이너", "detail_images": [f"https://img/d{i}.jpg" for i in range(22)], "detail_images_ko": [e]}


def test_old_render_polish_is_redrawn_once_with_cache(monkeypatch):
    from src.services import image_edit as IE
    from src.services import image_polish as P
    ex = _entry_with_old_polish()
    assert P.item_targets(ex) == [("detail", 20)]
    seen = _ai(monkeypatch, lambda p: json.dumps({"boxes": []}))
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    applied = []

    def _apply(extra, kind, idx, ops, by="user", small=None):
        applied.append(ops)
        e = IE._entry(extra, kind, idx)
        IE._normalize(e)
        e["edits"].append({"n": 2, "url": "https://res.cloudinary.com/x/new.jpg", "base_key": "translated", "by": by, "render": "local",
                           "render_v": IE.RENDER_V})
        IE.select(extra, kind, idx, "edit:2")
        return {"ok": True, "version": "edit:2"}
    monkeypatch.setattr(IE, "apply", _apply)
    r = P.polish_entry(ex, "detail", 20)
    e = ex["detail_images_ko"][0]
    assert r["ok"] and r["calls"] == 0 and not seen                          # 캐시 — AI 0회
    assert applied[0] == [{"id": "t2", "action": "text", "text": "부드럽고 탄탄한 쿠션감"}]
    assert [v["key"] for v in IE.versions(ex, "detail", 20)] == ["original", "translated", "edit:2"]   # 옛 번진 버전은 뺀다
    assert IE.current_key(e) == "edit:2" and e["polish_rerender"][0]["dropped"] == ["edit:1"]
    assert P.item_targets(ex) == []                                          # 새 렌더 다듬음은 다시 안 그린다


def test_user_edit_on_old_polish_is_left_alone():
    from src.services import image_polish as P
    ex = _entry_with_old_polish(user_on_top=True)
    assert P.item_targets(ex) == [] and not P.old_render(ex["detail_images_ko"][0])
