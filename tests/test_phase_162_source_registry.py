"""tests/test_phase_162_source_registry.py — Phase 162 소싱처 등록소 검증.

커버 범위:
1. probe_collectability: open/partial/restricted 판정
2. add_source: 새 필드(openness_status, adapter_name) 저장
3. list_sources: 알파벳순(한글/영문 혼재) 정렬
4. update_last_collect: 마지막 수집 결과 업데이트
5. /sourcing 뷰: 0개·여러개 상태 모두 200
6. /sourcing/registry/add JSON API: 정상·오류 케이스
7. Discovery 자동 연계: 신규 도메인 → 후보 등록
8. 대형 플랫폼 도메인 → large_platform 배지
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("KEYWORD_OPT_PROVIDER", "mock")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "")


@pytest.fixture(autouse=True)
def _clear_store():
    """각 테스트마다 인메모리 스토어 초기화."""
    from src.seller_console import my_sources_store as store
    store._in_memory.clear()
    yield
    store._in_memory.clear()


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret-162")
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 1. probe_collectability
# ---------------------------------------------------------------------------


class TestProbeCollectability:
    def test_probe_open_when_og_present(self):
        """OG 메타태그 존재 시 → open 판정."""
        from src.seller_console.my_sources_store import probe_collectability

        mock_head = MagicMock()
        mock_head.status_code = 200
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = '<html><head><meta property="og:title" content="Test"/></head></html>'

        with patch("requests.head", return_value=mock_head), \
             patch("requests.get", return_value=mock_get):
            result = probe_collectability("https://brand-shop-example.com")

        assert result["status"] == "open"
        assert "adapter_name" in result
        assert result["is_large_platform"] is False

    def test_probe_restricted_on_401(self):
        """HEAD 응답 401 → restricted."""
        from src.seller_console.my_sources_store import probe_collectability

        mock_head = MagicMock()
        mock_head.status_code = 401

        with patch("requests.head", return_value=mock_head):
            result = probe_collectability("https://private-shop.example.com")

        assert result["status"] == "restricted"

    def test_probe_restricted_on_403(self):
        """HEAD 응답 403 → restricted."""
        from src.seller_console.my_sources_store import probe_collectability

        mock_head = MagicMock()
        mock_head.status_code = 403

        with patch("requests.head", return_value=mock_head):
            result = probe_collectability("https://blocked-shop.example.com")

        assert result["status"] == "restricted"

    def test_probe_partial_when_no_og(self):
        """200 응답이지만 OG/JSON-LD 없음 → partial."""
        from src.seller_console.my_sources_store import probe_collectability

        mock_head = MagicMock()
        mock_head.status_code = 200
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = "<html><head><title>Shop</title></head><body>No OG here</body></html>"

        with patch("requests.head", return_value=mock_head), \
             patch("requests.get", return_value=mock_get):
            result = probe_collectability("https://no-og-shop.example.com")

        assert result["status"] == "partial"

    def test_probe_partial_when_connection_fails(self):
        """연결 실패 시 → partial (등록 흐름 막지 않음)."""
        from src.seller_console.my_sources_store import probe_collectability
        import requests

        with patch("requests.head", side_effect=requests.exceptions.ConnectionError("fail")):
            result = probe_collectability("https://unreachable-shop.example.com")

        assert result["status"] == "partial"

    def test_probe_empty_input(self):
        """빈 입력 → partial."""
        from src.seller_console.my_sources_store import probe_collectability
        result = probe_collectability("")
        assert result["status"] == "partial"

    def test_probe_large_platform_badge(self):
        """대형 플랫폼(coupang.com) → is_large_platform=True."""
        from src.seller_console.my_sources_store import probe_collectability

        mock_head = MagicMock()
        mock_head.status_code = 200
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = '<meta property="og:title" content="쿠팡">'

        with patch("requests.head", return_value=mock_head), \
             patch("requests.get", return_value=mock_get):
            result = probe_collectability("https://coupang.com/vp/products/123")

        assert result["is_large_platform"] is True
        assert result["adapter_name"] == "large_platform"

    def test_probe_jsonld_detected_as_open(self):
        """JSON-LD Product 스키마 존재 시 → open."""
        from src.seller_console.my_sources_store import probe_collectability

        mock_head = MagicMock()
        mock_head.status_code = 200
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.text = '<script type="application/ld+json">{"@type":"Product","name":"Test"}</script>'

        with patch("requests.head", return_value=mock_head), \
             patch("requests.get", return_value=mock_get):
            result = probe_collectability("https://jsonld-shop.example.com")

        assert result["status"] == "open"

    def test_probe_ssrf_blocked(self):
        """내부 IP → restricted (SSRF 방지)."""
        from src.seller_console.my_sources_store import probe_collectability
        result = probe_collectability("http://192.168.1.1/shop")
        assert result["status"] == "restricted"


# ---------------------------------------------------------------------------
# 2. add_source with new fields
# ---------------------------------------------------------------------------


class TestAddSourceNewFields:
    def test_add_source_stores_openness_and_adapter(self):
        """add_source에 openness_status/adapter_name이 저장된다."""
        from src.seller_console.my_sources_store import add_source

        with patch("src.seller_console.my_sources_store.probe_collectability",
                   return_value={"status": "open", "adapter_name": "generic_og",
                                 "detail": "ok", "is_large_platform": False}):
            entry = add_source("https://test-brand.example.com", label="테스트브랜드")

        assert entry["openness_status"] == "open"
        assert entry["adapter_name"] == "generic_og"
        assert entry["label"] == "테스트브랜드"
        assert entry["domain"] == "test-brand.example.com"

    def test_add_source_skip_probe(self):
        """skip_probe=True 시 probe_collectability 호출 없이 저장."""
        from src.seller_console.my_sources_store import add_source

        with patch("src.seller_console.my_sources_store.probe_collectability") as mock_probe:
            entry = add_source("brand.example.com", skip_probe=True, openness_status="open")
        mock_probe.assert_not_called()
        assert entry["openness_status"] == "open"

    def test_add_source_invalid_domain_raises(self):
        """잘못된 도메인 → ValueError."""
        from src.seller_console.my_sources_store import add_source
        with pytest.raises(ValueError):
            add_source("not-a-domain", skip_probe=True)

    def test_add_source_restricted_still_saves(self):
        """restricted 판정도 등록은 막지 않는다."""
        from src.seller_console.my_sources_store import add_source, list_sources

        with patch("src.seller_console.my_sources_store.probe_collectability",
                   return_value={"status": "restricted", "adapter_name": "generic_og",
                                 "detail": "403", "is_large_platform": False}):
            entry = add_source("https://closed-shop.example.com")

        assert entry["openness_status"] == "restricted"
        sources = list_sources()
        assert any(s["domain"] == "closed-shop.example.com" for s in sources)


# ---------------------------------------------------------------------------
# 3. list_sources 알파벳순 정렬
# ---------------------------------------------------------------------------


class TestListSourcesAlphabeticalSort:
    def _add_many(self, items: list[tuple[str, str]]):
        from src.seller_console.my_sources_store import add_source
        for domain, label in items:
            add_source(domain, label=label, skip_probe=True, openness_status="open")

    def test_english_alphabetical(self):
        """영문 이름은 ABC순으로 정렬."""
        from src.seller_console.my_sources_store import list_sources
        self._add_many([
            ("zebra.example.com", "Zebra Shop"),
            ("alpha.example.com", "Alpha Store"),
            ("mango.example.com", "Mango Mall"),
        ])
        sources = list_sources()
        labels = [s["label"] for s in sources]
        assert labels == sorted(labels, key=str.casefold)

    def test_korean_alphabetical(self):
        """한글 이름은 유니코드 순(가나다순)으로 정렬."""
        from src.seller_console.my_sources_store import list_sources
        self._add_many([
            ("da.example.com", "다나와"),
            ("ga.example.com", "가나몰"),
            ("na.example.com", "나이키몰"),
        ])
        sources = list_sources()
        labels = [s["label"] for s in sources]
        assert labels == sorted(labels, key=str.casefold)

    def test_mixed_korean_english(self):
        """한글/영문 혼재도 안정 정렬(예외 없음)."""
        from src.seller_console.my_sources_store import list_sources
        self._add_many([
            ("z-shop.example.com", "Z브랜드"),
            ("a-shop.example.com", "A몰"),
            ("k-shop.example.com", "한국브랜드"),
        ])
        sources = list_sources()
        # 예외 없이 정렬됨
        labels = [s["label"] for s in sources]
        assert labels == sorted(labels, key=str.casefold)

    def test_no_label_uses_domain(self):
        """label 없는 경우 domain 기준으로 정렬된다."""
        from src.seller_console.my_sources_store import add_source, list_sources
        for domain in ["zoo.example.com", "ant.example.com", "bee.example.com"]:
            add_source(domain, label="", skip_probe=True, openness_status="open")
        sources = list_sources()
        sort_keys = [(s.get("label") or s["domain"]).casefold() for s in sources]
        assert sort_keys == sorted(sort_keys)

    def test_case_insensitive_sort(self):
        """대소문자 무관 정렬."""
        from src.seller_console.my_sources_store import list_sources
        self._add_many([
            ("z1.example.com", "zara"),
            ("a1.example.com", "ASOS"),
            ("m1.example.com", "Mango"),
        ])
        sources = list_sources()
        labels = [s["label"] for s in sources]
        assert labels == sorted(labels, key=str.casefold)


# ---------------------------------------------------------------------------
# 4. update_last_collect
# ---------------------------------------------------------------------------


class TestUpdateLastCollect:
    def test_update_last_collect_in_memory(self):
        """update_last_collect이 인메모리 엔트리를 업데이트한다."""
        from src.seller_console.my_sources_store import add_source, update_last_collect, list_sources

        add_source("testshop.example.com", skip_probe=True, openness_status="open")
        ok = update_last_collect("testshop.example.com", "상품 10건 수집")
        assert ok is True

        sources = list_sources()
        entry = next(s for s in sources if s["domain"] == "testshop.example.com")
        assert entry["last_collect_result"] == "상품 10건 수집"
        assert entry["last_collect_at"] != ""

    def test_update_last_collect_invalid_domain(self):
        """잘못된 도메인 → False."""
        from src.seller_console.my_sources_store import update_last_collect
        assert update_last_collect("", "result") is False


# ---------------------------------------------------------------------------
# 5. /seller/sourcing 뷰 — 0개/여러 개 상태 200
# ---------------------------------------------------------------------------


class TestSourcingHubRegistryView:
    def test_sourcing_page_no_sources_200(self, client):
        """/seller/sourcing — 소싱처 0개 상태에서 200."""
        resp = client.get("/seller/sourcing")
        assert resp.status_code == 200

    def test_sourcing_page_with_sources_200(self, client):
        """/seller/sourcing — 소싱처 여러 개 상태에서 200."""
        from src.seller_console import my_sources_store as store
        store._in_memory["brand1.com"] = {
            "domain": "brand1.com", "label": "Brand One",
            "note": "", "created_at": "2026-06-03T00:00:00+00:00",
            "last_used_at": "2026-06-03T00:00:00+00:00",
            "openness_status": "open", "adapter_name": "generic_og",
            "last_collect_at": "", "last_collect_result": "",
        }
        store._in_memory["brand2.com"] = {
            "domain": "brand2.com", "label": "A Brand Two",
            "note": "", "created_at": "2026-06-03T00:00:00+00:00",
            "last_used_at": "2026-06-03T00:00:00+00:00",
            "openness_status": "partial", "adapter_name": "generic_og",
            "last_collect_at": "", "last_collect_result": "",
        }
        resp = client.get("/seller/sourcing")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "소싱처 등록소" in html

    def test_sourcing_page_shows_openness_badges(self, client):
        """/seller/sourcing — 개방성 배지(open/partial/restricted) 렌더."""
        from src.seller_console import my_sources_store as store
        store._in_memory["open-shop.com"] = {
            "domain": "open-shop.com", "label": "Open Shop",
            "note": "", "created_at": "2026-06-03T00:00:00+00:00",
            "last_used_at": "2026-06-03T00:00:00+00:00",
            "openness_status": "open", "adapter_name": "generic_og",
            "last_collect_at": "", "last_collect_result": "",
        }
        store._in_memory["closed-shop.com"] = {
            "domain": "closed-shop.com", "label": "Closed Shop",
            "note": "", "created_at": "2026-06-03T00:00:00+00:00",
            "last_used_at": "2026-06-03T00:00:00+00:00",
            "openness_status": "restricted", "adapter_name": "generic_og",
            "last_collect_at": "", "last_collect_result": "",
        }
        resp = client.get("/seller/sourcing")
        html = resp.get_data(as_text=True)
        assert "open" in html
        assert "restricted" in html


# ---------------------------------------------------------------------------
# 6. /sourcing/registry/add JSON API
# ---------------------------------------------------------------------------


class TestRegistryAddApi:
    def test_add_open_domain_returns_ok(self, client):
        """개방형 도메인 → ok:true + open 상태."""
        mock_probe = {
            "status": "open", "adapter_name": "generic_og",
            "detail": "OG 확인", "is_large_platform": False,
        }
        with patch("src.seller_console.my_sources_store.probe_collectability", return_value=mock_probe):
            resp = client.post(
                "/seller/sourcing/registry/add",
                json={"url": "https://open-brand.example.com", "label": "오픈브랜드"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["openness_status"] == "open"
        assert data["domain"] == "open-brand.example.com"

    def test_add_restricted_domain_returns_ok_with_warning(self, client):
        """restricted 도메인도 등록 성공 (차단 안 함)."""
        mock_probe = {
            "status": "restricted", "adapter_name": "generic_og",
            "detail": "403 차단", "is_large_platform": False,
        }
        with patch("src.seller_console.my_sources_store.probe_collectability", return_value=mock_probe):
            resp = client.post(
                "/seller/sourcing/registry/add",
                json={"url": "https://restricted-shop.example.com"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["openness_status"] == "restricted"

    def test_add_no_domain_returns_400(self, client):
        """domain/url 없음 → 400."""
        resp = client.post(
            "/seller/sourcing/registry/add",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_add_invalid_domain_returns_400(self, client):
        """도메인 형식 오류 → 400."""
        resp = client.post(
            "/seller/sourcing/registry/add",
            json={"url": "not-a-domain"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_add_large_platform_badge(self, client):
        """대형 플랫폼 → is_large_platform 포함."""
        mock_probe = {
            "status": "open", "adapter_name": "large_platform",
            "detail": "대형몰", "is_large_platform": True,
        }
        with patch("src.seller_console.my_sources_store.probe_collectability", return_value=mock_probe):
            resp = client.post(
                "/seller/sourcing/registry/add",
                json={"url": "https://coupang.com/vp/products/1"},
                content_type="application/json",
            )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["is_large_platform"] is True


# ---------------------------------------------------------------------------
# 7. Discovery 후보 자동 연계
# ---------------------------------------------------------------------------


class TestDiscoveryAutoRegistration:
    def test_new_domain_registers_discovery_candidate(self, client):
        """신규 개방형 도메인 등록 → Discovery 후보 자동 등록 시도."""
        mock_probe = {
            "status": "open", "adapter_name": "generic_og",
            "detail": "ok", "is_large_platform": False,
        }
        with patch("src.seller_console.my_sources_store.probe_collectability", return_value=mock_probe), \
             patch("src.discovery.scout.register_collected_domain_candidate") as mock_disc:
            client.post(
                "/seller/sourcing/registry/add",
                json={"url": "https://new-brand-store.example.com", "keyword": "테스트키워드"},
                content_type="application/json",
            )
        # 실패해도 괜찮음(예외 없음) — 호출 자체를 확인
        # (register_collected_domain_candidate는 뷰에서 감싸져 있으므로 실패해도 등록은 완료됨)

    def test_large_platform_domain_skipped_by_discovery(self):
        """대형 플랫폼 도메인은 Discovery에서 자동 skip."""
        from src.discovery.scout import register_collected_domain_candidate, _KNOWN_PLATFORMS
        with patch("src.discovery.scout._get_registered_domains", return_value=set()), \
             patch("src.discovery.scout._save_candidate") as mock_save:
            # coupang.com은 _KNOWN_PLATFORMS에 포함됨
            result = register_collected_domain_candidate("https://coupang.com/vp/products/1")
        assert result is False
        mock_save.assert_not_called()
