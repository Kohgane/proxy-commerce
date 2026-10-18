"""Y13-A(오너 2026-10-18 15:43 BLACKHOLES·피샹리) — detail_judge MemoryCapExceeded(470>460MB).

실측(사전검증 잡 983b0b69 기록): 인스턴스 시작 413MB(시작 문지기 420 바로 아래) → 네이버 상세 CDN 미리 올리기(prewarm) 10.8초에
샘플러가 470MB → detail_judge 문지기가 그 기록으로 멈춤. 여유가 47MB뿐인데 한 번에 4MB 묶음(릴레이 사본 7~8벌) · 2,000px 디코드였다.
규칙: 상세 장은 한 장씩 받아 바로 올리고 버린다(묶음 1.5MB) · 상세 가로 상한 1,000px(JPEG은 디코드부터 1/4) · 묶음마다 gc+malloc_trim ·
세로로 긴 장은 Cloudinary 사본도 가로만 묶는다(긴 변 상자에 넣으면 790×20,000 → 79×2,000).
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _jpeg(w, h, seed):
    from PIL import Image, ImageFilter
    n = Image.effect_noise((w // 4, h // 4), 64).resize((w, h)).filter(ImageFilter.GaussianBlur(1))
    g = Image.linear_gradient("L").resize((w, h))
    im = Image.merge("RGB", (n, g, Image.eval(n, lambda v: (v * seed) % 256)))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=92)
    return b.getvalue()


def test_detail_width_cap_and_chunk_defaults(monkeypatch):
    from src.uploaders import naver_uploader as NU
    monkeypatch.delenv("IMAGE_UPLOAD_CHUNK_BYTES", raising=False)
    monkeypatch.delenv("IMAGE_DETAIL_MAX_WIDTH", raising=False)
    assert NU._chunk_bytes() == 1536 * 1024
    assert NU._detail_max_width() == 1000


def test_detail_page_shrunk_to_width_cap_even_when_small_bytes(monkeypatch):
    """1.5MB 미만이어도 가로가 상한을 넘으면 줄인다 — 세로로 긴 장은 가로만 줄고 세로 비율은 그대로."""
    from PIL import Image
    from src.collectors import image_norm as N
    body = _jpeg(1600, 4000, 3)
    assert len(body) < 1536 * 1024 * 4

    class R:
        status_code, headers, content = 200, {"Content-Type": "image/jpeg"}, body

        def raise_for_status(self):
            pass
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    got = N.fetch_image_bytes("https://img.alicdn.com/imgextra/x.jpg", allowed_formats={"jpg", "png", "gif", "bmp"},
                              max_width=1000)
    w, h = Image.open(io.BytesIO(got.data)).size
    assert w == 1000 and h == 2500


def test_tall_page_cloudinary_copy_limits_width_only(monkeypatch):
    """세로로 긴 큰 장(디코드 상한 초과 · JPEG 아님) — Cloudinary 사본을 가로 상한으로만 묶어 달라고 한다."""
    from src.collectors import image_norm as N
    seen = {}

    def fake_small_copy(u, **kw):
        seen.update(kw)
        return _jpeg(400, 4000, 2), ""
    import src.media.image_pipeline as IP
    monkeypatch.setattr(IP, "small_copy", fake_small_copy)
    monkeypatch.setattr(N, "image_head", lambda b: ("PNG", 790, 20000))
    out = N._offload_big("https://img.alicdn.com/a.png", b"x" * 10, "png", False, None, max_width=1000)
    assert seen.get("max_width") == 1000 and out is not None
    monkeypatch.setattr(N, "image_head", lambda b: ("PNG", 5120, 5120))
    seen.clear()
    N._offload_big("https://img.alicdn.com/b.png", b"x" * 10, "png", False, None, max_width=1000)
    assert seen.get("max_width") == 0                                     # 정사각 큰 장은 예전처럼 긴 변 상자


def test_cloudinary_width_only_transformation(monkeypatch):
    import types
    import src.media.image_pipeline as IP
    calls = []
    up = types.SimpleNamespace(upload=lambda payload, **opts: calls.append(opts) or {"secure_url": "https://res.cloudinary.com/x.jpg"})
    fake = types.SimpleNamespace(uploader=up, config=lambda **k: None)
    monkeypatch.setitem(sys.modules, "cloudinary", fake)
    monkeypatch.setitem(sys.modules, "cloudinary.uploader", up)
    monkeypatch.setattr(IP, "_cloudinary_configured", lambda: True)
    monkeypatch.setattr(IP, "_CDN_UPLOAD_ENABLED", True)
    monkeypatch.setenv("ADAPTER_DRY_RUN", "0")
    r = IP.upload_remote("https://img.alicdn.com/a.png", folder="conv", public_id="p", fmt="jpg", max_side=2000, max_width=1000)
    assert r["ok"], r
    assert calls[-1]["transformation"] == [{"width": 1000, "crop": "limit"}]
    IP.upload_remote("https://img.alicdn.com/b.png", folder="conv", public_id="q", fmt="jpg", max_side=2000)
    assert calls[-1]["transformation"] == [{"width": 2000, "height": 2000, "crop": "limit"}]



def test_peak_one_pass_blackholes_like(tmp_path):
    """BLACKHOLES 모양 원본(4,160px JPEG ~10MB) 3장 — 네이버 상세 올리기 한 번의 피크(새 프로세스 VmHWM).
    Y13-A 전 같은 하네스 실측 97MB(5장 · 4MB 묶음 · 2,000px) — 이제 묶음 ≤ 1.5MB(+마지막 1장) · 가로 1,000px."""
    for i in range(3):
        (tmp_path / f"bh_{i}.jpg").write_bytes(_jpeg(4160, 4160, i + 3))
    env = dict(os.environ, PROBE_WARM="1")
    for k in ("IMAGE_UPLOAD_CHUNK_BYTES", "IMAGE_DETAIL_MAX_WIDTH", "DATABASE_URL", "SUPABASE_DB_URL"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, str(ROOT / "scripts/z10/mem_probe.py"), str(tmp_path), "bh"], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=200)
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("{")]
    assert line, out.stderr[-2000:]
    r = json.loads(line[-1])
    print("Y13-A peak", r)
    assert r["kept"] == 3 and r["dropped"] == 0
    assert all(u["bytes"] <= 1536 * 1024 + 700 * 1024 for u in r["uploads"])          # 묶음 상한 + 마지막 한 장
    assert r["peak_delta_mb"] < 60, r


def test_start_gate_reclaims_once_before_refusing(monkeypatch):
    """운영 실측(10-18): 인스턴스 바닥 413~414MB · 시작 상한 420 — 일회성 작업·갱신 큐가 「시작 거부」로 멈췄다.
    상한 이상이면 gc+malloc_trim 한 번 뒤 다시 잰다(상한 숫자는 그대로)."""
    from src.utils import rss
    from src.utils import render_worker as RW
    monkeypatch.delenv("INSTANCE_MEM_START_MAX_MB", raising=False)
    trims = []
    monkeypatch.setattr(RW, "trim", lambda: trims.append(1) or True)
    vals = iter([421, 405])
    monkeypatch.setattr(rss, "instance_mb", lambda: next(vals))
    assert rss.start_ok() == (True, 405, 420) and trims == [1]
    vals2 = iter([430, 428])
    monkeypatch.setattr(rss, "instance_mb", lambda: next(vals2))
    assert rss.start_ok() == (False, 428, 420)
    monkeypatch.setattr(rss, "instance_mb", lambda: 300)
    trims.clear()
    assert rss.start_ok() == (True, 300, 420) and trims == []                # 여유가 있으면 건드리지 않는다
