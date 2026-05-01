"""compliance/seller_whitelist.py — Seller whitelist loader.

Covers issue #91: load a YAML/JSON whitelist of approved sellers and expose
a membership check used by the Taobao gate.

Default whitelist path (override via env var SELLER_WHITELIST_PATH):
    data/seller_whitelist.yml
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import FrozenSet, Optional, Sequence, Union

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(os.getenv("SELLER_WHITELIST_PATH", "data/seller_whitelist.yml"))


def _load_yaml_or_json(path: Path) -> list:
    """Load a YAML or JSON file and return its content as a list."""
    if not path.exists():
        logger.warning("Whitelist file not found: %s — returning empty list", path)
        return []
    with path.open("r", encoding="utf-8") as fh:
        text = fh.read()
    if path.suffix.lower() in {".yml", ".yaml"}:
        data = yaml.safe_load(text) or []
    else:
        data = json.loads(text)
    if not isinstance(data, (list, dict)):
        raise ValueError(f"Whitelist file must contain a list or mapping, got {type(data)}")
    # Support both a bare list of IDs and a dict with a 'sellers' key
    if isinstance(data, dict):
        data = data.get("sellers") or data.get("whitelist") or list(data.keys())
    return data


class SellerWhitelist:
    """Immutable set of approved seller IDs loaded from a YAML/JSON file.

    Parameters
    ----------
    path:
        Path to the whitelist file.  Defaults to ``data/seller_whitelist.yml``.
    extra_ids:
        Optional additional seller IDs to always trust (e.g. hard-coded in code).
    """

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        extra_ids: Optional[Sequence[str]] = None,
    ) -> None:
        resolved_path = Path(path) if path else _DEFAULT_PATH
        raw = _load_yaml_or_json(resolved_path)
        loaded = frozenset(str(s).strip() for s in raw if s)
        extras = frozenset(str(s).strip() for s in (extra_ids or []) if s)
        self._ids: FrozenSet[str] = loaded | extras
        logger.info("SellerWhitelist loaded %d seller IDs from %s", len(self._ids), resolved_path)

    def __contains__(self, seller_id: object) -> bool:
        return str(seller_id) in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    @property
    def ids(self) -> FrozenSet[str]:
        return self._ids

    @classmethod
    def from_ids(cls, ids: Sequence[str]) -> "SellerWhitelist":
        """Construct directly from a sequence of IDs (no file I/O)."""
        obj = cls.__new__(cls)
        obj._ids = frozenset(str(s).strip() for s in ids if s)
        return obj
