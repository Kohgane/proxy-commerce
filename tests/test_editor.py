"""tests/test_editor.py — 상품 상세페이지 편집기 테스트."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_product():
    return {
        'sku': 'PTR-TNK-001',
        'title_ko': '샤넬 No.5 오드 퍼퓸 100ml',
        'title_en': 'Chanel No.5 Eau de Parfum 100ml',
        'description': '세계에서 가장 유명한 향수 중 하나.',
        'images': [
            'https://example.com/img1.jpg',
            'https://example.com/img2.jpg',
        ],
        'specs': {'용량': '100ml', '향': '플로럴', '원산지': '프랑스'},
        'shipping_info': '해외직배송 7-14일',
        'origin_country': '프랑스',
    }


# ---------------------------------------------------------------------------
# TemplateEngine 테스트
# ---------------------------------------------------------------------------

class TestTemplateEngine:
    """TemplateEngine 클래스 렌더링 검증."""

    def setup_method(self):
        from src.editor.template_engine import TemplateEngine
        self.engine = TemplateEngine()

    def test_list_templates_returns_four(self):
        templates = self.engine.list_templates()
        assert set(templates) == {'default', 'luxury', 'cosmetic', 'electronics'}

    def test_render_default_contains_title(self, sample_product):
        html = self.engine.render(sample_product, 'default')
        assert '샤넬 No.5 오드 퍼퓸 100ml' in html

    def test_render_luxury_contains_title(self, sample_product):
        html = self.engine.render(sample_product, 'luxury')
        assert '샤넬 No.5 오드 퍼퓸 100ml' in html

    def test_render_cosmetic_contains_title(self, sample_product):
        html = self.engine.render(sample_product, 'cosmetic')
        assert '샤넬 No.5 오드 퍼퓸 100ml' in html

    def test_render_electronics_contains_title(self, sample_product):
        html = self.engine.render(sample_product, 'electronics')
        assert '샤넬 No.5 오드 퍼퓸 100ml' in html

    def test_render_contains_image(self, sample_product):
        html = self.engine.render(sample_product, 'default')
        assert 'https://example.com/img1.jpg' in html

    def test_render_contains_spec(self, sample_product):
        html = self.engine.render(sample_product, 'default')
        assert '100ml' in html

    def test_render_unknown_template_raises(self, sample_product):
        with pytest.raises(ValueError):
            self.engine.render(sample_product, 'unknown_template')

    def test_render_empty_product(self):
        html = self.engine.render({}, 'default')
        assert html  # 빈 상품도 HTML을 반환해야 함

    def test_render_default_is_html(self, sample_product):
        html = self.engine.render(sample_product, 'default')
        assert '<html' in html or '<div' in html

    def test_render_includes_origin_country(self, sample_product):
        html = self.engine.render(sample_product, 'default')
        assert '프랑스' in html


# ---------------------------------------------------------------------------
# ImageProcessor 테스트
# ---------------------------------------------------------------------------

class TestImageProcessor:
    """ImageProcessor URL 변환 검증."""

    def setup_method(self):
        from src.editor.image_processor import ImageProcessor
        self.processor = ImageProcessor(cloud_name='testcloud')

    def test_resize_returns_cloudinary_url(self):
        url = self.processor.resize('https://example.com/img.jpg', 800, 600)
        assert 'cloudinary.com' in url
        assert 'w_800' in url
        assert 'h_600' in url

    def test_add_watermark_returns_cloudinary_url(self):
        url = self.processor.add_watermark('https://example.com/img.jpg', 'MyBrand')
        assert 'cloudinary.com' in url
        assert 'MyBrand' in url

    def test_optimize_for_coupang(self):
        url = self.processor.optimize_for_market('https://example.com/img.jpg', 'coupang')
        assert 'cloudinary.com' in url
        assert 'w_1000' in url
        assert 'h_1000' in url

    def test_optimize_for_smartstore(self):
        url = self.processor.optimize_for_market('https://example.com/img.jpg', 'smartstore')
        assert 'cloudinary.com' in url
        assert 'w_1000' in url

    def test_optimize_for_shopify(self):
        url = self.processor.optimize_for_market('https://example.com/img.jpg', 'shopify')
        assert 'cloudinary.com' in url
        assert 'w_2048' in url

    def test_batch_process_returns_list(self):
        urls = ['https://example.com/a.jpg', 'https://example.com/b.jpg']
        result = self.processor.batch_process(urls, 'coupang')
        assert len(result) == 2
        assert all('cloudinary.com' in u for u in result)

    def test_batch_process_empty_list(self):
        result = self.processor.batch_process([], 'coupang')
        assert result == []


# ---------------------------------------------------------------------------
# MarketSanitizer 테스트
# ---------------------------------------------------------------------------

class TestMarketSanitizer:
    """MarketSanitizer 위험 태그 제거 검증 및 마켓별 규격 검증."""

    def setup_method(self):
        from src.editor.market_sanitizer import MarketSanitizer
        self.sanitizer = MarketSanitizer()

    def test_coupang_removes_script(self):
        html = '<div><script>alert(1)</script><p>상품</p></div>'
        result = self.sanitizer.sanitize(html, 'coupang')
        assert '<script>' not in result
        assert '상품' in result

    def test_coupang_removes_iframe(self):
        html = '<div><iframe src="http://evil.com"></iframe><p>상품</p></div>'
        result = self.sanitizer.sanitize(html, 'coupang')
        assert '<iframe' not in result

    def test_coupang_removes_form(self):
        html = '<div><form action="/evil"><input></form><p>상품</p></div>'
        result = self.sanitizer.sanitize(html, 'coupang')
        assert '<form' not in result

    def test_smartstore_removes_script(self):
        html = '<p>상품 설명<script>alert(1)</script></p>'
        result = self.sanitizer.sanitize(html, 'smartstore')
        assert '<script>' not in result

    def test_smartstore_removes_external_links(self):
        html = '<a href="https://example.com">링크</a>'
        result = self.sanitizer.sanitize(html, 'smartstore')
        # href 속성이 제거되어야 함
        assert 'href="https://example.com"' not in result

    def test_shopify_escapes_liquid(self):
        html = '<div>{{ product.title }}</div>'
        result = self.sanitizer.sanitize(html, 'shopify')
        assert '{{' not in result

    def test_validate_passes_clean_html(self):
        html = '<div><p>깨끗한 HTML</p></div>'
        result = self.sanitizer.validate(html, 'coupang')
        assert result['passed'] is True
        assert result['warnings'] == []

    def test_validate_warns_on_script(self):
        html = '<div><script>alert(1)</script></div>'
        result = self.sanitizer.validate(html, 'coupang')
        assert result['passed'] is False
        assert len(result['warnings']) > 0

    def test_validate_returns_dict_with_required_keys(self):
        result = self.sanitizer.validate('<p>test</p>', 'coupang')
        assert 'passed' in result
        assert 'warnings' in result

    def test_sanitize_removes_event_handlers(self):
        html = '<div onclick="alert(1)"><p>상품</p></div>'
        result = self.sanitizer.sanitize(html, 'coupang')
        assert 'onclick' not in result


# ---------------------------------------------------------------------------
# ProductEditor 테스트
# ---------------------------------------------------------------------------

class TestProductEditor:
    """ProductEditor 편집 → 생성 → 내보내기 플로우 검증."""

    def setup_method(self):
        from src.editor.editor import ProductEditor
        self.editor = ProductEditor(cloud_name='testcloud')

    def test_load_product_returns_dict(self):
        product = self.editor.load_product('PTR-TEST-001')
        assert isinstance(product, dict)
        assert 'sku' in product

    def test_edit_fields_updates_title(self, sample_product):
        updated = self.editor.edit_fields(sample_product, {'title_ko': '새 상품명'})
        assert updated['title_ko'] == '새 상품명'

    def test_edit_fields_does_not_mutate_original(self, sample_product):
        original_title = sample_product['title_ko']
        self.editor.edit_fields(sample_product, {'title_ko': '새 상품명'})
        assert sample_product['title_ko'] == original_title

    def test_generate_detail_page_returns_html(self, sample_product):
        html = self.editor.generate_detail_page(sample_product)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_generate_detail_page_luxury_template(self, sample_product):
        html = self.editor.generate_detail_page(sample_product, template='luxury')
        assert '샤넬' in html

    def test_preview_returns_standalone_html(self, sample_product):
        html = self.editor.generate_detail_page(sample_product)
        preview = self.editor.preview(html)
        assert '<!DOCTYPE html>' in preview
        assert '<body>' in preview

    def test_export_for_coupang_returns_dict(self, sample_product):
        result = self.editor.export_for_market(sample_product, 'coupang')
        assert 'html' in result
        assert 'images' in result
        assert 'validation' in result
        assert result['market'] == 'coupang'

    def test_export_for_market_images_optimized(self, sample_product):
        result = self.editor.export_for_market(sample_product, 'shopify')
        assert len(result['images']) == len(sample_product['images'])
        assert all('cloudinary.com' in u for u in result['images'])

    def test_export_removes_scripts(self, sample_product):
        product_with_script = dict(sample_product)
        product_with_script['description'] = '<script>alert(1)</script>상품 설명'
        result = self.editor.export_for_market(product_with_script, 'coupang')
        assert '<script>' not in result['html']


# ---------------------------------------------------------------------------
# CLI 테스트
# ---------------------------------------------------------------------------

class TestEditorCli:
    """CLI 인자 파싱 및 액션 검증."""

    def _make_parser(self):
        from src.editor.cli import _build_parser
        return _build_parser()

    def test_list_templates_action_parsed(self):
        parser = self._make_parser()
        args = parser.parse_args(['--action', 'list-templates'])
        assert args.action == 'list-templates'

    def test_edit_action_parsed(self):
        parser = self._make_parser()
        args = parser.parse_args(['--action', 'edit', '--sku', 'PTR-TNK-001'])
        assert args.action == 'edit'
        assert args.sku == 'PTR-TNK-001'

    def test_preview_action_parsed(self):
        parser = self._make_parser()
        args = parser.parse_args(['--action', 'preview', '--sku', 'PTR-TNK-001', '--template', 'luxury'])
        assert args.action == 'preview'
        assert args.template == 'luxury'

    def test_export_action_parsed(self):
        parser = self._make_parser()
        args = parser.parse_args(['--action', 'export', '--sku', 'PTR-TNK-001', '--market', 'coupang'])
        assert args.action == 'export'
        assert args.market == 'coupang'

    def test_batch_export_action_parsed(self):
        parser = self._make_parser()
        args = parser.parse_args(['--action', 'batch-export', '--market', 'smartstore'])
        assert args.action == 'batch-export'
        assert args.market == 'smartstore'

    def test_invalid_action_fails(self):
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(['--action', 'invalid-action'])

    def test_list_templates_action_runs(self, capsys):
        from src.editor.cli import main
        main(['--action', 'list-templates'])
        captured = capsys.readouterr()
        assert 'default' in captured.out
        assert 'luxury' in captured.out
