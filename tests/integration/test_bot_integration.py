"""tests/integration/test_bot_integration.py — 봇 명령어 통합 테스트."""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestBotCommandsIntegration:
    """봇 명령어 통합 테스트."""

    def test_cmd_sync_inventory(self):
        from src.bot.commands import cmd_sync_inventory
        result = cmd_sync_inventory()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_stock_status(self):
        from src.bot.commands import cmd_stock_status
        result = cmd_stock_status()
        assert isinstance(result, str)

    def test_cmd_stock_status_with_sku(self):
        from src.bot.commands import cmd_stock_status
        result = cmd_stock_status(sku='test-sku')
        assert isinstance(result, str)

    def test_cmd_translate(self):
        from src.bot.commands import cmd_translate
        result = cmd_translate(product_id='prod-001')
        assert isinstance(result, str)

    def test_cmd_translation_status(self):
        from src.bot.commands import cmd_translation_status
        result = cmd_translation_status()
        assert isinstance(result, str)

    def test_cmd_reprice(self):
        from src.bot.commands import cmd_reprice
        result = cmd_reprice(sku='test-sku')
        assert isinstance(result, str)

    def test_cmd_price_history(self):
        from src.bot.commands import cmd_price_history
        result = cmd_price_history(sku='test-sku')
        assert isinstance(result, str)

    def test_cmd_suppliers(self):
        from src.bot.commands import cmd_suppliers
        result = cmd_suppliers()
        assert isinstance(result, str)

    def test_cmd_supplier_score(self):
        from src.bot.commands import cmd_supplier_score
        result = cmd_supplier_score(supplier_id='sup-001')
        assert isinstance(result, str)

    def test_cmd_po_create(self):
        from src.bot.commands import cmd_po_create
        result = cmd_po_create(args='sup-001 test-sku 100')
        assert isinstance(result, str)

    def test_cmd_po_create_invalid(self):
        from src.bot.commands import cmd_po_create
        result = cmd_po_create(args='')
        assert isinstance(result, str)
        assert '사용법' in result or 'error' in result.lower() or '오류' in result
