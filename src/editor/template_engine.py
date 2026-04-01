"""src/editor/template_engine.py — Jinja2 기반 상세페이지 HTML 자동 생성."""

import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')

AVAILABLE_TEMPLATES = ['default', 'luxury', 'cosmetic', 'electronics']


class TemplateEngine:
    """수집된 상품 데이터(이미지/텍스트)를 기반으로 상세페이지 HTML 자동 생성."""

    def __init__(self, templates_dir: str = TEMPLATES_DIR):
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(['html']),
        )

    def render(self, product_data: dict, template_name: str = 'default') -> str:
        """상품 데이터를 Jinja2 템플릿으로 렌더링하여 HTML 반환.

        Args:
            product_data: 상품 데이터 딕셔너리
                - title_ko: 한글 상품명
                - title_en: 영문 상품명
                - description: 상품 설명
                - images: 이미지 URL 리스트
                - specs: 스펙 딕셔너리
                - shipping_info: 배송 정보
                - origin_country: 원산지 국가
            template_name: 템플릿명 (default/luxury/cosmetic/electronics)

        Returns:
            렌더링된 HTML 문자열
        """
        if template_name not in AVAILABLE_TEMPLATES:
            raise ValueError(f'Unknown template: {template_name}. Available: {AVAILABLE_TEMPLATES}')
        template = self._env.get_template(f'{template_name}.html')
        context = {
            'title_ko': product_data.get('title_ko', ''),
            'title_en': product_data.get('title_en', ''),
            'description': product_data.get('description', ''),
            'images': product_data.get('images', []),
            'specs': product_data.get('specs', {}),
            'shipping_info': product_data.get('shipping_info', ''),
            'origin_country': product_data.get('origin_country', ''),
        }
        return template.render(**context)

    def list_templates(self) -> list:
        """사용 가능한 템플릿 목록 반환."""
        return list(AVAILABLE_TEMPLATES)
