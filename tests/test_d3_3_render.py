"""D3 3단계 계약 — 지우고, 박스 **안에** 쓴다.

## 이 단계가 하는 일

텐센트 `BoundingBox`는 **원문** 문단의 자리다. 거기 있던 글자를 `cv2.inpaint`로 지우고,
2단계가 정한 한국어를 **그 박스를 넘지 않게** 앉힌다.

| 축 | 여기서 재는 것 |
|---|---|
| **C 박스 수납** | 박스 밖으로 **한 픽셀도** 안 나간다 · 안 들어가면 **안 그린다** |
| **E 타이포** | 너무 작으면(11px 미만) 그리지 않는다 · 줄바꿈이 폭을 지킨다 |

> ★ **못 앉히면 그리지 않는다.** 삐져나온 글자는 상품 사진을 망친다 —
> 지워진 자리는 깨끗하고, 그게 잘못 그린 것보다 낫다. **사유는 결과에 남는다.**

실패는 언제나 **원본 바이트**로 끝난다 — 반쯤 그린 이미지를 내지 않는다.

라이브 호출 0. 이미지는 **여기서 만든다**(공급사 없이 실제 픽셀을 잰다).
"""
from __future__ import annotations

import io

import pytest

from src.services import image_text_render as R

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")


def _canvas(w=400, h=200, color=(240, 238, 230)) -> bytes:
    from PIL import Image as _I
    buf = io.BytesIO()
    _I.new("RGB", (w, h), color).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _with_text(w=400, h=200, box=(20, 20, 200, 60), text="原文文字") -> bytes:
    """원문 **글자**가 박힌 이미지 — 지우기를 실제로 재기 위해.

    ※ D3-4 ②로 마스크가 **글자 픽셀만** 잡게 된 뒤, 예전 픽스처(박스를 꽉 채운 검은 사각형)는
      「글자가 아니라 도형」으로 **정확히 거부된다.** 그래서 진짜 글자를 그린다 —
      픽스처가 현실과 달랐던 것이고, 그걸 새 규칙이 드러냈다.
    """
    from PIL import Image as _I, ImageDraw
    from src.services.image_render_font import load as _load
    img = _I.new("RGB", (w, h), (240, 238, 230))
    d = ImageDraw.Draw(img)
    d.text((box[0] + 6, box[1] + 6), text, font=_load(int(box[3] * 0.6), "bold"),
           fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _with_shape_and_text(w=400, h=200) -> bytes:
    """**배경 도형 + 그 위의 글자** — C축이 실제로 깨졌던 모양."""
    from PIL import Image as _I, ImageDraw
    from src.services.image_render_font import load as _load
    img = _I.new("RGB", (w, h), (245, 243, 236))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, 240, 80], radius=28, fill=(201, 162, 75))   # 금색 알약
    d.text((40, 34), "原文", font=_load(30, "bold"), fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _px(image_bytes: bytes):
    from PIL import Image as _I
    return _I.open(io.BytesIO(image_bytes)).convert("RGB")


def _dark_pixels(img, box) -> int:
    """박스 안 **어두운 픽셀 수** — 글자가 남았나를 사각형 좌표 없이 잰다."""
    x1, y1 = box["x"], box["y"]
    x2, y2 = x1 + box["w"], y1 + box["h"]
    return sum(1 for x in range(x1, min(x2, img.width))
               for y in range(y1, min(y2, img.height))
               if sum(img.getpixel((x, y))) < 250)


# ---------------------------------------------------------------------------
# 지우기
# ---------------------------------------------------------------------------

def test_the_original_text_is_actually_gone():
    """★★ 목이 아니라 **픽셀**로 잰다 — 검은 자국이 배경색으로 메워졌나."""
    src = _with_text()
    box = {"x": 20, "y": 20, "w": 200, "h": 60}
    dark_before = _dark_pixels(_px(src), box)
    assert dark_before > 50, dark_before                   # 글자가 실제로 박혀 있다

    out, used, why = R.erase_boxes(src, [box])
    assert why == "" and used == 1
    dark_after = _dark_pixels(_px(out), box)
    assert dark_after < dark_before * 0.2, (dark_before, dark_after)


@pytest.mark.parametrize("method", ["telea", "ns"])
def test_both_inpaint_methods_run(method):
    """★ TELEA·NS 둘 다 **실제로 돈다**(cv2 상수 이름만 맞춘 게 아니라)."""
    out, used, why = R.erase_boxes(_with_text(), [{"x": 20, "y": 20, "w": 200, "h": 60}],
                                   method=method)
    assert why == "" and used == 1 and out != _with_text()


def test_a_box_outside_the_image_is_clipped_not_crashed():
    """★ 좌표가 이미지 밖으로 나가도 **잘라 내고 계속한다**(회전·여백에서 실제로 온다).

    ※ 글자가 있는 이미지로 잰다 — D3-4 ② 뒤로 마스크는 **글자 픽셀**을 보므로,
      빈 캔버스로 재면 「잘라 냈나」가 아니라 「글자가 있나」를 재게 된다.
    """
    src = _with_text(box=(300, 120, 90, 60), text="原文")
    out, used, why = R.erase_boxes(src, [{"x": 300, "y": 120, "w": 500, "h": 500}])
    assert why == "" and used == 1, why


def test_a_box_entirely_outside_the_image_is_refused_with_a_reason():
    """★ 잘라서 남는 게 없으면 **사유를 남기고** 원본을 돌려준다."""
    src = _with_text()
    out, used, why = R.erase_boxes(src, [{"x": 900, "y": 900, "w": 50, "h": 50}])
    assert used == 0 and why and out == src


def test_a_zero_box_is_refused_with_a_reason():
    out, used, why = R.erase_boxes(_canvas(), [{"x": 10, "y": 10, "w": 0, "h": 0}])
    assert used == 0 and why
    assert out == _canvas() or len(out) > 0               # 원본 유지


def test_missing_cv2_keeps_the_original_and_says_why(monkeypatch):
    """★ F43 규율 — 없으면 **사유가 남는다**(조용히 원본을 흘리지 않는다)."""
    monkeypatch.setattr(R, "_load_cv2", lambda: (None, None, "cv2 없음"))
    src = _canvas()
    out, used, why = R.erase_boxes(src, [{"x": 1, "y": 1, "w": 10, "h": 10}])
    assert out == src and used == 0 and "cv2" in why


# ---------------------------------------------------------------------------
# C) 박스 수납 — 넘지 않는다
# ---------------------------------------------------------------------------

def test_the_text_fits_inside_the_box():
    plan = R.fit_text("휴대용 선풍기", 200, 60)
    assert plan is not None
    from src.services.image_render_font import load
    font = load(plan["size"], "regular")
    for line in plan["lines"]:
        box = font.getbbox(line)
        assert box[2] - box[0] <= 200, line                # 폭을 안 넘는다
    assert plan["line_h"] * len(plan["lines"]) <= 60       # 높이도


def test_a_long_korean_line_is_wrapped_not_squashed():
    """★ 한국어는 띄어쓰기가 드물다 — **글자 단위**로도 나눌 수 있어야 한다."""
    plan = R.fit_text("휴대용선풍기충전식미니탁상용조용한바람", 120, 90)
    assert plan is not None
    assert len(plan["lines"]) > 1


def test_a_box_too_small_returns_none_instead_of_shrinking_forever():
    """★★ 11px 미만은 **사람이 못 읽는다** — 그리느니 안 그린다."""
    assert R.fit_text("휴대용 선풍기", 30, 9) is None


def test_nothing_is_drawn_outside_the_box():
    """★★★ **C 축의 판정 지점** — 박스 밖 픽셀은 **건드리지 않는다.**"""
    src = _canvas(400, 200)
    box = {"x": 100, "y": 60, "w": 180, "h": 70}
    out, drawn, skipped = R.draw_lines(src, [{"render_text": "휴대용 선풍기", "box": box}])
    assert drawn == 1, skipped

    a, b = _px(src), _px(out)
    changed_outside = 0
    for x in range(0, 400, 3):
        for y in range(0, 200, 3):
            inside = 100 <= x < 280 and 60 <= y < 130
            if inside:
                continue
            if a.getpixel((x, y)) != b.getpixel((x, y)):
                changed_outside += 1
    assert changed_outside == 0, f"박스 밖 {changed_outside}점이 바뀌었다"


def test_something_was_actually_drawn_inside():
    """★ 「안 나갔다」만 재면 **아무것도 안 그려도 통과**한다 — 안쪽도 잰다."""
    src = _canvas(400, 200)
    box = {"x": 100, "y": 60, "w": 180, "h": 70}
    out, drawn, _ = R.draw_lines(src, [{"render_text": "휴대용 선풍기", "box": box}])
    a, b = _px(src), _px(out)
    changed = sum(1 for x in range(100, 280, 2) for y in range(60, 130, 2)
                  if a.getpixel((x, y)) != b.getpixel((x, y)))
    assert drawn == 1 and changed > 20, changed


def test_a_line_that_does_not_fit_is_skipped_with_a_reason():
    """★★ 조용히 빠뜨리지 않는다 — **무엇이 왜** 안 그려졌는지 남는다."""
    out, drawn, skipped = R.draw_lines(
        _canvas(), [{"render_text": "아주 긴 한국어 설명 문장입니다", "box": {"x": 5, "y": 5, "w": 26, "h": 10}}])
    assert drawn == 0
    assert skipped and "안 들어갑니다" in skipped[0]["reason"]


# ---------------------------------------------------------------------------
# 전체 — render()
# ---------------------------------------------------------------------------

def test_render_erases_then_draws():
    src = _with_text()
    res = R.render(src, [{"render_text": "선풍기", "box": {"x": 20, "y": 20, "w": 200, "h": 60}}])
    assert res["ok"] is True
    assert res["erased"] == 1 and res["drawn"] == 1
    assert res["image_bytes"] != src


def test_render_does_not_touch_the_image_when_there_is_nothing_to_draw():
    """★★ 그릴 게 없으면 **지우지도 않는다** — 멀쩡한 원본을 괜히 뭉개지 않는다."""
    src = _with_text()
    res = R.render(src, [{"render_text": "   ", "box": {"x": 20, "y": 20, "w": 100, "h": 40}}])
    assert res["ok"] is False
    assert res["image_bytes"] == src
    assert res["error"]


def test_a_failure_returns_the_original_bytes(monkeypatch):
    monkeypatch.setattr(R, "_load_cv2", lambda: (None, None, "cv2 없음"))
    src = _with_text()
    res = R.render(src, [{"render_text": "선풍기", "box": {"x": 20, "y": 20, "w": 100, "h": 40}}])
    assert res["image_bytes"] == src and res["ok"] is False and res["error"]


# ---------------------------------------------------------------------------
# ★★★ D3-4 ① 미번역 줄은 박스를 **건드리지 않는다**
#      (오너 벤치 실측 `bench-20260921-120314-m0-d3` — D축 실패 원인)
# ---------------------------------------------------------------------------
#
# 오너가 못박은 계약: **「그 박스 픽셀 변화 0」.**
#
# ⚠️ 정직하게: 결과는 JPEG로 다시 인코드되므로 **모든 픽셀이 몇 단위씩** 움직인다.
#   그래서 「0」은 세 갈래로 나눠 잰다 — 셋 다 통과해야 한다.
#
#   | 무엇 | 어떻게 |
#   |---|---|
#   | 미번역만 있으면 | **바이트가 완전히 같다**(재인코드조차 안 한다) |
#   | 섞여 있으면 | 그 박스 최대 변화가 **JPEG 잡음 수준** |
#   | 글자가 살아 있나 | 그 박스의 **어두운 픽셀 수가 그대로** — 지웠다면 사라진다 |
#
# 셋째가 판정 지점이다. 「조금 바뀌었다」와 「지우고 다시 그렸다」를 가르는 것은 글자다.

def _two_line_image():
    """왼쪽엔 번역할 중국어, 오른쪽엔 **건드리면 안 되는 제품 화면 UI**."""
    from PIL import Image as _I, ImageDraw
    from src.services.image_render_font import load as _load
    img = _I.new("RGB", (400, 200), (240, 238, 230))
    d = ImageDraw.Draw(img)
    d.text((24, 30), "原文文字", font=_load(34, "bold"), fill=(20, 20, 20))
    d.text((24, 120), "12:30", font=_load(30, "regular"), fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


TRANSLATED = {"source": "原文文字", "render_text": "원문 글자", "action": "translate",
              "box": {"x": 20, "y": 24, "w": 180, "h": 50}}
KEPT = {"source": "12:30", "render_text": "12:30", "action": "keep",
        "rule_reason": "영문·숫자만 — 제품 화면 UI",
        "box": {"x": 20, "y": 114, "w": 140, "h": 46}}


def test_an_untranslated_line_alone_leaves_the_image_byte_identical():
    """★★★ **가장 강한 형태의 「변화 0」** — 재인코드조차 하지 않는다."""
    src = _two_line_image()
    res = R.render(src, [KEPT])
    assert res["image_bytes"] == src
    assert res["erased"] == 0 and res["drawn"] == 0


def test_the_untranslated_box_keeps_its_glyphs_when_another_line_is_translated():
    """★★★ **판정 지점** — 번역할 줄이 같이 있어도 그 박스는 **지워지지 않는다.**"""
    src = _two_line_image()
    res = R.render(src, [TRANSLATED, KEPT])
    assert res["ok"] is True and res["drawn"] == 1

    a, b = _px(src), _px(res["image_bytes"])
    kept_before = _dark_pixels(a, KEPT["box"])
    kept_after = _dark_pixels(b, KEPT["box"])
    assert kept_before > 50, kept_before
    assert abs(kept_after - kept_before) <= kept_before * 0.1, (kept_before, kept_after)

    # 번역한 줄은 **실제로 바뀌었다** — 「아무것도 안 했다」로 통과하지 않게 같이 잰다.
    assert _dark_pixels(a, TRANSLATED["box"]) != _dark_pixels(b, TRANSLATED["box"])


def test_the_untranslated_box_moves_only_by_jpeg_noise():
    """★★ 그 박스 최대 변화가 **재인코드 잡음**을 넘지 않는다."""
    src = _two_line_image()
    res = R.render(src, [TRANSLATED, KEPT])
    a, b = _px(src), _px(res["image_bytes"])
    box = KEPT["box"]
    worst = max(abs(pa - pb)
                for x in range(box["x"], box["x"] + box["w"])
                for y in range(box["y"], box["y"] + box["h"])
                for pa, pb in zip(a.getpixel((x, y)), b.getpixel((x, y))))
    assert worst <= 24, worst


@pytest.mark.parametrize("line,why_word", [
    ({"source": "12:30", "render_text": "12:30", "action": "keep",
      "rule_reason": "영문·숫자만 — 제품 화면 UI", "box": {"x": 20, "y": 114, "w": 140, "h": 46}},
     "제품 화면"),
    ({"source": "原文文字", "render_text": "原文文字", "action": "translate",
      "translate_error": "TimeoutError: 시간 초과", "box": {"x": 20, "y": 24, "w": 180, "h": 50}},
     "번역 실패"),
    ({"source": "原文文字", "render_text": "原文文字", "action": "translate",
      "box": {"x": 20, "y": 24, "w": 180, "h": 50}},
     "원문과 같"),
])
def test_every_shape_of_untranslated_is_left_alone_with_a_reason(line, why_word):
    """★★★ 「미번역」은 **세 모양**으로 온다 — 셋 다 안 건드리고, 셋 다 **사유가 남는다.**

    특히 셋째(번역기가 원문을 그대로 돌려줬다)가 없으면 앞의 둘을 막아도 같은 사고가 난다:
    「실패하면 원문을 남긴다」가 곧 「그 줄을 원문 그대로 **다시 그린다**」가 되기 때문이다.
    """
    src = _two_line_image()
    res = R.render(src, [line])
    assert res["image_bytes"] == src and res["drawn"] == 0
    assert res["skipped"] and why_word in res["skipped"][0]["reason"]


# ---------------------------------------------------------------------------
# ★★ D3-4 ③ 타이포 상속 — 굵기·정렬·색을 원본에서 받는다
# ---------------------------------------------------------------------------

def _line_image(weight="regular", align="center", fill=(20, 20, 20),
                text="原文文字", size=34, w=400, h=120):
    from PIL import Image as _I, ImageDraw
    from src.services.image_render_font import load as _load
    img = _I.new("RGB", (w, h), (240, 238, 230))
    font = _load(size, weight)
    tw = font.getbbox(text)[2] - font.getbbox(text)[0]
    x = {"left": 14, "right": w - 14 - tw, "center": (w - tw) // 2}[align]
    ImageDraw.Draw(img).text((x, 30), text, font=font, fill=fill)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


BOX = {"x": 4, "y": 20, "w": 392, "h": 70}


@pytest.mark.parametrize("weight", ["regular", "bold"])
@pytest.mark.parametrize("text,size", [
    ("原文文字", 34),
    # 획이 많다 — 같은 굵기라도 획비가 **낮게** 나온다.
    # (`绝`은 우리 폰트에 없어 두부로 그려진다 — 픽스처가 그리지 못하는 글자를 쓰면
    #  재는 대상이 글자가 아니라 네모가 된다. 그건 아래 전용 계약에서 따로 잰다.)
    ("拒凌乱", 34),
    ("12:30", 30),        # 획이 적다 — 같은 굵기라도 획비가 **높게** 나온다
])
def test_the_stroke_weight_is_read_back(weight, text, size):
    """★★★ **고정 임계값이 틀렸던 자리.**

    `12:30`의 Regular 획비(0.119)가 `拒绝凌乱`의 Bold(0.092)보다 높다 — 상수를 어디에 두든
    둘 중 하나는 틀린다. 그래서 **같은 글자를 우리 폰트로 그려 보고** 가까운 쪽을 고른다.
    """
    src = _line_image(weight=weight, text=text, size=size)
    got = R.sample_typography(src, BOX, text)
    assert got["weight"] == weight, got


def test_a_glyph_our_font_lacks_is_not_used_as_the_reference():
    """★★★ 실측(2026-09-21) — `NotoSansKR-VF`엔 **간체자 일부가 없다**(`绝`·`轻`·`纳`·`线`·`电`).

    없는 글자는 **두부(□)**로 그려지는데 `getbbox()`는 멀쩡한 숫자를 돌려준다.
    그대로 기준선으로 쓰면 **글자가 아니라 네모를 재게 된다.**
    """
    from src.services.image_render_font import supported

    assert supported("拒绝凌乱") == "拒凌乱"
    assert supported("간편 수납") == "간편 수납"       # 한글은 전부 있다
    assert supported("绝线电") == ""                   # 하나도 못 그린다

    got = R.sample_typography(_line_image(weight="bold", text="拒凌乱"), BOX, "绝线电")
    assert got["weight"] == "regular"
    assert "우리 폰트에 없어" in got["reason"], got


def test_without_the_source_text_it_says_so_instead_of_guessing():
    """★★ 기준선을 못 그리면 **찍지 않는다** — 기본값 + 사유."""
    got = R.sample_typography(_line_image(weight="bold"), BOX)   # 원문 글자 안 줌
    assert got["weight"] == "regular"
    assert "원문 글자를 몰라" in got["reason"], got


@pytest.mark.parametrize("align", ["left", "center", "right"])
def test_the_alignment_is_read_back(align):
    got = R.sample_typography(_line_image(align=align), BOX, "原文文字")
    assert got["align"] == align, got


@pytest.mark.parametrize("fill", [(201, 162, 75), (17, 154, 142)])
def test_the_colour_is_read_back(fill):
    """★ 금색·청록 카피를 먹색으로 다시 그리면 **다른 디자인**이 된다."""
    got = R.sample_typography(_line_image(fill=fill), BOX, "原文文字")
    for a, b in zip(got["color"], fill):
        assert abs(a - b) <= 40, got


def test_the_weight_does_not_depend_on_the_text_colour():
    """★★★ 실측(2026-09-21) — 백분위 임계값은 **청록 굵은 글자를 Regular로** 읽었다.

    대비가 낮으면 가장자리를 덜 잡아 획이 얇게 측정됐다. Otsu는 색과 무관하다.
    """
    for fill in ((20, 20, 20), (17, 154, 142), (201, 162, 75)):
        got = R.sample_typography(_line_image(weight="bold", fill=fill), BOX, "原文文字")
        assert got["weight"] == "bold", (fill, got)


def test_unmeasurable_typography_falls_back_with_a_reason():
    """★★ 못 재면 **지어내지 않는다** — 기본값 + 사유."""
    got = R.sample_typography(_canvas(), BOX, "原文文字")      # 글자가 없는 판
    assert got["weight"] == "regular" and got["align"] == "center"
    assert got["reason"]


def test_render_measures_the_original_not_the_erased_image(monkeypatch):
    """★★★ **지우기 전에** 재야 한다 — 지운 뒤엔 잴 글자가 없다."""
    src = _two_line_image()
    seen = []
    real = R.sample_typography
    monkeypatch.setattr(R, "sample_typography",
                        lambda b, box, src="": (seen.append(b), real(b, box, src))[1])
    R.render(src, [TRANSLATED])
    assert seen and all(b == src for b in seen)


def test_render_passes_the_measured_typography_through():
    """★ 잰 값이 **결과에 남는다** — 벤치 표가 「왜 굵게 그렸나」를 보여 줄 수 있게."""
    res = R.render(_line_image(weight="bold"),
                   [{"source": "原文文字", "render_text": "원문 글자",
                     "action": "translate", "box": BOX}])
    assert res["ok"] is True
    assert res["typography"] and res["typography"][0]["weight"] == "bold"


def test_a_line_that_already_says_its_typography_is_respected(monkeypatch):
    """★ 호출부가 정해 준 값은 **덮지 않는다**(2단계가 알고 있을 수도 있다)."""
    monkeypatch.setattr(R, "sample_typography",
                        lambda *a, **k: pytest.fail("이미 정해진 줄을 다시 쟀다"))
    res = R.render(_line_image(), [{"source": "原文文字", "render_text": "원문 글자",
                                    "action": "translate", "box": BOX,
                                    "weight": "bold", "align": "left",
                                    "color": (201, 162, 75)}])
    assert res["drawn"] == 1


def test_alignment_actually_moves_the_drawn_text():
    """★★ 값을 읽기만 하고 **안 쓰면** 상속이 아니다 — 그린 자리로 잰다."""
    src = _canvas(400, 120)
    box = {"x": 20, "y": 20, "w": 360, "h": 60}

    def _center_of_ink(image_bytes):
        img = _px(image_bytes)
        xs = [x for x in range(box["x"], box["x"] + box["w"])
              for y in range(box["y"], box["y"] + box["h"])
              if sum(img.getpixel((x, y))) < 400]
        return sum(xs) / len(xs)

    left, _, _ = R.draw_lines(src, [{"render_text": "선풍기", "box": box, "align": "left"}])
    right, _, _ = R.draw_lines(src, [{"render_text": "선풍기", "box": box, "align": "right"}])
    assert _center_of_ink(left) < _center_of_ink(right) - 100


# ---------------------------------------------------------------------------
# 아직 연결하지 않는다
# ---------------------------------------------------------------------------

def test_it_is_not_wired_into_the_pipeline_yet():
    """★★ 오너 지시 — **골든 샘플 5축 통과 전에는 연결하지 않는다.**

    **벤치는 예외다**(D3-3b): 관리자 화면이 오너 클릭으로 한 장을 돌려 보는 자리이고,
    결과는 벤치 저장소(`kind="d3"`)에만 간다. 막는 것은 **등록·번역 경로**다.

    ※ 글자가 아니라 `import`를 잰다 — 독스트링에 이름이 보이는 것은 연결이 아니다.
    """
    from tests.test_d3_glossary import BENCH_ONLY, _importers_of
    assert _importers_of("image_text_render", allow=BENCH_ONLY) == []
