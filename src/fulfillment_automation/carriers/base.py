"""src/fulfillment_automation/carriers/base.py — 택배사 추상 기반 클래스 (Phase 84)."""
from __future__ import annotations

import abc
from typing import Dict


class CarrierBase(abc.ABC):
    """국내 택배사 추상 기반 클래스."""

    @property
    @abc.abstractmethod
    def carrier_id(self) -> str:
        """택배사 ID."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """택배사 이름."""

    @property
    @abc.abstractmethod
    def base_cost_krw(self) -> int:
        """기본 배송비 (원)."""

    @property
    @abc.abstractmethod
    def avg_delivery_days(self) -> float:
        """평균 배송 일수."""

    @abc.abstractmethod
    def create_waybill(self, order_id: str, recipient: Dict, package_info: Dict) -> Dict:
        """운송장을 생성한다.

        Returns:
            운송장 딕셔너리 (tracking_number, label_url 등 포함)
        """

    @abc.abstractmethod
    def request_pickup(self, tracking_number: str) -> Dict:
        """집하를 요청한다.

        Returns:
            집하 요청 결과 딕셔너리
        """

    @abc.abstractmethod
    def get_tracking(self, tracking_number: str) -> Dict:
        """배송 추적 정보를 조회한다.

        Returns:
            추적 정보 딕셔너리 (status, events 등 포함)
        """
