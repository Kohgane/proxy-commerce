"""src/integrations/integration_connector.py — IntegrationConnector ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod


class IntegrationConnector(ABC):
    """외부 연동 커넥터 추상 기반 클래스."""

    name: str = "base_connector"

    @abstractmethod
    def connect(self) -> bool:
        """연결. 성공 여부 반환."""

    @abstractmethod
    def disconnect(self) -> bool:
        """연결 해제. 성공 여부 반환."""

    @abstractmethod
    def health_check(self) -> dict:
        """연결 상태 확인."""

    @abstractmethod
    def sync(self) -> dict:
        """동기화 실행."""
