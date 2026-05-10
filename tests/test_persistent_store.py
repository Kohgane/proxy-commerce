from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_persistent_store_jsonl_roundtrip(tmp_path: Path):
    from src.utils.persistent_store import PersistentStore

    store = PersistentStore(sheet_name="x", fallback_path=tmp_path / "items.jsonl")
    data = [{"id": "1"}, {"id": "2"}]
    store.write_all(data)
    assert store.read_all() == data


def test_persistent_store_replace_failure_keeps_existing(tmp_path: Path, monkeypatch):
    from src.utils.persistent_store import PersistentStore

    path = tmp_path / "items.jsonl"
    store = PersistentStore(sheet_name="x", fallback_path=path)
    store.write_all([{"id": "seed"}])
    original = path.read_text(encoding="utf-8")

    def _raise_replace(src, dst):
        raise OSError("replace fail")

    monkeypatch.setattr("src.utils.persistent_store.os.replace", _raise_replace)
    try:
        store.write_all([{"id": "new"}])
    except OSError:
        pass

    assert path.read_text(encoding="utf-8") == original
