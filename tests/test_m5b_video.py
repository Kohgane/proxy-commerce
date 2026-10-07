"""M5 후속(오너 2026-10-07) — 상품 동영상: 무음 mp4(최대 30초 · 720p 이하 · 20MB 이하) → Cloudinary → 카드 썸네일.

픽스처 `fixtures/video/sample_3s_with_audio.mp4`: 3초 · 1280×960 h264 + AAC 오디오(재인코딩 경로를 탄다).
마켓 전송은 공식 근거가 있을 때만(지금은 0곳) — 카드에 마켓마다 「동영상 미지원」과 근거.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FX = Path(__file__).parent.parent / "fixtures" / "video" / "sample_3s_with_audio.mp4"


@pytest.fixture(autouse=True)
def _need_ffmpeg():
    from src.media import video_silent as V
    assert V.ffmpeg_exe(), "ffmpeg가 없다 — requirements의 imageio-ffmpeg(또는 PATH ffmpeg)가 필요"


def test_fixture_really_has_audio_and_is_big():
    from src.media import video_silent as V
    p = V.probe(str(FX))
    assert p["ok"] and p["audio"] is True and p["height"] == 960 and p["codec"] == "h264" and 2.5 < p["duration"] < 3.5


def test_make_silent_reencodes_to_720_without_audio(tmp_path):
    from src.media import video_silent as V
    out = tmp_path / "s.mp4"
    r = V.make_silent(str(FX), str(out))
    assert r["ok"] and r["mode"] == "encode" and r["audio"] is False                 # 오디오 스트림 0개
    assert r["height"] <= 720 and r["duration"] <= 30 and r["bytes"] <= 20 * 1024 * 1024
    assert V.probe(str(out))["audio"] is False


def test_make_silent_copies_when_already_h264_720(tmp_path):
    """이미 h264·720 이하면 재인코딩하지 않는다(지뢰 「Render 512MB ffmpeg OOM」 — libx264가 메모리 피크)."""
    from src.media import video_silent as V
    mid, out = tmp_path / "mid.mp4", tmp_path / "out.mp4"
    assert V.make_silent(str(FX), str(mid))["ok"]
    r = V.make_silent(str(mid), str(out))
    assert r["ok"] and r["mode"] == "copy" and r["audio"] is False


def test_process_uploads_video_and_builds_thumb(monkeypatch):
    from src.media import image_pipeline as IP
    from src.media import video_silent as V
    monkeypatch.setattr(V, "_download", lambda url, dst: shutil.copy(FX, dst) and None)
    sent = {}

    def _up(raw, **kw):
        sent.update(kw, n=len(raw))
        return {"ok": True, "secure_url": "https://res.cloudinary.com/demo/video/upload/v1/proxy-commerce/videos/video-i1.mp4"}
    monkeypatch.setattr(IP, "upload_bytes", _up)
    rec = V.process("https://cloud.video.taobao.com/play/u/1/p/1/e/6/t/1/x.mp4", label="video-i1")
    assert rec["state"] == "done" and rec["audio"] is False and sent["resource_type"] == "video"
    assert rec["thumb"] == "https://res.cloudinary.com/demo/video/upload/so_0/v1/proxy-commerce/videos/video-i1.jpg"
    assert sent["n"] <= 20 * 1024 * 1024


def test_process_failures_are_reasons_not_exceptions(monkeypatch):
    from src.media import image_pipeline as IP
    from src.media import video_silent as V
    monkeypatch.setattr(V, "_download", lambda url, dst: "HTTP 403")
    assert V.process("https://x/v.mp4")["why"] == "원본을 받지 못했어요 — HTTP 403"
    monkeypatch.setattr(V, "_download", lambda url, dst: shutil.copy(FX, dst) and None)
    monkeypatch.setattr(IP, "upload_bytes", lambda raw, **kw: {"ok": False, "error": "Cloudinary 자격 미설정: CLOUDINARY_API_KEY"})
    r = V.process("https://x/v.mp4")
    assert r["state"] == "failed" and "CLOUDINARY_API_KEY" in r["why"]
    assert V.process("")["state"] == "none"


def test_market_lines_are_honest():
    from src.media import video_silent as V
    lines = V.market_lines(["coupang:woojoo", "coupang:gogane", "smartstore:gocosmos", "shopify"])
    assert len(lines) == 3 and all("동영상 미지원" in x for x in lines)
    assert any("커머스API" in x for x in lines) and not any(V.MARKET_VIDEO[m][0] for m in V.MARKET_VIDEO)


def _item(extra):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "슬립 원피스", "images": ["https://img.alicdn.com/a.jpg"] * 2, "price": "328", "currency": "CNY"}
    ex.update(extra)
    return S.append(source="share_text", url="https://item.taobao.com/item.htm?id=1", seller_id="m5b-vid",
                    title="슬립 원피스", price="328", currency="CNY", extra=ex)


def _card(iid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "m5b-vid"
    return c.get(f"/seller/m/item/{iid}").get_data(as_text=True)


def test_video_job_saves_and_card_plays_muted(monkeypatch):
    from src.media import video_silent as V
    from src.seller_console import collect_history_store as S
    from src.services import taobao_auto as A
    iid = _item({"provider_detail": {"video_url": "https://cloud.video.taobao.com/x.mp4"}})
    h = _card(iid)
    assert 'data-role="m5-video" data-state="pending"' in h and "무음으로 만드는 중" in h
    monkeypatch.setattr(V, "process", lambda src, label="": {
        "state": "done", "url": "https://res.cloudinary.com/d/video/upload/v1/x.mp4",
        "thumb": "https://res.cloudinary.com/d/video/upload/so_0/v1/x.jpg", "duration": 3.0, "height": 720,
        "audio": False, "mode": "encode", "source_url": src})
    A._video_job("m5b-vid", iid, "https://cloud.video.taobao.com/x.mp4")
    ex = json.loads(S.get(iid, seller_ids={"m5b-vid"})["extra_json"])
    assert ex["video"]["state"] == "done" and ex["video_url"].endswith("x.mp4")
    h = _card(iid)
    assert 'data-role="m5-video-player"' in h and " muted " in h and 'poster="https://res.cloudinary.com/d/video/upload/so_0/v1/x.jpg"' in h
    assert "무음 동영상 3초 · 720p" in h and h.count('data-role="m5-video-market"') >= 3


def test_no_video_no_block_and_kick_respects_switch(monkeypatch):
    from src.services import taobao_auto as A
    assert 'data-role="m5-video"' not in _card(_item({}))
    monkeypatch.setenv("VIDEO_COLLECT", "0")
    assert A.kick_video("u", "i", "https://x/v.mp4") is False
