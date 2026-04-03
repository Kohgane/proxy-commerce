"""src/ab_testing/variant_assigner.py — 변형 할당."""
import hashlib
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class VariantAssigner:
    """사용자-실험 조합에 일관된 변형 할당."""

    def assign(self, experiment_id: str, user_id: str, variants: List[str]) -> Optional[str]:
        if not variants:
            return None
        key = f"{experiment_id}:{user_id}"
        digest = hashlib.md5(key.encode()).hexdigest()
        index = int(digest, 16) % len(variants)
        return variants[index]
