"""src/search/tokenizer.py — 텍스트 토크나이저."""
from __future__ import annotations

import re
from typing import List

# Korean unicode range: AC00-D7A3 (syllables), 1100-11FF, 3130-318F
_KOREAN_RE = re.compile(r"[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]+")
_NON_WORD_RE = re.compile(r"[\s\W]+")


class Tokenizer:
    """텍스트 토크나이저 (한국어 포함)."""

    def tokenize(self, text: str) -> List[str]:
        """텍스트를 토큰 목록으로 변환."""
        tokens: List[str] = []
        # Extract Korean words first
        korean_words = _KOREAN_RE.findall(text)
        tokens.extend(korean_words)
        # Remove Korean chars and split on whitespace/punctuation
        stripped = _KOREAN_RE.sub(" ", text)
        for part in _NON_WORD_RE.split(stripped):
            part = part.lower().strip()
            if part:
                tokens.append(part)
        return [t for t in tokens if t]
