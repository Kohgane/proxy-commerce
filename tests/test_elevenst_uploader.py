"""tests/test_elevenst_uploader.py — 11번가 OpenAPI 업로더 단위 검증.

requests를 목 처리하여 prepare_product 매핑, XML 구성, 응답 파싱,
업로드 성공/실패 계약(CoupangUploader와 동일)을 고정한다.
라이브 검증은 운영 환경에서 ELEVENST_API_KEY로 별도 수행.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def uploader(monkeypatch):
    monkeypatch.setenv("ELEVENST_API_KEY", "test-key")
    from src.uploaders.elevenst_uploader import ElevenStUploader
    return ElevenStUploader()


class TestPrepareProduct:
    def test_title_gets_haejikgu_prefix_and_price_rounds_to_10(self, uploader):
        prepared = uploader.prepare_product({
            "title_ko": "테스트 상품",
            "sell_price_krw": 19999,
            "category_code": "BTY",
            "images": ["https://img/1.jpg"],
        })
        assert prepared["title"].startswith("[해외직구]")
        assert prepared["price"] == 20000  # 10원 단위 올림
        assert prepared["category_id"] == uploader.CATEGORY_MAP["BTY"]

    def test_empty_collected_returns_empty(self, uploader):
        assert uploader.prepare_product({}) == {}

    def test_unknown_category_uses_default(self, uploader):
        prepared = uploader.prepare_product({"title_ko": "x", "sell_price_krw": 1000, "category_code": "ZZZ"})
        assert prepared["category_id"] == uploader.default_category


class TestBuildXml:
    def test_xml_contains_core_fields_and_escapes(self, uploader):
        xml = uploader._build_product_xml({
            "title": "A & B <test>",
            "price": 12340,
            "images": ["https://img/1.jpg", "https://img/2.jpg"],
            "category_id": "1001819",
            "brand": "BR",
            "stock": 999,
        })
        assert "<selPrc>12340</selPrc>" in xml
        assert "<dispCtgrNo>1001819</dispCtgrNo>" in xml
        # XML 이스케이프 적용
        assert "A &amp; B &lt;test&gt;" in xml
        assert "<prdImage01>https://img/1.jpg</prdImage01>" in xml


class TestParseResponse:
    def test_success_with_product_no(self):
        from src.uploaders.elevenst_uploader import ElevenStUploader
        xml = "<ProductResponse><result_code>200</result_code><ProductNo>123456</ProductNo></ProductResponse>"
        parsed = ElevenStUploader._parse_response(xml)
        assert parsed["ok"] is True
        assert parsed["product_no"] == "123456"

    def test_failure_code(self):
        from src.uploaders.elevenst_uploader import ElevenStUploader
        xml = "<ProductResponse><result_code>500</result_code><result_text>오류</result_text></ProductResponse>"
        parsed = ElevenStUploader._parse_response(xml)
        assert parsed["ok"] is False
        assert "오류" in parsed["message"]

    def test_malformed_xml(self):
        from src.uploaders.elevenst_uploader import ElevenStUploader
        parsed = ElevenStUploader._parse_response("not xml <<<")
        assert parsed["ok"] is False


class TestUploadProduct:
    def test_missing_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)
        from src.uploaders.elevenst_uploader import ElevenStUploader
        out = ElevenStUploader().upload_product({"sku": "S1", "title": "T", "price": 1000})
        assert out["success"] is False
        assert "ELEVENST_API_KEY" in out["error"]

    def test_success(self, uploader):
        resp = MagicMock(status_code=200,
                         text="<ProductResponse><result_code>200</result_code><ProductNo>P9</ProductNo></ProductResponse>")
        with patch("src.uploaders.elevenst_uploader.requests.post", return_value=resp):
            out = uploader.upload_product({"sku": "S1", "title": "T", "price": 1000, "images": []})
        assert out["success"] is True
        assert out["product_id"] == "P9"
        assert out["url"].endswith("/P9")

    def test_http_error(self, uploader):
        resp = MagicMock(status_code=401, text="Unauthorized")
        with patch("src.uploaders.elevenst_uploader.requests.post", return_value=resp):
            out = uploader.upload_product({"sku": "S1", "title": "T", "price": 1000})
        assert out["success"] is False
        assert "401" in out["error"]

    def test_api_logical_failure(self, uploader):
        resp = MagicMock(status_code=200,
                         text="<ProductResponse><result_code>500</result_code><result_text>등록 거부</result_text></ProductResponse>")
        with patch("src.uploaders.elevenst_uploader.requests.post", return_value=resp):
            out = uploader.upload_product({"sku": "S1", "title": "T", "price": 1000})
        assert out["success"] is False
        assert "등록 거부" in out["error"]
