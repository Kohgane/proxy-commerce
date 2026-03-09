"""
src/scrapers/listly_client.py
Listly에서 내보낸 크롤링 데이터(CSV/JSON)를 파이썬 딕셔너리 리스트로 변환하는 모듈.
표준 라이브러리(csv, json)만 사용.
"""

import csv
import io
import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

# 인코딩 폴백 순서 (utf-8-sig를 먼저 시도하여 BOM 자동 제거)
_ENCODINGS = ['utf-8-sig', 'utf-8', 'euc-kr', 'shift_jis']


def _read_text(file_path: str) -> str:
    """파일을 읽을 수 있는 첫 번째 인코딩으로 텍스트 반환."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f'파일을 찾을 수 없습니다: {file_path}')
    for enc in _ENCODINGS:
        try:
            with open(file_path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError(f'지원하는 인코딩으로 파일을 읽을 수 없습니다: {file_path}')


class ListlyLoader:
    """Listly에서 내보낸 크롤링 데이터를 로드하는 클래스."""

    def load_csv(self, file_path: str) -> list:
        """CSV 파일 로드 → 딕셔너리 리스트 반환."""
        logger.info('CSV 로드: %s', file_path)
        text = _read_text(file_path)
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            logger.warning('CSV 파일에 데이터가 없습니다: %s', file_path)
            return []
        logger.info('CSV 로드 완료: %d행', len(rows))
        return rows

    def load_json(self, file_path: str) -> list:
        """JSON 파일 로드 → 딕셔너리 리스트 반환."""
        logger.info('JSON 로드: %s', file_path)
        text = _read_text(file_path)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f'JSON 형식 오류 ({file_path}): {e}') from e
        if isinstance(data, dict):
            # {"items": [...]} 또는 {"data": [...]} 형태 지원
            for key in ('items', 'data', 'rows', 'results'):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                raise ValueError(f'JSON 최상위 객체에서 리스트를 찾을 수 없습니다: {file_path}')
        if not isinstance(data, list):
            raise ValueError(f'JSON 데이터가 리스트 형식이 아닙니다: {file_path}')
        logger.info('JSON 로드 완료: %d행', len(data))
        return data

    def load_from_url(self, url: str) -> list:
        """Listly 공유 URL에서 CSV 데이터 다운로드 후 로드."""
        # SSRF 방지: http/https 스킴만 허용
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            raise ValueError(f'허용되지 않는 URL 스킴: {parsed.scheme!r}. http/https만 지원합니다.')
        logger.info('URL에서 데이터 다운로드: %s', url)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                raw = resp.read()
        except Exception as e:
            raise RuntimeError(f'URL 다운로드 실패 ({url}): {e}') from e

        # 인코딩 감지 폴백
        text = None
        for enc in _ENCODINGS:
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if text is None:
            raise ValueError(f'다운로드한 데이터의 인코딩을 감지할 수 없습니다: {url}')

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        logger.info('URL 로드 완료: %d행', len(rows))
        return rows

    def clean_raw_data(self, rows: list) -> list:
        """원시 데이터 정리: 빈 행 제거, 공백 트림, 기본 유효성 검사."""
        cleaned = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                logger.debug('행 %d 건너뜀: dict가 아님', i)
                continue
            # 모든 값이 빈 문자열이면 빈 행으로 간주
            stripped = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            non_empty_values = [v for v in stripped.values() if v not in (None, '', [])]
            if not non_empty_values:
                logger.debug('행 %d 건너뜀: 빈 행', i)
                continue
            cleaned.append(stripped)
        logger.info('정리 완료: %d → %d행', len(rows), len(cleaned))
        return cleaned
