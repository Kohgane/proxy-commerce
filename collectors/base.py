"""collectors/base.py — Base collector pipeline.

Covers issue #86: fetch -> parse -> normalize -> validate pipeline
with failed item logging to logs/failed_items.jsonl.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from schemas.product import Product

logger = logging.getLogger(__name__)

LOGS_DIR = Path(os.getenv("LOGS_DIR", "logs"))
FAILED_ITEMS_LOG = LOGS_DIR / "failed_items.jsonl"


def _ensure_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _log_failed_item(raw: Any, stage: str, error: str) -> None:
    _ensure_logs_dir()
    record = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "stage": stage,
        "error": error,
        "raw": raw if isinstance(raw, (dict, list, str, int, float, bool, type(None))) else str(raw),
    }
    with FAILED_ITEMS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class BaseCollectorPipeline(ABC):
    """Abstract base for source-specific collector pipelines.

    Subclasses implement fetch/parse/normalize; this class handles
    validate and failed-item logging.
    """

    source: str = "unknown"

    # ------------------------------------------------------------------
    # Abstract stages — implement in subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch(self, source_id: str) -> Any:
        """Fetch raw data for a single item (HTML, JSON, etc.)."""

    @abstractmethod
    def parse(self, raw: Any) -> Dict[str, Any]:
        """Parse raw response into a plain dict."""

    @abstractmethod
    def normalize(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize parsed dict to Product field names."""

    # ------------------------------------------------------------------
    # Validate stage (common)
    # ------------------------------------------------------------------

    def validate(self, normalized: Dict[str, Any]) -> Optional[Product]:
        """Validate and return a Product, or None on failure."""
        try:
            return Product(**normalized)
        except (ValidationError, TypeError) as exc:
            raise exc

    # ------------------------------------------------------------------
    # Pipeline runner
    # ------------------------------------------------------------------

    def run_one(self, source_id: str) -> Optional[Product]:
        """Run the full pipeline for one item.

        Returns a validated Product on success, None on any stage failure.
        """
        raw = None
        try:
            raw = self.fetch(source_id)
        except Exception as exc:
            logger.error("[%s] fetch failed for %s: %s", self.source, source_id, exc)
            _log_failed_item(source_id, "fetch", str(exc))
            return None

        parsed = None
        try:
            parsed = self.parse(raw)
        except Exception as exc:
            logger.error("[%s] parse failed for %s: %s", self.source, source_id, exc)
            _log_failed_item(raw, "parse", str(exc))
            return None

        normalized = None
        try:
            normalized = self.normalize(parsed)
        except Exception as exc:
            logger.error("[%s] normalize failed for %s: %s", self.source, source_id, exc)
            _log_failed_item(parsed, "normalize", str(exc))
            return None

        try:
            product = self.validate(normalized)
            return product
        except (ValidationError, TypeError) as exc:
            logger.error("[%s] validate failed for %s: %s", self.source, source_id, exc)
            _log_failed_item(normalized, "validate", str(exc))
            return None

    def run_batch(self, source_ids: List[str]) -> List[Product]:
        """Run pipeline for a list of source IDs. Returns only successful products."""
        results: List[Product] = []
        for sid in source_ids:
            product = self.run_one(sid)
            if product is not None:
                results.append(product)
        return results

    def run_batch_report(self, source_ids: List[str]) -> Dict[str, Any]:
        """Run batch and return a dict with success/failed counts."""
        products = self.run_batch(source_ids)
        total = len(source_ids)
        success = len(products)
        return {
            "total": total,
            "success": success,
            "failed": total - success,
            "products": products,
        }
