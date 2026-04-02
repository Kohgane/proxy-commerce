"""tests/test_categories.py — Phase 39: 카테고리/태그 관리 테스트."""
import pytest


class TestCategoryManager:
    def setup_method(self):
        from src.categories.category_manager import CategoryManager
        self.manager = CategoryManager()

    def test_create_top_level(self):
        cat = self.manager.create({'name': '전자제품', 'slug': 'electronics'})
        assert cat['name'] == '전자제품'
        assert cat['parent_id'] is None

    def test_create_child(self):
        parent = self.manager.create({'name': '전자제품'})
        child = self.manager.create({'name': '노트북', 'parent_id': parent['id']})
        assert child['parent_id'] == parent['id']

    def test_create_invalid_parent(self):
        with pytest.raises(ValueError):
            self.manager.create({'name': '자식', 'parent_id': 'nonexistent'})

    def test_list_top_level(self):
        self.manager.create({'name': '카테고리A'})
        self.manager.create({'name': '카테고리B'})
        top = self.manager.list_top_level()
        assert len(top) == 2

    def test_list_children(self):
        parent = self.manager.create({'name': '부모'})
        self.manager.create({'name': '자식1', 'parent_id': parent['id']})
        self.manager.create({'name': '자식2', 'parent_id': parent['id']})
        children = self.manager.list_children(parent['id'])
        assert len(children) == 2

    def test_get_ancestors(self):
        root = self.manager.create({'name': '루트'})
        mid = self.manager.create({'name': '중간', 'parent_id': root['id']})
        leaf = self.manager.create({'name': '잎', 'parent_id': mid['id']})
        ancestors = self.manager.get_ancestors(leaf['id'])
        assert len(ancestors) == 2
        assert ancestors[0]['id'] == root['id']

    def test_get_descendants(self):
        root = self.manager.create({'name': '루트'})
        child = self.manager.create({'name': '자식', 'parent_id': root['id']})
        self.manager.create({'name': '손자', 'parent_id': child['id']})
        descendants = self.manager.get_descendants(root['id'])
        assert len(descendants) == 2

    def test_move_category(self):
        parent1 = self.manager.create({'name': '부모1'})
        parent2 = self.manager.create({'name': '부모2'})
        child = self.manager.create({'name': '자식', 'parent_id': parent1['id']})
        moved = self.manager.move(child['id'], parent2['id'])
        assert moved['parent_id'] == parent2['id']

    def test_move_circular_reference(self):
        root = self.manager.create({'name': '루트'})
        child = self.manager.create({'name': '자식', 'parent_id': root['id']})
        with pytest.raises(ValueError):
            self.manager.move(root['id'], child['id'])

    def test_delete_leaf(self):
        cat = self.manager.create({'name': '삭제 대상'})
        ok = self.manager.delete(cat['id'])
        assert ok is True

    def test_delete_with_children_raises(self):
        parent = self.manager.create({'name': '부모'})
        self.manager.create({'name': '자식', 'parent_id': parent['id']})
        with pytest.raises(ValueError):
            self.manager.delete(parent['id'], delete_children=False)

    def test_delete_with_children(self):
        parent = self.manager.create({'name': '부모'})
        self.manager.create({'name': '자식', 'parent_id': parent['id']})
        ok = self.manager.delete(parent['id'], delete_children=True)
        assert ok is True
        assert len(self.manager.list_all()) == 0

    def test_update(self):
        cat = self.manager.create({'name': '구 이름'})
        updated = self.manager.update(cat['id'], {'name': '새 이름'})
        assert updated['name'] == '새 이름'


class TestTagManager:
    def setup_method(self):
        from src.categories.tag_manager import TagManager
        self.manager = TagManager()

    def test_create_tag(self):
        tag = self.manager.create_tag('신상품')
        assert tag['name'] == '신상품'
        assert 'id' in tag

    def test_get_tag(self):
        tag = self.manager.create_tag('테스트')
        found = self.manager.get_tag(tag['id'])
        assert found is not None

    def test_list_tags(self):
        self.manager.create_tag('A')
        self.manager.create_tag('B')
        assert len(self.manager.list_tags()) == 2

    def test_delete_tag(self):
        tag = self.manager.create_tag('삭제')
        ok = self.manager.delete_tag(tag['id'])
        assert ok is True

    def test_add_tag_to_product(self):
        tag = self.manager.create_tag('프리미엄')
        self.manager.add_tag_to_product('PROD-001', tag['id'])
        tags = self.manager.get_product_tags('PROD-001')
        assert len(tags) == 1

    def test_remove_tag_from_product(self):
        tag = self.manager.create_tag('임시')
        self.manager.add_tag_to_product('PROD-001', tag['id'])
        ok = self.manager.remove_tag_from_product('PROD-001', tag['id'])
        assert ok is True
        assert len(self.manager.get_product_tags('PROD-001')) == 0

    def test_search_tags(self):
        self.manager.create_tag('여름특가')
        self.manager.create_tag('겨울특가')
        results = self.manager.search_tags('여름')
        assert len(results) == 1

    def test_auto_tag(self):
        tag = self.manager.create_tag('노트북')
        self.manager.add_keyword_rule(['laptop', '노트북'], tag['id'])
        applied = self.manager.auto_tag('PROD-001', '최신 노트북 할인')
        assert tag['id'] in applied

    def test_add_tag_invalid(self):
        with pytest.raises(ValueError):
            self.manager.add_tag_to_product('PROD-001', 'nonexistent-tag')


class TestCategoryMapping:
    def setup_method(self):
        from src.categories.mapping import CategoryMapping
        self.mapping = CategoryMapping()

    def test_set_mapping(self):
        result = self.mapping.set_mapping('INT-001', 'coupang', 'COUP-123')
        assert result['coupang'] == 'COUP-123'

    def test_get_mapping(self):
        self.mapping.set_mapping('INT-001', 'coupang', 'COUP-123')
        assert self.mapping.get_mapping('INT-001', 'coupang') == 'COUP-123'

    def test_invalid_platform(self):
        with pytest.raises(ValueError):
            self.mapping.set_mapping('INT-001', 'invalid_platform', 'X')

    def test_find_by_platform_id(self):
        self.mapping.set_mapping('INT-001', 'naver', 'NAV-456')
        internal_id = self.mapping.find_by_platform_id('naver', 'NAV-456')
        assert internal_id == 'INT-001'

    def test_find_unmapped(self):
        self.mapping.set_mapping('INT-001', 'coupang', 'COUP-123')
        unmapped = self.mapping.find_unmapped(['INT-001', 'INT-002'], 'coupang')
        assert 'INT-002' in unmapped
        assert 'INT-001' not in unmapped

    def test_delete_mapping(self):
        self.mapping.set_mapping('INT-001', 'coupang', 'COUP-123')
        ok = self.mapping.delete_mapping('INT-001')
        assert ok is True


class TestBreadcrumbGenerator:
    def setup_method(self):
        from src.categories.category_manager import CategoryManager
        from src.categories.breadcrumb import BreadcrumbGenerator
        self.manager = CategoryManager()
        self.gen = BreadcrumbGenerator()

    def test_build_single(self):
        cat = self.manager.create({'name': '전자제품'})
        path = self.gen.build(cat['id'], self.manager)
        assert path == '전자제품'

    def test_build_nested(self):
        root = self.manager.create({'name': '전자제품'})
        mid = self.manager.create({'name': '컴퓨터', 'parent_id': root['id']})
        leaf = self.manager.create({'name': '노트북', 'parent_id': mid['id']})
        path = self.gen.build(leaf['id'], self.manager)
        assert path == '전자제품 > 컴퓨터 > 노트북'

    def test_build_nonexistent(self):
        path = self.gen.build('nonexistent', self.manager)
        assert path == ''

    def test_custom_separator(self):
        gen = __import__('src.categories.breadcrumb', fromlist=['BreadcrumbGenerator']).BreadcrumbGenerator(separator=' / ')
        root = self.manager.create({'name': 'A'})
        child = self.manager.create({'name': 'B', 'parent_id': root['id']})
        path = gen.build(child['id'], self.manager)
        assert ' / ' in path

    def test_get_depth(self):
        root = self.manager.create({'name': '루트'})
        child = self.manager.create({'name': '자식', 'parent_id': root['id']})
        assert self.gen.get_depth(root['id'], self.manager) == 0
        assert self.gen.get_depth(child['id'], self.manager) == 1


class TestCategoriesAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.categories_api import categories_bp
        app = Flask(__name__)
        app.register_blueprint(categories_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get('/api/v1/categories/status')
        assert resp.status_code == 200

    def test_create_category(self):
        resp = self.client.post('/api/v1/categories/', json={'name': 'Electronics'})
        assert resp.status_code == 201

    def test_create_tag(self):
        resp = self.client.post('/api/v1/categories/tags/', json={'name': 'Sale'})
        assert resp.status_code == 201
