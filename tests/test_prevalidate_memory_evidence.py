"""Memory evidence must not misattribute overlapping checks or hide incomplete work."""
import sys
from types import ModuleType

import pytest

from src.utils import prevalidate_memory as M


@pytest.fixture
def readings(monkeypatch):
    current = {"worker_mb": 100, "instance_mb": 150}
    monkeypatch.setattr(M, "_snapshot", lambda: dict(current))
    return current


def test_parallel_checks_are_marked_on_both_intervals(readings):
    probe = M.BatchProbe()
    first = probe.start("elevenst")
    second = probe.start("woocommerce")
    readings.update(worker_mb=180, instance_mb=230)
    probe.finish(first, "returned")
    report = probe.report()
    assert report["unfinished"] == 1
    assert all(row["overlap"] for row in report["checks"])
    assert report["checks"][1]["status"] == "running"
    assert "after" not in report["checks"][1]
    assert report["delta"]["worker_mb"] == 80
    assert "process-wide" in report["scope"]
    probe.finish(second, "error")
    assert report["checks"][1]["status"] == "running"  # record is a snapshot
    assert probe.report()["unfinished"] == 0


def test_unknown_memory_is_not_zero_growth(readings):
    readings.update(worker_mb=-1, instance_mb=-1)
    probe = M.BatchProbe()
    row = probe.start("elevenst")
    readings.update(worker_mb=120, instance_mb=180)
    probe.finish(row, "returned")
    assert probe.report()["delta"] == {"worker_mb": None, "instance_mb": None}
    assert probe.report()["checks"][0]["delta"]["worker_mb"] is None


def test_bounds_and_new_import_names_only(monkeypatch, readings):
    probe = M.BatchProbe()
    for i in range(M.MAX_ROWS + 3):
        row = probe.start("elevenst")
        probe.finish(row, "returned")
    for i in range(M.MAX_MODULES + 5):
        mod = ModuleType(f"probe_fixture_{i}.child")
        mod.secret = "must not be recorded"
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    report = probe.report()
    assert len(report["checks"]) == M.MAX_ROWS
    assert report["omitted_checks"] == 3
    assert report["unfinished"] == 0
    assert len(report["new_module_roots"]) == M.MAX_MODULES
    assert report["omitted_module_roots"] >= 5
    assert "must not be recorded" not in str(report)


def test_off_switch_and_probe_failure_do_not_block(monkeypatch, readings):
    monkeypatch.setenv("MEMPROBE", "0")
    assert M.begin() is None
    monkeypatch.setenv("MEMPROBE", "1")
    monkeypatch.setattr(M, "_snapshot", lambda: (_ for _ in ()).throw(OSError("unavailable")))
    assert M.begin() is None
    M.record(None, "job")


def test_failed_start_does_not_decrement_other_running_check(monkeypatch, readings):
    probe = M.BatchProbe()
    row = probe.start("elevenst")
    with monkeypatch.context() as scoped:
        scoped.setattr(M, "_snapshot", lambda: (_ for _ in ()).throw(OSError()))
        failed = probe.start("woocommerce")
    probe.finish(failed, "returned")
    assert probe.report()["unfinished"] == 1
    probe.finish(row, "returned")


def test_market_runner_records_success_and_exception_without_changing_results(monkeypatch, readings):
    import time
    from src.seller_console import views as V
    from src.seller_console.upload_dispatcher import PrevalidationResult
    from src.utils import render_worker

    monkeypatch.setenv("MEMPROBE", "1")
    saved = []
    monkeypatch.setattr(render_worker, "record", lambda kind, **row: saved.append((kind, row)))
    monkeypatch.setattr(V, "_pv_update", lambda *a, **kw: None)
    monkeypatch.setattr(V, "_pv_dict", lambda row, rc: {"market": row.market, "ok": row.ok})

    class Dispatcher:
        def prevalidate(self, data, markets):
            if markets == ["elevenst"]:
                raise RuntimeError("fixture failure")
            return [PrevalidationResult(market=markets[0], ok=True, message="ok")]

    result = V._pv_run_markets("job123456", {}, ["elevenst", "woocommerce"],
                               Dispatcher(), None, time.time() + 5)
    assert [r.market for r in result] == ["woocommerce"]
    assert len(saved) == 1 and saved[0][0] == "pv_markets"
    report = saved[0][1]
    assert report["job"] == "job12345"
    assert report["unfinished"] == 0
    assert {r["market"]: r["status"] for r in report["checks"]} == {
        "elevenst": "error", "woocommerce": "returned"}
    assert "fixture failure" not in str(report)


def test_persistence_failure_is_nonfatal(monkeypatch, readings):
    from src.utils import render_worker
    monkeypatch.setattr(render_worker, "record", lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    M.record(M.BatchProbe(), "job")
