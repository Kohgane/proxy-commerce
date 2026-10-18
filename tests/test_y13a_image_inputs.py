"""Y13-A(오너 2026-10-18 15:43~15:46 피샹리 菲尚丽家 1인 소파 · 티몰 851803804374) — 사진 입력 3건.

3. 텐센트 `InvalidParameterValue.Data`: 저장 기록 실측 — 상세 24번 `https://g.alicdn.com/s.gif`(1×1 스페이서)가 그대로 나갔다.
   규칙: 보내기 전에 JPEG 변환·긴 변 4096·4MB · 공급사 최소 20px 미만·형식 미상은 **보내지 않는다**(우리 사유) ·
   그대로 보낸 JPEG·PNG가 Data로 거절되면 JPEG로 다시 구워 **딱 한 번** 다시 보낸다.
4. 상세 1번 ValueError: 주소가 `//img.alicdn.com/…jpg_1200x1200q30.jpg_.webp`(스킴 없음) — urllib이 ValueError.
   #911은 진단 한 곳만 고쳤다 → 모든 이미지 받기 경로가 `image_norm.abs_image_url` 한 함수를 지난다.
5. 「그릴 줄이 없습니다」는 OCR이 정말 0상자일 때만 — 번역이 실패했으면 「번역 실패 · 사유」.
"""
from __future__ import annotations

import io
from unittest.mock import patch

from PIL import Image

FISH_1 = "//img.alicdn.com/imgextra/i3/6000000007737/O1CN010wC6NJ271b2e20Ib4_!!6000000007737-0-shopmanager.jpg_1200x1200q30.jpg_.webp"
FISH_24 = "https://g.alicdn.com/s.gif"


def _img(fmt, w, h):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(b, fmt)
    return b.getvalue()


# ── 4. `//` 주소 ─────────────────────────────────────────────────────────────────────────────────────
def test_abs_image_url():
    from src.collectors.image_norm import abs_image_url
    assert abs_image_url(FISH_1).startswith("https://img.alicdn.com/")
    assert abs_image_url("  https://a.b/c.jpg ") == "https://a.b/c.jpg"
    assert abs_image_url("") == ""


def test_tencent_fetch_image_accepts_protocol_relative_fishangli_1():
    from src.services import image_translate_tencent as tc
    seen = []
    with patch.object(tc, "_download", lambda url, proxies=None: seen.append(url) or _img("JPEG", 800, 800)):
        raw, why = tc.fetch_image(FISH_1)
    assert why == "" and raw and seen == ["https:" + FISH_1]


def test_tencent_fetch_image_real_urllib_no_value_error(monkeypatch):
    """예전 모습 재현 — urllib에 `//…`를 넘기면 ValueError(unknown url type). 이제 https로 열린다."""
    import urllib.request
    from src.services import image_translate_tencent as tc
    opened = []

    class _R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=None):
            return _img("JPEG", 400, 400)

    def _open(req, timeout=None):
        opened.append(req.full_url)
        return _R()
    monkeypatch.setattr(urllib.request, "urlopen", _open)
    raw, why = tc.fetch_image(FISH_1)
    assert why == "" and opened[0].startswith("https://img.alicdn.com/")
    import pytest
    with pytest.raises(ValueError):
        urllib.request.Request(FISH_1)                              # 고치기 전 경로가 던지던 것(재현)


def test_fetch_image_bytes_and_coupang_check_accept_protocol_relative(monkeypatch):
    import requests
    from src.collectors import image_norm as N
    seen = []

    class R:
        status_code, headers = 200, {"Content-Type": "image/jpeg"}
        content = _img("JPEG", 900, 900)

        def raise_for_status(self):
            pass
    monkeypatch.setattr(requests, "get", lambda url, *a, **k: seen.append(url) or R())
    got = N.fetch_image_bytes(FISH_1)
    assert got is not None and seen[-1].startswith("https://img.alicdn.com/")
    from src.services import coupang_image_check as C
    from src.services import image_translate_tencent as tc
    with patch.object(tc, "_download", lambda url, proxies=None: _img("JPEG", 500, 500)):
        raw, why = C._bytes_for(FISH_1)
    assert raw and why == ""


# ── 3. 텐센트 입력 ───────────────────────────────────────────────────────────────────────────────────
def test_prepare_refuses_spacer_and_converts_webp():
    from src.services.detail_image_plan import prepare_for_tencent
    out, info = prepare_for_tencent(_img("GIF", 1, 1))
    assert out is None and info["note"].startswith("너무 작은 사진(1×1")
    out, info = prepare_for_tencent(_img("WEBP", 1200, 1200))
    assert out[:2] == b"\xff\xd8" and info["converted"]
    raw = _img("JPEG", 800, 800)
    assert prepare_for_tencent(raw)[0] is raw                                  # 한도 안의 JPEG은 그대로(다시 굽지 않음)
    forced, finfo = prepare_for_tencent(raw, force=True)
    assert forced is not raw and forced[:2] == b"\xff\xd8" and finfo["converted"]


class _DataErr(Exception):
    def __init__(self):
        super().__init__("输入Data无效，请参考Data参数说明。")
        self.code, self.message = "InvalidParameterValue.Data", "输入Data无效，请参考Data参数说明。"


class _Resp:
    Data = "aW1n"
    Source, Target, SourceText, TargetText = "zh", "ko", "原文", "원문"
    TransDetails, RequestId, Angle = [], "req-1", 0


def _env(monkeypatch):
    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")


def test_spacer_never_sent_to_tencent(monkeypatch):
    from src.services import image_translate_tencent as tc
    _env(monkeypatch)
    calls = []

    class _Cli:
        def ImageTranslateLLM(self, req):
            calls.append(1)
            raise _DataErr()
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), \
            patch.object(tc, "fetch_image", lambda u: (_img("GIF", 1, 1), "")):
        out = tc.translate_image(url=FISH_24)
    assert calls == [] and out["error_class"] == "ConvertFailed" and "너무 작은 사진" in out["error_message"]


def test_data_rejection_retried_once_as_jpeg(monkeypatch):
    from src.services import image_translate_tencent as tc
    _env(monkeypatch)
    sent = []
    raw = _img("PNG", 900, 900)

    class _Cli:
        def ImageTranslateLLM(self, req):
            sent.append(len(req._serialize().get("Data") or ""))
            if len(sent) == 1:
                raise _DataErr()
            return _Resp()
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), patch.object(tc, "fetch_image", lambda u: (raw, "")):
        out = tc.translate_image(url="https://img.alicdn.com/x.png")
    assert out["ok"] and len(sent) == 2 and out.get("data_retried", "").startswith("PNG → JPEG")


def test_data_rejection_not_retried_forever(monkeypatch):
    from src.services import image_translate_tencent as tc
    _env(monkeypatch)
    sent = []

    class _Cli:
        def ImageTranslateLLM(self, req):
            sent.append(1)
            raise _DataErr()
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), \
            patch.object(tc, "fetch_image", lambda u: (_img("JPEG", 900, 900), "")):
        out = tc.translate_image(url="https://img.alicdn.com/x.jpg")
    assert len(sent) == 2 and not out["ok"] and out["error_code"] == "InvalidParameterValue.Data"


def test_ocr_refuses_tiny_image():
    from src.services import ocr_tencent as O
    import pytest
    with pytest.raises(ValueError, match="너무 작은 사진"):
        O.shrink(_img("GIF", 1, 1), O.AS_IS)


# ── 5. 「그릴 줄이 없습니다」는 0상자일 때만 ──────────────────────────────────────────────────────────
def test_fail_reason_labels():
    from src.services.detail_image_plan import fail_reason, verdict
    old = {"status": "failed", "error_class": "RenderFailed", "error_message": "그릴 줄이 없습니다(원본 그대로)"}
    assert fail_reason(old).startswith("번역 실패 · ") and "그릴 줄이 없습니다" not in fail_reason(old)
    tr = dict(old, skipped=[{"text": "包邮", "reason": "번역 실패 — 번역기가 빈 문자열을 돌려줬습니다"}])
    assert fail_reason(tr).startswith("번역 실패 · 번역 실패 — 번역기가 빈 문자열")
    small = dict(old, skipped=[{"text": "a", "reason": "작은 글자(9px)"}, {"text": "b", "reason": "작은 글자(8px)"}])
    assert fail_reason(small) == "번역 안 함 · 작은 글자(9px)(읽은 줄 2개 모두 뺌)"
    tencent = {"status": "failed", "error_class": "TencentCloudSDKException", "error_code": "InvalidParameterValue.Data",
               "error_message": "输入Data无效，请参考Data参数说明。"}
    assert fail_reason(tencent) == "번역 실패 · 输入Data无效，请参考Data参数说明。"
    v = verdict(old, "https://img.alicdn.com/imgextra/i3/2211654478308/O1CN01O2ktJn2BF7WQH27vJ_!!2211654478308.jpg")
    assert v["use"] == "failed" and v["reason"].startswith("번역 실패 · ")


def test_d3_zero_boxes_is_the_only_no_draw_line(monkeypatch):
    """D3: OCR 0상자 → 「그릴 줄이 없습니다 — 글자 0상자」 · 스페이서·`//` 주소는 본선과 같은 규칙(보내지 않음/정리)."""
    from src.services import image_translate_auto as A
    from src.services import image_translate_tencent as tc
    out = A.translate_page_d3(FISH_24, idx=23, kind="detail", item_id="i", seller_id="s")
    assert out["status"] == "excluded" and "스페이서" in out["reason"]
    from src.services import image_text_precheck as P
    from src.services import image_translate_budget as B
    monkeypatch.setattr(P, "han_text", lambda raw: (True, "包邮"))
    monkeypatch.setattr(B, "can_send", lambda m: (True, 0.0, 200.0))
    monkeypatch.setattr(B, "record_call", lambda *a, **k: None)
    got = []
    monkeypatch.setattr(tc, "fetch_image", lambda u: got.append(u) or (_img("JPEG", 800, 800), ""))
    monkeypatch.setattr(tc, "translate_image", lambda url, mode=0: {"ok": True, "lines": [], "ms": 5})
    out = A.translate_page_d3(FISH_1, idx=0, kind="detail", item_id="i", seller_id="s")
    assert got[0].startswith("https://img.alicdn.com/") and out["status"] == "skipped"
    assert out["reason"] == "그릴 줄이 없습니다 — 글자 0상자(원본 그대로)"
