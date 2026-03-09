"""다국어 번역 모듈 — DeepL API 기반 범용 번역 + 인메모리 캐시"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

# DeepL Free API 기본 엔드포인트
_DEEPL_DEFAULT_URL = 'https://api-free.deepl.com/v2/translate'

# 인메모리 캐시: (text, source_lang, target_lang) → 번역 결과
_cache: dict = {}


def translate(text: str, source_lang: str, target_lang: str) -> str:
    """범용 번역 함수.

    - TRANSLATE_PROVIDER=none 이면 원문 그대로 반환 (테스트/개발용)
    - API 키 없거나 오류 시 경고 로그 출력 후 원문 반환 (절대 크래시하지 않음)
    - 빈 문자열 또는 None 입력 시 빈 문자열 반환
    - 캐시 히트 시 API 호출 생략
    """
    if not text:
        return ''

    provider = os.getenv('TRANSLATE_PROVIDER', 'deepl').lower()

    if provider == 'none':
        return text

    cache_key = (text, source_lang.upper(), target_lang.upper())
    if cache_key in _cache:
        return _cache[cache_key]

    if provider == 'deepl':
        result = _deepl_translate(text, source_lang, target_lang)
    else:
        logger.warning('알 수 없는 TRANSLATE_PROVIDER=%s, 원문 반환', provider)
        result = text

    _cache[cache_key] = result
    return result


def _deepl_translate(text: str, source_lang: str, target_lang: str) -> str:
    """DeepL API를 호출하여 번역 결과를 반환한다."""
    api_key = os.getenv('DEEPL_API_KEY', '')
    if not api_key:
        logger.warning('DEEPL_API_KEY가 설정되지 않았습니다. 원문을 반환합니다.')
        return text

    api_url = os.getenv('DEEPL_API_URL', _DEEPL_DEFAULT_URL)
    try:
        response = requests.post(
            api_url,
            data={
                'auth_key': api_key,
                'text': text,
                'source_lang': source_lang.upper(),
                'target_lang': target_lang.upper(),
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data['translations'][0]['text']
    except requests.exceptions.HTTPError as exc:
        logger.warning('DeepL API HTTP 오류 (%s), 원문 반환: %s', exc.response.status_code, exc)
    except requests.exceptions.RequestException as exc:
        logger.warning('DeepL API 요청 실패, 원문 반환: %s', exc)
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning('DeepL 응답 파싱 실패, 원문 반환: %s', exc)
    return text


# ── 언어쌍별 편의 함수 ────────────────────────────────────────

def ja_to_ko(text: str) -> str:
    """일본어 → 한국어 (포터 상품명)"""
    return translate(text, 'JA', 'KO')


def fr_to_ko(text: str) -> str:
    """프랑스어 → 한국어 (메모파리 상품명)"""
    return translate(text, 'FR', 'KO')


def ko_to_en(text: str) -> str:
    """한국어 → 영어 (Shopify 글로벌 판매)"""
    return translate(text, 'KO', 'EN')


def ko_to_ja(text: str) -> str:
    """한국어 → 일본어 (일본 수출용)"""
    return translate(text, 'KO', 'JA')


def ko_to_en_if_needed(text_ko: str) -> str:
    """하위호환용. 내부적으로 ko_to_en() 호출."""
    return ko_to_en(text_ko)
