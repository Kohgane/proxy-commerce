from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class InboundMessage:
    raw_id: str         # 외부 ID
    customer_id: str
    customer_name: str
    body: str
    received_at: str
    metadata: dict = field(default_factory=dict)  # 채널별 추가 정보

class InboundChannelAdapter(ABC):
    name: str

    @abstractmethod
    def is_active(self) -> bool:
        """환경변수/키 점검."""

    @abstractmethod
    def poll(self, since: str | None = None) -> list[InboundMessage]:
        """주기적 폴링. since 이후 신규 메시지 반환."""

    @abstractmethod
    def send_reply(self, customer_id: str, message: str, *, ref: str = "") -> bool:
        """답변 발송."""
