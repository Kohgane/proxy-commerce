"""src/disputes/evidence.py — 증거 자료 관리 (Phase 91).

분쟁에 첨부된 증거 자료(파일, 스크린샷, 대화 기록 등)를 관리한다.
분쟁당 최대 증거 수: 10개
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_EVIDENCE_PER_DISPUTE = 10


class EvidenceType(str, Enum):
    """증거 유형."""

    SCREENSHOT = "screenshot"
    PHOTO = "photo"
    CHAT_LOG = "chat_log"
    TRACKING_INFO = "tracking_info"
    INVOICE = "invoice"


@dataclass
class Evidence:
    """증거 엔티티."""

    evidence_id: str
    dispute_id: str
    evidence_type: EvidenceType
    file_name: str
    file_type: str
    file_size: int
    description: str = ""
    uploaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    url: str = ""

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "evidence_id": self.evidence_id,
            "dispute_id": self.dispute_id,
            "evidence_type": self.evidence_type.value,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "description": self.description,
            "uploaded_at": self.uploaded_at,
            "url": self.url,
        }


class EvidenceCollector:
    """분쟁 증거 자료 수집 및 관리."""

    def __init__(self) -> None:
        # dispute_id → List[Evidence]
        self._store: Dict[str, List[Evidence]] = {}

    def add(
        self,
        dispute_id: str,
        evidence_type: str,
        file_name: str,
        file_type: str = "application/octet-stream",
        file_size: int = 0,
        description: str = "",
        url: str = "",
    ) -> Evidence:
        """증거 자료를 추가한다.

        Args:
            dispute_id: 분쟁 ID
            evidence_type: 증거 유형 (EvidenceType 문자열)
            file_name: 파일명
            file_type: MIME 타입
            file_size: 파일 크기 (bytes)
            description: 설명
            url: 파일 URL

        Returns:
            생성된 Evidence 객체

        Raises:
            ValueError: 유효하지 않은 증거 유형이거나 최대 개수 초과 시
        """
        try:
            etype = EvidenceType(evidence_type)
        except ValueError:
            raise ValueError(f"유효하지 않은 증거 유형: {evidence_type}")

        existing = self._store.get(dispute_id, [])
        if len(existing) >= MAX_EVIDENCE_PER_DISPUTE:
            raise ValueError(
                f"분쟁당 최대 {MAX_EVIDENCE_PER_DISPUTE}개의 증거만 첨부할 수 있습니다."
            )

        evidence = Evidence(
            evidence_id=str(uuid.uuid4()),
            dispute_id=dispute_id,
            evidence_type=etype,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            description=description,
            url=url,
        )
        self._store.setdefault(dispute_id, []).append(evidence)
        logger.info("증거 추가: %s (dispute=%s)", evidence.evidence_id, dispute_id)
        return evidence

    def list(self, dispute_id: str) -> List[Evidence]:
        """분쟁의 증거 목록을 반환한다."""
        return list(self._store.get(dispute_id, []))

    def get(self, dispute_id: str, evidence_id: str) -> Optional[Evidence]:
        """특정 증거를 조회한다."""
        for ev in self._store.get(dispute_id, []):
            if ev.evidence_id == evidence_id:
                return ev
        return None

    def delete(self, dispute_id: str, evidence_id: str) -> bool:
        """증거를 삭제한다.

        Returns:
            삭제 성공 여부
        """
        items = self._store.get(dispute_id, [])
        before = len(items)
        self._store[dispute_id] = [ev for ev in items if ev.evidence_id != evidence_id]
        deleted = len(self._store[dispute_id]) < before
        if deleted:
            logger.info("증거 삭제: %s (dispute=%s)", evidence_id, dispute_id)
        return deleted

    def count(self, dispute_id: str) -> int:
        """분쟁의 증거 개수를 반환한다."""
        return len(self._store.get(dispute_id, []))

    def has_photo_evidence(self, dispute_id: str) -> bool:
        """분쟁에 사진 증거가 있는지 확인한다."""
        return any(
            ev.evidence_type in (EvidenceType.PHOTO, EvidenceType.SCREENSHOT)
            for ev in self._store.get(dispute_id, [])
        )
