from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class FaqItem:
    faq_id: str
    keyword: str
    answer: str
    locale: str = "ko"
    source: str = "jsonl"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "FaqItem":
        return cls(
            faq_id=str(payload.get("faq_id") or ""),
            keyword=str(payload.get("keyword") or ""),
            answer=str(payload.get("answer") or ""),
            locale=str(payload.get("locale") or "ko"),
            source=str(payload.get("source") or "jsonl"),
        )

