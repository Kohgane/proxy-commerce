"""src/translate.py 단위 테스트"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── 테스트 실행 전 캐시 초기화 헬퍼 ──────────────────────────

def _clear_cache():
    """인메모리 캐시를 비운다."""
    import src.translate as t
    t._cache.clear()


# ── provider=none 시 원문 그대로 반환 ────────────────────────

class TestProviderNone:
    def setup_method(self):
        _clear_cache()

    def test_translate_returns_original(self):
        with patch.dict(os.environ, {'TRANSLATE_PROVIDER': 'none'}):
            from src.translate import translate
            assert translate('안녕하세요', 'KO', 'EN') == '안녕하세요'

    def test_ja_to_ko_returns_original(self):
        with patch.dict(os.environ, {'TRANSLATE_PROVIDER': 'none'}):
            from src.translate import ja_to_ko
            assert ja_to_ko('こんにちは') == 'こんにちは'

    def test_fr_to_ko_returns_original(self):
        with patch.dict(os.environ, {'TRANSLATE_PROVIDER': 'none'}):
            from src.translate import fr_to_ko
            assert fr_to_ko('Bonjour') == 'Bonjour'

    def test_ko_to_en_returns_original(self):
        with patch.dict(os.environ, {'TRANSLATE_PROVIDER': 'none'}):
            from src.translate import ko_to_en
            assert ko_to_en('안녕하세요') == '안녕하세요'

    def test_ko_to_ja_returns_original(self):
        with patch.dict(os.environ, {'TRANSLATE_PROVIDER': 'none'}):
            from src.translate import ko_to_ja
            assert ko_to_ja('안녕하세요') == '안녕하세요'


# ── 하위호환: ko_to_en_if_needed ─────────────────────────────

class TestBackwardCompat:
    def setup_method(self):
        _clear_cache()

    def test_ko_to_en_if_needed_returns_original_when_none(self):
        with patch.dict(os.environ, {'TRANSLATE_PROVIDER': 'none'}):
            from src.translate import ko_to_en_if_needed
            assert ko_to_en_if_needed('테스트') == '테스트'

    def test_ko_to_en_if_needed_calls_ko_to_en(self):
        """ko_to_en_if_needed는 내부적으로 ko_to_en을 호출해야 함."""
        with patch.dict(os.environ, {'TRANSLATE_PROVIDER': 'none'}):
            from src.translate import ko_to_en_if_needed, ko_to_en
            text = '상품명 테스트'
            assert ko_to_en_if_needed(text) == ko_to_en(text)


# ── 빈 문자열 / None 입력 ─────────────────────────────────────

class TestEmptyInput:
    def setup_method(self):
        _clear_cache()

    def test_empty_string_returns_empty(self):
        from src.translate import translate
        assert translate('', 'KO', 'EN') == ''

    def test_none_input_returns_empty(self):
        from src.translate import translate
        assert translate(None, 'KO', 'EN') == ''

    def test_ja_to_ko_empty(self):
        from src.translate import ja_to_ko
        assert ja_to_ko('') == ''

    def test_fr_to_ko_empty(self):
        from src.translate import fr_to_ko
        assert fr_to_ko('') == ''

    def test_ko_to_en_empty(self):
        from src.translate import ko_to_en
        assert ko_to_en('') == ''

    def test_ko_to_ja_empty(self):
        from src.translate import ko_to_ja
        assert ko_to_ja('') == ''


# ── API 키 없을 때 크래시하지 않고 원문 반환 ─────────────────

class TestNoApiKey:
    def setup_method(self):
        _clear_cache()

    def test_no_api_key_returns_original(self):
        env = {'TRANSLATE_PROVIDER': 'deepl', 'DEEPL_API_KEY': ''}
        with patch.dict(os.environ, env):
            from src.translate import translate
            result = translate('안녕하세요', 'KO', 'EN')
            assert result == '안녕하세요'

    def test_no_api_key_does_not_raise(self):
        env = {'TRANSLATE_PROVIDER': 'deepl', 'DEEPL_API_KEY': ''}
        with patch.dict(os.environ, env):
            from src.translate import ko_to_en
            # 예외 없이 실행되어야 함
            result = ko_to_en('테스트')
            assert isinstance(result, str)


# ── Rate limit / HTTP 오류 시 원문 반환 ──────────────────────

class TestApiErrors:
    def setup_method(self):
        _clear_cache()

    def _mock_http_error(self, status_code):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        http_err = __import__('requests').exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_err
        return mock_resp

    def test_http_429_returns_original(self):
        """Rate limit(429) 시 원문 반환."""
        env = {'TRANSLATE_PROVIDER': 'deepl', 'DEEPL_API_KEY': 'dummy-key'}
        with patch.dict(os.environ, env):
            import requests
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_resp
            )
            with patch('requests.post', return_value=mock_resp):
                from src.translate import translate
                result = translate('안녕하세요', 'KO', 'EN')
                assert result == '안녕하세요'

    def test_connection_error_returns_original(self):
        """네트워크 오류 시 원문 반환."""
        env = {'TRANSLATE_PROVIDER': 'deepl', 'DEEPL_API_KEY': 'dummy-key'}
        with patch.dict(os.environ, env):
            import requests
            with patch('requests.post', side_effect=requests.exceptions.ConnectionError('네트워크 오류')):
                from src.translate import translate
                result = translate('안녕하세요', 'KO', 'EN')
                assert result == '안녕하세요'


# ── 캐시 동작: 같은 입력 두 번 호출 시 API 1회만 호출 ─────────

class TestCache:
    def setup_method(self):
        _clear_cache()

    def test_same_input_calls_api_once(self):
        """동일한 텍스트+언어쌍은 캐시에서 반환 — API 호출 1회만."""
        env = {'TRANSLATE_PROVIDER': 'deepl', 'DEEPL_API_KEY': 'dummy-key'}
        with patch.dict(os.environ, env):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                'translations': [{'text': 'Hello'}]
            }
            with patch('requests.post', return_value=mock_resp) as mock_post:
                from src.translate import translate
                result1 = translate('안녕하세요', 'KO', 'EN')
                result2 = translate('안녕하세요', 'KO', 'EN')
                assert result1 == 'Hello'
                assert result2 == 'Hello'
                # API는 1회만 호출되어야 함
                assert mock_post.call_count == 1

    def test_different_inputs_each_call_api(self):
        """다른 텍스트는 각각 API를 호출."""
        env = {'TRANSLATE_PROVIDER': 'deepl', 'DEEPL_API_KEY': 'dummy-key'}
        with patch.dict(os.environ, env):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.side_effect = [
                {'translations': [{'text': 'Hello'}]},
                {'translations': [{'text': 'Good morning'}]},
            ]
            with patch('requests.post', return_value=mock_resp) as mock_post:
                from src.translate import translate
                translate('안녕하세요', 'KO', 'EN')
                translate('좋은 아침', 'KO', 'EN')
                assert mock_post.call_count == 2
