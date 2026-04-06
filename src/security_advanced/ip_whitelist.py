"""src/security_advanced/ip_whitelist.py — IP 화이트리스트 관리 (Phase 116)."""
from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class IPEntry:
    ip_address: str
    description: str
    added_by: str
    added_at: datetime
    network: Any = field(repr=False, default=None)  # ipaddress network object


@dataclass
class BlockedAttempt:
    ip_address: str
    timestamp: datetime
    endpoint: str
    reason: str = "not_in_whitelist"


class IPWhitelistManager:
    """IP 화이트리스트 관리자. CIDR 범위 지원."""

    def __init__(self) -> None:
        self._whitelist: Dict[str, IPEntry] = {}  # ip_address -> IPEntry
        self._blocked: List[BlockedAttempt] = []

    # ── 화이트리스트 관리 ─────────────────────────────────────────────────

    def add_ip(self, ip_address: str, description: str = "", added_by: str = "system") -> IPEntry:
        """IPv4/IPv6 또는 CIDR 범위 추가."""
        try:
            network = ipaddress.ip_network(ip_address, strict=False)
        except ValueError as exc:
            raise ValueError(f"유효하지 않은 IP/CIDR: {ip_address}") from exc

        entry = IPEntry(
            ip_address=ip_address,
            description=description,
            added_by=added_by,
            added_at=datetime.now(tz=timezone.utc),
            network=network,
        )
        self._whitelist[ip_address] = entry
        logger.info("IP 화이트리스트 추가: %s (%s)", ip_address, added_by)
        return entry

    def remove_ip(self, ip_address: str) -> None:
        if ip_address not in self._whitelist:
            raise KeyError(f"등록되지 않은 IP: {ip_address}")
        del self._whitelist[ip_address]
        logger.info("IP 화이트리스트 삭제: %s", ip_address)

    def is_allowed(self, ip_address: str) -> bool:
        """화이트리스트가 비어있으면 모두 허용."""
        if not self._whitelist:
            return True
        try:
            addr = ipaddress.ip_address(ip_address)
        except ValueError:
            logger.warning("유효하지 않은 IP 주소: %s", ip_address)
            return False
        for entry in self._whitelist.values():
            if addr in entry.network:
                return True
        return False

    def list_ips(self) -> List[IPEntry]:
        return list(self._whitelist.values())

    # ── 차단 이력 ──────────────────────────────────────────────────────────

    def record_blocked(self, ip_address: str, endpoint: str) -> BlockedAttempt:
        attempt = BlockedAttempt(
            ip_address=ip_address,
            timestamp=datetime.now(tz=timezone.utc),
            endpoint=endpoint,
        )
        self._blocked.append(attempt)
        logger.warning("IP 차단: %s -> %s", ip_address, endpoint)
        return attempt

    def get_blocked_attempts(self) -> List[BlockedAttempt]:
        return list(self._blocked)


class IPFilterMiddleware:
    """Flask before_request IP 필터 미들웨어."""

    def __init__(
        self,
        manager: IPWhitelistManager,
        excluded_paths: Optional[List[str]] = None,
    ) -> None:
        self._manager = manager
        self._excluded = set(excluded_paths or ["/health", "/api/docs"])

    def init_app(self, app: Any) -> None:
        """Flask 앱에 미들웨어 등록."""
        @app.before_request
        def _check_ip() -> Any:
            from flask import request, jsonify
            if request.path in self._excluded:
                return None
            ip = request.remote_addr or ""
            if not self._manager.is_allowed(ip):
                self._manager.record_blocked(ip, request.path)
                return jsonify({"error": "접근 거부: IP 차단됨", "ip": ip}), 403
            return None
