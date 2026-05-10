from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _worker_write_rule(path: str):
    os.environ["PRICING_RULES_FALLBACK_PATH"] = path
    from src.pricing.rule import PricingRule, PricingRuleStore

    store = PricingRuleStore()
    store.create(PricingRule(name="멀티워커 룰"))
    return True


def _worker_read_rule(path: str):
    os.environ["PRICING_RULES_FALLBACK_PATH"] = path
    from src.pricing.rule import PricingRuleStore

    return len(PricingRuleStore().list_all())


def test_pricing_rule_persists_across_multiple_processes(tmp_path: Path):
    path = str(tmp_path / "pricing_rules.jsonl")
    with ProcessPoolExecutor(max_workers=2) as ex:
        assert ex.submit(_worker_write_rule, path).result() is True
        count = ex.submit(_worker_read_rule, path).result()
    assert count >= 1


def test_concurrent_writes_no_corruption(tmp_path: Path):
    from src.utils.persistent_store import PersistentStore

    store = PersistentStore(sheet_name="x", fallback_path=tmp_path / "concurrent.jsonl")

    def _writer(i: int):
        store.write_all([{"seq": i}])

    with ThreadPoolExecutor(max_workers=10) as ex:
        list(ex.map(_writer, range(10)))
    rows = store.read_all()
    assert rows
    assert "seq" in rows[-1]


def test_atomic_write_no_partial_file(tmp_path: Path):
    from src.utils.persistent_store import PersistentStore

    path = tmp_path / "atomic.jsonl"
    store = PersistentStore(sheet_name="x", fallback_path=path)
    store.write_all([{"v": 1}])

    old = path.read_text(encoding="utf-8")
    try:
        from unittest.mock import patch

        with patch("src.utils.persistent_store.os.replace", side_effect=RuntimeError("boom")):
            store.write_all([{"v": 2}])
    except RuntimeError:
        pass

    assert path.read_text(encoding="utf-8") == old
