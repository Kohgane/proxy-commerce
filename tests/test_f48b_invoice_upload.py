"""F48-b — 쿠팡 구매대행 인보이스영수증 파일: 업로드 + **새지 않는다**(경로 열거 계약).

오너 브리프(2026-09-25):
  - 브라우저 → 서버 multipart → 서버가 Cloudinary에 업로드(키는 서버 env만, 클라이언트에 키·서명 0).
  - 저장값은 `secure_url`. 이 URL은 `requiredDocuments[templateName="인보이스영수증(해외구매대행 선택시)"]
    .documentPath`에**만** 쓴다 — 상품 상세·이미지·타 마켓 페이로드에 절대 섞이지 않는다.

「섞이지 않는다」를 두 방식으로 잰다:
  ① **페이로드 전수 탐색** — 실제로 만든 쿠팡 생성 요청 JSON을 끝까지 걸어, 센티널 URL이 나타나는
     **모든 경로**를 모은다. 그 목록이 정확히 `requiredDocuments[0].documentPath` 하나여야 한다.
  ② **코드 열거** — 인보이스 값을 읽는 이름들이 나오는 파일을 열거한다. 새 파일이 그 이름을 읽기
     시작하면(= 새 경로가 생기면) 이 계약이 먼저 깨진다(볼트 [[한 값에 두 이름]] F40-b 규율).
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

from src.uploaders.coupang_uploader import CoupangUploader

pytestmark = pytest.mark.coupang_precheck

SENTINEL = "https://res.cloudinary.com/demo/image/upload/v1/proxy-commerce/coupang-invoice/INV-SENTINEL.pdf"
INVOICE = "인보이스영수증(해외구매대행 선택시)"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"x" * 64

SHIP_ENV = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A0001",
    "COUPANG_VENDOR_USER_ID": "wing", "COUPANG_RETURN_CENTER_CODE": "1000",
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "22796911",
    "COUPANG_OVERSEAS_OUTBOUND_SHIPPING_PLACE_CODE": "25099966",
    "COUPANG_RETURN_ZIP_CODE": "06236", "COUPANG_RETURN_ADDRESS": "서울",
    "COUPANG_RETURN_CHARGE_NAME": "CS", "COUPANG_COMPANY_CONTACT_NUMBER": "02-1",
    "COUPANG_DELIVERY_COMPANY_CODE": "CJGLS", "COUPANG_IMAGE_SCREEN": "0",
}


# ---------------------------------------------------------------------------
# 업로드 — 서버가 올리고, 쿠팡 칸에만 저장
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(mc, "_path", lambda sid: str(tmp_path / f"{sid}.json"))
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u-inv"
        yield c


def _fake_upload(calls, ok=True):
    def _up(data, **kw):
        calls.append(kw)
        if not ok:
            return {"ok": False, "error": "Cloudinary 자격 미설정: CLOUDINARY_API_KEY"}
        return {"ok": True, "secure_url": SENTINEL}
    return _up


def test_upload_goes_through_the_server_and_lands_in_the_coupang_slot(client, monkeypatch):
    calls = []
    monkeypatch.setattr("src.media.image_pipeline.upload_bytes", _fake_upload(calls))
    r = client.post("/seller/markets/connect/coupang/invoice",
                    data={"file": (io.BytesIO(PDF), "invoice.pdf")}, content_type="multipart/form-data")
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True and body["secure_url"] == SENTINEL
    # 상품 이미지와 다른 폴더 · PDF는 auto
    assert calls == [{"folder": "coupang-invoice", "resource_type": "auto"}]
    from src.seller_console import market_credentials as mc
    assert mc.get("u-inv", "coupang")["COUPANG_INVOICE_DOCUMENT_URL"] == SENTINEL
    # 응답에 키·서명이 없다 — 주소와 형식만
    assert set(body) == {"ok", "secure_url", "kind"}


def test_the_format_is_read_from_the_bytes(client, monkeypatch):
    calls = []
    monkeypatch.setattr("src.media.image_pipeline.upload_bytes", _fake_upload(calls))
    r = client.post("/seller/markets/connect/coupang/invoice",
                    data={"file": (io.BytesIO(b"MZ\x90\x00 not a receipt"), "invoice.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 502 and "JPG·PNG·PDF" in r.get_json()["error"] and calls == []


def test_an_upload_failure_is_said_and_nothing_is_saved(client, monkeypatch):
    monkeypatch.setattr("src.media.image_pipeline.upload_bytes", _fake_upload([], ok=False))
    r = client.post("/seller/markets/connect/coupang/invoice",
                    data={"file": (io.BytesIO(PNG), "r.png")}, content_type="multipart/form-data")
    assert r.status_code == 502 and "CLOUDINARY_API_KEY" in r.get_json()["error"]
    from src.seller_console import market_credentials as mc
    assert "COUPANG_INVOICE_DOCUMENT_URL" not in mc.get("u-inv", "coupang")


def test_the_browser_holds_no_key_or_signature():
    """클라이언트 코드에 Cloudinary 키·서명·직접 업로드 주소가 없다 — 파일만 서버로."""
    html = pathlib.Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")
    block = html[html.index("F48-b — 인보이스 파일"):]
    block = block[:block.index("const dc = form.querySelector")]
    for banned in ("api_key", "api_secret", "signature", "cloudinary.com", "CLOUDINARY"):
        assert banned not in block, banned
    assert "/seller/markets/connect/coupang/invoice" in block and "FormData" in block


def test_the_upload_box_is_coupang_only():
    """오너 역질문의 답 — 칸은 쿠팡 자격에만 있다(다른 마켓엔 이 칸이 없다)."""
    from src.seller_console.market_credentials import MARKET_CRED_FIELDS
    owners = [m for m, fields in MARKET_CRED_FIELDS.items()
              if any(f["env"] == "COUPANG_INVOICE_DOCUMENT_URL" for f in fields)]
    assert owners == ["coupang"]


# ---------------------------------------------------------------------------
# ① 페이로드 전수 탐색 — 센티널이 나타나는 경로는 documentPath 하나뿐
# ---------------------------------------------------------------------------

def _paths_with(obj, needle, here="$"):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _paths_with(v, needle, f"{here}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _paths_with(v, needle, f"{here}[{i}]")
    elif needle in str(obj):
        out.append(here)
    return out


def test_the_invoice_url_appears_only_at_document_path(monkeypatch):
    for k, v in SHIP_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("COUPANG_INVOICE_DOCUMENT_URL", SENTINEL)
    up = CoupangUploader()
    sent = []

    def _api(method, path, data=None):
        if "categorization/predict" in path:
            return {"data": {"predictedCategoryId": "63955"}}
        if "category-related-metas" in path:
            return {"data": {"attributes": [], "noticeCategories": [],
                             "requiredDocumentNames": [{"templateName": INVOICE, "required": "MANDATORY"}]}}
        if "shipping-place/outbound" in path:
            return {"data": [{"outboundShippingPlaceCode": "25099966", "addressType": "OVERSEA"}]}
        if method == "POST" and "seller-products" in path and data is not None:
            sent.append(data)
            return {"code": "SUCCESS", "data": 1}
        return {"code": "SUCCESS", "data": None}

    monkeypatch.setattr(up, "_api_request", _api)
    res = up.upload_product({"sku": "617129397971", "title": "수행방패", "price": 24000, "origin": "중국",
                             "images": ["https://img/1.jpg", "https://img/2.jpg"],
                             "description_html": "<p>상세</p>", "options": []})
    assert res.get("success") is True, res
    [payload] = sent
    assert _paths_with(payload, SENTINEL) == ["$.requiredDocuments[0].documentPath"]
    assert payload["requiredDocuments"][0]["templateName"] == INVOICE


# ---------------------------------------------------------------------------
# ② 코드 열거 — 인보이스 값을 읽는 이름이 나오는 파일
# ---------------------------------------------------------------------------

READERS = {
    "src/uploaders/coupang_uploader.py",           # requiredDocuments[].documentPath (유일한 소비처)
    "src/seller_console/market_credentials.py",    # 쿠팡 자격 칸 정의
    "src/seller_console/coupang_invoice.py",       # 업로드·저장
    "src/seller_console/views.py",                 # 업로드 라우트
    "src/seller_console/templates/markets_connect.html",   # 업로드 칸(쿠팡 카드)
}
_NAMES = re.compile(r"COUPANG_INVOICE_DOCUMENT_URL|invoice_document_url|INVOICE_URL_ENV|coupang_invoice")


def test_only_the_enumerated_files_touch_the_invoice_value():
    found = set()
    for p in pathlib.Path("src").rglob("*"):
        if p.suffix not in (".py", ".html", ".js") or "__pycache__" in p.parts:
            continue
        if _NAMES.search(p.read_text(encoding="utf-8", errors="ignore")):
            found.add(str(p))
    assert found == READERS, sorted(found ^ READERS)


def test_no_other_uploader_reads_it():
    for p in pathlib.Path("src/uploaders").glob("*.py"):
        if p.name == "coupang_uploader.py":
            continue
        assert not _NAMES.search(p.read_text(encoding="utf-8")), p
