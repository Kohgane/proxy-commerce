"""tests/e2e/test_collection_flow.py — E2E: 상품 수집 -> 번역 -> 가격 -> 재고 동기화."""

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestCollectionFlow:
    """상품 수집 -> 번역 -> 가격 산정 -> 재고 동기화 E2E 플로우 테스트."""

    def test_translate_product(self):
        """번역 요청 생성 및 승인 테스트."""
        from src.translation.translator import TranslationManager, STATUS_APPROVED, STATUS_REVIEW

        manager = TranslationManager()
        req = manager.create_request('prod-001', 'Free Shipping', 'en', 'ko')

        assert req['product_id'] == 'prod-001'
        assert req['status'] == STATUS_REVIEW
        assert req['translated_text'] is not None

        ok = manager.approve(req['request_id'])
        assert ok is True

        updated = manager.get_status(req['request_id'])
        assert updated['status'] == STATUS_APPROVED

    def test_glossary_applied(self):
        """용어집 적용 테스트."""
        from src.translation.glossary import CommerceGlossary

        glossary = CommerceGlossary()
        result = glossary.apply('Free Shipping available. In Stock.')
        assert '무료배송' in result
        assert '재고있음' in result

    def test_quality_check(self):
        """번역 품질 검사 테스트."""
        from src.translation.quality_checker import QualityChecker

        checker = QualityChecker()
        result = checker.check('Hello World', '안녕하세요')
        assert 'is_valid' in result
        assert 'issues' in result

    def test_price_calculation(self):
        """가격 산정 테스트."""
        from src.pricing_engine.rules import MarginBasedRule, CompetitorBasedRule
        from decimal import Decimal

        rule = MarginBasedRule(cost=Decimal('10000'), margin_rate=0.3, channel_fee_rate=0.05)
        price = rule.calculate_price()
        assert price > Decimal('10000')

        comp_rule = CompetitorBasedRule(competitor_price=Decimal('15000'), adjustment_pct=-0.02)
        comp_price = comp_rule.calculate_price()
        assert comp_price < Decimal('15000')

    def test_inventory_sync(self):
        """재고 동기화 테스트."""
        from src.inventory_sync.sync_manager import InventorySyncManager

        manager = InventorySyncManager()
        status = manager.get_sync_status()
        assert 'channels' in status
        assert 'coupang' in status['channels']

    def test_full_flow(self):
        """전체 플로우 통합 테스트."""
        from src.translation.translator import TranslationManager
        from src.pricing_engine.auto_pricer import AutoPricer
        from src.inventory_sync.sync_manager import InventorySyncManager

        # 1. 번역
        translator = TranslationManager()
        req = translator.create_request('sku-001', 'New Product In Stock', 'en', 'ko')
        assert req['request_id'] is not None

        # 2. 가격 산정
        pricer = AutoPricer()
        sim = pricer.simulate('sku-001', {
            'cost': 5000,
            'margin_rate': 0.3,
            'channel_fee_rate': 0.05,
        })
        assert 'prices' in sim
        assert 'margin_based' in sim['prices']

        # 3. 재고 동기화
        sync_manager = InventorySyncManager()
        result = sync_manager.sync_sku('sku-001')
        assert result['sku'] == 'sku-001'
