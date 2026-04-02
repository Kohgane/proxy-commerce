"""tests/test_migration_extended.py — Phase 42: 마이그레이션/시드/검증 테스트."""
import pytest
import json


class TestSeedGenerator:
    def setup_method(self):
        from src.migration.seed import SeedGenerator
        self.gen = SeedGenerator()

    def test_generate_products(self):
        products = self.gen.generate_products(50)
        assert len(products) == 50
        assert all('id' in p for p in products)
        assert all('name' in p for p in products)
        assert all('sku' in p for p in products)

    def test_generate_products_custom_count(self):
        products = self.gen.generate_products(10)
        assert len(products) == 10

    def test_generate_customers(self):
        customers = self.gen.generate_customers(20)
        assert len(customers) == 20
        assert all('id' in c for c in customers)
        assert all('email' in c for c in customers)

    def test_generate_orders(self):
        products = self.gen.generate_products(5)
        customers = self.gen.generate_customers(5)
        orders = self.gen.generate_orders(10, products=products, customers=customers)
        assert len(orders) == 10
        assert all('id' in o for o in orders)
        assert all('total_amount' in o for o in orders)

    def test_generate_all(self):
        data = self.gen.generate_all()
        assert 'products' in data
        assert 'customers' in data
        assert 'orders' in data
        assert len(data['products']) == 50
        assert len(data['customers']) == 20
        assert len(data['orders']) == 30

    def test_products_have_korean_names(self):
        products = self.gen.generate_products(10)
        # 한국어 이름 포함 확인 (유니코드 범위)
        names = [p['name'] for p in products]
        has_korean = any(any('\uAC00' <= c <= '\uD7A3' for c in name) for name in names)
        assert has_korean

    def test_unique_product_ids(self):
        products = self.gen.generate_products(20)
        ids = [p['id'] for p in products]
        assert len(ids) == len(set(ids))


class TestDataValidator:
    def setup_method(self):
        from src.migration.validators import DataValidator
        self.validator = DataValidator()

    def test_validate_required_pass(self):
        data = {'id': '001', 'name': 'Test', 'price': 1000}
        errors = self.validator.validate_required(data, ['id', 'name', 'price'])
        assert errors == []

    def test_validate_required_fail(self):
        data = {'id': '001'}
        errors = self.validator.validate_required(data, ['id', 'name', 'price'])
        assert 'name' in errors
        assert 'price' in errors

    def test_validate_type_pass(self):
        error = self.validator.validate_type(42, int, 'age')
        assert error is None

    def test_validate_type_fail(self):
        error = self.validator.validate_type('not_int', int, 'age')
        assert error is not None
        assert 'age' in error

    def test_validate_decimal_pass(self):
        error = self.validator.validate_decimal('99.99', 'price')
        assert error is None

    def test_validate_decimal_fail(self):
        error = self.validator.validate_decimal('not_a_number', 'price')
        assert error is not None

    def test_validate_referential_pass(self):
        data = {'customer_id': 'CUST-001'}
        error = self.validator.validate_referential(data, 'customer_id', {'CUST-001', 'CUST-002'}, 'order')
        assert error is None

    def test_validate_referential_fail(self):
        data = {'customer_id': 'NONEXISTENT'}
        error = self.validator.validate_referential(data, 'customer_id', {'CUST-001'}, 'order')
        assert error is not None

    def test_validate_product(self):
        product = {'id': 'P001', 'name': '테스트 상품', 'sku': 'SKU-001', 'price': 10000}
        errors = self.validator.validate_product(product)
        assert errors == []

    def test_validate_product_missing_fields(self):
        product = {'id': 'P001'}
        errors = self.validator.validate_product(product)
        assert len(errors) > 0

    def test_validate_order(self):
        order = {'id': 'O001', 'customer_id': 'C001', 'total_amount': 50000, 'status': 'new'}
        errors = self.validator.validate_order(order)
        assert errors == []

    def test_validate_batch(self):
        products = [
            {'id': 'P001', 'name': 'A', 'sku': 'S1', 'price': 1000},
            {'id': 'P002'},  # 필수 필드 누락
        ]
        results = self.validator.validate_batch(products, self.validator.validate_product)
        assert 'P002' in results
        assert 'P001' not in results

    def test_is_valid(self):
        data = {'id': '001', 'name': 'Test'}
        assert self.validator.is_valid(data, ['id', 'name']) is True
        assert self.validator.is_valid(data, ['id', 'name', 'missing']) is False


class TestExportImport:
    def setup_method(self):
        from src.migration.export_import import ExportImport
        self.ei = ExportImport()
        self.sample_records = [
            {'id': '001', 'name': '상품A', 'price': 10000},
            {'id': '002', 'name': '상품B', 'price': 20000},
        ]

    def test_export_json(self):
        result = self.ei.export_json(self.sample_records)
        data = json.loads(result)
        assert len(data) == 2

    def test_import_json(self):
        json_str = json.dumps(self.sample_records, ensure_ascii=False)
        records = self.ei.import_json(json_str)
        assert len(records) == 2

    def test_import_json_single(self):
        json_str = json.dumps({'id': '001', 'name': 'Single'})
        records = self.ei.import_json(json_str)
        assert len(records) == 1

    def test_export_csv(self):
        result = self.ei.export_csv(self.sample_records, fields=['id', 'name', 'price'])
        assert 'id' in result
        assert '상품A' in result

    def test_import_csv(self):
        csv_str = self.ei.export_csv(self.sample_records, fields=['id', 'name', 'price'])
        records = self.ei.import_csv(csv_str)
        assert len(records) == 2
        assert records[0]['name'] == '상품A'

    def test_bulk_import(self):
        store = {}
        result = self.ei.bulk_import(self.sample_records, store)
        assert result['inserted'] == 2
        assert result['skipped'] == 0
        assert len(store) == 2

    def test_bulk_import_skip_existing(self):
        store = {'001': {'id': '001', 'name': '기존'}}
        result = self.ei.bulk_import(self.sample_records, store, overwrite=False)
        assert result['skipped'] == 1
        assert result['inserted'] == 1

    def test_bulk_import_overwrite(self):
        store = {'001': {'id': '001', 'name': '기존'}}
        result = self.ei.bulk_import(self.sample_records, store, overwrite=True)
        assert result['inserted'] == 2
        assert store['001']['name'] == '상품A'

    def test_bulk_import_missing_id(self):
        records = [{'name': 'no_id'}]
        store = {}
        result = self.ei.bulk_import(records, store)
        assert result['skipped'] == 1
        assert len(result['errors']) == 1

    def test_export_import_roundtrip_json(self, tmp_path):
        path = str(tmp_path / 'export.json')
        count = self.ei.export_to_file(self.sample_records, path, fmt='json')
        assert count == 2
        imported = self.ei.import_from_file(path, fmt='json')
        assert len(imported) == 2

    def test_export_import_roundtrip_csv(self, tmp_path):
        path = str(tmp_path / 'export.csv')
        count = self.ei.export_to_file(self.sample_records, path, fmt='csv')
        assert count == 2
        imported = self.ei.import_from_file(path, fmt='csv')
        assert len(imported) == 2

    def test_unsupported_format(self):
        with pytest.raises(ValueError):
            self.ei.export_to_file([], '/dev/null', fmt='xml')
