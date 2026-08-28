"""tests/test_p5_smartstore.py — P5: 스마트스토어 정본 승계 + 마켓 select(어댑터 첫 실증).

정본 = 오너 SSH 실측 `ss_upload.py`. 쿠팡과 **다른 값**을 쓰는 지점이 있고, 섞으면 안 된다:
  · 원산지 `originAreaCode "03"` + `"상세설명에 표시"` (스마트스토어 허용 문구)
  · 통관 `customsTaxType PURCHASE_AGENT` · 반품 25,000 / 교환 50,000
  · 계정 축 = chezgoga / gocosmos (쿠팡 고가네/우주대행과 **별개**)

계약:
  1. 정본 상수가 전부 페이로드에 실린다.
  2. 주소 ID는 **env화**(하드코딩 금지) + 계정별 접두 우선. 기본값은 정본 실증값.
  3. 계정 축이 섞이면 정직 차단(쿠팡 계정명으로 스마트스토어 등록 불가).
  4. 등록 라우트가 마켓별로 어댑터·대장·중복 방지를 분기한다.
  5. 인증·호출은 **릴레이 경유**(네이버 IP 게이트).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from src.collectors import image_norm as IN
from src.pipeline import register_adapters as RA
from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS


_PRODUCT = {"title": "Fellow Stagg 주전자", "price": 894000, "sku": "B0GS4698H2",
            "description_html": "<p>상세</p>", "brand": "Fellow",
            "images": ["https://m.media-amazon.com/images/I/71a._SS1600_.jpg",
                       "https://m.media-amazon.com/images/I/71b._SS1600_.jpg"]}


# ── 1. 정본 상수 ────────────────────────────────────────────────────────────────
def test_canon_constants():
    assert SS.CUSTOMS_TAX_TYPE == "PURCHASE_AGENT"
    assert (SS.RETURN_FEE, SS.EXCHANGE_FEE) == (25000, 50000)
    assert SS.STATUS_TYPE == "SALE" and SS.STOCK_QUANTITY == 999
    assert SS.NAVER_SHOPPING_REGISTRATION is True
    assert SS.ORIGIN_AREA_CODE == "03" and SS.ORIGIN_AREA_CONTENT == "상세설명에 표시"
    assert SS.DEFAULT_LEAF_CATEGORY == "50004132"


def test_payload_carries_canon(monkeypatch):
    up = SS(account="chezgoga")
    p = up._build_product_payload(_PRODUCT)
    op = p["originProduct"]
    assert op["statusType"] == "SALE" and op["stockQuantity"] == 999
    # category_id 미상 → 상품명으로 정본 매칭('주전자' = 7행 주방).
    assert op["leafCategoryId"] == "50004737"
    assert op["salePrice"] == 894000
    da = op["detailAttribute"]
    assert da["customsTaxType"] == "PURCHASE_AGENT"
    # ★ 원산지는 쿠팡과 다른 축 — 스마트스토어 허용 문구.
    assert da["originAreaInfo"] == {"originAreaCode": "03", "content": "상세설명에 표시"}
    assert da["sellerCodeInfo"]["sellerManagementCode"] == "B0GS4698H2"
    cdi = op["deliveryInfo"]["claimDeliveryInfo"]
    assert cdi["returnDeliveryFee"] == 25000 and cdi["exchangeDeliveryFee"] == 50000
    assert p["smartstoreChannelProduct"]["naverShoppingRegistration"] is True
    # 대표/추가 이미지 분리.
    assert op["images"]["representativeImage"]["url"].endswith("71a._SS1600_.jpg")
    assert len(op["images"]["optionalImages"]) == 1


# ── 카테고리 정본 11패턴(순서 유지·첫 매칭 우선) ────────────────────────────────
@pytest.mark.parametrize("title,leaf", [
    ("EDC 피젯 스피너", "50004132"),
    ("분재 오브제 퍼즐", "50004132"),
    ("슬링백 파우치", "50000646"),
    ("백팩 패킹큐브", "50000646"),
    ("키링 카라비너", "50000570"),
    ("목걸이 주얼리", "50000570"),
    ("멀티툴 나이프", "50003413"),
    ("에어펌프 드라이버", "50003413"),
    ("원예 전정가위", "50000406"),
    ("스텐 텀블러", "50004737"),
    ("만년필 북마크", "50002335"),
    ("블루투스 스피커", "50000205"),
    ("이어팁 카드리더", "50000205"),
    ("여름 샌들", "50000167"),
    ("캔들 디퓨저", "50001854"),
    ("정체불명 상품", "50004132"),          # 미매칭 → 기본 리프(정본 동작 그대로)
])
def test_category_canon_patterns(title, leaf):
    assert SS.resolve_category(title) == leaf


def test_category_order_is_canon_and_must_not_be_resorted():
    """**첫 매칭 우선** — 순서를 바꾸면 판정이 바뀐다. 정본 순서를 그대로 고정한다.

    실제 사례: '티셔츠'는 10행(재킷|티셔츠)이 아니라 **7행의 '티'**에 먼저 걸려 주방(50004737)이 된다.
    정본 스크립트와 동일한 결과이므로 재정렬하지 않는다(발명 금지). 바꾸려면 오너가 정본을 고쳐야 한다.
    """
    assert SS.resolve_category("티셔츠") == "50004737"      # 7행 '티' 선매칭(정본 동작)
    assert SS.resolve_category("재킷") == "50000167"        # '티' 없는 의류는 10행으로
    # 패턴 순서 자체를 고정 — 재정렬 시 이 테스트가 깨진다.
    assert [leaf for _, leaf in SS.CATEGORY_PATTERNS] == [
        "50004132", "50000646", "50000570", "50000570", "50003413",
        "50000406", "50004737", "50002335", "50000205", "50000167", "50001854"]
    assert len(SS.CATEGORY_PATTERNS) == 11


def test_payload_uses_canon_category_when_unspecified():
    """명시 카테고리가 없으면 상품명으로 정본 매칭(기본 리프 고정이 아니다)."""
    p = SS(account="chezgoga")._build_product_payload({**_PRODUCT, "title": "멀티툴 나이프"})
    assert p["originProduct"]["leafCategoryId"] == "50003413"


def test_explicit_category_overrides_default():
    up = SS(account="chezgoga")
    p = up._build_product_payload({**_PRODUCT, "category_id": "50001234"})
    assert p["originProduct"]["leafCategoryId"] == "50001234"


# ── 2. 주소 ID env화 ────────────────────────────────────────────────────────────
def test_address_ids_default_to_canon_per_account():
    assert SS(account="chezgoga").ship_address_id == "107519271"
    assert SS(account="chezgoga").return_address_id == "107519270"
    assert SS(account="gocosmos").ship_address_id == "107987297"
    assert SS(account="gocosmos").return_address_id == "107987296"


def test_address_ids_overridable_by_env(monkeypatch):
    """하드코딩 금지 — 계정 접두 env가 정본 기본값을 덮는다."""
    monkeypatch.setenv("NAVER_CHEZGOGA_SHIP_ADDRESS_ID", "999111")
    assert SS(account="chezgoga").ship_address_id == "999111"
    # 다른 계정은 영향 없음(혼입 방지).
    assert SS(account="gocosmos").ship_address_id == "107987297"


def test_address_ids_sent_as_int():
    p = SS(account="chezgoga")._build_product_payload(_PRODUCT)
    cdi = p["originProduct"]["deliveryInfo"]["claimDeliveryInfo"]
    assert cdi["shippingAddressId"] == 107519271 and cdi["returnAddressId"] == 107519270


def test_no_hardcoded_address_outside_canon_table():
    """주소 ID 리터럴은 정본 표 안에만 있어야 한다(페이로드 빌더에 하드코딩 0)."""
    src = Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8")
    body = src.split("def _build_product_payload")[1].split("\n    @staticmethod")[0]
    for lit in ("107519271", "107519270", "107987297", "107987296"):
        assert lit not in body, lit


# ── 3. 계정 축 분리 ─────────────────────────────────────────────────────────────
def test_smartstore_adapter_is_canon_ready():
    st = RA.get_adapter("smartstore").canon_status()
    assert st["ready"] is True and st["gaps"] == []
    # 카테고리 11패턴 승계 완료 → partial 없음(#672).
    assert st["partial"] == {}
    assert "11패턴" in st["points"]["category"]["source"]


def test_coupang_account_rejected_on_smartstore():
    """축이 다르다 — 쿠팡 계정명으로 스마트스토어 등록 시도는 정직 차단."""
    res = RA.get_adapter("smartstore").register({"title_ko": "x"}, "gogane")
    assert res["success"] is False and res["held"] is True
    assert "스마트스토어 계정이 아닙니다" in res["error"]


def test_smartstore_dispatch_blocks_without_credentials(monkeypatch):
    from src.seller_console.views import _smartstore_account_dispatch
    for k in ("NAVER_CLIENT_ID", "NAVER_COMMERCE_CLIENT_ID",
              "NAVER_CHEZGOGA_CLIENT_ID", "NAVER_CLIENT_SECRET",
              "NAVER_COMMERCE_CLIENT_SECRET", "NAVER_CHEZGOGA_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    res = _smartstore_account_dispatch({"title_ko": "x", "sell_price_krw": 10000}, "chezgoga")
    assert res["success"] is False and "자격 미설정" in res["error"]


def test_smartstore_dispatch_blocks_without_address(monkeypatch):
    from src.seller_console.views import _smartstore_account_dispatch
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "sec")
    monkeypatch.setenv("NAVER_CHEZGOGA_SHIP_ADDRESS_ID", "")
    # 정본 기본값이 있는 계정은 통과하지만, 축이 없는 계정명은 주소가 비어 차단된다.
    res = _smartstore_account_dispatch({"title_ko": "x", "sell_price_krw": 10000}, "unknown_acct")
    assert res["success"] is False and res["held"] is True
    assert "주소 ID 미설정" in res["error"]


# ── 4. 라우트 마켓 분기 ─────────────────────────────────────────────────────────
def test_route_dispatches_by_market():
    src = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    seg = src.split("def sourcing_register_pipe_register")[1].split("\n@bp.")[0]
    assert 'request.form.get("market")' in seg
    assert "adapter.register(pd, acct)" in seg
    # 대장·중복 방지가 마켓별로 판정된다(같은 상품을 두 마켓에 등록하는 건 정상).
    assert "marketplace=market" in seg


def test_unknown_market_rejected(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_check_auth", lambda: True)
    from src.order_webhook import app
    r = app.test_client().post("/seller/sourcing/register-pipe/register",
                               data={"urls": "https://x/1", "market": "gmarket"})
    assert r.status_code == 400 and "지원하지 않는 마켓" in r.get_json()["error"]


def test_template_has_market_select():
    html = Path("src/seller_console/templates/register_pipe.html").read_text(encoding="utf-8")
    assert 'id="p3Market"' in html
    assert '<option value="smartstore">스마트스토어</option>' in html
    # 계정 목록이 마켓에 따라 바뀐다(축 혼입 방지).
    assert "P3_ACCOUNTS" in html and "chezgoga" in html and "gogane" in html
    assert "market: market" in html                       # 전송에 마켓 포함


def test_pipeline_no_longer_hardcodes_coupang_accounts():
    """계정 축 검증은 어댑터가 한다 — 파이프라인이 쿠팡 계정만 알던 것 제거."""
    src = Path("src/pipeline/register_pipe.py").read_text(encoding="utf-8")
    assert '("gogane", "woojoo")' not in src


# ── 5. 릴레이 경유 ──────────────────────────────────────────────────────────────
def test_naver_calls_go_through_relay():
    """네이버는 IP 게이트 — 토큰 발급까지 릴레이 경유여야 한다(v87-S7)."""
    src = Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8")
    tok = src.split("def _get_access_token")[1].split("\n    def ")[0]
    assert "relay_request(" in tok and 'market="smartstore"' in tok
    relay = Path("src/market_relay.py").read_text(encoding="utf-8")
    assert "api.commerce.naver.com" in relay
    assert '"smartstore"' in relay


# ── 6. 이미지 업로드 정본(오너 SSH `naver_img.py`) ──────────────────────────────
def test_image_upload_canon_constants():
    assert SS.IMAGE_UPLOAD_PATH == "/v1/product-images/upload"
    assert SS.IMAGE_MIN_BYTES == 1024 and SS.IMAGE_MAX_COUNT == 10 and SS.IMAGE_RETRY == 3


@pytest.mark.parametrize("raw,expected", [
    ("https://m.media-amazon.com/i/a.jpg?v=2", "https://m.media-amazon.com/i/a.jpg"),
    ("//m.media-amazon.com/i/a.jpg", "https://m.media-amazon.com/i/a.jpg"),   # 정본: https: 부착
    ("//cdn.x/a.png?q=1", "https://cdn.x/a.png"),
    ("", ""),
])
def test_source_url_normalization(raw, expected):
    assert SS.normalize_source_url(raw) == expected


def _fake_resp(content=b"", ct="image/jpeg", status=200):
    class _R:
        status_code = status
        headers = {"Content-Type": ct}
    r = _R()
    r.content = content
    r.raise_for_status = lambda: None
    return r


def test_fetch_uses_browser_ua(monkeypatch):
    """UA 헤더 필수 — 아마존 CDN이 기본 UA를 막는다(정본)."""
    seen = {}
    monkeypatch.setattr("requests.get",
                        lambda u, **k: seen.update(k) or _fake_resp(b"x" * 2000))
    got = SS(account="chezgoga")._fetch_image("https://m.media-amazon.com/i/a.jpg")
    assert got is not None and got.filename == "img.jpg"
    assert "Mozilla" in seen["headers"]["User-Agent"]


def test_fetch_skips_tiny_files(monkeypatch):
    """1KB 미만 = 썸네일 쓰레기 → 스킵(정본)."""
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(b"x" * 500))
    assert SS(account="chezgoga")._fetch_image("https://x/a.jpg") is None


@pytest.mark.parametrize("ct,ext", [("image/jpeg", "jpg"), ("image/png", "png"),
                                    ("image/gif", "gif"), ("image/bmp", "bmp")])
def test_fetch_extension_from_content_type(monkeypatch, ct, ext):
    """매직 바이트를 못 읽으면 Content-Type 폴백. (webp는 네이버 미허용 → 변환 계약에서 별도로 본다.)"""
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(b"x" * 2000, ct=ct))
    assert SS(account="chezgoga")._fetch_image("https://x/a").filename == f"img.{ext}"


def test_fetch_rejects_unsupported_content_type(monkeypatch):
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(b"x" * 2000, ct="text/html"))
    assert SS(account="chezgoga")._fetch_image("https://x/a") is None


def test_ssl_verification_not_disabled():
    """정본의 CERT_NONE은 Bluehost 구환경 땜빵 — **승계하지 않는다**(오너 지시)."""
    # 독스트링에 '승계하지 않는다'는 설명이 있으므로 **실행되는 호출 형태**만 본다.
    src = Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8")
    assert "verify=False" not in src
    assert "ssl._create_unverified_context" not in src
    assert "CERT_NONE" not in src.replace("정본의 CERT_NONE은", "")   # 설명 1곳만 예외


def test_upload_images_goes_through_relay(monkeypatch):
    """multipart도 릴레이 경유 — IP 게이트(직결 시 GW.IP_NOT_ALLOWED)."""
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(b"x" * 2000))
    seen = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"images": [{"url": "https://shop-phinf.naver.net/a.jpg"}]}

    def _relay(method, url, **kw):
        seen.update({"method": method, "url": url, **kw})
        return _Resp()

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request", _relay)
    out = up.upload_images(["https://m.media-amazon.com/i/a.jpg"])
    assert out["ok"] is True and out["urls"] == ["https://shop-phinf.naver.net/a.jpg"]
    assert seen["market"] == "smartstore"                      # 릴레이 마켓 지정
    assert seen["url"].endswith("/v1/product-images/upload")
    assert seen["headers"]["Authorization"] == "Bearer tok"
    # multipart 본문이 바이트로 조립돼 나간다(릴레이가 body를 그대로 전달).
    assert "multipart/form-data; boundary=" in seen["headers"]["Content-Type"]
    assert b'name="imageFiles"' in seen["data"]


def test_upload_images_retries_on_429(monkeypatch):
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(b"x" * 2000))
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    class _R429:
        status_code = 429
        def raise_for_status(self): pass

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request",
                        lambda *a, **k: calls.append(1) or _R429())
    out = up.upload_images(["https://x/a.jpg"])
    assert out["ok"] is False and len(calls) == SS.IMAGE_RETRY      # 정본: 최대 3회
    assert "429" in out["reason"]


def test_upload_images_surfaces_http_error_body(monkeypatch):
    """조용한 실패 금지 — 오류 본문 200자까지 사유에 담는다(정본)."""
    import requests as _rq
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(b"x" * 2000))
    monkeypatch.setattr("time.sleep", lambda s: None)

    class _Err:
        status_code = 400
        text = "INVALID_IMAGE: 규격 오류입니다"
        def raise_for_status(self):
            raise _rq.exceptions.HTTPError(response=self)

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request", lambda *a, **k: _Err())
    out = up.upload_images(["https://x/a.jpg"])
    assert out["ok"] is False and "INVALID_IMAGE" in out["reason"] and "400" in out["reason"]


def test_upload_images_zero_blocks_registration(monkeypatch):
    """업로드 0장이면 등록 차단(정본의 raise와 같은 철학)."""
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "upload_images",
                        lambda urls: {"ok": False, "urls": [], "skipped": [], "reason": "전부 실패"})
    monkeypatch.setattr(up, "_api_request",
                        lambda *a, **k: pytest.fail("이미지 0장인데 등록 호출됨"))
    res = up.upload_product(dict(_PRODUCT))
    assert res["success"] is False and res["held"] is True
    assert "이미지 업로드 실패" in res["error"]


def test_uploaded_cdn_urls_are_used_in_payload(monkeypatch):
    """등록 페이로드에는 **네이버 CDN URL**이 실린다(외부 URL 아님)."""
    up = SS(account="chezgoga")
    cdn = ["https://shop-phinf.naver.net/a.jpg", "https://shop-phinf.naver.net/b.jpg"]
    monkeypatch.setattr(up, "upload_images",
                        lambda urls: {"ok": True, "urls": cdn, "skipped": [], "reason": ""})
    sent = {}
    monkeypatch.setattr(up, "_api_request",
                        lambda m, p, data=None: sent.update({"d": data}) or {"originProductNo": "1"})
    res = up.upload_product(dict(_PRODUCT))
    assert res["success"] is True
    imgs = sent["d"]["originProduct"]["images"]
    assert imgs["representativeImage"]["url"] == cdn[0]
    assert [i["url"] for i in imgs["optionalImages"]] == cdn[1:]


def test_image_upload_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("NAVER_IMAGE_UPLOAD", "0")
    up = SS(account="chezgoga")
    assert up.image_upload_enabled is False
    monkeypatch.setattr(up, "upload_images", lambda urls: pytest.fail("게이트 껐는데 업로드됨"))
    monkeypatch.setattr(up, "_api_request", lambda *a, **k: {"originProductNo": "1"})
    assert up.upload_product(dict(_PRODUCT))["success"] is True


# ── 7. 토큰 발급 정본(bcrypt 서명) + 조용한 실패 수리 ───────────────────────────
def _valid_salt():
    """네이버가 발급하는 시크릿은 **bcrypt salt**($2a$…) 형식이다 — 실제 salt로 테스트."""
    import bcrypt
    return bcrypt.gensalt(rounds=4).decode()
def test_token_uses_bcrypt_signature_not_plain_secret(monkeypatch):
    """★ 카나리 1차 근원: 평문 client_secret을 보냈다. 정본은 **bcrypt client_secret_sign**."""
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", _valid_salt())
    up = SS(account="chezgoga")
    sent = {}

    class _R:
        status_code = 200
        text = ""
        def json(self): return {"access_token": "tok", "expires_in": 3600}

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request",
                        lambda m, u, **kw: sent.update(kw) or _R())
    assert up._get_access_token() == "tok"
    body = sent["data"]
    assert "client_secret_sign" in body and body["client_secret_sign"]
    assert "client_secret" not in body                  # 평문 시크릿은 보내지 않는다
    assert body["timestamp"] and body["type"] == "SELF"
    assert sent["market"] == "smartstore"               # 릴레이 경유(IP 게이트)


def test_signature_is_single_source():
    """서명 규칙은 smartstore_adapter가 단일 소스 — 이 파일이 따로 구현하면 두 경로가 갈린다."""
    src = Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8")
    assert "_naver_signature" in src
    assert "import bcrypt" not in src                   # 서명 재구현 금지


def test_token_failure_surfaces_response_body(monkeypatch):
    """조용한 실패 수리 — 네이버 응답 본문 200자를 사유로 올린다(원문이 범인을 지목)."""
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", _valid_salt())
    up = SS(account="chezgoga")

    class _R:
        status_code = 401
        text = '{"code":"invalid_client","message":"Client authentication failed"}'

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request", lambda *a, **k: _R())
    assert up._get_access_token() == ""
    assert "401" in up.token_error and "invalid_client" in up.token_error


def test_ip_gate_error_is_visible(monkeypatch):
    """GW.IP_NOT_ALLOWED도 그대로 보인다 — 릴레이 IP 미등록을 즉시 판별."""
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", _valid_salt())
    up = SS(account="chezgoga")

    class _R:
        status_code = 403
        text = '{"code":"GW.IP_NOT_ALLOWED"}'

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request", lambda *a, **k: _R())
    up._get_access_token()
    assert "GW.IP_NOT_ALLOWED" in up.token_error


def test_bad_secret_format_reports_actionable_reason(monkeypatch):
    """평문 시크릿(bcrypt salt 아님)이면 무엇을 고쳐야 하는지 말한다."""
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "cid")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "plaintext-secret")
    up = SS(account="chezgoga")
    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request",
                        lambda *a, **k: pytest.fail("서명 실패인데 토큰 요청됨"))
    assert up._get_access_token() == ""
    assert "$2a$" in up.token_error and "전자서명" in up.token_error


def test_missing_credentials_names_account_env(monkeypatch):
    """계정별 env 이름을 안내한다(스토어별 앱 구조)."""
    for k in ("NAVER_CLIENT_ID", "NAVER_COMMERCE_CLIENT_ID", "NAVER_CHEZGOGA_CLIENT_ID",
              "NAVER_CLIENT_SECRET", "NAVER_COMMERCE_CLIENT_SECRET", "NAVER_CHEZGOGA_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    up = SS(account="chezgoga")
    up._get_access_token()
    assert "NAVER_CHEZGOGA_CLIENT_ID" in up.token_error


def test_image_upload_reports_token_reason(monkeypatch):
    """이미지 업로드 사유에 토큰 실패 **원문**이 실린다('발급 실패'만 아님)."""
    up = SS(account="chezgoga")
    monkeypatch.setattr("src.collectors.image_norm.fetch_image_bytes",
                        lambda u, **k: IN.FetchedImage(b"x" * 2000, "image/jpeg", "jpg"))
    monkeypatch.setattr(up, "_get_access_token", lambda: "")
    up.token_error = "HTTP 403: {\"code\":\"GW.IP_NOT_ALLOWED\"}"
    out = up.upload_images(["https://x/a.jpg"])
    assert out["ok"] is False and "GW.IP_NOT_ALLOWED" in out["reason"]


# ── 카나리 3차: WebP 거부 → JPEG 실변환 (네이버 경로 전용) ────────────────────────
# 네이버 400 원문: "PhotoInfraUpload.extension — JPEG/JPG/GIF/PNG/BMP만 허용".
# 소스가 amazon.de WebP였다. **파일명 위장이 아니라 실제 바이트 변환**이어야 한다.

def _mk_image(fmt: str, *, alpha: bool = False, size=(600, 600)) -> bytes:
    """계약 검증용 **실제 이미지 바이트** 생성(Pillow)."""
    from io import BytesIO
    from PIL import Image
    mode = "RGBA" if alpha else "RGB"
    bg = (255, 0, 0, 0) if alpha else (255, 0, 0)
    im = Image.new(mode, size, bg)
    im.paste(Image.new(mode, (200, 200), (0, 0, 255, 255) if alpha else (0, 0, 255)), (0, 0))
    # 1KB 게이트를 넘도록 압축되지 않는 잡음을 섞는다(단색은 webp가 1KB 미만으로 줄어든다).
    rnd = random.Random(7)
    px = im.load()
    for y in range(0, size[1] // 2, 3):        # 아래 절반은 깨끗이 둔다(플래튼 검증용)
        for x in range(0, size[0], 3):
            px[x, y] = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256),
                        255) if alpha else (rnd.randrange(256), rnd.randrange(256),
                                            rnd.randrange(256))
    if fmt.upper() in ("JPEG", "BMP") and alpha:
        im = im.convert("RGB")
    buf = BytesIO()
    im.save(buf, format=fmt.upper())
    return buf.getvalue()


def test_pillow_available_for_conversion():
    """변환은 Pillow에 의존한다 — 서버 가용성부터 못박는다(파일럿 이미지 처리에서 이미 사용)."""
    from PIL import Image                                    # noqa: F401
    assert IN.convert_image_bytes(_mk_image("PNG")) is not None


@pytest.mark.parametrize("fmt,ext", [("JPEG", "jpg"), ("PNG", "png"),
                                     ("GIF", "gif"), ("BMP", "bmp"), ("WEBP", "webp")])
def test_magic_bytes_detect_format(fmt, ext):
    """형식 판별은 **매직 바이트 우선**(CDN이 Content-Type을 틀리게 줄 수 있다)."""
    assert IN.detect_image_format(_mk_image(fmt)) == ext


def test_webp_converted_to_real_jpeg_bytes(monkeypatch):
    """webp 바이트 → **jpeg 실변환**. 매직바이트(\\xff\\xd8\\xff)로 검증 — 확장자만 바꾼 위장이면 실패."""
    webp = _mk_image("WEBP")
    assert IN.detect_image_format(webp) == "webp"
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(webp, ct="image/webp"))
    got = SS(account="chezgoga")._fetch_image("https://m.media-amazon.com/i/a.jpg")
    assert got is not None
    body, name = got.data, got.filename
    assert name == "img.jpg"
    assert body[:3] == b"\xff\xd8\xff"                        # 진짜 JPEG
    assert IN.detect_image_format(body) == "jpg"
    assert body != webp                                       # 원본 바이트가 아니다


def test_webp_alpha_flattened_on_white():
    """webp 알파 채널은 JPEG가 못 담는다 → **흰 배경 플래튼**(검게 뭉치지 않는다)."""
    from io import BytesIO
    from PIL import Image
    conv = IN.convert_image_bytes(_mk_image("WEBP", alpha=True))
    assert conv is not None
    with Image.open(BytesIO(conv)) as im:
        assert im.mode == "RGB"
        assert im.getpixel((im.width - 5, im.height - 5)) == (255, 255, 255)   # 투명 → 흰색


@pytest.mark.parametrize("fmt,ext", [("JPEG", "jpg"), ("PNG", "png"),
                                     ("GIF", "gif"), ("BMP", "bmp")])
def test_allowed_formats_pass_through_unconverted(monkeypatch, fmt, ext):
    """허용 형식(jpeg/png/gif/bmp)은 **무변환 통과** — 불필요한 재인코딩 금지."""
    raw = _mk_image(fmt)
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(raw, ct=f"image/{ext}"))
    got = SS(account="chezgoga")._fetch_image("https://x/a")
    body, name = got.data, got.filename
    assert name == f"img.{ext}"
    assert body == raw                                        # 바이트 동일 = 무변환


def test_conversion_failure_skips_image_with_reason(monkeypatch, caplog):
    """변환 실패 시 그 이미지는 **스킵 + 사유 로그**(가짜 성공 0)."""
    monkeypatch.setattr("requests.get",
                        lambda u, **k: _fake_resp(b"RIFF" + b"\x00" * 4 + b"WEBP" + b"z" * 2000,
                                                  ct="image/webp"))
    with caplog.at_level("WARNING"):
        assert SS(account="chezgoga")._fetch_image("https://x/a.webp") is None
    assert any("변환" in r.message or "변환" in r.getMessage() for r in caplog.records)


def test_conversion_failure_zero_images_blocks_registration(monkeypatch):
    """변환 전멸 → 0장 → **기존 게이트가 등록 차단**(카나리를 이미지 없이 태우지 않는다)."""
    monkeypatch.setattr("src.collectors.image_norm.fetch_image_bytes", lambda u, **k: None)
    out = SS(account="chezgoga").upload_images(["https://x/a.webp", "https://x/b.webp"])
    assert out["ok"] is False and "0장" in out["reason"] and len(out["skipped"]) == 2


def test_conversion_is_naver_only_not_global(monkeypatch):
    """**쿠팡/WC 전역 강제 금지**(오너 지시) — allowed_formats 미지정이면 webp 원본 그대로."""
    webp = _mk_image("WEBP")
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(webp, ct="image/webp"))
    got = IN.fetch_image_bytes("https://x/a.jpg")              # 기본 호출 = 쿠팡·WC 경로
    assert got.filename == "img.webp" and got.data == webp
    assert got.content_type == "image/webp"


def test_naver_declares_allowed_formats_and_passes_them():
    """허용 형식 집합은 **네이버 업로더가 보유**하고 fetch에 넘긴다(전역 상수 아님)."""
    assert set(SS.IMAGE_ALLOWED_FORMATS) >= {"jpg", "png", "gif", "bmp"}
    assert "webp" not in {f.lower() for f in SS.IMAGE_ALLOWED_FORMATS}
    src = Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8")
    assert "allowed_formats=self.IMAGE_ALLOWED_FORMATS" in src


def test_coupang_uploader_does_not_force_conversion():
    """쿠팡 업로더는 allowed_formats를 넘기지 않는다(webp 무해 — 마켓별 이미지 축)."""
    src = Path("src/uploaders/coupang_uploader.py").read_text(encoding="utf-8")
    assert "allowed_formats" not in src


def test_pillow_pinned_in_requirements():
    """**프로덕션 이미지에 Pillow가 실제로 들어가야** 변환이 산다.

    실측 근원(카나리 3차 부수 발견): Pillow가 requirements.txt에 없었고 `pip show` Required-by도
    비어 있어(전이 의존 0), Dockerfile이 requirements만 설치하는 프로덕션에는 **Pillow가 없었다**.
    지연 import라 예외 없이 조용히 무력화된다 — 변환 전멸 → 이미지 0장 → 등록 차단.
    """
    req = Path("requirements.txt").read_text(encoding="utf-8")
    assert any(l.strip().lower().startswith("pillow") for l in req.splitlines()), \
        "Pillow가 requirements.txt에 없다 — 프로덕션에서 이미지 변환이 조용히 죽는다"


# ── 카나리 5차: 멀티파트 part 메타 (filename · Content-Type · 바이트 3종 동시) ──────
# 네이버 400: invalidInputs name=imageFiles[0], type=PhotoInfraUpload.extension.
# 실측 근원: `files=[(name,(filename, body))]` **2-튜플**을 주면 requests가 part Content-Type을
# 아예 붙이지 않는다. filename은 이미 .jpg였다 — 빠진 건 part MIME이었다.

def _multipart_parts(fetched):
    """업로더와 **동일한 방식**으로 조립한 멀티파트에서 part 헤더+본문 시작을 뽑는다."""
    import requests as _rq
    files = [('imageFiles', (p.filename, p.data, p.content_type)) for p in fetched]
    prepped = _rq.Request('POST', SS.API_BASE + SS.IMAGE_UPLOAD_PATH, files=files).prepare()
    return prepped.body, prepped.headers['Content-Type']


def test_webp_part_carries_filename_contenttype_and_jpeg_bytes(monkeypatch):
    """webp 입력 → part의 **filename=.jpg · Content-Type=image/jpeg · 바이트 JPEG 매직** 3종 동시."""
    webp = _mk_image("WEBP")
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(webp, ct="image/webp"))
    p = SS(account="chezgoga")._fetch_image("https://m.media-amazon.com/i/a.jpg")
    assert p is not None
    # ① 3종 세트 자체
    assert (p.filename, p.content_type, p.ext) == ("img.jpg", "image/jpeg", "jpg")
    assert p.data[:3] == b"\xff\xd8\xff"
    # ② 실제 조립된 멀티파트에 셋이 전부 실렸는지
    body, ctype = _multipart_parts([p])
    assert ctype.startswith("multipart/form-data; boundary=")
    head = body[:400].decode("latin-1")
    assert 'name="imageFiles"; filename="img.jpg"' in head
    assert "Content-Type: image/jpeg" in head          # ← 카나리 5차에 빠져 있던 줄
    assert b"\r\n\r\n\xff\xd8\xff" in body[:600]        # 헤더 끝 직후가 JPEG 매직


def test_multipart_never_omits_part_content_type():
    """**2-튜플 조립 금지** — 업로더가 3-튜플로 넘기지 않으면 part MIME이 사라진다(회귀 봉인)."""
    src = Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8")
    assert "(p.filename, p.data, p.content_type)" in src
    # 실증: 2-튜플이면 정말 Content-Type이 없다(우리 주장의 근거를 테스트가 직접 보여준다).
    import requests as _rq
    two = _rq.Request('POST', SS.API_BASE, files=[('imageFiles', ("img.jpg", b"x" * 32))]).prepare()
    assert "Content-Type: image/jpeg" not in two.body[:300].decode("latin-1")


@pytest.mark.parametrize("fmt,ext,ct", [("JPEG", "jpg", "image/jpeg"), ("PNG", "png", "image/png"),
                                        ("GIF", "gif", "image/gif"), ("BMP", "bmp", "image/bmp")])
def test_allowed_formats_keep_their_own_mime(monkeypatch, fmt, ext, ct):
    """무변환 통과 형식도 **자기 MIME**을 단다 — 전부 image/jpeg로 뭉개지 않는다."""
    raw = _mk_image(fmt)
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(raw, ct=ct))
    p = SS(account="chezgoga")._fetch_image("https://x/a")
    assert (p.filename, p.content_type, p.ext) == (f"img.{ext}", ct, ext)
    assert p.data == raw
    assert f"Content-Type: {ct}" in _multipart_parts([p])[0][:400].decode("latin-1")


def test_meta_cannot_diverge_from_bytes():
    """**이중화 구조적 차단** — 메타는 바이트를 되읽어 검증한 뒤에만 만들어진다."""
    jpeg = _mk_image("JPEG")
    assert IN._make_part(jpeg, "jpg") is not None
    assert IN._make_part(jpeg, "png") is None          # 확장자만 갈아끼운 위장은 통과 못 한다
    assert IN._make_part(_mk_image("WEBP"), "jpg") is None
    assert IN._make_part(jpeg, "tiff") is None         # MIME 미상 형식


def test_ext_and_mime_tables_do_not_diverge():
    """수신(CT→ext)과 발신(ext→MIME) 표가 **같은 ext 집합**을 덮는다(한쪽만 늘리면 red)."""
    assert set(IN._EXT_BY_CT.values()) <= set(IN._CT_BY_EXT)
    for ext, ct in IN._CT_BY_EXT.items():
        assert IN._EXT_BY_CT.get(ct) == ext, (ext, ct)   # 정규 MIME은 왕복이 일치


def test_upload_logs_part_metadata(monkeypatch, caplog):
    """다음 반려 때 **추측 대신 증거**로 판정하도록 실제 part 메타를 로그로 남긴다."""
    up = SS(account="chezgoga")
    monkeypatch.setattr("src.collectors.image_norm.fetch_image_bytes",
                        lambda u, **k: IN.FetchedImage(b"\xff\xd8\xff" + b"x" * 2000,
                                                       "image/jpeg", "jpg"))
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))
    with caplog.at_level("INFO"):
        up.upload_images(["https://x/a.jpg"])
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "img.jpg" in joined and "image/jpeg" in joined


# ── 카나리 6차: 실패 원문 노출(단계 태그) + 스킵 사유 ────────────────────────────
# 오너 회수 로그가 확정한 것: parts 라인까지 도달 = 토큰·변환·조립 통과.
# **측정 정정**: generic "API request failed after retries"는 `_api_request`에만 있고
# `upload_images`는 그 함수를 쓰지 않는다 → 이미지 업로드는 성공, 실패는 상품 등록 POST였다.

def test_generic_failure_message_is_gone():
    """generic 문구 금지 — 사유는 단계·시도·유형·상태·본문으로만 말한다(로그 고고학 종료).

    주석에는 옛 문구가 근거로 남아 있어도 되므로 **실행되는 줄**만 본다.
    """
    lines = [l for l in Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8").splitlines()
             if not l.lstrip().startswith("#")]
    code = "\n".join(lines)
    for gone in ("API request failed after retries", "Authentication failed (401)", "Server error ("):
        assert gone not in code, gone


def test_product_register_4xx_surfaces_naver_body(monkeypatch):
    """★ 카나리 6차 근원: 상품 등록 4xx가 **원문째** 올라온다(3회 삼키기 금지)."""
    up = SS(account="chezgoga")
    up.client_id, up.client_secret = "cid", "sec"
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    calls = []

    class _R:
        status_code = 400
        text = '{"invalidInputs":[{"name":"leafCategoryId","message":"카테고리 오류"}]}'
        content = text.encode()
        def raise_for_status(self):
            raise AssertionError("4xx는 raise_for_status 전에 반환돼야 한다")

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request",
                        lambda *a, **k: calls.append(1) or _R())
    out = up._api_request("POST", "/v2/products", data={})
    assert len(calls) == 1                                   # 4xx는 재시도 낭비 0
    err = out["error"]
    for token in ("stage=POST /v2/products", "attempt=1", "http_status=400",
                  "leafCategoryId", "카테고리 오류"):
        assert token in err, (token, err)


def test_product_register_relay_error_is_distinguishable(monkeypatch):
    """릴레이가 죽은 것 vs 네이버가 거부한 것 — `error_type`으로 갈린다.

    `RelayError`는 `requests.RequestException` 상속이라 같은 except로 잡힌다(실측).
    유형을 안 찍으면 둘이 구분 불가 — 오너 지시 4항의 '릴레이 지목' 판정 근거.
    """
    from src.market_relay import RelayError
    up = SS(account="chezgoga")
    up.client_id, up.client_secret = "cid", "sec"
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RelayError("릴레이 오류: 릴레이가 HTTP 504")))
    err = up._api_request("POST", "/v2/products", data={})["error"]
    assert "error_type=RelayError" in err and "504" in err
    assert "최대 3회" in err          # 네트워크 계열은 3회 소진 후 사유


def test_product_register_timeout_says_so(monkeypatch):
    """타임아웃이면 타임아웃이라고 말한다(generic 금지)."""
    import requests as _rq
    up = SS(account="chezgoga")
    up.client_id, up.client_secret = "cid", "sec"
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request",
                        lambda *a, **k: (_ for _ in ()).throw(_rq.exceptions.ReadTimeout("timed out")))
    err = up._api_request("POST", "/v2/products", data={})["error"]
    assert "error_type=ReadTimeout" in err


def test_each_retry_logged_once(monkeypatch, caplog):
    """재시도 3회가 **각각** 1줄 — 같은 오류 3연속인지 다른 오류인지 구분(오너 지시 2항)."""
    import requests as _rq
    up = SS(account="chezgoga")
    up.client_id, up.client_secret = "cid", "sec"
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request",
                        lambda *a, **k: (_ for _ in ()).throw(_rq.exceptions.ConnectionError("boom")))
    with caplog.at_level("WARNING"):
        up._api_request("POST", "/v2/products", data={})
    lines = [r.getMessage() for r in caplog.records if "stage=POST /v2/products" in r.getMessage()]
    assert len(lines) == 3
    assert [f"attempt={i}" in lines[i - 1] for i in (1, 2, 3)] == [True, True, True]


def test_image_upload_failure_also_tagged(monkeypatch):
    """두 재시도 루프가 **같은 사유 조립기**를 쓴다 — 한쪽만 고쳐지는 패턴 차단."""
    import requests as _rq
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")
    monkeypatch.setattr("src.collectors.image_norm.fetch_image_bytes",
                        lambda u, **k: IN.FetchedImage(b"\xff\xd8\xff" + b"x" * 2000,
                                                       "image/jpeg", "jpg"))
    monkeypatch.setattr("time.sleep", lambda s: None)

    class _Err:
        status_code = 400
        text = "PhotoInfraUpload.extension"
        def raise_for_status(self):
            raise _rq.exceptions.HTTPError(response=self)

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request", lambda *a, **k: _Err())
    out = up.upload_images(["https://x/a.jpg"])
    assert out["ok"] is False
    for token in ("stage=image_upload", "http_status=400", "PhotoInfraUpload.extension"):
        assert token in out["reason"], (token, out["reason"])
    assert "전송" in out["reason"]        # 릴레이 지목 대비 — 페이로드 크기 동봉


@pytest.mark.parametrize("payload,ct,expect", [
    (b"x" * 300, "image/jpeg", "바이트"),                 # 1KB 미만
    (b"x" * 2000, "text/html", "형식 미상"),              # Content-Type 미지원
])
def test_skip_reason_is_reported(monkeypatch, payload, ct, expect):
    """조용한 스킵 금지 — 왜 빠졌는지 사유가 `skipped`에 실린다(오너 지시 3항)."""
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(payload, ct=ct))
    monkeypatch.setattr(SS, "_get_access_token", lambda self: "tok")
    out = SS(account="chezgoga").upload_images(["https://x/a.jpg"])
    assert out["ok"] is False
    assert len(out["skipped"]) == 1
    assert expect in out["skipped"][0]["reason"], out["skipped"]
    assert expect in out["reason"]                  # 0장 사유에도 그대로


def test_conversion_failure_skip_reason(monkeypatch):
    """변환 실패도 사유로 — '왜 3장 중 1장이 빠졌나'가 화면에서 읽힌다."""
    bad_webp = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"z" * 2000
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(bad_webp, ct="image/webp"))
    monkeypatch.setattr(SS, "_get_access_token", lambda self: "tok")
    out = SS(account="chezgoga").upload_images(["https://x/a.webp"])
    assert "변환 실패" in out["skipped"][0]["reason"]


def test_partial_skip_still_uploads_the_rest(monkeypatch):
    """일부 스킵돼도 남은 장수로 진행 — 스킵 사유는 표기하되 등록을 막지 않는다(3장 중 2장 사례)."""
    good = _mk_image("JPEG")
    seq = [good, b"x" * 100, good]                    # 가운데 1장만 1KB 미만
    monkeypatch.setattr("requests.get",
                        lambda u, **k: _fake_resp(seq.pop(0), ct="image/jpeg"))
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "_get_access_token", lambda: "tok")

    class _OK:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"images": [{"url": "https://n/1.jpg"}, {"url": "https://n/2.jpg"}]}

    monkeypatch.setattr("src.uploaders.naver_uploader.relay_request", lambda *a, **k: _OK())
    out = up.upload_images(["https://x/a.jpg", "https://x/b.jpg", "https://x/c.jpg"])
    assert out["ok"] is True and len(out["urls"]) == 2
    assert len(out["skipped"]) == 1 and "바이트" in out["skipped"][0]["reason"]


def test_naver_image_endpoint_is_ip_gated_same_as_product(monkeypatch):
    """오너 지시 4항 조사 — 이미지 엔드포인트도 **같은 호스트·같은 IP 게이트**다.

    `api.commerce.naver.com`이 릴레이 허용 호스트이고 smartstore가 IP 게이트 대상이므로,
    '이미지 업로드만 직결'은 게이트를 우회하는 셈이 된다 → **구조적 해법 아님**.
    (게다가 6차 로그상 이미지 업로드는 성공했다 — 재배선 근거 자체가 없다. 추측 배선 금지.)
    """
    from urllib.parse import urlparse
    from src import market_relay as MR
    host = urlparse(SS.API_BASE + SS.IMAGE_UPLOAD_PATH).hostname
    assert host == "api.commerce.naver.com"
    assert host in MR._API_RELAY_ALLOWED_HOSTS
    assert "smartstore" in MR._IP_GATED_MARKETS
    assert issubclass(MR.RelayError, __import__("requests").exceptions.RequestException)


# ── 카나리 7차: 정본 템플릿 기본값 + 페이로드 오버레이 (오너 지시 3항) ──────────────
# 네이버 400: originProduct.detailAttribute.minorPurchasable NotNull.
# 근원: 정본 ss_upload.py는 ss_template.json의 originProduct 기본값 **위에** 페이로드를 얹는다.
# 필드를 하나씩 때우지 않는다(오너 지시 2항) — 템플릿 도착 시 통째 승계.

def test_merge_order_is_template_then_payload(monkeypatch):
    """조립 순서 = **deepcopy(템플릿) → 페이로드 덮어쓰기**(정본과 동일)."""
    tpl = {"originProduct": {"detailAttribute": {"minorPurchasable": True},
                             "statusType": "WAIT", "customField": "정본기본값"}}
    monkeypatch.setattr(SS, "_template_cache", tpl, raising=False)
    p = SS(account="chezgoga")._build_product_payload(_PRODUCT)
    op = p["originProduct"]
    # ① 템플릿에만 있는 기본값은 **살아남는다**(이번 반려의 그 필드).
    assert op["detailAttribute"]["minorPurchasable"] is True
    assert op["customField"] == "정본기본값"
    # ② 우리가 채우는 값은 템플릿을 **덮는다**(페이로드 우선).
    assert op["statusType"] == "SALE"
    assert op["salePrice"] == 894000


def test_merge_is_deep_not_shallow(monkeypatch):
    """얕은 update면 `detailAttribute` 통째 대입이 템플릿 형제 기본값을 **지운다** — 그게 근원이다."""
    # 형제 기본값은 **우리가 건드리지 않는** 서브트리로 잡는다(고시정보는 이제 우리가 덮는다).
    tpl = {"originProduct": {"detailAttribute": {"minorPurchasable": True,
                                                 "seoInfo": {"sellerTags": [{"text": "정본"}]}}}}
    monkeypatch.setattr(SS, "_template_cache", tpl, raising=False)
    da = SS(account="chezgoga")._build_product_payload(_PRODUCT)["originProduct"]["detailAttribute"]
    assert da["minorPurchasable"] is True                 # 형제 기본값 생존
    assert da["seoInfo"] == {"sellerTags": [{"text": "정본"}]}
    assert da["customsTaxType"] == "PURCHASE_AGENT"       # 우리 값도 함께
    assert da["originAreaInfo"]["originAreaCode"] == "03"


def test_template_is_not_mutated_between_calls(monkeypatch):
    """deepcopy — 한 번 등록한 값이 캐시된 템플릿을 오염시키면 다음 상품에 샌다."""
    tpl = {"originProduct": {"detailAttribute": {"minorPurchasable": True}}}
    monkeypatch.setattr(SS, "_template_cache", tpl, raising=False)
    up = SS(account="chezgoga")
    up._build_product_payload({**_PRODUCT, "title": "첫 상품", "sku": "AAA"})
    second = up._build_product_payload({**_PRODUCT, "title": "둘째 상품", "sku": "BBB"})
    assert tpl["originProduct"]["detailAttribute"] == {"minorPurchasable": True}   # 원본 불변
    assert second["originProduct"]["detailAttribute"]["sellerCodeInfo"][
        "sellerManagementCode"] == "BBB"                  # 이전 상품 값이 새지 않는다


def test_empty_template_keeps_current_behaviour(monkeypatch):
    """템플릿 미도착 = **현재 동작 불변**(가짜 기본값 발명 0)."""
    monkeypatch.setattr(SS, "_template_cache", {}, raising=False)
    p = SS(account="chezgoga")._build_product_payload(_PRODUCT)
    assert p["originProduct"]["statusType"] == "SALE"
    assert "minorPurchasable" not in p["originProduct"]["detailAttribute"]


def test_no_stopgap_field_patch_in_source():
    """오너 지시 2항 — **임시 배선 금지**. minorPurchasable을 코드에 박지 않는다(템플릿이 준다)."""
    src = Path("src/uploaders/naver_uploader.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "'minorPurchasable'" not in code and '"minorPurchasable"' not in code


def test_template_status_is_honest():
    """미승계를 '됐다'고 말하지 않는다 — 진단이 ready=False로 사실을 말한다."""
    SS._template_cache = None                      # 실제 파일을 읽는다
    st = SS.template_status()
    assert st["path"].endswith("ss_template.json")
    assert isinstance(st["ready"], bool)
    assert st["ready"] is bool(SS.payload_template())


def test_template_note_keys_are_not_sent():
    """`_` 접두 메모 키는 전송 페이로드에 실리지 않는다."""
    SS._template_cache = None
    assert not any(k.startswith("_") for k in SS.payload_template())


def test_template_file_is_valid_json():
    """템플릿 파일은 항상 파싱 가능해야 한다(도착 시 붙여넣기 실수 조기 검출)."""
    import json as _json
    raw = _json.loads(Path("src/uploaders/ss_template.json").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)


def test_template_ships_in_docker_image():
    """`COPY src/`에 포함되는 위치여야 한다 — scripts/ 누락 선례(#423) 재발 방지."""
    assert Path("src/uploaders/ss_template.json").exists()
    df = Path("Dockerfile").read_text(encoding="utf-8")
    assert "COPY src/" in df


# ── 카나리 8차 준비: 정본 템플릿의 **상품별 예시값 오염 차단** (오너 지시 4항) ──────
# 오너 실측: 템플릿에 하베스트라벨 상품의 예시값이 남아 있다(itemName·modelName·manufacturer).
# 이게 살아 나가면 **남의 상품 정보로 등록**하는 것 — 정직 데이터 위반이자 마켓 제재 사유.

_TPL_FIXTURE = {                       # 오너가 지목한 실제 값들로 재현(파일 미도착 → 값만 인용)
    "originProduct": {
        "saleType": "NEW",
        "detailAttribute": {
            "minorPurchasable": True,
            "customsTaxType": "NOT_APPLICABLE",
            "sellerCodeInfo": {"sellerManagementCode": "hgl-0187"},
            "productInfoProvidedNotice": {
                "productInfoProvidedNoticeType": "ETC",
                "etc": {"itemName": "HARVEST LABEL 하베스트라벨 토트백",
                        "modelName": "hgl-0187",
                        "manufacturer": "HARVEST LABEL",
                        "afterServiceDirector": "070-0000-0000"}},
        },
        "deliveryInfo": {"businessCustomsClearanceSaleYn": True, "deliveryCompany": "CJGLS",
                         "claimDeliveryInfo": {"shippingAddressId": 107519663}},
    }
}


@pytest.fixture
def _tpl(monkeypatch):
    import copy as _copy
    monkeypatch.setattr(SS, "_template_cache", _copy.deepcopy(_TPL_FIXTURE), raising=False)
    return SS(account="chezgoga")


def test_notice_etc_is_overridden_with_our_product(_tpl):
    """① 고시정보 etc = **우리 상품 값**(쿠팡 고시와 같은 소스: 상품명·SKU·수집 브랜드·env 연락처)."""
    etc = _tpl._build_product_payload(_PRODUCT)["originProduct"]["detailAttribute"][
        "productInfoProvidedNotice"]["etc"]
    assert etc["itemName"] == "Fellow Stagg 주전자"
    assert etc["modelName"] == "B0GS4698H2"
    assert etc["manufacturer"] == "Fellow"
    assert "HARVEST" not in json.dumps(etc, ensure_ascii=False)


def test_notice_as_director_from_env(monkeypatch):
    """afterServiceDirector = env 연락처. 미설정이면 **빈 값**(예시 연락처를 물려받지 않는다)."""
    import copy as _copy
    monkeypatch.setattr(SS, "_template_cache", _copy.deepcopy(_TPL_FIXTURE), raising=False)
    monkeypatch.setenv("NAVER_CHEZGOGA_AS_PHONE", "02-1234-5678")
    etc = SS(account="chezgoga")._build_product_payload(_PRODUCT)["originProduct"][
        "detailAttribute"]["productInfoProvidedNotice"]["etc"]
    assert etc["afterServiceDirector"] == "02-1234-5678"
    monkeypatch.delenv("NAVER_CHEZGOGA_AS_PHONE")
    etc2 = SS(account="chezgoga")._build_product_payload(_PRODUCT)["originProduct"][
        "detailAttribute"]["productInfoProvidedNotice"]["etc"]
    assert etc2["afterServiceDirector"] == ""          # 예시값 070-0000-0000 이 아니다


def test_no_example_values_survive_in_payload(_tpl):
    """① 계약 본체 — 전송 페이로드에 `HARVEST LABEL`·`hgl-0187` **잔존 0**."""
    blob = json.dumps(_tpl._build_product_payload(_PRODUCT), ensure_ascii=False)
    assert "HARVEST LABEL" not in blob
    assert "hgl-0187" not in blob
    assert _tpl.find_template_leaks(_tpl._build_product_payload(_PRODUCT)) == []


def test_leak_scanner_catches_field_we_do_not_override():
    """필드를 **빠뜨리면 조용히 샌다** — 값 기준 전수 스캔이 그걸 잡는다(필드 열거 방식의 한계 보완)."""
    leaked = {"originProduct": {"detailAttribute": {"productInfoProvidedNotice": {
        "etc": {"certificateDetails": "HARVEST LABEL 인증"}}}}}
    found = SS.find_template_leaks(leaked)
    assert len(found) == 1
    assert found[0]["path"].endswith("etc.certificateDetails")
    assert found[0]["token"] == "HARVEST LABEL"


def test_leak_blocks_registration(monkeypatch):
    """유출이 남으면 **등록 중단**(held) — 남의 상품 정보로 등록하느니 멈춘다(택배사 게이트 동형)."""
    up = SS(account="chezgoga")
    monkeypatch.setattr(up, "_build_product_payload",
                        lambda p: {"originProduct": {"name": "HARVEST LABEL 토트백"}})
    monkeypatch.setattr(up, "_api_request",
                        lambda *a, **k: pytest.fail("유출 상태로 네이버에 보내면 안 된다"))
    out = up.upload_product({"sku": "X1", "images": []})
    assert out["success"] is False and out["held"] is True
    assert "템플릿 예시값" in out["error"] and "HARVEST LABEL" in out["error"]


def test_extra_leak_tokens_from_env(monkeypatch):
    """예시값이 더 발견되면 배포 없이 env로 막는다(`NAVER_TEMPLATE_EXAMPLE_TOKENS`)."""
    monkeypatch.setenv("NAVER_TEMPLATE_EXAMPLE_TOKENS", "샘플상호, 000-0000")
    found = SS.find_template_leaks({"a": {"b": "샘플상호 주식회사"}})
    assert found and found[0]["token"] == "샘플상호"


def test_env_address_beats_template(_tpl, monkeypatch):
    """② 주소 ID 우선순위 = **env > 템플릿**. 템플릿 107519663 이 아니라 정본 107519271 이 나간다."""
    cdi = _tpl._build_product_payload(_PRODUCT)["originProduct"]["deliveryInfo"]["claimDeliveryInfo"]
    assert cdi["shippingAddressId"] == 107519271
    assert SS.DEFAULT_ADDRESS_IDS["chezgoga"]["ship"] == "107519271"     # 정본 스크립트 값
    monkeypatch.setenv("NAVER_CHEZGOGA_SHIP_ADDRESS_ID", "999111")       # env가 최우선
    assert SS(account="chezgoga")._build_product_payload(
        _PRODUCT)["originProduct"]["deliveryInfo"]["claimDeliveryInfo"]["shippingAddressId"] == 999111


def test_customs_and_seller_code_override_template(_tpl):
    """③ 구매대행 통관·판매자코드는 **우리 값이 이긴다**(정본 ss_upload의 da 덮어쓰기 순서)."""
    da = _tpl._build_product_payload(_PRODUCT)["originProduct"]["detailAttribute"]
    assert da["customsTaxType"] == "PURCHASE_AGENT"          # 템플릿 NOT_APPLICABLE 아님
    assert da["sellerCodeInfo"]["sellerManagementCode"] == "B0GS4698H2"   # hgl-0187 아님


def test_structural_defaults_are_inherited(_tpl):
    """④ 구조 기본값은 **그대로 승계** — 우리가 안 채우는 필드는 템플릿이 맡는다."""
    p = _tpl._build_product_payload(_PRODUCT)
    op, di = p["originProduct"], p["originProduct"]["deliveryInfo"]
    assert di["businessCustomsClearanceSaleYn"] is True
    assert di["deliveryCompany"] == "CJGLS"
    assert op["detailAttribute"]["minorPurchasable"] is True             # 7차 반려 필드
    assert op["detailAttribute"]["productInfoProvidedNotice"][
        "productInfoProvidedNoticeType"] == "ETC"                        # 타입도 승계
