"""src/security/security_audit.py — 보안 감사 로그."""
from __future__ import annotations

import datetime


class SecurityAudit:
    """보안 감사 로그 관리자."""

    def __init__(self) -> None:
        self._logs: list[dict] = []

    def log_event(
        self,
        event_type: str,
        user_id: str,
        ip: str,
        details: dict | None = None,
    ) -> dict:
        """보안 이벤트를 기록한다."""
        entry = {
            "event_type": event_type,
            "user_id": user_id,
            "ip": ip,
            "details": details or {},
            "logged_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        self._logs.append(entry)
        return entry

    def get_logs(self, event_type: str | None = None, limit: int = 50) -> list:
        """로그 목록을 반환한다."""
        logs = self._logs
        if event_type:
            logs = [l for l in logs if l.get("event_type") == event_type]
        return logs[-limit:]

    def get_suspicious_activity(self) -> list:
        """의심스러운 활동을 반환한다 (같은 IP에서 5회 초과 실패 로그인)."""
        failed: dict[str, int] = {}
        for log in self._logs:
            if log.get("event_type") == "login_failed":
                ip = log.get("ip", "")
                failed[ip] = failed.get(ip, 0) + 1
        return [
            {"ip": ip, "failed_attempts": count}
            for ip, count in failed.items()
            if count > 5
        ]
