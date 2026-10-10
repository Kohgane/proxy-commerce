"""Z10(오너 2026-10-10 22:29~22:35 KST — 네이버 사전검증 1건 159→420MB(+261), Render 512MB 초과 2회).

범인 단계: 네이버 상세 본문 사진 올리기(`cdn_map` — 사전검증 detail_judge·prewarm). BLACKHOLES 갤러리 5장은 타오바오 **원본**
(크기 꼬리 없음 · 4,160px JPEG + PNG). 예전엔 전부 받아 둔 뒤 한 번에 올렸다 — 받은 바이트 + multipart + 릴레이 base64 + JSON이
7~8벌 동시에 떴다(재현: +228MB). 이제: 한 장씩 받기(큰 원본은 받은 자리에서 줄임 · 디코드는 프로세스당 1장) → 4MB 묶음으로 올리고 버림.
지킴이: 사전검증 잡 프로세스당 1개(줄 서기) · 잡 안 RSS 400MB 넘으면 그 잡만 멈춤 · 워커 RSS 380MB 넘으면 그 워커만 재시작.
"""
from __future__ import annotations

import io
import threading
import time

import pytest


def _jpeg(w, h, q=85):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (120, 30, 200)).save(b, "JPEG", quality=q)
    return b.getvalue()


# ── 이미지: 한 장씩 · 묶음 상한 · 큰 원본 줄임 ───────────────────────────────────────────────

def test_cdn_map_fetches_one_at_a_time_and_uploads_in_small_chunks(monkeypatch):
    from src.collectors.image_norm import FetchedImage
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    import src.uploaders.naver_cdn_cache as CC
    monkeypatch.setattr(CC, "get", lambda *a, **k: None)
    monkeypatch.setattr(CC, "put", lambda *a, **k: None)
    monkeypatch.setattr(CC, "put_fail", lambda *a, **k: None)
    monkeypatch.setenv("IMAGE_UPLOAD_CHUNK_BYTES", str(3 * 1024 * 1024))
    live = {"now": 0, "max": 0}
    held_at_upload = []

    def fetch(self, url, on_skip=None):
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        time.sleep(0.01)
        live["now"] -= 1
        return FetchedImage(b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024), "image/jpeg", "jpg")
    monkeypatch.setattr(SS, "_fetch_image", fetch)

    def upload(self, parts):
        held_at_upload.append((len(parts), sum(len(p.data) for p in parts)))
        return {"ok": True, "urls": [f"https://shop-phinf.pstatic.net/{i}.jpg" for i in range(len(parts))], "reason": ""}
    monkeypatch.setattr(SS, "_upload_parts", upload)
    out = SS(account=None).cdn_map([f"https://img.alicdn.com/{i}.jpg" for i in range(7)])
    assert len(out["mapping"]) == 7 and not out["dropped"]
    assert live["max"] == 1                                                        # 한 장씩 받는다
    assert all(b <= 4 * 1024 * 1024 + 16 for _n, b in held_at_upload)              # 묶음 상한(3MB) + 마지막 한 장
    assert [n for n, _b in held_at_upload] == [2, 2, 2, 1]


def test_big_original_is_shrunk_on_fetch_for_naver_only(monkeypatch):
    from src.collectors import image_norm as N
    big = _jpeg(4000, 3000, q=95)
    big += b"\x00" * max(0, 1600 * 1024 - len(big))                                # 1.5MB 넘김(JPEG 끝 뒤 바이트 — 디코드엔 무해)
    monkeypatch.setattr("requests.get", lambda *a, **k: type("R", (), {"content": big, "headers": {"Content-Type": "image/jpeg"},
                                                                       "raise_for_status": lambda self: None})())
    part = N.fetch_image_bytes("https://img.alicdn.com/a.jpg", allowed_formats={"jpg", "png", "gif", "bmp"})
    from PIL import Image
    w, h = Image.open(io.BytesIO(part.data)).size
    assert w == 2000 and h == 1500 and len(part.data) < len(big)
    raw = N.fetch_image_bytes("https://img.alicdn.com/a.jpg")                     # 쿠팡 등(형식 지정 없음)은 손대지 않는다
    assert raw.data == big


def test_tall_detail_image_is_not_shrunk():
    from src.collectors.image_norm import shrink_image_bytes
    assert shrink_image_bytes(_jpeg(790, 15000), max_pixels=16_000_000, max_width=2000) is None


def test_conversion_is_one_at_a_time():
    from src.collectors import image_norm as N
    done = threading.Event()
    with N._CONVERT_LOCK:
        t = threading.Thread(target=lambda: (N.shrink_image_bytes(_jpeg(3000, 100), max_pixels=0, max_width=2000), done.set()))
        t.start()
        assert not done.wait(0.3)                                                  # 다른 장이 풀리는 중이면 기다린다
    assert done.wait(5)


# ── RSS 측정 · 잡 상한 ────────────────────────────────────────────────────────────────────────

def test_rss_lines_carry_job_and_stage(caplog):
    from src.utils import rss
    caplog.set_level("INFO", logger="rss")
    tok = rss.JOB.set("abcdef1234567890")
    try:
        with rss.span("image_fetch", images=1) as sp:
            sp["bytes"] = 123
    finally:
        rss.JOB.reset(tok)
    line = [r.getMessage() for r in caplog.records if "stage=image_fetch" in r.getMessage()][-1]
    assert "job=abcdef12" in line and "bytes=123" in line and "ms=" in line and "delta_mb=" in line


def test_guard_only_inside_a_job(monkeypatch):
    from src.utils import rss
    monkeypatch.setenv("PREVALIDATE_RSS_LIMIT_MB", "1")
    rss.guard("image_fetch")                                                       # 잡 밖 — 막지 않는다
    tok = rss.JOB.set("job-x")
    try:
        with pytest.raises(rss.MemoryCapExceeded) as e:
            rss.guard("image_fetch", "사진 3/5장째")
        assert "메모리 상한" in str(e.value) and "사진 3/5장째" in str(e.value)
    finally:
        rss.JOB.reset(tok)


def test_memory_cap_stops_only_that_job(monkeypatch):
    monkeypatch.setenv("PREVALIDATE_JOB_CONCURRENCY", "1")
    import src.seller_console.views as V
    from src.utils import rss
    from tests._pv_helper import prevalidate

    def boom(data, pd):
        raise rss.MemoryCapExceeded("image_fetch", 431, 400, "사진 4/5장째")
    monkeypatch.setattr(V, "_pv_prepare", boom)
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: object())
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "z10-cap"
    d = prevalidate(c, {"product": {"title": "x", "price": 1}, "markets": ["elevenst"]})
    r = d["results"][0]
    assert r["transport"] == "memory_cap" and "메모리 상한" in r["message"] and "다시 눌러" in r["message"]
    # 다음 사전검증은 평소대로(줄 서기 자리를 돌려줬다)
    assert V._pv_semaphore().acquire(blocking=False)
    V._pv_semaphore().release()


def test_second_job_waits_in_line(monkeypatch):
    monkeypatch.setenv("PREVALIDATE_JOB_CONCURRENCY", "1")                       # 운영 기본값
    import src.seller_console.views as V
    started = threading.Event()
    gate = threading.Event()

    def body(job_id, data, markets, dispatcher):
        started.set()
        gate.wait(5)
        V._pv_update(job_id, state="done")
    monkeypatch.setattr(V, "_pv_job_body", body)
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "z10-q"
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: object())
    j1 = c.post("/seller/collect/prevalidate", json={"product": {"title": "a"}, "markets": ["elevenst"]}).get_json()
    assert started.wait(5)
    j2 = c.post("/seller/collect/prevalidate", json={"product": {"title": "b"}, "markets": ["elevenst"]}).get_json()
    for _ in range(50):
        d2 = c.get(j2["poll"]).get_json()
        if d2.get("queued"):
            break
        time.sleep(0.05)
    assert d2["queued"] is True and "앞 사전검증이 끝나면" in d2["queue_note"] and d2["state"] == "running"
    gate.set()
    for _ in range(100):
        d2 = c.get(j2["poll"]).get_json()
        if d2.get("state") == "done":
            break
        time.sleep(0.05)
    assert d2["state"] == "done" and not d2["queued"]
    assert c.get(j1["poll"]).get_json()["state"] == "done"


def test_cards_show_queue_note():
    from pathlib import Path
    cp = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    m5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert 'data-role="pv-queued"' in cp and "queue_note" in cp
    assert 'data-queued="1"' in m5 and "queue_note" in m5


# ── gunicorn — 이 워커만 재시작 ─────────────────────────────────────────────────────────────────

def test_worker_restarts_alone_over_rss_limit(monkeypatch, tmp_path):
    import importlib.util
    monkeypatch.setenv("WORKER_RSS_LIMIT_MB", "380")
    monkeypatch.setenv("WORKER_RSS_RESTART_STAMP", str(tmp_path / "stamp"))
    spec = importlib.util.spec_from_file_location("gconf", "gunicorn.conf.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)

    class W:
        def __init__(self, pid):
            self.pid, self.alive = pid, True
            self.log = type("L", (), {"warning": lambda *a, **k: None})()
    monkeypatch.setattr(g, "_worker_rss_mb", lambda: 300)
    w = W(1)
    g.post_request(w, None, None, None)
    assert w.alive is True                                                         # 상한 아래 — 그대로
    monkeypatch.setattr(g, "_worker_rss_mb", lambda: 401)
    g.post_request(w, None, None, None)
    assert w.alive is False                                                        # 이 워커만 나간다
    w2 = W(2)
    g.post_request(w2, None, None, None)
    assert w2.alive is True                                                        # 방금 다른 워커가 나갔으면 남는다(둘 다 비우지 않음)
    assert g.max_requests == 200 and g.max_requests_jitter == 50
