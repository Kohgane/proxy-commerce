"""tests/test_search.py — Phase 48: 검색 엔진 + 필터링 테스트."""
import pytest


SAMPLE_PRODUCTS = [
    {
        'id': 'P001',
        'title': '삼성 노트북 갤럭시북',
        'description': '가벼운 노트북 컴퓨터',
        'tags': ['노트북', '컴퓨터', '삼성'],
        'category': '전자제품',
        'price': 1200000,
        'rating': 4.5,
        'stock': 10,
        'sales_count': 100,
        'marketplace': 'coupang',
        'created_at': '2024-01-01T00:00:00+00:00',
    },
    {
        'id': 'P002',
        'title': 'Apple MacBook Pro',
        'description': 'Professional laptop for creative work',
        'tags': ['노트북', 'Apple', '맥북'],
        'category': '전자제품',
        'price': 2500000,
        'rating': 4.8,
        'stock': 5,
        'sales_count': 200,
        'marketplace': 'naver',
        'created_at': '2024-02-01T00:00:00+00:00',
    },
    {
        'id': 'P003',
        'title': '나이키 티셔츠',
        'description': '편안한 운동복',
        'tags': ['의류', '스포츠', '나이키'],
        'category': '의류',
        'price': 50000,
        'rating': 4.0,
        'stock': 0,
        'sales_count': 50,
        'marketplace': 'coupang',
        'created_at': '2024-03-01T00:00:00+00:00',
    },
    {
        'id': 'P004',
        'title': '索尼 耳机',  # 중국어 제목
        'description': '高品质耳机',
        'tags': ['耳机', '索尼', '电子'],
        'category': '전자제품',
        'price': 300000,
        'rating': 4.2,
        'stock': 20,
        'sales_count': 75,
        'marketplace': 'naver',
        'created_at': '2024-01-15T00:00:00+00:00',
    },
]


class TestSearchEngine:
    def setup_method(self):
        from src.search.search_engine import SearchEngine
        self.engine = SearchEngine()
        for p in SAMPLE_PRODUCTS:
            self.engine.index_product(p)

    def test_search_by_title_keyword(self):
        results = self.engine.search('노트북')
        ids = [r['id'] for r in results]
        assert 'P001' in ids
        assert 'P002' in ids

    def test_search_by_tag(self):
        results = self.engine.search('삼성')
        ids = [r['id'] for r in results]
        assert 'P001' in ids

    def test_search_english_keyword(self):
        results = self.engine.search('macbook')
        ids = [r['id'] for r in results]
        assert 'P002' in ids

    def test_search_no_results(self):
        results = self.engine.search('찾을수없는키워드xyz123')
        assert results == []

    def test_search_empty_query(self):
        results = self.engine.search('')
        assert results == []

    def test_title_has_higher_score_than_description(self):
        # 제목에 있는 키워드가 설명에만 있는 것보다 높은 점수
        results = self.engine.search('노트북')
        assert len(results) > 0
        title_match = next((r for r in results if '노트북' in r.get('title', '')), None)
        assert title_match is not None

    def test_remove_product(self):
        self.engine.remove_product('P001')
        results = self.engine.search('삼성')
        ids = [r['id'] for r in results]
        assert 'P001' not in ids

    def test_reindex_product(self):
        updated = dict(SAMPLE_PRODUCTS[0])
        updated['title'] = '새로운 제목 블루투스'
        self.engine.index_product(updated)
        results = self.engine.search('블루투스')
        assert len(results) > 0

    def test_chinese_keyword_search(self):
        results = self.engine.search('索尼')
        ids = [r['id'] for r in results]
        assert 'P004' in ids

    def test_product_without_id_raises(self):
        with pytest.raises(ValueError):
            self.engine.index_product({'title': '아이디 없음'})


class TestSearchFilter:
    def setup_method(self):
        from src.search.filters import SearchFilter
        self.fltr = SearchFilter()

    def test_filter_by_price_range(self):
        results = self.fltr.filter(SAMPLE_PRODUCTS, min_price=100000, max_price=1500000)
        ids = [r['id'] for r in results]
        assert 'P001' in ids
        assert 'P003' not in ids
        assert 'P002' not in ids

    def test_filter_by_category(self):
        results = self.fltr.filter(SAMPLE_PRODUCTS, categories=['전자제품'])
        ids = [r['id'] for r in results]
        assert 'P001' in ids
        assert 'P003' not in ids

    def test_filter_by_marketplace(self):
        results = self.fltr.filter(SAMPLE_PRODUCTS, marketplaces=['coupang'])
        ids = [r['id'] for r in results]
        assert 'P001' in ids
        assert 'P002' not in ids

    def test_filter_by_rating(self):
        results = self.fltr.filter(SAMPLE_PRODUCTS, min_rating=4.5)
        ids = [r['id'] for r in results]
        assert 'P002' in ids
        assert 'P003' not in ids

    def test_filter_in_stock_only(self):
        results = self.fltr.filter(SAMPLE_PRODUCTS, in_stock_only=True)
        ids = [r['id'] for r in results]
        assert 'P003' not in ids

    def test_combined_filters(self):
        results = self.fltr.filter(
            SAMPLE_PRODUCTS,
            categories=['전자제품'],
            min_price=200000,
            in_stock_only=True,
        )
        for r in results:
            assert r['category'] == '전자제품'
            assert r['price'] >= 200000
            assert r['stock'] > 0


class TestSearchSorter:
    def setup_method(self):
        from src.search.sort import SearchSorter
        self.sorter = SearchSorter()

    def test_sort_price_asc(self):
        sorted_products = self.sorter.sort(SAMPLE_PRODUCTS, 'price_asc')
        prices = [p['price'] for p in sorted_products]
        assert prices == sorted(prices)

    def test_sort_price_desc(self):
        sorted_products = self.sorter.sort(SAMPLE_PRODUCTS, 'price_desc')
        prices = [p['price'] for p in sorted_products]
        assert prices == sorted(prices, reverse=True)

    def test_sort_newest(self):
        sorted_products = self.sorter.sort(SAMPLE_PRODUCTS, 'newest')
        dates = [p['created_at'] for p in sorted_products]
        assert dates == sorted(dates, reverse=True)

    def test_sort_popularity(self):
        sorted_products = self.sorter.sort(SAMPLE_PRODUCTS, 'popularity')
        counts = [p['sales_count'] for p in sorted_products]
        assert counts == sorted(counts, reverse=True)

    def test_sort_rating(self):
        sorted_products = self.sorter.sort(SAMPLE_PRODUCTS, 'rating')
        ratings = [p['rating'] for p in sorted_products]
        assert ratings == sorted(ratings, reverse=True)

    def test_sort_invalid(self):
        with pytest.raises(ValueError):
            self.sorter.sort(SAMPLE_PRODUCTS, 'invalid_sort')


class TestAutocomplete:
    def setup_method(self):
        from src.search.autocomplete import Autocomplete
        self.ac = Autocomplete()
        self.ac.index_keywords(['노트북', '노트북 케이스', '나이키', '낮잠', '삼성'])

    def test_complete_prefix(self):
        suggestions = self.ac.complete('노트')
        assert '노트북' in suggestions
        assert '노트북 케이스' in suggestions

    def test_complete_no_match(self):
        suggestions = self.ac.complete('xyz')
        assert suggestions == []

    def test_record_query_increases_popularity(self):
        self.ac.record_query('노트북')
        self.ac.record_query('노트북')
        popular = self.ac.get_popular()
        assert popular[0] == '노트북'

    def test_recent_queries(self):
        self.ac.record_query('삼성')
        self.ac.record_query('나이키')
        recent = self.ac.get_recent(2)
        assert recent[0] == '나이키'
        assert '삼성' in recent

    def test_popular_limit(self):
        for i in range(15):
            self.ac.record_query(f'query_{i}')
        popular = self.ac.get_popular(top_n=10)
        assert len(popular) <= 10

    def test_record_query_adds_to_index(self):
        self.ac.record_query('새검색어')
        suggestions = self.ac.complete('새')
        assert '새검색어' in suggestions


class TestSearchAnalytics:
    def setup_method(self):
        from src.search.search_analytics import SearchAnalytics
        self.analytics = SearchAnalytics()

    def test_record_search(self):
        self.analytics.record_search('노트북', result_count=5)
        summary = self.analytics.get_summary()
        assert summary['total_searches'] == 1

    def test_no_result_tracking(self):
        self.analytics.record_search('없는검색어', result_count=0)
        no_result = self.analytics.get_no_result_queries()
        assert len(no_result) == 1

    def test_popular_queries(self):
        self.analytics.record_search('노트북', 5)
        self.analytics.record_search('노트북', 5)
        self.analytics.record_search('의류', 3)
        popular = self.analytics.get_popular_queries()
        assert popular[0]['query'] == '노트북'
        assert popular[0]['count'] == 2

    def test_click_rate(self):
        self.analytics.record_search('노트북', 10)
        self.analytics.record_click('노트북', 'P001')
        rate = self.analytics.get_click_rate('노트북')
        assert rate == 1.0

    def test_click_rate_zero_searches(self):
        rate = self.analytics.get_click_rate('없는쿼리')
        assert rate == 0.0

    def test_summary(self):
        self.analytics.record_search('A', 3)
        self.analytics.record_search('B', 0)
        summary = self.analytics.get_summary()
        assert summary['unique_queries'] == 2
        assert summary['no_result_queries'] == 1
