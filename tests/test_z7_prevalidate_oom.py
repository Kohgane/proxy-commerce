"""Z7(오너 2026-10-08) — 사전검증 OOM.

Render Events 원문: 13:30·13:33 KST 「Instance failed: Ran out of memory (used over 512MB)」, 15:19 재발.
재현: 플리츠 세트(8 SKU) → 쿠팡 우주대행만 → 사전검증 → 매번 502.
원인(실측, 워커 1개): 쿠팡 대표 사진 판정이 **요청 프로세스 안에서** RapidOCR(PP-OCR 모델 + onnxruntime)을
올리고 원본 해상도로 돌렸다 — 앱 로드 81MB → 사전검증 1회 피크 582MB(1500px)·312MB(800px).
수리: 로컬 ML 모델을 프로세스에 올리지 않는다. 글자 판정은 텐센트 OCR API(긴 변 1024px로 줄여 전송),
실패하면 `ocr_unavailable`로 건너뛰고 등록은 막지 않는다. 단계마다 RSS 로그. gunicorn 워커 2개 이상이면 max-requests.
"""
from __future__ import annotations

import base64
import io
import logging
import runpy
import sys
from pathlib import Path

import pytest

from tests._ast_probe import importers_of

#: 요청 프로세스에 올라가면 안 되는 로컬 ML·OCR 엔진(모델을 메모리에 싣는 것들).
LOCAL_ML = ("torch", "torchvision", "easyocr", "paddle", "paddleocr", "rapidocr", "rapidocr_onnxruntime",
            "onnxruntime", "tensorflow", "keras", "transformers", "pytesseract")


@pytest.mark.parametrize("name", LOCAL_ML)
def test_no_local_ml_import_anywhere_in_src(name):
    """AST로 고정 — `src/` 어디에도 로컬 ML·OCR 엔진 import가 없다(사전검증·미리보기·이미지 번역 전부 포함)."""
    assert importers_of(name) == [], f"{name}을(를) import하는 파일: {importers_of(name)}"


def _jpeg(side=1920):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (side, side), "white")
    ImageDraw.Draw(im).text((side // 10, side // 2), "INTERSTELLAR", fill="black")
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def ocr(monkeypatch):
    from src.services import ocr_tencent as O
    monkeypatch.setattr(O, "is_configured", lambda: True)
    sent = []

    def fake_call(b64):
        sent.append(base64.b64decode(b64))
        return {"RequestId": "r1", "TextDetections": [
            {"DetectedText": "INTERSTELLAR", "Confidence": 99}, {"DetectedText": "흐림", "Confidence": 20}]}
    monkeypatch.setattr(O, "_call", fake_call)
    return O, sent


def test_tencent_ocr_shrinks_to_1024_and_filters_confidence(ocr):
    O, sent = ocr
    res = O.read(_jpeg(1920))
    assert res["ok"] is True and res["text"] == "INTERSTELLAR"          # 확신 20 조각은 버린다
    from PIL import Image
    assert max(Image.open(io.BytesIO(sent[0])).size) == 1024              # 긴 변 1024px로 줄여 보냈다
    small = O.read(_jpeg(600))
    assert small["ok"] and max(Image.open(io.BytesIO(sent[1])).size) == 600   # 작은 건 키우지 않는다


@pytest.mark.parametrize("setup,why", [
    ("unconfigured", "텐센트 키 미설정"),
    ("raises", "텐센트 OCR 실패(TencentCloudSDKException)"),
])
def test_tencent_ocr_failure_is_ocr_unavailable(monkeypatch, setup, why):
    from src.services import ocr_tencent as O
    if setup == "unconfigured":
        monkeypatch.setattr(O, "is_configured", lambda: False)
        monkeypatch.setattr(O, "_call", lambda b64: pytest.fail("키 없는데 호출"))
    else:
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
        monkeypatch.setattr(O, "is_configured", lambda: True)

        def boom(b64):
            raise TencentCloudSDKException("InternalError", "boom")
        monkeypatch.setattr(O, "_call", boom)
    res = O.read(_jpeg(800))
    if setup == "raises":
        why = "텐센트 OCR 실패(InternalError)"
    assert res == {"ok": False, "code": "ocr_unavailable", "why": why, "lines": [], "text": ""}


def _pd(images):
    src = ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"]
    return {"title": "플리츠 미니멀 여성 여름 세트", "title_ko": "플리츠 미니멀 여성 여름 세트", "price": "168",
            "currency": "CNY", "url": "https://item.taobao.com/item.htm?id=1", "images": images,
            "options": [{"name": "颜色分类", "values": src}, {"name": "尺码", "values": ["均码"]}],
            "skus": [{"sku_id": str(i), "spec": [v, "均码"], "price": 168.0, "currency": "CNY", "stock": 10}
                     for i, v in enumerate(src)]}


@pytest.fixture
def rep(monkeypatch):
    """쿠팡 대표 사진 판정 켜고, 사진 바이트는 합성 1920px(네트워크 0)."""
    from src.services import coupang_image_check as C
    monkeypatch.setenv("COUPANG_IMAGE_CHECK", "1")
    C.reset_cache()
    raw = _jpeg(1920)
    monkeypatch.setattr(C, "_bytes_for", lambda url: (raw, ""))
    yield C
    C.reset_cache()


def test_ocr_unavailable_never_holds_and_is_not_cached(rep, monkeypatch):
    """텐센트가 실패하면 「글자 판정 못 함」(ocr_unavailable) 한 줄 — 보류 아님, 결과도 굳히지 않는다(다음에 다시 잰다)."""
    from src.services import ocr_tencent as O
    monkeypatch.setattr(O, "is_configured", lambda: True)
    calls = []

    def boom(b64):
        calls.append(1)
        raise RuntimeError("network down")
    monkeypatch.setattr(O, "_call", boom)
    res = rep.check_url("https://img.alicdn.com/a.jpg")
    assert res["state"] == "ok" and res["text"] is None and res["ocr"] == "unavailable"
    flag = [f for f in res["flags"] if f["key"] == "ocr_unavailable"][0]
    assert flag["code"] == "ocr_unavailable" and flag["hold"] is False and "등록은 막지 않아요" in flag["line"]
    assert rep.hold(_pd(["https://img.alicdn.com/a.jpg"]), "coupang") is None
    rep.check_url("https://img.alicdn.com/a.jpg")
    assert len(calls) >= 2                                                # 캐시 안 됨 → 다시 잰다


def test_text_found_still_holds_via_tencent(rep, ocr):
    h = rep.hold(_pd(["https://img.alicdn.com/a.jpg"]), "coupang")
    assert h and "텍스트 있음" in h["line"] and "INTERSTELLAR" in h["line"]


def test_prevalidate_loads_no_local_ml_and_logs_rss_stages(rep, ocr, monkeypatch, caplog):
    """플리츠 세트 쿠팡 사전검증 한 번 — 로컬 ML 모듈이 프로세스에 안 올라오고, 단계마다 `[RSS] stage=… rss_mb=…`."""
    for k, v in {"COUPANG_ACCESS_KEY": "a", "COUPANG_SECRET_KEY": "s", "COUPANG_VENDOR_ID": "A0",
                 "COUPANG_VENDOR_USER_ID": "u", "COUPANG_RETURN_CENTER_CODE": "1",
                 "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "1", "COUPANG_RETURN_ZIP_CODE": "12345",
                 "COUPANG_RETURN_ADDRESS": "x", "COUPANG_RETURN_CHARGE_NAME": "x",
                 "COUPANG_COMPANY_CONTACT_NUMBER": "010"}.items():
        monkeypatch.setenv(k, v)
    from src.seller_console.upload_dispatcher import UploadDispatcher
    caplog.set_level(logging.INFO, logger="rss")
    # Z9: 사전검증은 대표 사진 판정을 기다리지 않는다(백그라운드 + 「대기 중」) — 판정이 끝나면 다시 잰다(잡이 하는 그대로)
    import time as _t
    from src.services import coupang_image_check as _cic
    UploadDispatcher().prevalidate(_pd(["https://img.alicdn.com/a.jpg"]), ["coupang"])
    assert _cic.wait_done(["https://img.alicdn.com/a.jpg"], until_ts=_t.time() + 10, step=0.05)
    [r] = UploadDispatcher().prevalidate(_pd(["https://img.alicdn.com/a.jpg"]), ["coupang"])
    assert r.hold is True and "대표 사진 텍스트 있음" in (r.message or "")
    loaded = [m for m in LOCAL_ML if m in sys.modules]
    assert loaded == [], loaded
    stages = [rec.getMessage() for rec in caplog.records if rec.name == "rss"]
    for st in ("prevalidate_start", "rep_image_check_before", "rep_image_check_after", "prevalidate_end"):
        assert any(f"stage={st} rss_mb=" in m for m in stages), (st, stages)


def test_rss_reader_returns_numbers():
    from src.utils import rss
    cur, peak = rss.read_mb()
    assert cur > 0 and peak >= cur


@pytest.mark.parametrize("workers,mr,jit", [("2", 200, 50), ("3", 200, 50), ("1", 0, 0)])
def test_gunicorn_max_requests_only_with_two_or_more_workers(monkeypatch, workers, mr, jit):
    monkeypatch.setenv("GUNICORN_WORKERS", workers)
    monkeypatch.delenv("GUNICORN_MAX_REQUESTS", raising=False)
    monkeypatch.delenv("GUNICORN_MAX_REQUESTS_JITTER", raising=False)
    conf = runpy.run_path(str(Path(__file__).resolve().parents[1] / "gunicorn.conf.py"))
    assert (conf["max_requests"], conf["max_requests_jitter"]) == (mr, jit)
