"""Y13-F F2(오너 2026-10-19) — 스마트스토어 셰고가·고코스모스(BLACKHOLES) 「이미지 업로드 실패(최대 3회, 전송 3,633,210B):
릴레이가 HTTP 413」.

뿌리: 대표 4장을 **한 요청**에 담아 릴레이 base64 봉투가 nginx `client_max_body_size 4m`를 넘었다 → 413을 예외 재시도로
3회 × 스로틀 백오프. 고친 것: ① 대표도 바이트 상한으로 나눠 올림 ② 413은 즉시 「사진 용량 초과 · 장 번호」(재시도·대기 0)
③ 상세 묶음은 넣기 **전에** 잰다 ④ Cloudinary 축소본 JPEG 품질 85.
"""
from unittest.mock import MagicMock, patch

import pytest

from src.collectors.image_norm import FetchedImage
from src.market_relay import RelayError, RelayTooLarge


def _img(n):
    return FetchedImage(b"x" * n, "image/jpeg", "jpg")


def _up():
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as U
    up = U.__new__(U)
    up.client_id, up.account, up.token_error = "cid", "", ""
    up._get_access_token = lambda: "tok"
    return up


def test_throttle_does_not_retry_no_retry_exception():
    from src.market_throttle import throttled_request
    calls = []

    def boom():
        calls.append(1)
        raise RelayTooLarge("릴레이가 HTTP 413")
    with patch("src.market_throttle.time.sleep") as sl:
        with pytest.raises(RelayTooLarge):
            throttled_request(boom, market="smartstore", key="t413")
    assert len(calls) == 1 and not sl.called


def test_relay_413_raises_too_large(monkeypatch):
    from src import market_relay as R
    r = MagicMock()
    r.status_code = 413
    monkeypatch.setattr(R, "api_relay_url", lambda: "https://relay.example/mkt.php")
    monkeypatch.setattr(R, "_api_relay_key", lambda: "k")
    with patch.object(R.requests, "post", return_value=r):
        with pytest.raises(RelayTooLarge) as ei:
            R._api_relay_send("POST", "https://api.commerce.naver.com/x", {}, None, b"abc", 10)
    assert isinstance(ei.value, RelayError) and "413" in str(ei.value)


def test_upload_parts_413_stops_at_once_with_photo_numbers():
    up = _up()
    sent = []

    def relay(*a, **k):
        sent.append(1)
        raise RelayTooLarge("릴레이 오류: 릴레이가 HTTP 413")
    with patch("src.uploaders.naver_uploader.relay_request", side_effect=relay), \
         patch("src.uploaders.naver_uploader.time.sleep") as sl:
        out = up._upload_parts([_img(900_000), _img(800_000)], nos=[2, 3])
    assert len(sent) == 1 and not sl.called
    assert out["ok"] is False and out["too_large"] and out["nos"] == [2, 3]
    assert out["reason"].startswith("사진 용량 초과 · 2번, 3번")
    assert "2번 900,000B" in out["reason"]


def test_rep_upload_is_split_by_bytes_and_keeps_order(monkeypatch):
    monkeypatch.setenv("IMAGE_UPLOAD_CHUNK_BYTES", str(1_500_000))
    up = _up()
    sizes = {"u1": 900_000, "u2": 800_000, "u3": 700_000, "u4": 600_000}
    up._fetch_image = lambda n, on_skip=None: _img(sizes[n.rsplit("/", 1)[-1]])
    batches = []

    def parts(cleaned, nos=None):
        batches.append(list(nos))
        return {"ok": True, "urls": [f"cdn{n}" for n in nos], "reason": ""}
    up._upload_parts = parts
    out = up.upload_images([f"https://img.example/u{i}" for i in range(1, 5)])
    assert out["ok"] and out["urls"] == ["cdn1", "cdn2", "cdn3", "cdn4"]
    assert batches == [[1], [2, 3], [4]]                       # 묶음마다 1.5MB 이하(넣기 전에 잰다)
    assert out["requests"] == 3


def test_rep_upload_reports_413_photo_numbers():
    up = _up()
    up._fetch_image = lambda n, on_skip=None: _img(100)
    up._upload_parts = lambda cleaned, nos=None: {"ok": False, "urls": [], "too_large": True, "nos": nos,
                                                  "reason": "사진 용량 초과 · 1번"}
    out = up.upload_images(["https://img.example/a"])
    assert out["ok"] is False and out["reason"].startswith("사진 용량 초과")


def test_small_copy_asks_cloudinary_for_q85(monkeypatch):
    from src.media import image_pipeline as IPL
    seen = {}

    def fake_remote(url, **kw):
        seen.update(kw)
        return {"ok": False, "error": "x"}
    monkeypatch.setattr(IPL, "upload_remote", fake_remote)
    IPL.small_copy("https://img.example/big.webp")
    assert seen["quality"] == 85 and seen["max_side"] == 2000
    monkeypatch.setenv("IMAGE_SMALL_COPY_QUALITY", "0")
    pid85 = seen["public_id"]
    IPL.small_copy("https://img.example/big.webp")
    assert seen["quality"] == 0 and seen["public_id"] != pid85      # 품질이 바뀌면 다른 사본 이름


def test_upload_product_413_is_held_with_non_retry_code():
    from src.seller_console.upload_dispatcher import RETRYABLE_CODES
    up = _up()
    up.image_upload_enabled = True
    up.upload_images = lambda urls: {"ok": False, "urls": [], "too_large": True, "skipped": [],
                                     "reason": "사진 용량 초과 · 1번"}
    out = up.upload_product({"sku": "s", "images": ["https://img.example/a.jpg"]})
    assert out["held"] and out["reason_code"] == "naver_image_too_large"
    assert out["reason_code"] not in RETRYABLE_CODES             # 같은 몸통은 같은 답 — 재시도 버튼 없음
