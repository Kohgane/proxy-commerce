"""src/security/ip_filter.py — IP 필터."""
from __future__ import annotations

import ipaddress


class IPFilter:
    """IP 화이트리스트/블랙리스트 필터."""

    def __init__(self) -> None:
        self._whitelist: list[str] = []
        self._blacklist: list[str] = []

    def add_whitelist(self, ip: str) -> None:
        """IP를 화이트리스트에 추가한다."""
        if ip not in self._whitelist:
            self._whitelist.append(ip)

    def add_blacklist(self, ip: str) -> None:
        """IP를 블랙리스트에 추가한다."""
        if ip not in self._blacklist:
            self._blacklist.append(ip)

    def remove_whitelist(self, ip: str) -> None:
        """IP를 화이트리스트에서 제거한다."""
        if ip in self._whitelist:
            self._whitelist.remove(ip)

    def remove_blacklist(self, ip: str) -> None:
        """IP를 블랙리스트에서 제거한다."""
        if ip in self._blacklist:
            self._blacklist.remove(ip)

    def _matches(self, ip: str, network_str: str) -> bool:
        """IP가 네트워크 범위에 속하는지 확인한다 (CIDR 지원)."""
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(network_str, strict=False)
        except ValueError:
            return ip == network_str

    def is_allowed(self, ip: str) -> bool:
        """IP의 접근 허용 여부를 반환한다."""
        for blacklisted in self._blacklist:
            if self._matches(ip, blacklisted):
                return False
        if self._whitelist:
            return any(self._matches(ip, allowed) for allowed in self._whitelist)
        return True

    def get_lists(self) -> dict:
        """화이트리스트와 블랙리스트를 반환한다."""
        return {
            "whitelist": list(self._whitelist),
            "blacklist": list(self._blacklist),
        }
