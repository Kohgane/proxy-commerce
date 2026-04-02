"""src/analytics/product_analytics.py — Phase 29: Product Analytics."""


class ProductAnalytics:
    """상품 분석 클래스 (ABC 분류, 마진 분석, 재고 회전율)."""

    # ──────────────────────────────────────────────
    # ABC Classification
    # ──────────────────────────────────────────────

    def abc_classification(self, products: list) -> dict:
        """ABC 분류.

        Args:
            products: [{'product_id', 'revenue'}, ...]

        Returns:
            {'A': [product_ids], 'B': [product_ids], 'C': [product_ids]}
            A = 상위 20% 매출, B = 다음 30%, C = 하위 50%
        """
        if not products:
            return {'A': [], 'B': [], 'C': []}

        sorted_products = sorted(products, key=lambda p: float(p['revenue']), reverse=True)
        total_revenue = sum(float(p['revenue']) for p in sorted_products)

        if total_revenue == 0:
            n = len(sorted_products)
            a_cut = max(1, round(n * 0.2))
            b_cut = max(a_cut, round(n * 0.5))
            return {
                'A': [p['product_id'] for p in sorted_products[:a_cut]],
                'B': [p['product_id'] for p in sorted_products[a_cut:b_cut]],
                'C': [p['product_id'] for p in sorted_products[b_cut:]],
            }

        cumulative = 0.0
        a_ids, b_ids, c_ids = [], [], []
        for p in sorted_products:
            cumulative += float(p['revenue'])
            pct = cumulative / total_revenue
            pid = p['product_id']
            if pct <= 0.80:
                a_ids.append(pid)
            elif pct <= 0.95:
                b_ids.append(pid)
            else:
                c_ids.append(pid)

        # Guarantee every product is classified
        if not a_ids and sorted_products:
            a_ids.append(sorted_products[0]['product_id'])

        return {'A': a_ids, 'B': b_ids, 'C': c_ids}

    # ──────────────────────────────────────────────
    # Margin Analysis
    # ──────────────────────────────────────────────

    def margin_analysis(self, products: list) -> list:
        """마진 분석.

        Args:
            products: [{'product_id', 'sale_price', 'cost_price'}, ...]

        Returns:
            [{'product_id', 'margin_rate', 'margin_amount'}, ...]
        """
        result = []
        for p in products:
            sale = float(p['sale_price'])
            cost = float(p['cost_price'])
            margin_amount = sale - cost
            margin_rate = round(margin_amount / sale * 100, 4) if sale != 0 else 0.0
            result.append({
                'product_id': p['product_id'],
                'margin_rate': round(margin_rate, 2),
                'margin_amount': round(margin_amount, 2),
            })
        return result

    # ──────────────────────────────────────────────
    # Inventory Turnover
    # ──────────────────────────────────────────────

    def inventory_turnover(self, products: list) -> list:
        """재고 회전율 분석.

        Args:
            products: [{'product_id', 'cogs', 'avg_inventory'}, ...]

        Returns:
            [{'product_id', 'turnover_rate'}, ...]
        """
        result = []
        for p in products:
            cogs = float(p['cogs'])
            avg_inv = float(p['avg_inventory'])
            turnover = round(cogs / avg_inv, 4) if avg_inv != 0 else 0.0
            result.append({
                'product_id': p['product_id'],
                'turnover_rate': round(turnover, 2),
            })
        return result
