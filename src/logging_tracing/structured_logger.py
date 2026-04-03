"""src/logging_tracing/structured_logger.py — JSON 형식 구조화 로그."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, IO, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class StructuredLogger:
    """JSON 형식 로그 출력 (timestamp, level, service, trace_id, message, extra)."""

    def __init__(self, service: str = "proxy-commerce",
                 output: IO = None,
                 min_level: str = "DEBUG") -> None:
        self.service = service
        self.output = output or sys.stdout
        self._levels = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        self.min_level = min_level

    def _log(self, level: str, message: str, trace_id: str = "",
             span_id: str = "", **extra) -> dict:
        if self._levels.get(level, 0) < self._levels.get(self.min_level, 0):
            return {}
        entry = {
            "timestamp": _now_iso(),
            "level": level,
            "service": self.service,
            "trace_id": trace_id,
            "span_id": span_id,
            "message": message,
            **extra,
        }
        print(json.dumps(entry, ensure_ascii=False, default=str), file=self.output)
        return entry

    def debug(self, message: str, **kwargs) -> dict:
        return self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs) -> dict:
        return self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs) -> dict:
        return self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs) -> dict:
        return self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs) -> dict:
        return self._log("CRITICAL", message, **kwargs)
