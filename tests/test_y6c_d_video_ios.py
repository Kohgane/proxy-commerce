"""Y6-C D(오너 2026-10-07 21:17 KST, 가족 iPhone Safari) — 상품 「이식 현대 디자이너 소파 의자 … Desede」(1225 CNY) 동영상 재생 불가.

실측(그 상품 7ac5ef91 · Cloudinary 파일):
- curl(iOS Safari UA) → HTTP/2 200 `video/mp4;codecs=avc1` · Range 0-1 → **206** `content-range: bytes 0-1/2564608` · accept-ranges bytes.
- ffmpeg -i → h264 (Constrained Baseline) L3.1 · yuv420p · 540×720 · 30fps · moov가 mdat 앞(faststart) — iOS 재생 조건 충족.
- 원인 = **앱 CSP**: `default-src 'self'`에 `media-src`가 없어 <video src=https://res.cloudinary.com/…>를 브라우저가 막았다.
  포스터 jpg는 img-src https:라 보여서 「재생만 안 됨」으로 보였다.
수리: media-src에 res.cloudinary.com · ffmpeg 한 줄 고정(libx264 high · yuv420p · faststart, copy 없음) ·
<video playsinline muted preload="metadata" controls> · 실패 배지 「동영상을 불러오지 못했어요 — 사유」 + 「다시 변환」.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

CLD = "https://res.cloudinary.com/dzxkl9put/video/upload/v1791375420/proxy-commerce/videos/video-y6cd.mp4"


def _client(uid="y6c-d"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
    return c


def _item(video, uid="y6c-d"):
    from src.seller_console import collect_history_store as S
    return S.append(source="share", url="https://item.taobao.com/item.htm?id=511822926875", seller_id=uid,
                    title="이탈리안 스타일 소파 의자", price="1225", currency="CNY",
                    extra={"title_ko": "이탈리안 스타일 소파 의자", "price": "1225", "currency": "CNY",
                           "images": ["https://img.alicdn.com/a.jpg"], "video": video,
                           "provider_detail": {"video_url": "https://cloud.video.taobao.com/play/u/1/x.mp4"}})


DONE = {"state": "done", "url": CLD, "thumb": CLD.replace("/upload/", "/upload/so_0/").replace(".mp4", ".jpg"),
        "duration": 24.93, "height": 720, "audio": False, "mode": "encode", "source_url": "https://cloud.video.taobao.com/play/u/1/x.mp4"}


def test_page_csp_allows_cloudinary_media():
    r = _client().get(f"/seller/m/item/{_item(DONE)}")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "media-src 'self' https://res.cloudinary.com" in csp and "default-src 'self'" in csp
    assert "media-src *" not in csp and "media-src https:" not in csp                 # 좁게 — Cloudinary만


def test_video_tag_has_ios_attributes():
    h = _client().get(f"/seller/m/item/{_item(DONE)}").get_data(as_text=True)
    tag = h[h.index('<video'):h.index('</video>')]
    for a in (" playsinline", " muted", 'preload="metadata"', " controls", f'src="{CLD}"'):
        assert a in tag
    assert 'data-role="m5-video-fail" hidden' in h                                     # 실패 배지는 재생 오류 때만


@pytest.mark.parametrize("code, why", [
    ("fetch_failed", "원본을 받지 못했어요 — HTTP 403"),
    ("codec_unsupported", "영상 형식을 바꾸지 못했어요 — ffmpeg 실패: Invalid data"),
    ("upload_failed", "Cloudinary 업로드 실패 — 자격 미설정"),
])
def test_failed_badge_and_reconvert_button(code, why):
    h = _client().get(f"/seller/m/item/{_item({'state': 'failed', 'code': code, 'why': why, 'source_url': 'https://x/v.mp4'})}").get_data(as_text=True)
    box = h.split('data-role="m5-video-fail"')[1][:500]
    assert f'data-code="{code}"' in box and "동영상을 불러오지 못했어요 — " + why.split(" — ")[0] in box
    assert 'data-role="m5-video-reconvert"' in box and "다시 변환" in box


def test_reconvert_route_kicks_job(monkeypatch):
    from src.services import taobao_auto as A
    from src.seller_console import collect_history_store as S
    kicked = []
    monkeypatch.setattr(A, "kick_video", lambda u, i, s: kicked.append((u, i, s)) or True)
    iid = _item({"state": "failed", "code": "codec_unsupported", "why": "x", "source_url": "https://cloud.video.taobao.com/v.mp4"})
    d = _client().post(f"/seller/collect/{iid}/video-reconvert").get_json()
    assert d == {"ok": True, "state": "pending"} and kicked == [("y6c-d", iid, "https://cloud.video.taobao.com/v.mp4")]
    assert json.loads(S.get(iid, seller_ids={"y6c-d"})["extra_json"])["video"]["state"] == "pending"
    assert _client("someone-else").post(f"/seller/collect/{iid}/video-reconvert").status_code == 404   # 남의 상품 0


@pytest.mark.skipif(not os.path.exists("/opt/pw-browsers/chromium") and not os.environ.get("KGP_REQUIRE_BROWSER"),
                    reason="브라우저 없음")
def test_browser_csp_no_longer_blocks_cloudinary_video():
    """실브라우저(390px): 서버가 실제로 보낸 CSP 헤더로 카드를 띄우고 — Cloudinary 동영상 요청이 CSP 위반 없이 나간다."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    iid = _item(DONE)
    r = _client().get(f"/seller/m/item/{iid}")
    html, csp = r.get_data(as_text=True), r.headers["Content-Security-Policy"]
    mp4 = (Path(__file__).parent.parent / "fixtures" / "video" / "sample_3s_with_audio.mp4").read_bytes()
    hits = []
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page(viewport={"width": 390, "height": 900})

        def handle(route):
            u = route.request.url
            if u.endswith(f"/seller/m/item/{iid}"):
                return route.fulfill(status=200, content_type="text/html", body=html, headers={"Content-Security-Policy": csp})
            if u.startswith("https://res.cloudinary.com/") and u.endswith(".mp4"):
                hits.append(u)
                return route.fulfill(status=200, content_type="video/mp4", body=mp4)
            return route.fulfill(status=200, content_type="application/json", body="{}")
        pg.route("**/*", handle)
        pg.add_init_script("window.__csp = []; document.addEventListener('securitypolicyviolation', e => window.__csp.push([e.violatedDirective, e.blockedURI]));")
        pg.goto(f"http://kgp.test/seller/m/item/{iid}")
        pg.evaluate("document.querySelector('[data-role=m5-video-player]').load()")
        pg.wait_for_timeout(800)
        viol = pg.evaluate("window.__csp")
        b.close()
    assert not [v for v in viol if "cloudinary" in (v[1] or "")], viol
    assert hits and hits[0] == CLD
