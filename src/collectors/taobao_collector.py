"""Taobao / 1688 상품 수집기."""

import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import requests

from .base_collector import BaseCollector

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False
    logger.warning('beautifulsoup4 not installed; HTML parsing will be limited')


class TaobaoCollector(BaseCollector):
    """Taobao / 1688 상품 수집기."""

    marketplace = 'taobao'

    MARKETPLACES = {
        'taobao': {
            'base_url': 'https://item.taobao.com',
            'search_url': 'https://s.taobao.com/search',
            'currency': 'CNY',
            'language': 'zh',
            'country': 'CN',
        },
        '1688': {
            'base_url': 'https://detail.1688.com',
            'search_url': 'https://s.1688.com/selloffer/offer_search.htm',
            'currency': 'CNY',
            'language': 'zh',
            'country': 'CN',
        },
    }

    CATEGORY_MAP = {
        '女装': 'WCL', '男装': 'MCL', '箱包': 'BAG', '鞋靴': 'SHO',
        '配饰': 'ACC', '内衣': 'UND', '家居': 'HOM', '美妆': 'BTY',
        '母婴': 'BBY', '食品': 'FOD', '数码': 'DIG', '运动': 'SPT',
        '玩具': 'TOY', '汽车': 'AUT', '办公': 'OFC', '宠物': 'PET',
        '家电': 'ELC', '手机': 'PHN', '电脑': 'CMP',
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

    def __init__(self, platform: str = 'taobao'):
        """Taobao / 1688 수집기 초기화.

        Args:
            platform: 'taobao' 또는 '1688'
        """
        if platform not in self.MARKETPLACES:
            raise ValueError(f'Unsupported platform: {platform}. Use one of {list(self.MARKETPLACES)}')
        self.platform = platform
        mp_config = self.MARKETPLACES[platform]
        self.base_url = mp_config['base_url']
        self.search_url = mp_config['search_url']
        self.currency = mp_config['currency']
        self.language = mp_config['language']
        self.country = mp_config['country']
        self.collector_name = f'taobao_{platform}' if platform == '1688' else 'taobao'
        self.timeout = int(os.getenv('COLLECTOR_TIMEOUT', '20'))
        self.delay = float(os.getenv('COLLECTOR_DELAY', '3'))
        self.max_retries = int(os.getenv('COLLECTOR_MAX_RETRIES', '3'))
        self._cookie = os.getenv('TAOBAO_COOKIE', '')
        self._proxy = os.getenv('COLLECTOR_CN_PROXY', '')
        self._custom_user_agent = os.getenv('COLLECTOR_USER_AGENT', '')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_product(self, url: str) -> dict:
        """Taobao / 1688 상품 페이지에서 정보를 수집한다.

        에러 시 None 반환 (절대 크래시하지 않음).
        """
        try:
            item_id = self._extract_item_id(url)
            if not item_id:
                logger.warning('Could not extract item ID from URL: %s', url)
                return None
            html = self._fetch(url)
            if html is None:
                return None
            if self.platform == '1688':
                product = self._parse_1688_page(html, item_id)
            else:
                product = self._parse_taobao_page(html, item_id)
            if not product:
                return None
            product['source_url'] = url
            product['collected_at'] = datetime.now(timezone.utc).isoformat()
            product['marketplace'] = self.marketplace
            product['country'] = self.country
            product['vendor'] = self.collector_name
            product = self.translate_product(product)
            product = self.calculate_prices(product)
            product['sku'] = self.generate_sku(product)
            return product
        except Exception as exc:
            logger.error('collect_product failed for %s: %s', url, exc)
            return None

    def search_products(self, keyword: str, max_results: int = 20) -> list:
        """Taobao / 1688에서 키워드 검색 후 상품 목록을 수집한다."""
        results = []
        try:
            page = 1
            while len(results) < max_results:
                if self.platform == 'taobao':
                    search_url = f'{self.search_url}?q={requests.utils.quote(keyword)}&s={(page - 1) * 44}'
                else:
                    search_url = f'{self.search_url}?keywords={requests.utils.quote(keyword)}&beginPage={page}'
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
        """여러 Taobao / 1688 상품 URL을 배치로 수집한다.

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
    # Private helpers — ID extraction
    # ------------------------------------------------------------------

    def _extract_item_id(self, url: str) -> str:
        """URL에서 상품 ID를 추출한다.

        Taobao: item.taobao.com/item.htm?id=XXXXXXXXXX → id 파라미터
        1688: detail.1688.com/offer/XXXXXXXXXX.html → 숫자
        """
        if not url:
            return None
        if self.platform == 'taobao':
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            ids = params.get('id', [])
            if ids:
                return ids[0]
            match = re.search(r'[?&]id=(\d+)', url)
            return match.group(1) if match else None
        else:
            # 1688: /offer/XXXXXXXXXX.html
            match = re.search(r'/offer/(\d+)\.html', url)
            if match:
                return match.group(1)
            match = re.search(r'offerId=(\d+)', url)
            return match.group(1) if match else None

    # ------------------------------------------------------------------
    # Private helpers — HTML parsing
    # ------------------------------------------------------------------

    def _parse_taobao_page(self, html: str, item_id: str) -> dict:
        """Taobao 상품 페이지 HTML을 파싱하여 정보를 추출한다."""
        if not _BS4_AVAILABLE:
            return {'collector_id': item_id, 'title_original': item_id}

        soup = BeautifulSoup(html, 'lxml')
        product = {'collector_id': item_id}

        # 상품명
        title_tag = (
            soup.select_one('.tb-main-title')
            or soup.select_one('#J_Title h3')
            or soup.select_one('h1')
        )
        product['title_original'] = title_tag.get_text(strip=True) if title_tag else ''

        # 가격 (¥19.9 또는 범위 ¥19.9-39.9)
        product['price_original'] = self._extract_taobao_price(soup)
        product['currency'] = self.currency

        # 이미지
        product['images'] = self._extract_taobao_images(soup)

        # 카테고리
        category_raw = self._extract_taobao_category(soup)
        product['category'] = category_raw
        product['category_code'] = self._map_category(category_raw)

        # 브랜드
        brand_tag = soup.select_one('[data-label="品牌"] .tb-prop-val')
        product['brand'] = brand_tag.get_text(strip=True) if brand_tag else ''

        # 평점/리뷰
        rating_tag = soup.select_one('.J_Score .score-num')
        if rating_tag:
            try:
                product['rating'] = float(rating_tag.get_text(strip=True))
            except ValueError:
                product['rating'] = None
        else:
            product['rating'] = None
        product['review_count'] = 0

        # 상세설명
        desc_tag = soup.select_one('#description') or soup.select_one('#J_DivItemDesc')
        product['description_original'] = desc_tag.get_text(strip=True) if desc_tag else ''
        product['description_html'] = str(desc_tag) if desc_tag else ''

        # 재고
        product['stock_status'] = 'unknown'

        # 중량 — 상품속성에서 추출 시도
        product['weight_kg'] = self._extract_taobao_weight(soup)
        product['dimensions'] = ''
        product['options'] = self._extract_taobao_options(soup)
        product['tags'] = [category_raw] if category_raw else []

        return product

    def _parse_1688_page(self, html: str, item_id: str) -> dict:
        """1688 상품 페이지 HTML을 파싱하여 정보를 추출한다."""
        if not _BS4_AVAILABLE:
            return {'collector_id': item_id, 'title_original': item_id}

        soup = BeautifulSoup(html, 'lxml')
        product = {'collector_id': item_id}

        # 상품명
        title_tag = (
            soup.select_one('.d-title')
            or soup.select_one('h1.product-title')
            or soup.select_one('h1')
        )
        product['title_original'] = title_tag.get_text(strip=True) if title_tag else ''

        # 가격
        product['price_original'] = self._extract_1688_price(soup)
        product['currency'] = self.currency

        # 이미지
        product['images'] = self._extract_1688_images(soup)

        # 카테고리
        category_raw = self._extract_1688_category(soup)
        product['category'] = category_raw
        product['category_code'] = self._map_category(category_raw)

        # 브랜드
        brand_tag = soup.select_one('.brand-name') or soup.select_one('[class*="brand"]')
        product['brand'] = brand_tag.get_text(strip=True) if brand_tag else ''

        product['rating'] = None
        product['review_count'] = 0

        desc_tag = soup.select_one('#description') or soup.select_one('.product-description')
        product['description_original'] = desc_tag.get_text(strip=True) if desc_tag else ''
        product['description_html'] = str(desc_tag) if desc_tag else ''

        product['stock_status'] = 'unknown'
        product['weight_kg'] = None
        product['dimensions'] = ''
        product['options'] = {}
        product['tags'] = [category_raw] if category_raw else []

        return product

    def _extract_taobao_price(self, soup) -> float:
        """Taobao 가격을 파싱한다 (¥19.9 또는 ¥19.9-39.9)."""
        selectors = [
            '.tb-rmb-num',
            '.J_Price .price',
            '.tb-price .tb-rmb-num',
            '#J_StrPrice .tb-rmb-num',
        ]
        for sel in selectors:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(strip=True)
                # 범위 가격 처리: 첫 번째 숫자 사용
                match = re.search(r'([\d.]+)', text.replace(',', ''))
                if match:
                    try:
                        return float(match.group(1))
                    except ValueError:
                        continue
        # 범위 패턴: ¥19.9-39.9
        price_text = soup.get_text()
        match = re.search(r'[¥￥]([\d.]+)(?:-[\d.]+)?', price_text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    def _extract_1688_price(self, soup) -> float:
        """1688 가격을 파싱한다."""
        selectors = [
            '.price-common .price-unit',
            '.price .num',
            '.offer-price .price',
        ]
        for sel in selectors:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(strip=True)
                match = re.search(r'([\d.]+)', text.replace(',', ''))
                if match:
                    try:
                        return float(match.group(1))
                    except ValueError:
                        continue
        return None

    def _extract_taobao_images(self, soup) -> list:
        """Taobao 이미지 URL 목록을 파싱한다."""
        images = []
        # 메인 이미지
        main_img = soup.select_one('#J_ImgBooth img') or soup.select_one('.tb-main-pic img')
        if main_img:
            src = main_img.get('src') or main_img.get('data-src', '')
            if src:
                if src.startswith('//'):
                    src = 'https:' + src
                images.append(src)
        # 썸네일 이미지들
        thumb_tags = soup.select('#J_UlThumb li img') or soup.select('.tb-img-list img')
        for t in thumb_tags:
            src = t.get('src') or t.get('data-src', '')
            if src:
                if src.startswith('//'):
                    src = 'https:' + src
                if src not in images:
                    images.append(src)
        return images

    def _extract_1688_images(self, soup) -> list:
        """1688 이미지 URL 목록을 파싱한다."""
        images = []
        img_tags = soup.select('.detail-image img') or soup.select('.main-image img')
        for t in img_tags:
            src = t.get('src') or t.get('data-src', '')
            if src:
                if src.startswith('//'):
                    src = 'https:' + src
                if src not in images:
                    images.append(src)
        return images

    def _extract_taobao_category(self, soup) -> str:
        """Taobao 카테고리를 파싱한다."""
        crumb = soup.select('.breadcrumb a') or soup.select('#J_breadCrumb a')
        if crumb:
            return crumb[0].get_text(strip=True)
        return ''

    def _extract_1688_category(self, soup) -> str:
        """1688 카테고리를 파싱한다."""
        crumb = soup.select('.breadcrumb a') or soup.select('.crumb a')
        if crumb:
            return crumb[0].get_text(strip=True)
        return ''

    def _map_category(self, category_raw: str) -> str:
        """카테고리 문자열을 내부 코드로 매핑한다."""
        if not category_raw:
            return 'GEN'
        for key, code in self.CATEGORY_MAP.items():
            if key in category_raw:
                return code
        return 'GEN'

    def _extract_taobao_weight(self, soup) -> float:
        """Taobao 상품속성에서 중량을 파싱한다."""
        prop_tags = soup.select('.attributes-list li') or soup.select('.tb-prop li')
        for tag in prop_tags:
            text = tag.get_text()
            if '重量' in text or '克重' in text:
                match = re.search(r'([\d.]+)\s*(kg|g|克|千克)', text, re.IGNORECASE)
                if match:
                    amount = float(match.group(1))
                    unit = match.group(2).lower()
                    if unit in ('g', '克'):
                        return round(amount / 1000, 3)
                    return amount
        return None

    def _extract_taobao_options(self, soup) -> dict:
        """Taobao 옵션(색상, 사이즈 등)을 파싱한다."""
        options = {}
        sku_props = soup.select('.J_TSaleProp .tb-menus li')
        for prop in sku_props:
            label = prop.get('data-value', '')
            if label:
                options.setdefault('variants', []).append(label)
        return options

    def _parse_search_page(self, html: str) -> list:
        """검색 결과 페이지 HTML을 파싱한다."""
        if not _BS4_AVAILABLE:
            return []
        results = []
        try:
            soup = BeautifulSoup(html, 'lxml')
            if self.platform == 'taobao':
                items = soup.select('.item.J_MouserOnverReq') or soup.select('[data-item-id]')
            else:
                items = soup.select('.sm-offer-item') or soup.select('.offer-item')
            for item in items:
                try:
                    if self.platform == 'taobao':
                        item_id = item.get('data-item-id', '')
                        if not item_id:
                            continue
                        title_tag = item.select_one('.item-name') or item.select_one('a[title]')
                        title = (
                            title_tag.get('title', '') or title_tag.get_text(strip=True)
                        ) if title_tag else ''
                        price = self._extract_taobao_price(item)
                        img_tag = item.select_one('img')
                        src = (img_tag.get('src') or img_tag.get('data-src', '')) if img_tag else ''
                        if src and src.startswith('//'):
                            src = 'https:' + src
                        images = [src] if src else []
                        link_tag = item.select_one('a')
                        url = ''
                        if link_tag and link_tag.get('href'):
                            href = link_tag['href']
                            url = href if href.startswith('http') else ('https:' + href if href.startswith('//') else href)
                    else:
                        item_id = item.get('data-offer-id', '') or item.get('id', '')
                        if not item_id:
                            continue
                        title_tag = item.select_one('.offer-title') or item.select_one('a[title]')
                        title = (
                            title_tag.get('title', '') or title_tag.get_text(strip=True)
                        ) if title_tag else ''
                        price = self._extract_1688_price(item)
                        img_tag = item.select_one('img')
                        src = (img_tag.get('src') or img_tag.get('data-src', '')) if img_tag else ''
                        if src and src.startswith('//'):
                            src = 'https:' + src
                        images = [src] if src else []
                        link_tag = item.select_one('a')
                        url = ''
                        if link_tag and link_tag.get('href'):
                            href = link_tag['href']
                            url = href if href.startswith('http') else ('https:' + href if href.startswith('//') else href)

                    results.append({
                        'collector_id': str(item_id),
                        'source_url': url,
                        'title_original': title,
                        'price_original': price,
                        'currency': self.currency,
                        'images': images,
                        'rating': None,
                        'review_count': 0,
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

    # ------------------------------------------------------------------
    # Price calculation
    # ------------------------------------------------------------------

    def calculate_prices(self, product: dict) -> dict:
        """CNY 상품 가격을 KRW로 계산한다 (BaseCollector override)."""
        if not product:
            return product
        return self._calculate_import_price(product)

    def _calculate_import_price(self, product: dict) -> dict:
        """CNY → KRW 변환 및 창고비·관세·마진을 적용하여 판매가를 계산한다.

        계산 항목:
        - CNY → KRW 환산 (FX_CNYKRW 환율)
        - 중국 창고비: CN_WAREHOUSE_FEE_BASE_KRW 기본 + CN_WAREHOUSE_FEE_PER_KG_KRW × 중량(kg)
        - 관부가세: 원가 KRW > CUSTOMS_THRESHOLD_KRW(150000)이면 CUSTOMS_RATE_DEFAULT(20%) 적용
        - 마진율: IMPORT_MARGIN_PCT
        """
        try:
            price_orig = product.get('price_original')
            if price_orig is None:
                return product
            price_orig = Decimal(str(price_orig))

            cny_krw = Decimal(os.getenv('FX_CNYKRW', '185'))
            cost_krw = price_orig * cny_krw

            warehouse_base = Decimal(os.getenv('CN_WAREHOUSE_FEE_BASE_KRW', '3000'))
            warehouse_per_kg = Decimal(os.getenv('CN_WAREHOUSE_FEE_PER_KG_KRW', '2000'))
            weight_kg = product.get('weight_kg')
            warehouse_fee = warehouse_base
            if weight_kg:
                warehouse_fee += warehouse_per_kg * Decimal(str(weight_kg))

            customs_threshold = Decimal(os.getenv('CUSTOMS_THRESHOLD_KRW', '150000'))
            if cost_krw > customs_threshold:
                customs_rate = Decimal(os.getenv('CUSTOMS_RATE_DEFAULT', '0.20'))
            else:
                customs_rate = Decimal('0')

            total_before_margin = (cost_krw + warehouse_fee) * (Decimal('1') + customs_rate)
            margin_pct = Decimal(os.getenv('IMPORT_MARGIN_PCT', '25'))
            sell_krw = total_before_margin * (Decimal('1') + margin_pct / Decimal('100'))

            product['price_krw'] = int(cost_krw)
            product['sell_price_krw'] = int(sell_krw)

            usd_krw = Decimal(os.getenv('FX_USDKRW', '1350'))
            product['sell_price_usd'] = round(float(sell_krw / usd_krw), 2)
        except Exception as exc:
            logger.warning('_calculate_import_price failed: %s', exc)
        return product

    # ------------------------------------------------------------------
    # SKU generation
    # ------------------------------------------------------------------

    def generate_sku(self, product: dict) -> str:
        """상품에 SKU를 부여한다.

        Taobao: TAO-{CATEGORY_CODE}-{SUFFIX}
        1688:   ALB-{CATEGORY_CODE}-{SUFFIX}
        """
        if not product:
            return ''
        prefix = 'ALB' if self.platform == '1688' else 'TAO'
        category_code = product.get('category_code', 'GEN')
        collector_id = product.get('collector_id', '')
        if collector_id:
            id_str = str(collector_id)
            digits = ''.join(filter(str.isdigit, id_str))
            if digits:
                suffix = digits[-3:].zfill(3)
            else:
                suffix = datetime.now(timezone.utc).strftime('%H%M')
        else:
            suffix = datetime.now(timezone.utc).strftime('%H%M')
        return f'{prefix}-{category_code}-{suffix}'

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def translate_product(self, product: dict) -> dict:
        """수집된 중국어 상품명/설명을 한글로 번역한다."""
        if not product:
            return product
        try:
            try:
                from src.translate import zh_to_ko, zh_to_en
                _zh_to_ko = zh_to_ko
                _zh_to_en = zh_to_en
            except ImportError:
                from src.translate import translate as _translate

                def _zh_to_ko(text):
                    return _translate(text, 'ZH', 'KO')

                def _zh_to_en(text):
                    return _translate(text, 'ZH', 'EN')

            title_orig = product.get('title_original', '') or ''
            if title_orig and not product.get('title_ko'):
                product['title_ko'] = _zh_to_ko(title_orig) or title_orig
            if title_orig and not product.get('title_en'):
                product['title_en'] = _zh_to_en(title_orig) or title_orig
            desc_orig = product.get('description_original', '') or ''
            if desc_orig and not product.get('description_ko'):
                product['description_ko'] = _zh_to_ko(desc_orig) or desc_orig
        except Exception:
            pass
        return product

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> str:
        """URL을 GET 요청하고 HTML을 반환한다. 실패 시 None."""
        headers = {
            'User-Agent': self._get_user_agent(),
            'Accept-Language': 'zh-CN,zh;q=0.9,ko;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        if self._cookie:
            headers['Cookie'] = self._cookie

        proxies = None
        if self._proxy:
            proxies = {'http': self._proxy, 'https': self._proxy}

        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, headers=headers, proxies=proxies, timeout=self.timeout)
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

    def _get_user_agent(self) -> str:
        """User-Agent를 로테이션한다."""
        if self._custom_user_agent:
            return self._custom_user_agent
        try:
            from fake_useragent import UserAgent
            return UserAgent().random
        except Exception:
            return random.choice(self._USER_AGENTS)
