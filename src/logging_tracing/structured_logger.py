"""src/logging_tracing/structured_logger.py — 구조화된 로거."""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class StructuredLogger:
    """JSON 형식으로 구조화된 로그 출력."""

    def get_log_record(
        self,
        level: str,
        message: str,
        service: str = 'proxy-commerce',
        trace_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> dict:
        record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': level.upper(),
            'message': message,
            'service': service,
        }
        if trace_id:
            record['trace_id'] = trace_id
        if extra:
            record.update(extra)
        return record

    def log(
        self,
        level: str,
        message: str,
        service: str = 'proxy-commerce',
        trace_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> dict:
        record = self.get_log_record(level, message, service, trace_id, extra)
        print(json.dumps(record, ensure_ascii=False), file=sys.stderr)
        return record
