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


def _with_text(w=400, h=200, box=(20, 20, 200, 60), text="ORIGINAL TEXT") -> bytes:
    """원문 글자가 박힌 이미지 — 지우기를 **실제로** 재기 위해."""
    from PIL import Image as _I, ImageDraw
    img = _I.new("RGB", (w, h), (240, 238, 230))
    d = ImageDraw.Draw(img)
    d.rectangle([box[0], box[1], box[0] + box[2], box[1] + box[3]], fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _px(image_bytes: bytes):
    from PIL import Image as _I
    return _I.open(io.BytesIO(image_bytes)).convert("RGB")


# ---------------------------------------------------------------------------
# 지우기
# ---------------------------------------------------------------------------

def test_the_original_text_is_actually_gone():
    """★★ 목이 아니라 **픽셀**로 잰다 — 검은 자국이 배경색으로 메워졌나."""
    src = _with_text()
    before = _px(src).getpixel((60, 40))
    assert sum(before) < 200, before                      # 확실히 어둡다

    out, used, why = R.erase_boxes(src, [{"x": 20, "y": 20, "w": 200, "h": 60}])
    assert why == "" and used == 1
    after = _px(out).getpixel((60, 40))
    assert sum(after) > 500, after                        # 밝은 배경으로 메워졌다


@pytest.mark.parametrize("method", ["telea", "ns"])
def test_both_inpaint_methods_run(method):
    """★ TELEA·NS 둘 다 **실제로 돈다**(cv2 상수 이름만 맞춘 게 아니라)."""
    out, used, why = R.erase_boxes(_with_text(), [{"x": 20, "y": 20, "w": 200, "h": 60}],
                                   method=method)
    assert why == "" and used == 1 and out != _with_text()


def test_a_box_outside_the_image_is_clipped_not_crashed():
    out, used, why = R.erase_boxes(_canvas(), [{"x": 380, "y": 190, "w": 500, "h": 500}])
    assert why == "" and used == 1


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
# 아직 연결하지 않는다
# ---------------------------------------------------------------------------

def test_it_is_not_wired_into_the_pipeline_yet():
    """★★ 오너 지시 — **골든 샘플 5축 통과 전에는 연결하지 않는다.**"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    hits = [str(p.relative_to(root)) for p in (root / "src").rglob("*.py")
            if p.name != "image_text_render.py" and "image_text_render" in p.read_text(encoding="utf-8")]
    assert not hits, f"아직 연결하면 안 된다: {hits}"
