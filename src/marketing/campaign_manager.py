"""src/marketing/campaign_manager.py — 캠페인 관리.

Google Sheets 기반 마케팅 캠페인 저장 및 관리.

환경변수:
  MARKETING_ENABLED     — 마케팅 기능 활성화 여부 (기본 "0")
  MARKETING_SHEET_NAME  — 캠페인 워크시트명 (기본 "campaigns")
  GOOGLE_SHEET_ID       — Google Sheets ID
"""

import datetime
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("MARKETING_ENABLED", "0") == "1"
_SHEET_NAME = os.getenv("MARKETING_SHEET_NAME", "campaigns")
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

_HEADERS = [
    "campaign_id", "name", "type", "target_segment",
    "start_date", "end_date", "status", "budget_krw", "spent_krw", "created_at",
]

# 허용 상태 전환
_TRANSITIONS = {
    "draft": {"active"},
    "active": {"paused", "completed"},
    "paused": {"active"},
    "completed": set(),
}

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore


class CampaignManager:
    """마케팅 캠페인 관리자."""

    def __init__(self, sheet_id: str = "", sheet_name: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID
        self._sheet_name = sheet_name or _SHEET_NAME

    def is_enabled(self) -> bool:
        """마케팅 기능 활성화 여부를 반환한다."""
        return os.getenv("MARKETING_ENABLED", "0") == "1"

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _load(self) -> List[Dict[str, Any]]:
        """Google Sheets에서 캠페인 목록을 로드한다."""
        if open_sheet is None:
            return []
        try:
            ws = open_sheet(self._sheet_id, self._sheet_name)
            records = ws.get_all_records()
            return [dict(r) for r in records]
        except Exception as exc:
            logger.warning("캠페인 로드 실패: %s", exc)
            return []

    def _save_all(self, campaigns: List[Dict[str, Any]]) -> None:
        """캠페인 목록 전체를 Google Sheets에 저장한다."""
        if open_sheet is None:
            return
        try:
            ws = open_sheet(self._sheet_id, self._sheet_name)
            ws.clear()
            ws.append_row(_HEADERS)
            for c in campaigns:
                ws.append_row([str(c.get(h, "")) for h in _HEADERS])
        except Exception as exc:
            logger.warning("캠페인 저장 실패: %s", exc)

    def _append_row(self, campaign: Dict[str, Any]) -> None:
        """단일 캠페인 행을 Google Sheets에 추가한다."""
        if open_sheet is None:
            return
        try:
            ws = open_sheet(self._sheet_id, self._sheet_name)
            # 헤더가 없으면 추가
            existing = ws.get_all_values()
            if not existing:
                ws.append_row(_HEADERS)
            ws.append_row([str(campaign.get(h, "")) for h in _HEADERS])
        except Exception as exc:
            logger.warning("캠페인 행 추가 실패: %s", exc)

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def create_campaign(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """새 캠페인을 생성한다.

        Args:
            data: 캠페인 데이터 딕셔너리.

        Returns:
            생성된 캠페인 딕셔너리.
        """
        campaign: Dict[str, Any] = {
            "campaign_id": str(uuid.uuid4()),
            "name": data.get("name", ""),
            "type": data.get("type", "email"),
            "target_segment": data.get("target_segment", "ALL"),
            "start_date": data.get("start_date", ""),
            "end_date": data.get("end_date", ""),
            "status": "draft",
            "budget_krw": data.get("budget_krw", 0),
            "spent_krw": data.get("spent_krw", 0),
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        self._append_row(campaign)
        logger.info("캠페인 생성: %s (%s)", campaign["name"], campaign["campaign_id"])
        return campaign

    def update_campaign(self, campaign_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """캠페인 정보를 업데이트한다.

        Args:
            campaign_id: 캠페인 ID.
            data: 업데이트할 필드.

        Returns:
            업데이트된 캠페인 딕셔너리 또는 None.
        """
        campaigns = self._load()
        for c in campaigns:
            if c.get("campaign_id") == campaign_id:
                for key, value in data.items():
                    if key in _HEADERS and key not in ("campaign_id", "created_at"):
                        c[key] = value
                self._save_all(campaigns)
                return c
        logger.warning("캠페인을 찾을 수 없음: %s", campaign_id)
        return None

    def _change_status(self, campaign_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        """캠페인 상태를 변경한다."""
        campaigns = self._load()
        for c in campaigns:
            if c.get("campaign_id") == campaign_id:
                current = c.get("status", "draft")
                allowed = _TRANSITIONS.get(current, set())
                if new_status not in allowed:
                    logger.warning(
                        "유효하지 않은 상태 전환: %s → %s (캠페인 %s)",
                        current, new_status, campaign_id,
                    )
                    return None
                c["status"] = new_status
                self._save_all(campaigns)
                return c
        logger.warning("캠페인을 찾을 수 없음: %s", campaign_id)
        return None

    def pause_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """캠페인을 일시 중단한다."""
        return self._change_status(campaign_id, "paused")

    def resume_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """캠페인을 재개한다."""
        return self._change_status(campaign_id, "active")

    def complete_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """캠페인을 완료 처리한다."""
        return self._change_status(campaign_id, "completed")

    def get_campaigns(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """캠페인 목록을 반환한다.

        Args:
            status: 상태 필터 (draft/active/paused/completed). None이면 전체.

        Returns:
            캠페인 딕셔너리 리스트.
        """
        campaigns = self._load()
        if status:
            campaigns = [c for c in campaigns if c.get("status") == status]
        return campaigns

    def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """단일 캠페인을 조회한다.

        Args:
            campaign_id: 캠페인 ID.

        Returns:
            캠페인 딕셔너리 또는 None.
        """
        for c in self._load():
            if c.get("campaign_id") == campaign_id:
                return c
        return None
