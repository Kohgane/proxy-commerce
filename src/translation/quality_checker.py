"""번역 품질 검사기."""

import logging
import re

logger = logging.getLogger(__name__)

_FORBIDDEN_WORDS = ['spam', 'xxx', 'casino']


class QualityChecker:
    """번역 품질 검사."""

    def __init__(self, min_ratio: float = 0.3, max_ratio: float = 3.0):
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio

    def check(self, original: str, translated: str) -> dict:
        """번역 품질 검사.

        Args:
            original: 원본 텍스트
            translated: 번역된 텍스트

        Returns:
            {is_valid: bool, issues: list}
        """
        issues = []

        # 길이 비율 검사
        orig_len = len(original)
        trans_len = len(translated)
        if orig_len > 0:
            ratio = trans_len / orig_len
            if ratio < self.min_ratio:
                issues.append(f'번역이 너무 짧음: 비율 {ratio:.2f} (최소 {self.min_ratio})')
            elif ratio > self.max_ratio:
                issues.append(f'번역이 너무 김: 비율 {ratio:.2f} (최대 {self.max_ratio})')

        # HTML 태그 보존 검사
        orig_tags = set(re.findall(r'<[^>]+>', original))
        trans_tags = set(re.findall(r'<[^>]+>', translated))
        missing_tags = orig_tags - trans_tags
        if missing_tags:
            issues.append(f'누락된 HTML 태그: {missing_tags}')

        # 금지어 검사
        for word in _FORBIDDEN_WORDS:
            if word.lower() in translated.lower():
                issues.append(f'금지어 포함: {word}')

        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
        }
