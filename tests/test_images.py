"""tests/test_images.py — Phase 46: 이미지 관리 파이프라인 테스트."""
import pytest


class TestImageManager:
    def setup_method(self):
        from src.images.image_manager import ImageManager
        self.mgr = ImageManager()

    def test_register_image(self):
        image = self.mgr.register('https://example.com/img.jpg',
                                  alt_text='상품 이미지', width=800, height=600)
        assert 'id' in image
        assert image['url'] == 'https://example.com/img.jpg'
        assert image['alt_text'] == '상품 이미지'

    def test_detect_format_jpg(self):
        image = self.mgr.register('https://example.com/photo.jpg')
        assert image['format'] == 'jpg'

    def test_detect_format_png(self):
        image = self.mgr.register('https://example.com/photo.png')
        assert image['format'] == 'png'

    def test_detect_format_webp(self):
        image = self.mgr.register('https://example.com/photo.webp')
        assert image['format'] == 'webp'

    def test_get_image(self):
        image = self.mgr.register('https://example.com/img.jpg')
        found = self.mgr.get(image['id'])
        assert found['id'] == image['id']

    def test_list_all(self):
        self.mgr.register('https://example.com/1.jpg')
        self.mgr.register('https://example.com/2.png')
        assert len(self.mgr.list_all()) == 2

    def test_list_by_product(self):
        self.mgr.register('https://example.com/1.jpg', product_id='P001')
        self.mgr.register('https://example.com/2.jpg', product_id='P002')
        result = self.mgr.list_all(product_id='P001')
        assert len(result) == 1

    def test_update_image(self):
        image = self.mgr.register('https://example.com/img.jpg')
        updated = self.mgr.update(image['id'], alt_text='새 alt 텍스트')
        assert updated['alt_text'] == '새 alt 텍스트'

    def test_delete_image(self):
        image = self.mgr.register('https://example.com/img.jpg')
        assert self.mgr.delete(image['id'])
        assert self.mgr.get(image['id']) is None

    def test_delete_nonexistent(self):
        assert not self.mgr.delete('nonexistent')


class TestImageOptimizer:
    def setup_method(self):
        from src.images.optimizer import ImageOptimizer
        self.optimizer = ImageOptimizer()
        self.image = {'id': 'IMG001', 'url': 'https://example.com/photo.jpg'}

    def test_resize_thumbnail(self):
        result = self.optimizer.resize(self.image, 'thumbnail')
        assert result['width'] == 150
        assert result['height'] == 150
        assert result['simulated'] is True

    def test_resize_medium(self):
        result = self.optimizer.resize(self.image, 'medium')
        assert result['width'] == 600

    def test_resize_large(self):
        result = self.optimizer.resize(self.image, 'large')
        assert result['width'] == 1200

    def test_resize_invalid_spec(self):
        with pytest.raises(ValueError):
            self.optimizer.resize(self.image, 'invalid')

    def test_convert_format(self):
        result = self.optimizer.convert_format(self.image, 'webp')
        assert result['target_format'] == 'webp'
        assert result['url'].endswith('.webp')

    def test_generate_variants(self):
        variants = self.optimizer.generate_variants(self.image)
        assert len(variants) == 3


class TestWatermarkService:
    def setup_method(self):
        from src.images.watermark import WatermarkService
        self.ws = WatermarkService()
        self.image = {'id': 'IMG001', 'url': 'https://example.com/photo.jpg'}

    def test_configure(self):
        config = self.ws.configure(text='Copyright', position='bottom_right', opacity=0.7)
        assert config['text'] == 'Copyright'
        assert config['opacity'] == 0.7

    def test_configure_invalid_position(self):
        with pytest.raises(ValueError):
            self.ws.configure(text='Test', position='invalid')

    def test_configure_invalid_opacity(self):
        with pytest.raises(ValueError):
            self.ws.configure(text='Test', opacity=1.5)

    def test_apply(self):
        self.ws.configure(text='© MyStore')
        result = self.ws.apply(self.image)
        assert result['watermark_text'] == '© MyStore'
        assert result['simulated'] is True


class TestCDNUploader:
    def test_cloudinary_upload(self):
        from src.images.cdn_uploader import CloudinaryUploader
        uploader = CloudinaryUploader()
        result = uploader.upload('https://example.com/img.jpg')
        assert 'public_id' in result
        assert result['provider'] == 'cloudinary'
        assert result['cdn_url'].startswith('https://res.cloudinary.com/')

    def test_cloudinary_delete(self):
        from src.images.cdn_uploader import CloudinaryUploader
        uploader = CloudinaryUploader()
        result = uploader.upload('https://example.com/img.jpg')
        assert uploader.delete(result['public_id'])

    def test_cloudinary_get_url(self):
        from src.images.cdn_uploader import CloudinaryUploader
        uploader = CloudinaryUploader()
        url = uploader.get_url('products/abc123', width=300, height=300)
        assert 'w_300' in url

    def test_s3_upload(self):
        from src.images.cdn_uploader import S3Uploader
        uploader = S3Uploader()
        result = uploader.upload('https://example.com/img.jpg')
        assert result['provider'] == 's3'
        assert result['cdn_url'].startswith('https://')

    def test_s3_delete(self):
        from src.images.cdn_uploader import S3Uploader
        uploader = S3Uploader()
        result = uploader.upload('https://example.com/img.jpg')
        assert uploader.delete(result['public_id'])


class TestProductGallery:
    def setup_method(self):
        from src.images.gallery import ProductGallery
        self.gallery = ProductGallery()

    def test_add_image(self):
        result = self.gallery.add_image('P001', 'IMG1')
        assert 'IMG1' in result

    def test_first_image_is_primary(self):
        self.gallery.add_image('P001', 'IMG1')
        assert self.gallery.get_primary('P001') == 'IMG1'

    def test_set_primary(self):
        self.gallery.add_image('P001', 'IMG1')
        self.gallery.add_image('P001', 'IMG2')
        self.gallery.set_primary('P001', 'IMG2')
        assert self.gallery.get_primary('P001') == 'IMG2'

    def test_set_primary_not_in_gallery(self):
        with pytest.raises(ValueError):
            self.gallery.set_primary('P001', 'NOT_EXIST')

    def test_remove_image(self):
        self.gallery.add_image('P001', 'IMG1')
        self.gallery.add_image('P001', 'IMG2')
        self.gallery.remove_image('P001', 'IMG1')
        gallery = self.gallery.get_gallery('P001')
        assert 'IMG1' not in gallery

    def test_primary_updates_after_removal(self):
        self.gallery.add_image('P001', 'IMG1')
        self.gallery.add_image('P001', 'IMG2')
        self.gallery.remove_image('P001', 'IMG1')
        assert self.gallery.get_primary('P001') == 'IMG2'

    def test_max_images(self):
        from src.images.gallery import MAX_GALLERY_IMAGES
        for i in range(MAX_GALLERY_IMAGES):
            self.gallery.add_image('P001', f'IMG{i}')
        with pytest.raises(ValueError):
            self.gallery.add_image('P001', 'IMG_OVERFLOW')

    def test_reorder(self):
        self.gallery.add_image('P001', 'IMG1')
        self.gallery.add_image('P001', 'IMG2')
        self.gallery.add_image('P001', 'IMG3')
        self.gallery.reorder('P001', ['IMG3', 'IMG1', 'IMG2'])
        assert self.gallery.get_gallery('P001')[0] == 'IMG3'

    def test_reorder_invalid(self):
        self.gallery.add_image('P001', 'IMG1')
        with pytest.raises(ValueError):
            self.gallery.reorder('P001', ['IMG1', 'IMG2'])
