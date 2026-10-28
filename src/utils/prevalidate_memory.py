"""Bounded evidence for parallel market checks; RSS belongs to the process, not a market.

No collection, cache clearing, tracemalloc, response bodies or product data. A batch
record can locate an interval worth investigating; it cannot attribute allocations
while other threads are running. Timed-out checks are explicitly unfinished.
"""
from __future__ import annotations

import logging
import sys
import threading
import time

from src.utils import rss

logger = logging.getLogger("rss")
MAX_ROWS = 12
MAX_MODULES = 30


def _snapshot():
    return {"worker_mb": rss.read_mb()[0], "instance_mb": rss.instance_mb()}


def _delta(before, after):
    return {k: after[k] - before[k] if before[k] >= 0 and after[k] >= 0 else None
            for k in before}


class BatchProbe:
    def __init__(self):
        self._lock = threading.Lock()
        self._rows = []
        self._total = 0
        self._active = 0
        self._t0 = time.monotonic()
        self._base = _snapshot()
        self._modules = set(sys.modules)

    def start(self, market):
        try:
            snap = _snapshot()
            with self._lock:
                self._total += 1
                self._active += 1
                # Existing checks overlap this one even when they began alone.
                for row in self._rows:
                    if row["status"] == "running":
                        row["overlap"] = True
                row = {"market": str(market)[:64], "start_ms": self._ms(),
                       "before": snap, "status": "running", "overlap": self._active > 1}
                if len(self._rows) < MAX_ROWS:
                    self._rows.append(row)
                return row
        except Exception:
            return None

    def finish(self, row, status):
        if row is None:
            return
        try:
            snap = _snapshot()
            with self._lock:
                self._active = max(0, self._active - 1)
                row.update(after=snap, delta=_delta(row["before"], snap),
                           end_ms=self._ms(), status=status)
        except Exception:
            pass

    def _ms(self):
        return int((time.monotonic() - self._t0) * 1000)

    def report(self):
        end = _snapshot()
        added = set(sys.modules) - self._modules
        # Root names only: bounded output, no module paths or objects retained.
        roots = sorted({name.split(".", 1)[0] for name in added})
        with self._lock:
            rows = [dict(row) for row in self._rows]
            unfinished = self._active
            total = self._total
        return {"scope": "process-wide; concurrent requests may contribute",
                "before": self._base, "after": end, "delta": _delta(self._base, end),
                "elapsed_ms": self._ms(), "checks_started": total,
                "unfinished": unfinished, "checks": rows,
                "omitted_checks": max(0, total - len(rows)),
                "new_module_count": len(added), "new_module_roots": roots[:MAX_MODULES],
                "omitted_module_roots": max(0, len(roots) - MAX_MODULES)}


def begin():
    try:
        from src.utils.memprobe import enabled
        return BatchProbe() if enabled() else None
    except Exception:
        return None


def record(probe, job):
    if probe is None:
        return
    try:
        from src.utils.render_worker import record as persist
        persist("pv_markets", job=job[:8], **probe.report())
    except Exception as exc:
        logger.debug("[RSS] market evidence unavailable: %s", type(exc).__name__)
