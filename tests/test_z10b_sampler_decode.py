"""Z10-B(오너 2026-10-11 KST OOM 02:10·02:20·02:25·02:30·02:33) — 200ms 샘플러 · 디코드 가드 · 이미지 저장본 원격 업로드.

02:24:30 사전검증 job=3aaff0c7: `pv_job_start rss=156 peak=156` → `image_fetch n=1/5 rss=159 peak=417`(3초).
그 1번 장은 303KB **PNG** — 같은 시각 같은 프로세스의 `cpx-check`(쿠팡 대표 사진 판정)가 그 PNG를 원본 화소로 풀고
(draft는 JPEG 전용) RGB 사본을 만들고, OCR 줄이기가 한 번 더 풀었다. 02:10·02:20·02:30은 `/cron/image-copies`가
장마다 스레드를 띄워 원본을 풀고 6초 넘으면 스레드를 버리고 다음 장으로 간 시각이다.
"""
from __future__ import annotations

import io
import threading
import time

import pytest


def _png(w, h, mode="RGBA"):
    from PIL import Image
    b = io.BytesIO()
    Image.new(mode, (w, h), (255, 255, 255, 0) if mode == "RGBA" else (255, 255, 255)).save(b, "PNG")
    return b.getvalue()


def _jpeg(w, h):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(b, "JPEG", quality=80)
    return b.getvalue()


# ── 샘플러 ─────────────────────────────────────────────────────────────────────────────────────

def _hold_mb(mb, sec):
    blob = bytearray(mb * 1024 * 1024)
    for i in range(0, len(blob), 4096):
        blob[i] = 1                                           # 실제로 페이지를 잡게
    time.sleep(sec)
    del blob


def test_sampler_catches_peak_between_boundaries(monkeypatch):
    """단계 경계(시작·끝)만 재면 0, 샘플러는 그 사이 +80MB를 본다."""
    monkeypatch.setenv("Z10_SAMPLE_MS", "50")
    from src.utils import rss, rss_sampler as S
    with S.watch("t_between") as w:
        a, _ = rss.read_mb()
        _hold_mb(80, 0.5)
        b, _ = rss.read_mb()
    assert w["peak"] - w["base"] >= 60, w
    assert w["samples"] >= 3 and w["peak_at"] > 0
    assert S.active_count() == 0


def test_trace_names_the_thread_and_frame(monkeypatch):
    """Z10_TRACE=1 — 피크 순간 스레드별 맨 위 프레임 + tracemalloc 상위(가능하면)."""
    monkeypatch.setenv("Z10_SAMPLE_MS", "50")
    monkeypatch.setenv("Z10_TRACE", "1")
    from src.utils import rss_sampler as S

    def decode_like_cpx_check():
        _hold_mb(60, 0.6)
    with S.watch("t_trace") as w:
        th = threading.Thread(target=decode_like_cpx_check, name="cpx-check")
        th.start()
        th.join()
    assert any("cpx-check" in s for s in w["stacks"]), w["stacks"]
    assert w["top"], "tracemalloc 상위가 비었다"


def test_guard_stops_the_job_after_a_transient_spike(monkeypatch):
    """경계 사이에 상한을 넘었다 내려와도 — 샘플러가 봤으면 다음 경계(guard)에서 그 잡만 멈춘다."""
    monkeypatch.setenv("Z10_SAMPLE_MS", "50")
    from src.utils import rss, rss_sampler as S
    base, _ = rss.read_mb()
    monkeypatch.setenv("PREVALIDATE_RSS_LIMIT_MB", str(base + 40))
    tok = rss.JOB.set("job-spike")
    try:
        with S.watch("pv_job", job="job-spike"):
            _hold_mb(90, 0.5)
            assert rss.read_mb()[0] < base + 40 + 20                          # 지금은 내려와 있다
            with pytest.raises(rss.MemoryCapExceeded) as e:
                rss.guard("image_fetch", "사진 1/5장째")
        assert "샘플러가" in str(e.value)
    finally:
        rss.JOB.reset(tok)


def test_worker_restart_waits_for_running_jobs(monkeypatch, tmp_path):
    import importlib.util
    monkeypatch.setenv("WORKER_RSS_LIMIT_MB", "380")
    monkeypatch.setenv("WORKER_RSS_RESTART_STAMP", str(tmp_path / "stamp"))
    spec = importlib.util.spec_from_file_location("gconf_b", "gunicorn.conf.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)

    class W:
        pid, alive = 7, True
        log = type("L", (), {"warning": lambda *a, **k: None})()
    monkeypatch.setattr(g, "_worker_rss_mb", lambda: 401)
    from src.utils import rss_sampler as S
    w = W()
    with S.watch("pv_job", job="abc"):
        g.post_request(w, None, None, None)
        assert w.alive is True                                                  # 잡이 도는 중 — 남는다
    g.post_request(w, None, None, None)
    assert w.alive is False                                                     # 잡이 끝난 뒤 첫 요청에서


def test_cron_and_pv_job_run_under_the_sampler(monkeypatch):
    from src.utils import bg_job, rss_sampler as S
    seen = []
    bg_job.start("z10b-probe", lambda: seen.append(S.active_names()) or {"ok": True})
    bg_job.join("z10b-probe", timeout=5)
    assert seen and "cron_z10b-probe" in seen[0]


# ── 디코드 가드 ───────────────────────────────────────────────────────────────────────────────

def test_big_png_is_not_decoded(monkeypatch):
    monkeypatch.setenv("IMAGE_DECODE_MAX_PIXELS", "1000000")
    from PIL import Image
    from src.collectors.image_norm import open_small
    raw = _png(2000, 2000)
    loads = []
    real = Image.Image.load
    monkeypatch.setattr(Image.Image, "load", lambda self: loads.append(self.format) or real(self))
    im, fmt, w, h, why = open_small(raw, 1024)
    assert im is None and (fmt, w, h) == ("PNG", 2000, 2000) and "풀지 않았어요" in why
    assert loads == []                                                          # 화소를 안 풀었다


def test_jpeg_is_drafted_and_png_reduced_before_rgb(monkeypatch):
    monkeypatch.setenv("IMAGE_DECODE_MAX_PIXELS", "12000000")
    from src.collectors.image_norm import open_small
    im, fmt, w, h, why = open_small(_jpeg(4000, 3000), 1000)
    assert fmt == "JPEG" and (w, h) == (4000, 3000) and max(im.size) <= 1000 and im.mode == "RGB" and not why
    im2, *_ = open_small(_png(1600, 1600), 400)
    assert max(im2.size) <= 400 and im2.mode == "RGB" and im2.getpixel((0, 0)) == (255, 255, 255)   # 투명 → 흰 배경


def test_cpx_check_big_png_skips_white_but_keeps_size(monkeypatch):
    monkeypatch.setenv("IMAGE_DECODE_MAX_PIXELS", "1000000")
    from src.services import coupang_image_check as C
    import src.services.ocr_tencent as O
    sent = []
    monkeypatch.setattr(O, "is_configured", lambda: True)
    monkeypatch.setattr(O, "_call", lambda b64: sent.append(len(b64)) or {"TextDetections": []})
    raw = _png(2400, 2400)
    r = C.check_bytes(raw)
    assert r["state"] == "ok" and (r["w"], r["h"]) == (2400, 2400) and r["white_pct"] is None and r["decode_why"]
    assert sent and sent[0] == len(__import__("base64").b64encode(raw))       # OCR엔 원본 PNG 그대로(우리가 안 풂)


def test_ocr_shrink_small_png_still_shrinks(monkeypatch):
    monkeypatch.setenv("IMAGE_DECODE_MAX_PIXELS", "12000000")
    from src.services.ocr_tencent import shrink
    from PIL import Image
    out = shrink(_png(2000, 1000))
    with Image.open(io.BytesIO(out)) as im:
        assert im.format == "JPEG" and max(im.size) == 1024


def test_naver_shrink_skips_undecodable_png(monkeypatch):
    monkeypatch.setenv("IMAGE_DECODE_MAX_PIXELS", "1000000")
    from src.collectors.image_norm import shrink_image_bytes
    assert shrink_image_bytes(_png(3000, 3000), max_pixels=4_000_000, max_width=2000) is None


# ── 이미지 저장본 크론 ─────────────────────────────────────────────────────────────────────────

def test_copy_falls_back_to_bytes_in_the_same_thread(monkeypatch):
    import src.api.extension_api as ea
    from src.media import image_pipeline as P
    from src.collectors import image_norm as N
    calls = []

    def up(src, **kw):
        calls.append("url" if isinstance(src, str) else len(src))
        if isinstance(src, str):
            return {"ok": False, "error": "Error in loading https://img.alicdn.com/x.jpg - 403"}
        return {"ok": True, "secure_url": "https://res.cloudinary.com/x/1.jpg"}
    monkeypatch.setattr(P, "upload_remote", up)
    monkeypatch.setattr(N, "fetch_image_bytes", lambda url, **kw: N.FetchedImage(_jpeg(300, 300), "image/jpeg", "jpg"))
    monkeypatch.setattr(ea, "_cdn_configured", lambda: True)
    before = threading.active_count()
    out = ea._store_image_copies(["https://img.alicdn.com/x.jpg", "https://img.alicdn.com/y.jpg"], item_id="301c02cd", budget_sec=30)
    assert out["images_stored"] == ["https://res.cloudinary.com/x/1.jpg"] or len(out["images_stored"]) >= 1
    assert "원격 0 · 직접 2" in out["images_stored_note"]
    assert calls[0] == "url" and isinstance(calls[1], int)                       # 원격 먼저 → 실패하면 바이트
    assert threading.active_count() == before


def test_remote_upload_passes_url_and_size_limit(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "x")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "x")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "x")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    import cloudinary.uploader as CU
    from src.media import image_pipeline as P
    monkeypatch.setattr(P, "_CDN_UPLOAD_ENABLED", True, raising=False)
    got = {}
    monkeypatch.setattr(CU, "upload", lambda src, **o: got.update(src=src, **o) or {"secure_url": "https://res.cloudinary.com/x/a.jpg"})
    r = P.upload_remote("https://img.alicdn.com/a.png", timeout=12)
    assert r["ok"] and got["src"] == "https://img.alicdn.com/a.png"            # 바이트가 아니라 URL
    assert got["transformation"] == [{"width": 2000, "height": 2000, "crop": "limit"}] and got["timeout"] == 12.0
