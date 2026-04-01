"""Amazon 상품 수집기 — US/JP 지원."""

import logging
import os
import random
import re
import time
from datetime import datetime, timezone

import requests

from .base_collector import BaseCollector

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False
    logger.warning('beautifulsoup4 not installed; HTML parsing will be limited')


class AmazonCollector(BaseCollector):
    """Amazon 상품 수집기 (US/JP 지원)."""

    marketplace = 'amazon'

    # 지원 마켓플레이스
    MARKETPLACES = {
        'US': {
            'base_url': 'https://www.amazon.com',
            'currency': 'USD',
            'language': 'en',
        },
        'JP': {
            'base_url': 'https://www.amazon.co.jp',
            'currency': 'JPY',
            'language': 'ja',
        },
    }

    # Amazon 카테고리 → 내부 카테고리 코드 매핑
    CATEGORY_MAP = {
        'Electronics': 'ELC',
        'Home & Kitchen': 'HOM',
        'Beauty & Personal Care': 'BTY',
        'Health & Household': 'HLT',
        'Toys & Games': 'TOY',
        'Sports & Outdoors': 'SPT',
        'Clothing': 'CLO',
        'Books': 'BOK',
        'Pet Supplies': 'PET',
        'Baby': 'BBY',
        'Grocery': 'GRC',
        'Tools & Home Improvement': 'TLS',
        'Automotive': 'AUT',
        'Office Products': 'OFC',
        # 일본어 카테고리 매핑
        '家電&カメラ': 'ELC',
        'ホーム&キッチン': 'HOM',
        'ビューティー': 'BTY',
        '食品・飲料・お酒': 'GRC',
        'おもちゃ': 'TOY',
        'スポーツ&アウトドア': 'SPT',
        'ファッション': 'CLO',
        'ペット用品': 'PET',
        'ベビー&マタニティ': 'BBY',
    }

    _USER_AGENTS = [
        (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        (
            'Mozilla/5.0 (X11; Linux x86_64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) '
            'Gecko/20100101 Firefox/125.0'
        ),
        (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) '
            'Version/17.4 Safari/605.1.15'
        ),
    ]

    def __init__(self, country: str = 'US'):
        """Amazon 수집기 초기화.

        Args:
            country: 'US' 또는 'JP'
        """
        if country not in self.MARKETPLACES:
            raise ValueError(f'Unsupported country: {country}. Use one of {list(self.MARKETPLACES)}')
        self.country = country
        mp_config = self.MARKETPLACES[country]
        self.base_url = mp_config['base_url']
        self.currency = mp_config['currency']
        self.language = mp_config['language']
        self.collector_name = f'amazon_{country.lower()}'
        self.timeout = int(os.environ.get('COLLECTOR_TIMEOUT', '20'))
        self.delay = float(os.environ.get('COLLECTOR_DELAY', '3'))
        self.max_retries = int(os.environ.get('COLLECTOR_MAX_RETRIES', '3'))
        self._custom_user_agent = os.environ.get('COLLECTOR_USER_AGENT', '')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_product(self, url: str) -> dict:
        """Amazon 상품 페이지에서 정보를 수집한다.

        에러 시 None 반환 (절대 크래시하지 않음).
        """
        try:
            asin = self._extract_asin(url)
            if not asin:
                logger.warning('Could not extract ASIN from URL: %s', url)
                return None
            html = self._fetch(url)
            if html is None:
                return None
            product = self._parse_product_page(html, asin)
            if not product:
                return None
            product['source_url'] = url
            product['collected_at'] = datetime.now(timezone.utc).isoformat()
            product['marketplace'] = self.marketplace
            product['country'] = self.country
            product['vendor'] = self.collector_name
            # 번역
            product = self.translate_product(product)
            # 가격 계산
            product = self.calculate_prices(product)
            # SKU 생성
            product['sku'] = self.generate_sku(product)
            return product
        except Exception as exc:
            logger.error('collect_product failed for %s: %s', url, exc)
            return None

    def search_products(self, keyword: str, max_results: int = 20) -> list:
        """Amazon에서 키워드 검색 후 상품 목록을 수집한다."""
        results = []
        try:
            page = 1
            while len(results) < max_results:
                search_url = f'{self.base_url}/s?k={requests.utils.quote(keyword)}&page={page}'
                html = self._fetch(search_url)
                if html is None:
                    break
                items = self._parse_search_page(html)
                if not items:
                    break
                for item in items:
                    if len(results) >= max_results:
                        break
                    results.append(item)
                page += 1
                if page > 5:
                    break
                time.sleep(self.delay)
        except Exception as exc:
            logger.error('search_products failed for keyword=%s: %s', keyword, exc)
        return results

    def collect_batch(self, urls: list) -> list:
        """여러 Amazon 상품 URL을 배치로 수집한다.

        COLLECTOR_DELAY 간격으로 순차 수집.
        실패한 URL은 스킵하고 성공한 것만 반환.
        """
        results = []
        for i, url in enumerate(urls):
            try:
                product = self.collect_product(url)
                if product:
                    results.append(product)
            except Exception as exc:
                logger.error('collect_batch: failed for URL %s: %s', url, exc)
            if i < len(urls) - 1:
                time.sleep(self.delay)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_asin(self, url: str) -> str:
        """URL에서 ASIN을 추출한다."""
        if not url:
            return None
        # 형식: /dp/XXXXXXXXXX  또는 /gp/product/XXXXXXXXXX
        match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
        if match:
            return match.group(1)
        # ASIN이 쿼리 파라미터에 있는 경우
        match = re.search(r'[?&]asin=([A-Z0-9]{10})', url, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _fetch(self, url: str) -> str:
        """URL을 GET 요청하고 HTML을 반환한다. 실패 시 None."""
        headers = {
            'User-Agent': self._get_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                return resp.text
            except requests.exceptions.Timeout:
                logger.warning('Timeout fetching %s (attempt %d)', url, attempt + 1)
            except requests.exceptions.HTTPError as exc:
                logger.warning('HTTP error fetching %s: %s', url, exc)
                break
            except requests.exceptions.RequestException as exc:
                logger.warning('Request error fetching %s: %s', url, exc)
            if attempt < self.max_retries - 1:
                time.sleep(self.delay)
        return None

    def _parse_product_page(self, html: str, asin: str) -> dict:
        """상품 페이지 HTML을 파싱하여 정보를 추출한다."""
        if not _BS4_AVAILABLE:
            return {'collector_id': asin, 'title_original': asin}

        soup = BeautifulSoup(html, 'lxml')
        product = {'collector_id': asin}

        # 상품명
        title_tag = soup.select_one('#productTitle')
        product['title_original'] = title_tag.get_text(strip=True) if title_tag else ''

        # 가격
        product['price_original'] = self._extract_price(soup)
        product['currency'] = self.currency

        # 이미지
        product['images'] = self._extract_images(soup)

        # 카테고리
        category_raw = self._extract_category(soup)
        product['category'] = category_raw
        product['category_code'] = self.CATEGORY_MAP.get(category_raw, 'GEN')

        # 브랜드
        brand_tag = (
            soup.select_one('#bylineInfo')
            or soup.select_one('.po-brand .po-break-word')
        )
        product['brand'] = brand_tag.get_text(strip=True).replace('Brand: ', '').replace('Visit the ', '').split(' Store')[0] if brand_tag else ''

        # 평점
        rating_tag = soup.select_one('#acrPopover') or soup.select_one('.a-icon-alt')
        if rating_tag:
            rating_text = rating_tag.get('title', '') or rating_tag.get_text(strip=True)
            match = re.search(r'([\d.]+)', rating_text)
            product['rating'] = float(match.group(1)) if match else None
        else:
            product['rating'] = None

        # 리뷰 수
        review_tag = soup.select_one('#acrCustomerReviewText')
        if review_tag:
            match = re.search(r'[\d,]+', review_tag.get_text())
            product['review_count'] = int(match.group().replace(',', '')) if match else 0
        else:
            product['review_count'] = 0

        # 상세설명
        desc_parts = []
        feature_bullets = soup.select('#feature-bullets li span.a-list-item')
        for bullet in feature_bullets:
            text = bullet.get_text(strip=True)
            if text:
                desc_parts.append(text)
        desc_tag = soup.select_one('#productDescription')
        if desc_tag:
            desc_parts.append(desc_tag.get_text(strip=True))
        product['description_original'] = '\n'.join(desc_parts)
        product['description_html'] = str(desc_tag) if desc_tag else ''

        # 재고
        avail_tag = soup.select_one('#availability')
        product['stock_status'] = avail_tag.get_text(strip=True) if avail_tag else 'unknown'

        # 중량/사이즈
        product['weight_kg'] = self._extract_weight(soup)
        product['dimensions'] = self._extract_dimensions(soup)

        # 옵션
        product['options'] = self._extract_options(soup)

        # 태그 기본값
        product['tags'] = [product['category']] if product.get('category') else []

        return product

    def _extract_price(self, soup) -> float:
        """가격을 파싱한다. 없으면 None."""
        selectors = [
            '.a-price .a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '.a-price-whole',
            '#price_inside_buybox',
        ]
        for sel in selectors:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(strip=True)
                # $19.99, ¥2,980, €12.99 등에서 숫자 추출
                match = re.search(r'[\d,]+(?:\.\d+)?', text.replace(',', ''))
                if match:
                    try:
                        return float(match.group().replace(',', ''))
                    except ValueError:
                        continue
        return None

    def _extract_images(self, soup) -> list:
        """이미지 URL 목록을 파싱한다."""
        images = []
        # data-a-dynamic-image 속성에서 추출
        img_tag = soup.select_one('#landingImage, #imgBlkFront')
        if img_tag:
            data_img = img_tag.get('data-a-dynamic-image', '')
            if data_img:
                urls = re.findall(r'"(https://[^"]+)"', data_img)
                images.extend(urls)
            if not images:
                src = img_tag.get('src', '')
                if src:
                    images.append(src)
        # 썸네일 이미지들
        thumb_tags = soup.select('#altImages img')
        for t in thumb_tags:
            src = t.get('src', '')
            if src and 'sprite' not in src:
                # 썸네일 URL을 원본 크기로 변환
                src = re.sub(r'\._[A-Z0-9_]+_\.', '.', src)
                if src not in images:
                    images.append(src)
        return images

    def _extract_category(self, soup) -> str:
        """카테고리를 파싱한다."""
        crumb_tag = soup.select_one('#wayfinding-breadcrumbs_feature_div')
        if crumb_tag:
            items = crumb_tag.select('li span.a-list-item a')
            if items:
                return items[0].get_text(strip=True)
        return ''

    def _extract_weight(self, soup) -> float:
        """중량(kg)을 파싱한다."""
        tech_table = soup.select('#productDetails_techSpec_section_1 tr')
        for row in tech_table:
            label = row.select_one('th')
            value = row.select_one('td')
            if label and value:
                label_text = label.get_text(strip=True).lower()
                if 'weight' in label_text or '重量' in label_text:
                    val_text = value.get_text(strip=True)
                    match = re.search(r'([\d.]+)\s*(kg|lb|g|oz)', val_text, re.IGNORECASE)
                    if match:
                        amount = float(match.group(1))
                        unit = match.group(2).lower()
                        if unit == 'lb':
                            return round(amount * 0.453592, 3)
                        elif unit == 'g':
                            return round(amount / 1000, 3)
                        elif unit == 'oz':
                            return round(amount * 0.0283495, 3)
                        return amount
        return None

    def _extract_dimensions(self, soup) -> str:
        """사이즈 정보를 파싱한다."""
        tech_table = soup.select('#productDetails_techSpec_section_1 tr')
        for row in tech_table:
            label = row.select_one('th')
            value = row.select_one('td')
            if label and value:
                label_text = label.get_text(strip=True).lower()
                if 'dimension' in label_text or 'size' in label_text or '寸法' in label_text:
                    return value.get_text(strip=True)
        return ''

    def _extract_options(self, soup) -> dict:
        """옵션(색상, 사이즈 등)을 파싱한다."""
        options = {}
        color_tag = soup.select_one('#variation_color_name .selection')
        if color_tag:
            options['color'] = color_tag.get_text(strip=True)
        size_tag = soup.select_one('#variation_size_name .selection')
        if size_tag:
            options['size'] = size_tag.get_text(strip=True)
        return options

    def _parse_search_page(self, html: str) -> list:
        """검색 결과 페이지 HTML을 파싱한다."""
        if not _BS4_AVAILABLE:
            return []
        results = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            items = soup.select('[data-component-type="s-search-result"]')
            for item in items:
                try:
                    asin = item.get('data-asin', '')
                    if not asin:
                        continue
                    title_tag = item.select_one('h2 a span')
                    title = title_tag.get_text(strip=True) if title_tag else ''
                    price = self._extract_price(item)
                    img_tag = item.select_one('img.s-image')
                    images = [img_tag['src']] if img_tag and img_tag.get('src') else []
                    rating_tag = item.select_one('.a-icon-alt')
                    rating = None
                    if rating_tag:
                        match = re.search(r'([\d.]+)', rating_tag.get_text())
                        rating = float(match.group(1)) if match else None
                    review_tag = item.select_one('.a-size-base.s-underline-text')
                    review_count = 0
                    if review_tag:
                        match = re.search(r'[\d,]+', review_tag.get_text())
                        review_count = int(match.group().replace(',', '')) if match else 0
                    link_tag = item.select_one('h2 a')
                    url = ''
                    if link_tag and link_tag.get('href'):
                        href = link_tag['href']
                        if href.startswith('/'):
                            url = self.base_url + href
                        else:
                            url = href
                    results.append({
                        'collector_id': asin,
                        'source_url': url,
                        'title_original': title,
                        'price_original': price,
                        'currency': self.currency,
                        'images': images,
                        'rating': rating,
                        'review_count': review_count,
                        'marketplace': self.marketplace,
                        'country': self.country,
                        'vendor': self.collector_name,
                        'collected_at': datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as item_exc:
                    logger.debug('Failed to parse search item: %s', item_exc)
        except Exception as exc:
            logger.error('_parse_search_page failed: %s', exc)
        return results

    def _get_user_agent(self) -> str:
        """User-Agent를 로테이션한다."""
        if self._custom_user_agent:
            return self._custom_user_agent
        try:
            from fake_useragent import UserAgent
            return UserAgent().random
        except Exception:
            return random.choice(self._USER_AGENTS)

    def _calculate_import_price(self, product: dict) -> dict:
        """수입 구매대행 가격을 계산한다.

        계산 항목:
        - 원본 가격 (현지 통화)
        - KRW 환산 (실시간 환율)
        - 해외배송비 (중량 기반 추정)
        - 관세 (15만원 초과 시 약 20%, 카테고리별 차등)
        - 구매대행 수수료 (마진)
        - 최종 판매가
        """
        return self.calculate_prices(product)
