"""src/backup/backup_strategy.py — 백업 전략 ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BackupStrategy(ABC):
    """백업 전략 기본 클래스."""

    @abstractmethod
    def create(self, data: dict) -> str:
        """데이터를 직렬화하여 백업 문자열 반환."""

    @abstractmethod
    def restore(self, backup_data: str) -> dict:
        """백업 문자열을 역직렬화하여 데이터 반환."""
