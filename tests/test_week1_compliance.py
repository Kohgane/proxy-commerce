"""tests/test_week1_compliance.py — Tests for seller whitelist and Taobao gate."""
from __future__ import annotations

import pytest

from compliance.seller_whitelist import SellerWhitelist
from compliance.taobao_gate import GateResult, TaobaoGate


# ---------------------------------------------------------------------------
# SellerWhitelist tests
# ---------------------------------------------------------------------------

class TestSellerWhitelist:
    def test_from_ids(self):
        wl = SellerWhitelist.from_ids(["TB-001", "TB-002"])
        assert "TB-001" in wl
        assert "TB-002" in wl
        assert "TB-999" not in wl

    def test_len(self):
        wl = SellerWhitelist.from_ids(["A", "B", "C"])
        assert len(wl) == 3

    def test_from_ids_strips_whitespace(self):
        wl = SellerWhitelist.from_ids(["  TB-001  ", "TB-002"])
        assert "TB-001" in wl

    def test_empty_whitelist(self):
        wl = SellerWhitelist.from_ids([])
        assert len(wl) == 0
        assert "TB-001" not in wl

    def test_ids_property_is_frozenset(self):
        wl = SellerWhitelist.from_ids(["A", "B"])
        assert isinstance(wl.ids, frozenset)

    def test_load_missing_file_returns_empty(self, tmp_path):
        wl = SellerWhitelist(path=tmp_path / "does_not_exist.yml")
        assert len(wl) == 0

    def test_load_yaml_file(self, tmp_path):
        yaml_file = tmp_path / "whitelist.yml"
        yaml_file.write_text("sellers:\n  - TB-GOLD-001\n  - TB-GOLD-002\n", encoding="utf-8")
        wl = SellerWhitelist(path=yaml_file)
        assert "TB-GOLD-001" in wl
        assert "TB-GOLD-002" in wl
        assert "TB-UNKNOWN" not in wl

    def test_load_json_file(self, tmp_path):
        import json
        json_file = tmp_path / "whitelist.json"
        json_file.write_text(json.dumps(["TB-A", "TB-B"]), encoding="utf-8")
        wl = SellerWhitelist(path=json_file)
        assert "TB-A" in wl
        assert "TB-B" in wl

    def test_extra_ids_merged(self, tmp_path):
        yaml_file = tmp_path / "whitelist.yml"
        yaml_file.write_text("sellers:\n  - TB-001\n", encoding="utf-8")
        wl = SellerWhitelist(path=yaml_file, extra_ids=["EXTRA-001"])
        assert "TB-001" in wl
        assert "EXTRA-001" in wl


# ---------------------------------------------------------------------------
# TaobaoGate tests
# ---------------------------------------------------------------------------

class TestTaobaoGate:
    def _gate(self, threshold: float = 0.6, ids=("TB-WHITE",)) -> TaobaoGate:
        return TaobaoGate(
            trust_threshold=threshold,
            extra_whitelist_ids=list(ids),
        )

    def test_whitelisted_seller_always_passes(self):
        gate = self._gate(threshold=0.9, ids=["TB-WHITE"])
        result = gate.check(seller_id="TB-WHITE", trust_score=0.0)
        assert result.allowed is True
        assert result.whitelisted is True

    def test_above_threshold_passes(self):
        gate = self._gate(threshold=0.6)
        result = gate.check(seller_id="TB-NEW", trust_score=0.8)
        assert result.allowed is True
        assert result.whitelisted is False

    def test_below_threshold_blocked(self):
        gate = self._gate(threshold=0.6)
        result = gate.check(seller_id="TB-RISKY", trust_score=0.4)
        assert result.allowed is False

    def test_exactly_at_threshold_passes(self):
        gate = self._gate(threshold=0.6)
        result = gate.check(seller_id="TB-EDGE", trust_score=0.6)
        assert result.allowed is True

    def test_result_fields(self):
        gate = self._gate(threshold=0.7)
        result = gate.check(seller_id="TB-X", trust_score=0.8)
        assert isinstance(result, GateResult)
        assert result.seller_id == "TB-X"
        assert result.trust_score == 0.8
        assert result.reason  # non-empty string

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            TaobaoGate(trust_threshold=1.5)
        with pytest.raises(ValueError):
            TaobaoGate(trust_threshold=-0.1)

    def test_out_of_range_score_clamped(self):
        gate = self._gate(threshold=0.6)
        result = gate.check(seller_id="TB-OVER", trust_score=1.5)
        assert result.trust_score == 1.0
        assert result.allowed is True

    def test_check_product_uses_source_product_id(self):
        gate = self._gate(threshold=0.5)

        class FakeProduct:
            source_product_id = "TB-PROD-001"

        result = gate.check_product(FakeProduct(), trust_score=0.7)
        assert result.seller_id == "TB-PROD-001"
        assert result.allowed is True
