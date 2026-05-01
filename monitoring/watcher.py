"""monitoring/watcher.py — Stock / price change detector.

Covers issue #92: compare a product's current state against a stored snapshot
and emit a ``ChangeEvent`` when values differ.

Typical usage:
    from monitoring.watcher import ProductWatcher, ChangeEvent
    watcher = ProductWatcher(state_path="data/watcher_state.json")
    events = watcher.check(product)
    for e in events:
        print(e)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_STATE_PATH = Path(os.getenv("WATCHER_STATE_PATH", "data/watcher_state.json"))

# Fields we watch for changes
_WATCHED_FIELDS = ("cost_price", "sell_price", "stock_status")


@dataclass
class ChangeEvent:
    """Represents a detected change in a product field."""

    source: str
    source_product_id: str
    field: str
    old_value: Any
    new_value: Any
    title: str = ""

    def __str__(self) -> str:
        return (
            f"[{self.source}] {self.title or self.source_product_id} — "
            f"{self.field}: {self.old_value!r} → {self.new_value!r}"
        )


def _state_key(product: Any) -> str:
    return f"{product.source}:{product.source_product_id}"


def _snapshot(product: Any) -> Dict[str, Any]:
    return {f: getattr(product, f, None) for f in _WATCHED_FIELDS}


class ProductWatcher:
    """Persistent watcher that detects stock / price changes.

    State is stored as JSON on disk (path configurable via ``state_path``).
    Each run loads the previous snapshot, compares it against the current
    product, emits events for any differences, and then saves the new state.

    Parameters
    ----------
    state_path:
        Path to the JSON file used to persist state between runs.
        Created automatically if it does not exist.
    """

    def __init__(self, state_path: Optional[Path] = None) -> None:
        self.state_path = Path(state_path) if state_path else _DEFAULT_STATE_PATH
        self._state: Dict[str, Dict[str, Any]] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, product: Any) -> List[ChangeEvent]:
        """Compare *product* against the stored snapshot.

        Returns a (possibly empty) list of :class:`ChangeEvent` objects.
        Saves the updated snapshot afterwards.
        """
        key = _state_key(product)
        current = _snapshot(product)
        previous = self._state.get(key)

        events: List[ChangeEvent] = []
        if previous is not None:
            for f in _WATCHED_FIELDS:
                old_val = previous.get(f)
                new_val = current.get(f)
                if old_val != new_val:
                    events.append(
                        ChangeEvent(
                            source=product.source,
                            source_product_id=product.source_product_id,
                            field=f,
                            old_value=old_val,
                            new_value=new_val,
                            title=getattr(product, "title", ""),
                        )
                    )
                    logger.info("Change detected: %s", events[-1])
        else:
            logger.debug("[watcher] First-seen product: %s", key)

        self._state[key] = current
        self._save()
        return events

    def check_batch(self, products: List[Any]) -> List[ChangeEvent]:
        """Run :meth:`check` for each product; return all events."""
        all_events: List[ChangeEvent] = []
        for p in products:
            all_events.extend(self.check(p))
        return all_events

    def reset(self, product: Any) -> None:
        """Remove stored snapshot for a product (forces re-baseline on next check)."""
        key = _state_key(product)
        self._state.pop(key, None)
        self._save()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.state_path.exists():
            return {}
        try:
            with self.state_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[watcher] Could not load state from %s: %s — starting fresh", self.state_path, exc)
            return {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.state_path.open("w", encoding="utf-8") as fh:
                json.dump(self._state, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.error("[watcher] Could not save state to %s: %s", self.state_path, exc)
