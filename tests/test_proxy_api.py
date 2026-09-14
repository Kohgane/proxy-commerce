"""구매대행 API 엔드포인트 테스트."""

import json
import os
import pytest

os.environ.setdefault('SELLER_CONSOLE_AUTH', '0')
os.environ.setdefault('FX_DISABLE_NETWORK', '1')
os.environ.setdefault('TRANSLATE_PROVIDER', 'none')


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestCalcMargin:
    def test_basic_margin(self, client):
        resp = client.post('/api/proxy/calc/margin', json={
            'buy_price': 50, 'currency': 'USD',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['cost_krw'] > 0
        assert data['sell_price_krw'] > 0
        assert data['net_profit_krw'] > 0

    def test_missing_buy_price(self, client):
        resp = client.post('/api/proxy/calc/margin', json={'currency': 'USD'})
        assert resp.status_code == 400

    def test_invalid_buy_price(self, client):
        resp = client.post('/api/proxy/calc/margin', json={
            'buy_price': 'not_a_number', 'currency': 'USD',
        })
        assert resp.status_code == 400

    def test_with_options(self, client):
        resp = client.post('/api/proxy/calc/margin', json={
            'buy_price': 100,
            'currency': 'JPY',
            'source_country': 'JP',
            'target_market': 'smartstore',
            'margin_pct': 30,
            'shipping_method': 'express',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['commission_pct'] == 5.5


class TestCalcCompare:
    def test_compare_markets(self, client):
        resp = client.post('/api/proxy/calc/compare', json={
            'buy_price': 50, 'currency': 'USD',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'markets' in data
        assert len(data['markets']) >= 3

    def test_compare_missing_price(self, client):
        resp = client.post('/api/proxy/calc/compare', json={'currency': 'USD'})
        assert resp.status_code == 400


class TestCalcReverse:
    def test_reverse(self, client):
        resp = client.post('/api/proxy/calc/reverse', json={
            'target_sell_price': 100000, 'currency': 'USD',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['max_buy_price'] > 0

    def test_reverse_missing_price(self, client):
        resp = client.post('/api/proxy/calc/reverse', json={'currency': 'USD'})
        assert resp.status_code == 400


class TestCalcBatch:
    def test_batch(self, client):
        resp = client.post('/api/proxy/calc/batch', json={
            'items': [
                {'buy_price': 30, 'currency': 'USD'},
                {'buy_price': 5000, 'currency': 'JPY', 'source_country': 'JP'},
            ],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['results']) == 2

    def test_batch_empty(self, client):
        resp = client.post('/api/proxy/calc/batch', json={'items': []})
        assert resp.status_code == 400


class TestEditorGenerate:
    def test_generate(self, client):
        resp = client.post('/api/proxy/editor/generate', json={
            'title': '테스트 상품',
            'brand': 'TestBrand',
            'images': ['https://example.com/img.jpg'],
            'features': ['특징1', '특징2'],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'html' in data
        assert '테스트 상품' in data['html']

    def test_generate_missing_title(self, client):
        resp = client.post('/api/proxy/editor/generate', json={'brand': 'X'})
        assert resp.status_code == 400


class TestEditorUpdate:
    def test_update(self, client):
        gen_resp = client.post('/api/proxy/editor/generate', json={
            'title': '원래 제목',
        })
        html = gen_resp.get_json()['html']

        resp = client.post('/api/proxy/editor/update', json={
            'html': html,
            'updates': {'title_ko': '수정된 제목'},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'html' in data

    def test_update_missing_html(self, client):
        resp = client.post('/api/proxy/editor/update', json={'updates': {}})
        assert resp.status_code == 400
