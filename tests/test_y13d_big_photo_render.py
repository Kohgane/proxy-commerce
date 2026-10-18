"""Y13-D 3(오너 2026-10-18 18:20 UTC — BLACKHOLES 대표 0번(5120×5120 PNG) 다듬기·편집 직후 인스턴스 교체).

다듬기는 「원본 픽셀 되살리기」(로고·판촉 상자)에서 **수집 원본을 받아 Pillow로 통째로 풀었다**(`render_local` 의
`Image.open(orig_raw).convert("RGB")`) — 실측(같은 실사진 · 별 프로세스 ru_maxrss): 한 번에 **+197MB**.
수리: 다듬기·사진 편집·틀 확인·좌우반전 확인이 쓰는 그림은 긴 변 2,000 안쪽만 — 큰 장은 텐센트 입력처럼
Cloudinary 축소 사본(`small_copy`)을 받는다(`image_edit.work_bytes`). 원본 화소는 우리 프로세스에서 풀지 않는다.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_FIX = Path("tests/fixtures/realimages/blackholes")
_PNG = _FIX / "O1CN01yqZT4K3oxSKAOX2W_!!3596090318.png"          # 5120×5120 PNG(대표 0번)
_WEBP = _FIX / "O1CN01f9Vrp5CshwF8RgLQ_!!3596090318.jpg"         # 4160×4160 WebP(주소는 .jpg)


def _jpeg(side, color=(30, 90, 160)):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (side, side), color).save(b, "JPEG", quality=85)
    return b.getvalue()


# ── 피크 메모리(별 프로세스 · 실사진) ────────────────────────────────────────────────────────────

_MEASURE = textwrap.dedent('''
    import io, os, resource, sys
    sys.path.insert(0, os.getcwd())
    ORIG = open(sys.argv[1], "rb").read()
    def mb():
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    from PIL import Image, ImageDraw
    import numpy, cv2  # noqa: F401
    def jpeg(side, text=True):
        im = Image.new("RGB", (side, side), (235, 232, 225))
        d = ImageDraw.Draw(im)
        for i in range(6):
            d.rectangle([100 + i * 300, 200, 300 + i * 300, 400], fill=(20 + i * 30, 60, 120))
        if text:
            d.rectangle([150, 1700, 1300, 1800], fill=(250, 250, 250))
        b = io.BytesIO(); im.save(b, "JPEG", quality=88); im.close()
        return b.getvalue()
    TRANS, COPY = jpeg(2000), jpeg(2000, text=False)
    from src.services import image_edit as IE
    from src.media import image_pipeline as P
    from src.db import image_translate_queue_pg as q
    TU, OU = "https://res.cloudinary.com/x/image/upload/v1/t.jpg", "https://img.alicdn.com/imgextra/big.png"
    asked, seen = [], []
    P.small_copy = lambda url, **k: asked.append(url) or (COPY, "")
    P.upload_bytes = lambda data, **k: {"ok": True, "secure_url": "https://res.cloudinary.com/x/edit/e.jpg"}
    q.take_start = lambda *a, **k: (True, 1)
    IE.configured = lambda: (True, "")
    _rl = IE.render_local
    def spy(raw, *a, **k):
        from src.collectors.image_norm import image_head
        seen.append(max(image_head(raw)[1:]))
        if k.get("orig_raw"):
            seen.append(max(image_head(k["orig_raw"])[1:]))
        return _rl(raw, *a, **k)
    IE.render_local = spy
    def extra():
        return {"images": [OU], "images_ko": [{
            "idx": 0, "kind": "gallery", "status": "done", "use": True, "url": TU, "translated_url": TU, "boxes_img": TU,
            "box_frame": "identity", "box_size": [2000, 2000],
            "boxes": [{"x": 150, "y": 1700, "w": 1150, "h": 100, "src": "BLACKHOLES", "tgt": "BLACKHOLES"},
                      {"x": 150, "y": 500, "w": 400, "h": 80, "src": "下单享好礼", "tgt": "주문 시 선물 증정"}]}]}
    OPS = [{"id": "t0", "action": "restore"}, {"id": "t1", "action": "text", "text": "선물"}]
    small = Image.new("RGB", (256, 256), (230, 230, 230))
    IE._fetch = lambda u: {TU: TRANS, OU: COPY}.get(u, b"")          # 데우기: 같은 경로를 작은 원본으로
    IE.apply(extra(), "gallery", 0, OPS, by="polish", small=small)
    IE._fetch = lambda u: {TU: TRANS, OU: ORIG}.get(u, b"")
    asked.clear(); seen.clear()
    base = mb()
    r = IE.apply(extra(), "gallery", 0, OPS, by="polish", small=small)
    print("RESULT", int(bool(r.get("ok"))), len(asked), max(seen or [0]), round(mb() - base, 1))
''')


@pytest.mark.parametrize("fixture", [_PNG, _WEBP], ids=["png5120", "webp4160"])
def test_polish_restore_on_big_original_peak_under_40mb(fixture, tmp_path):
    """오너 기준: 5120px 입력에서 피크 +40MB 이하(수리 전 같은 실사진 +197MB)."""
    script = tmp_path / "measure.py"
    script.write_text(_MEASURE)
    env = dict(os.environ, SELLER_CONSOLE_AUTH="0")
    for k in ("DATABASE_URL", "SUPABASE_DB_URL", "DATABASE_URL_DIRECT"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, str(script), str(fixture.resolve())], cwd=os.getcwd(), env=env,
                         capture_output=True, text=True, timeout=240)
    line = next((ln for ln in out.stdout.splitlines() if ln.startswith("RESULT")), "")
    assert line, out.stdout[-2000:] + out.stderr[-2000:]
    _r, ok, asked, biggest, delta = line.split()
    assert ok == "1"                                              # 되살리기·글자 그리기는 그대로 된다
    assert int(asked) == 1                                        # 큰 원본은 Cloudinary 축소 사본 한 번
    assert int(biggest) <= 2000                                   # 그리기 워커가 받은 그림은 전부 긴 변 2,000 안쪽
    assert float(delta) <= 40.0, f"피크 +{delta}MB"


# ── work_bytes 규칙 ───────────────────────────────────────────────────────────────────────────

def test_work_bytes_small_photo_is_untouched(monkeypatch):
    from src.services import image_edit as IE
    from src.media import image_pipeline as P
    body = _jpeg(1200)
    monkeypatch.setattr(IE, "_fetch", lambda u: body)
    monkeypatch.setattr(P, "small_copy", lambda *a, **k: pytest.fail("작은 사진에 사본을 만들었다"))
    assert IE.work_bytes("https://img.alicdn.com/a.jpg") == (body, "")


def test_work_bytes_big_png_uses_cloudinary_copy_without_decoding(monkeypatch):
    from src.services import image_edit as IE
    from src.media import image_pipeline as P
    from src.collectors import image_norm as N
    copy = _jpeg(2000)
    monkeypatch.setattr(IE, "_fetch", lambda u: _PNG.read_bytes())
    asked = []
    monkeypatch.setattr(P, "small_copy", lambda url, **k: asked.append((url, k.get("max_side"))) or (copy, ""))
    monkeypatch.setattr(N, "open_small", lambda *a, **k: pytest.fail("5120px PNG 원본을 우리가 풀었다"))
    got, why = IE.work_bytes("//img.alicdn.com/big.png")
    assert got == copy and not why and asked == [("https://img.alicdn.com/big.png", 2000)]


def test_work_bytes_big_jpeg_without_copy_is_drafted(monkeypatch):
    from src.services import image_edit as IE
    from src.media import image_pipeline as P
    from src.collectors.image_norm import image_head
    monkeypatch.setattr(IE, "_fetch", lambda u: _jpeg(4800))
    monkeypatch.setattr(P, "small_copy", lambda *a, **k: (None, "Cloudinary 미설정"))
    got, why = IE.work_bytes("https://img.alicdn.com/a.jpg")
    assert got and not why and max(image_head(got)[1:]) <= 2000


def test_work_bytes_big_png_without_copy_refuses_with_reason(monkeypatch):
    from src.services import image_edit as IE
    from src.media import image_pipeline as P
    monkeypatch.setattr(IE, "_fetch", lambda u: _PNG.read_bytes())
    monkeypatch.setattr(P, "small_copy", lambda *a, **k: (None, "Cloudinary 미설정"))
    got, why = IE.work_bytes("https://img.alicdn.com/big.png")
    assert got == b"" and "5120×5120" in why and "Cloudinary 미설정" in why


def test_work_max_side_env(monkeypatch):
    from src.services import image_edit as IE
    monkeypatch.setenv("IMAGE_WORK_MAX_SIDE", "1600")
    assert IE.work_max_side() == 1600
    monkeypatch.setenv("IMAGE_WORK_MAX_SIDE", "abc")
    assert IE.work_max_side() == 2000


def test_restore_skipped_when_big_original_cannot_be_shrunk(monkeypatch):
    """축소 사본을 못 받으면 되살리기만 건너뛴다(텐센트 글자 그대로) — 원본을 풀지 않는다."""
    from PIL import Image
    from src.services import image_edit as IE
    from src.media import image_pipeline as P
    from src.db import image_translate_queue_pg as q
    trans = _jpeg(2000, (240, 240, 240))
    TU, OU = "https://res.cloudinary.com/x/t.jpg", "https://img.alicdn.com/big.png"
    monkeypatch.setattr(IE, "_fetch", lambda u: {TU: trans, OU: _PNG.read_bytes()}.get(u, b""))
    monkeypatch.setattr(P, "small_copy", lambda *a, **k: (None, "Cloudinary 미설정"))
    monkeypatch.setattr(P, "upload_bytes", lambda data, **k: {"ok": True, "secure_url": "https://res.cloudinary.com/x/e.jpg"})
    monkeypatch.setattr(q, "take_start", lambda *a, **k: (True, 1))
    monkeypatch.setattr(IE, "configured", lambda: (True, ""))
    got = {}
    real = IE.render_local
    monkeypatch.setattr(IE, "render_local", lambda raw, *a, **k: got.update(k) or real(raw, *a, **k))
    ex = {"images": [OU], "images_ko": [{"idx": 0, "kind": "gallery", "status": "done", "use": True, "url": TU,
                                        "translated_url": TU, "boxes_img": TU, "box_frame": "identity", "box_size": [2000, 2000],
                                        "boxes": [{"x": 100, "y": 100, "w": 600, "h": 90, "src": "菲尚丽家", "tgt": "피샹리가"},
                                                  {"x": 100, "y": 900, "w": 600, "h": 90, "src": "下单享好礼", "tgt": "주문 시 선물"}]}]}
    r = IE.apply(ex, "gallery", 0, [{"id": "t0", "action": "restore"}, {"id": "t1", "action": "text", "text": "선물"}],
                 by="polish", small=Image.new("RGB", (64, 64)))
    assert r["ok"] and got.get("restore") == [] and got.get("orig_raw") == b""


# ── 같은 유형: 틀 확인 · 좌우반전 확인 ────────────────────────────────────────────────────────────

def test_box_frame_small_gray_does_not_decode_big_png(monkeypatch):
    from src.services import box_frame as BF
    with pytest.raises(ValueError):
        BF._gray_small(_PNG.read_bytes())                          # 디코드 상한 — 풀지 않고 사유
    g, (W, H) = BF._gray_small(_jpeg(3000))
    assert (W, H) == (3000, 3000) and max(g.size) <= BF.SMALL_SIDE


def test_box_frame_scores_in_box_space_when_original_is_a_shrunk_copy():
    """원본이 축소 사본(2000)이어도 상자는 번역 기록 공간(3000) 그대로 맞는다 — 같은 자리를 잰다."""
    from PIL import Image, ImageDraw
    from src.services import box_frame as BF

    def img(side, text):
        im = Image.new("RGB", (side, side), (250, 250, 250))
        if text:
            ImageDraw.Draw(im).rectangle([int(side * .1), int(side * .1), int(side * .4), int(side * .2)], fill=(0, 0, 0))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=90)
        return b.getvalue()
    box = [{"x": 300, "y": 300, "w": 900, "h": 300}]               # 3000 공간의 글자 자리
    got = BF.pick(img(2000, True), img(3000, False), box, space=[3000, 3000])
    assert got["frame"] == "identity" and got["boxes"][0]["x"] == 300


def test_flip_check_big_png_is_not_decoded():
    from src.services import flip_check as F
    out = F.compare(_PNG.read_bytes(), _PNG.read_bytes())
    assert out["verdict"] == "판정 못 함" and "풀지 않았어요" in out["why"]
    same = F.compare(_jpeg(3000), _jpeg(3000))
    assert same["verdict"] == "같음"
