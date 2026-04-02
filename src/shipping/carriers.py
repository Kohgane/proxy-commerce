"""src/shipping/carriers.py — 택배사 추적 구현 (모의 데이터)."""
import abc
from datetime import datetime, timedelta

from .models import ShipmentRecord, ShipmentStatus, TrackingEvent


class Carrier(abc.ABC):
    """택배사 기본 추상 클래스."""

    @abc.abstractmethod
    def track(self, tracking_number: str) -> ShipmentRecord:
        """운송장 번호로 배송 현황 조회."""


def _make_mock_record(tracking_number: str, carrier_name: str) -> ShipmentRecord:
    now = datetime.utcnow()
    events = [
        TrackingEvent(
            timestamp=now - timedelta(hours=24),
            status=ShipmentStatus.picked_up,
            location="서울 집하센터",
            description="상품이 집하되었습니다.",
        ),
        TrackingEvent(
            timestamp=now - timedelta(hours=12),
            status=ShipmentStatus.in_transit,
            location="대전 중계센터",
            description="간선 상차 완료.",
        ),
        TrackingEvent(
            timestamp=now - timedelta(hours=2),
            status=ShipmentStatus.out_for_delivery,
            location="수신 배송지 근처",
            description="배송 출발.",
        ),
    ]
    return ShipmentRecord(
        tracking_number=tracking_number,
        carrier=carrier_name,
        status=ShipmentStatus.out_for_delivery,
        updated_at=now,
        events=events,
    )


class CJCarrier(Carrier):
    """CJ대한통운 모의 구현."""

    name = "cj"

    def track(self, tracking_number: str) -> ShipmentRecord:
        return _make_mock_record(tracking_number, self.name)


class HanjinCarrier(Carrier):
    """한진택배 모의 구현."""

    name = "hanjin"

    def track(self, tracking_number: str) -> ShipmentRecord:
        return _make_mock_record(tracking_number, self.name)


class KoreaPostCarrier(Carrier):
    """우체국 택배 모의 구현."""

    name = "koreapost"

    def track(self, tracking_number: str) -> ShipmentRecord:
        return _make_mock_record(tracking_number, self.name)


_CARRIER_MAP: dict = {
    "cj": CJCarrier,
    "hanjin": HanjinCarrier,
    "koreapost": KoreaPostCarrier,
}


class CarrierFactory:
    """택배사 인스턴스 팩토리."""

    @staticmethod
    def get_carrier(carrier_name: str) -> Carrier:
        """carrier_name으로 Carrier 인스턴스 반환."""
        cls = _CARRIER_MAP.get(carrier_name.lower())
        if cls is None:
            raise ValueError(f"지원하지 않는 택배사: {carrier_name!r}")
        return cls()
