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

from pathlib import Path

import pytest

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
    assert got is not None and got[1] == "img.jpg"
    assert "Mozilla" in seen["headers"]["User-Agent"]


def test_fetch_skips_tiny_files(monkeypatch):
    """1KB 미만 = 썸네일 쓰레기 → 스킵(정본)."""
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(b"x" * 500))
    assert SS(account="chezgoga")._fetch_image("https://x/a.jpg") is None


@pytest.mark.parametrize("ct,ext", [("image/jpeg", "jpg"), ("image/png", "png"),
                                    ("image/webp", "webp"), ("image/gif", "gif")])
def test_fetch_extension_from_content_type(monkeypatch, ct, ext):
    monkeypatch.setattr("requests.get", lambda u, **k: _fake_resp(b"x" * 2000, ct=ct))
    assert SS(account="chezgoga")._fetch_image("https://x/a")[1] == f"img.{ext}"


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
                        lambda u, **k: (b"x" * 2000, "img.jpg"))
    monkeypatch.setattr(up, "_get_access_token", lambda: "")
    up.token_error = "HTTP 403: {\"code\":\"GW.IP_NOT_ALLOWED\"}"
    out = up.upload_images(["https://x/a.jpg"])
    assert out["ok"] is False and "GW.IP_NOT_ALLOWED" in out["reason"]
