"""src/security_advanced/security_audit.py — 보안 감사 로그 (Phase 116)."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SecurityEvent:
    event_id: str
    event_type: str          # access / auth / permission_change / suspicious
    user_id: Optional[str]
    resource: Optional[str]
    action: Optional[str]
    result: str              # success / failure / blocked
    ip_address: str
    details: Dict[str, Any]
    timestamp: datetime


@dataclass
class SuspiciousActivity:
    user_id: Optional[str]
    ip_address: str
    failure_count: int
    window_minutes: int
    first_occurrence: datetime
    last_occurrence: datetime
    events: List[str]        # event_id 목록


class SecurityAuditLogger:
    """보안 감사 로그 — 접근/인증/권한 변경 이벤트 기록 및 의심 활동 탐지."""

    def __init__(self) -> None:
        self._events: List[SecurityEvent] = []
        self._id_counter = 0

    def _new_id(self) -> str:
        self._id_counter += 1
        return f"sec_{self._id_counter:06d}"

    def _add_event(self, **kwargs: Any) -> SecurityEvent:
        evt = SecurityEvent(
            event_id=self._new_id(),
            timestamp=datetime.now(tz=timezone.utc),
            **kwargs,
        )
        self._events.append(evt)
        return evt

    # ── 이벤트 기록 API ───────────────────────────────────────────────────

    def log_access(
        self,
        user_id: str,
        resource: str,
        action: str,
        result: str,
        ip_address: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> SecurityEvent:
        return self._add_event(
            event_type="access",
            user_id=user_id,
            resource=resource,
            action=action,
            result=result,
            ip_address=ip_address,
            details=details or {},
        )

    def log_auth_event(
        self,
        user_id: str,
        event_type: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
    ) -> SecurityEvent:
        return self._add_event(
            event_type="auth",
            user_id=user_id,
            resource=None,
            action=event_type,
            result="success" if success else "failure",
            ip_address=ip_address,
            details=details or {},
        )

    def log_permission_change(
        self,
        admin_id: str,
        target_user_id: str,
        changes: Dict[str, Any],
        ip_address: str = "",
    ) -> SecurityEvent:
        return self._add_event(
            event_type="permission_change",
            user_id=admin_id,
            resource=f"user:{target_user_id}",
            action="permission_change",
            result="success",
            ip_address=ip_address,
            details={"target_user_id": target_user_id, "changes": changes},
        )

    # ── 이벤트 조회 ───────────────────────────────────────────────────────

    def get_security_events(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        events = self._events[:]
        filters = filters or {}

        if "event_type" in filters:
            events = [e for e in events if e.event_type == filters["event_type"]]
        if "user_id" in filters:
            events = [e for e in events if e.user_id == filters["user_id"]]
        if "result" in filters:
            events = [e for e in events if e.result == filters["result"]]
        if "ip_address" in filters:
            events = [e for e in events if e.ip_address == filters["ip_address"]]
        if "since" in filters:
            since: datetime = filters["since"]
            events = [e for e in events if e.timestamp >= since]

        total = len(events)
        start = (page - 1) * per_page
        end = start + per_page
        page_events = events[start:end]

        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "events": [_event_to_dict(e) for e in page_events],
        }

    # ── 의심 활동 탐지 ────────────────────────────────────────────────────

    def get_suspicious_activity(
        self,
        threshold: int = 10,
        window_minutes: int = 5,
    ) -> List[SuspiciousActivity]:
        """window_minutes 내에 threshold회 이상 실패한 사용자/IP 탐지."""
        now = datetime.now(tz=timezone.utc)
        window_start = now - timedelta(minutes=window_minutes)

        recent_failures = [
            e for e in self._events
            if e.result == "failure" and e.timestamp >= window_start
        ]

        # IP별 그룹화
        by_ip: Dict[str, List[SecurityEvent]] = defaultdict(list)
        for e in recent_failures:
            by_ip[e.ip_address].append(e)

        suspicious: List[SuspiciousActivity] = []
        for ip, evts in by_ip.items():
            if len(evts) >= threshold:
                suspicious.append(SuspiciousActivity(
                    user_id=evts[-1].user_id,
                    ip_address=ip,
                    failure_count=len(evts),
                    window_minutes=window_minutes,
                    first_occurrence=evts[0].timestamp,
                    last_occurrence=evts[-1].timestamp,
                    events=[e.event_id for e in evts],
                ))

        return suspicious


def _event_to_dict(e: SecurityEvent) -> Dict[str, Any]:
    return {
        "event_id": e.event_id,
        "event_type": e.event_type,
        "user_id": e.user_id,
        "resource": e.resource,
        "action": e.action,
        "result": e.result,
        "ip_address": e.ip_address,
        "details": e.details,
        "timestamp": e.timestamp.isoformat(),
    }
