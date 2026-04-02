"""src/coupons/code_generator.py — Phase 38: 쿠폰 코드 생성기."""
import random
import string
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

_CHARS = string.ascii_uppercase + string.digits
# 혼동하기 쉬운 문자 제거
_SAFE_CHARS = ''.join(c for c in _CHARS if c not in 'O0I1')


class CodeGenerator:
    """랜덤 쿠폰 코드 생성기.

    - 8~16자 랜덤 코드
    - 접두사 지원 (SUMMER-XXXX)
    - 일괄 생성
    """

    def __init__(self, length: int = 8, safe_chars: bool = True):
        self.length = length
        self._chars = _SAFE_CHARS if safe_chars else _CHARS

    def generate(self, prefix: Optional[str] = None) -> str:
        """단일 코드 생성."""
        code = ''.join(random.choices(self._chars, k=self.length))
        if prefix:
            return f"{prefix.upper()}-{code}"
        return code

    def generate_batch(self, count: int, prefix: Optional[str] = None) -> List[str]:
        """여러 코드 일괄 생성 (중복 없음)."""
        codes = set()
        attempts = 0
        max_attempts = count * 10
        while len(codes) < count and attempts < max_attempts:
            codes.add(self.generate(prefix))
            attempts += 1
        result = list(codes)[:count]
        logger.info("쿠폰 코드 %d개 생성 (prefix=%s)", len(result), prefix)
        return result

    def generate_seasonal(self, season: str, year: int, count: int = 1) -> List[str]:
        """시즌 코드 생성 (예: SUMMER2024-XXXX)."""
        prefix = f"{season.upper()}{year}"
        return self.generate_batch(count, prefix=prefix)
