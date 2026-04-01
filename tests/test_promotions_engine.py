"""tests/test_promotions_engine.py — 할인 계산 + 조건 검증 테스트."""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _future(hours=48):
    return (datetime.now(tz=timezone.utc) + timedelta(hours=hours)).isoformat()


def _past(hours=48):
    return (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()


def _make_promo(
    promo_id="P1",
    name="Test",
    ptype="PERCENTAGE",
    value=10,
    active="1",
    start_date=None,
    end_date=None,
    min_order_krw=0,
    skus="",
    countries="",
    buy_x=0,
    get_y=0,
):
    return {
        "promo_id": promo_id,
        "name": name,
        "type": ptype,
        "value": value,
        "min_order_krw": min_order_krw,
        "start_date": start_date or _past(72),
        "end_date": end_date or _future(72),
        "skus": skus,
        "countries": countries,
        "buy_x": buy_x,
        "get_y": get_y,
        "active": active,
        "usage_count": 0,
        "total_discount_krw": 0,
    }


class TestPromotionEngineCreate:
    def test_create_valid_promotion(self):
        """유효한 프로모션 생성 시 promo_id가 포함되어야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        data = {"name": "Summer Sale", "type": "PERCENTAGE", "value": 10}
        with patch.object(engine, '_save_promo', return_value=None):
            result = engine.create_promotion(data)
        assert "promo_id" in result
        assert result["type"] == "PERCENTAGE"

    def test_create_missing_name_raises(self):
        """name 필드 누락 시 ValueError가 발생해야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        try:
            engine.create_promotion({"type": "PERCENTAGE", "value": 10})
            assert False, "ValueError 미발생"
        except ValueError:
            pass

    def test_create_invalid_type_raises(self):
        """유효하지 않은 타입 시 ValueError가 발생해야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        try:
            engine.create_promotion({"name": "X", "type": "INVALID"})
            assert False, "ValueError 미발생"
        except ValueError:
            pass

    def test_create_all_types(self):
        """4가지 프로모션 타입 모두 생성 가능해야 한다."""
        from src.promotions.engine import PromotionEngine, PROMO_TYPES
        engine = PromotionEngine()
        for ptype in PROMO_TYPES:
            with patch.object(engine, '_save_promo', return_value=None):
                result = engine.create_promotion({"name": f"Test {ptype}", "type": ptype})
            assert result["type"] == ptype


class TestPromotionEngineCalculate:
    def test_percentage_discount(self):
        """PERCENTAGE 타입 할인이 정확하게 계산되어야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 100000}
        promo = _make_promo(ptype="PERCENTAGE", value=10)
        result = engine.calculate_discount(order, [promo])
        assert result["discount_krw"] == 10000.0

    def test_fixed_amount_discount(self):
        """FIXED_AMOUNT 타입 할인이 정확해야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 100000}
        promo = _make_promo(ptype="FIXED_AMOUNT", value=5000)
        result = engine.calculate_discount(order, [promo])
        assert result["discount_krw"] == 5000.0

    def test_fixed_amount_capped_at_total(self):
        """고정 금액이 주문 총액을 초과하지 않아야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 3000}
        promo = _make_promo(ptype="FIXED_AMOUNT", value=5000)
        result = engine.calculate_discount(order, [promo])
        assert result["discount_krw"] == 3000.0

    def test_free_shipping(self):
        """FREE_SHIPPING 타입은 free_shipping 플래그를 설정해야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 50000}
        promo = _make_promo(ptype="FREE_SHIPPING", value=0)
        result = engine.calculate_discount(order, [promo])
        assert result["free_shipping"] is True

    def test_buy_x_get_y(self):
        """BUY_X_GET_Y 할인이 정확해야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        # 3개 사면 1개 무료, 총 3개 구매, 단가 10000
        order = {"order_total_krw": 30000, "quantity": 3}
        promo = _make_promo(ptype="BUY_X_GET_Y", value=0, buy_x=3, get_y=1)
        result = engine.calculate_discount(order, [promo])
        assert result["discount_krw"] == 10000.0

    def test_no_applicable_promos(self):
        """적용 가능한 프로모션이 없으면 0이어야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 1000}
        result = engine.calculate_discount(order, [])
        assert result["discount_krw"] == 0

    def test_min_order_filter(self):
        """최소 주문 금액 미달 시 프로모션이 적용되지 않아야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 10000}
        promo = _make_promo(ptype="PERCENTAGE", value=10, min_order_krw=50000)
        result = engine.calculate_discount(order, [promo])
        assert result["discount_krw"] == 0

    def test_sku_filter(self):
        """SKU 제한이 적용되어야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 50000, "skus": ["SKU-B"]}
        promo = _make_promo(ptype="PERCENTAGE", value=10, skus="SKU-A")
        result = engine.calculate_discount(order, [promo])
        assert result["discount_krw"] == 0

    def test_stack_mode_best(self):
        """best 모드에서는 최대 할인 하나만 적용되어야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 100000}
        promos = [
            _make_promo("P1", ptype="PERCENTAGE", value=10),   # 10000원
            _make_promo("P2", ptype="FIXED_AMOUNT", value=5000),  # 5000원
        ]
        with patch.dict(os.environ, {"PROMO_STACK_MODE": "best"}):
            result = engine.calculate_discount(order, promos)
        assert result["discount_krw"] == 10000.0

    def test_stack_mode_stack(self):
        """stack 모드에서는 모든 할인이 합산되어야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        order = {"order_total_krw": 100000}
        promos = [
            _make_promo("P1", ptype="PERCENTAGE", value=10),   # 10000원
            _make_promo("P2", ptype="FIXED_AMOUNT", value=5000),  # 5000원
        ]
        with patch.dict(os.environ, {"PROMO_STACK_MODE": "stack"}):
            result = engine.calculate_discount(order, promos)
        assert result["discount_krw"] == 15000.0

    def test_expired_promotion_excluded(self):
        """만료된 프로모션은 활성 목록에서 제외되어야 한다."""
        from src.promotions.engine import PromotionEngine
        engine = PromotionEngine()
        promos = [_make_promo(end_date=_past(10))]
        with patch.object(engine, '_load_promos', return_value=promos):
            active = engine.get_promotions(active_only=True)
        assert len(active) == 0
