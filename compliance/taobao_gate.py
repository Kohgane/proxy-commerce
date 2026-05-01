"""compliance/taobao_gate.py — Taobao seller trust-score gate.

Covers issue #91: load whitelist + enforce trust score threshold before
allowing a product to be published.

Typical usage:
    from compliance.taobao_gate import TaobaoGate
    gate = TaobaoGate(trust_threshold=0.6)
    result = gate.check(seller_id="TB-123", trust_score=0.75)
    if result.allowed:
        ...  # proceed to publish
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence, Union
from pathlib import Path

from compliance.seller_whitelist import SellerWhitelist

logger = logging.getLogger(__name__)

DEFAULT_TRUST_THRESHOLD = 0.6  # 0–1 scale


@dataclass(frozen=True)
class GateResult:
    """Outcome of a single gate check."""

    allowed: bool
    seller_id: str
    trust_score: float
    reason: str
    whitelisted: bool = False


class TaobaoGate:
    """Gate that combines whitelist membership with a trust score threshold.

    A seller passes if **either**:
    - They are on the whitelist (unconditional trust), OR
    - Their ``trust_score >= trust_threshold``

    Parameters
    ----------
    trust_threshold:
        Minimum trust score required for sellers not on the whitelist.
        Defaults to 0.6.
    whitelist_path:
        Path to the seller whitelist YAML/JSON file. If ``None``, uses the
        default path from :class:`SellerWhitelist`.
    extra_whitelist_ids:
        Hard-coded seller IDs that always pass (merged into whitelist).
    """

    def __init__(
        self,
        trust_threshold: float = DEFAULT_TRUST_THRESHOLD,
        whitelist_path: Optional[Union[str, Path]] = None,
        extra_whitelist_ids: Optional[Sequence[str]] = None,
    ) -> None:
        if not 0.0 <= trust_threshold <= 1.0:
            raise ValueError(f"trust_threshold must be in [0, 1], got {trust_threshold}")
        self.trust_threshold = trust_threshold
        self.whitelist = SellerWhitelist(path=whitelist_path, extra_ids=extra_whitelist_ids)

    # ------------------------------------------------------------------

    def check(self, seller_id: str, trust_score: float) -> GateResult:
        """Evaluate whether the seller is allowed to publish.

        Parameters
        ----------
        seller_id:
            Unique identifier for the Taobao seller.
        trust_score:
            Numeric score in [0.0, 1.0].  Values outside this range are
            clamped with a warning.

        Returns
        -------
        GateResult
        """
        if trust_score < 0.0 or trust_score > 1.0:
            logger.warning(
                "[TaobaoGate] trust_score %.4f out of [0,1] for seller %s — clamping",
                trust_score,
                seller_id,
            )
            trust_score = max(0.0, min(1.0, trust_score))

        whitelisted = seller_id in self.whitelist

        if whitelisted:
            reason = "seller is on whitelist"
            allowed = True
        elif trust_score >= self.trust_threshold:
            reason = f"trust_score {trust_score:.4f} >= threshold {self.trust_threshold:.4f}"
            allowed = True
        else:
            reason = (
                f"trust_score {trust_score:.4f} < threshold {self.trust_threshold:.4f}"
                " and seller is not whitelisted"
            )
            allowed = False

        result = GateResult(
            allowed=allowed,
            seller_id=seller_id,
            trust_score=trust_score,
            reason=reason,
            whitelisted=whitelisted,
        )

        log_fn = logger.info if allowed else logger.warning
        log_fn(
            "[TaobaoGate] seller=%s score=%.4f allowed=%s reason=%s",
            seller_id,
            trust_score,
            allowed,
            reason,
        )
        return result

    def check_product(self, product: object, trust_score: float) -> GateResult:
        """Convenience wrapper that extracts ``source_product_id`` from a Product."""
        seller_id = getattr(product, "source_product_id", str(product))
        return self.check(seller_id=seller_id, trust_score=trust_score)
