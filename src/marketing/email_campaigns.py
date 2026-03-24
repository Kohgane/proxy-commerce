"""src/marketing/email_campaigns.py — 이메일 캠페인 발송.

이메일 캠페인 일괄 발송 및 로그 관리.

환경변수:
  EMAIL_CAMPAIGN_BATCH_SIZE  — 배치 크기 (기본 50)
  EMAIL_CAMPAIGN_DELAY_SEC   — 배치 간 대기 시간 초 (기본 2)
  GOOGLE_SHEET_ID            — Google Sheets ID
"""

import datetime
import logging
import os
import time
from typing import Dict, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

logger = logging.getLogger(__name__)

_BATCH_SIZE = int(os.getenv("EMAIL_CAMPAIGN_BATCH_SIZE", "50"))
_DELAY_SEC = int(os.getenv("EMAIL_CAMPAIGN_DELAY_SEC", "2"))
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
_LOG_SHEET_NAME = "email_campaign_log"

_LOG_HEADERS = ["campaign_id", "email", "sent_at", "success", "subject"]

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore


class EmailCampaignSender:
    """이메일 캠페인 발송 관리자."""

    def __init__(self, sheet_id: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _log_send(self, campaign_id: str, email: str, success: bool, subject: str = "") -> None:
        """발송 결과를 Google Sheets에 기록한다."""
        if open_sheet is None:
            return
        try:
            ws = open_sheet(self._sheet_id, _LOG_SHEET_NAME)
            existing = ws.get_all_values()
            if not existing:
                ws.append_row(_LOG_HEADERS)
            ws.append_row([
                campaign_id, email,
                datetime.datetime.utcnow().isoformat(),
                str(success), subject,
            ])
        except Exception as exc:
            logger.warning("이메일 발송 로그 기록 실패: %s", exc)

    def _generate_tracking_url(self, campaign_id: str, email: str, url: str) -> str:
        """트래킹 UTM 파라미터를 URL에 추가한다."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            params.update({
                "utm_source": ["email"],
                "utm_medium": ["campaign"],
                "utm_campaign": [campaign_id],
                "utm_content": [email],
            })
            new_query = urlencode({k: v[0] for k, v in params.items() if v})
            return urlunparse(parsed._replace(query=new_query))
        except Exception:
            return url

    def _get_sender(self):
        """EmailSender 인스턴스를 반환한다."""
        from ..notifications.email_sender import EmailSender
        return EmailSender()

    def _get_customers_by_segment(self, segment: Optional[str]) -> List[str]:
        """세그먼트에 해당하는 고객 이메일 목록을 반환한다."""
        try:
            from ..crm.customer_profile import CustomerProfileManager
            manager = CustomerProfileManager()
            customers = manager.get_all_customers(segment=segment)
            return [c.get("email", "") for c in customers if c.get("email")]
        except Exception as exc:
            logger.warning("고객 세그먼트 조회 실패: %s", exc)
            return []

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def send_campaign(
        self,
        campaign_id: str,
        subject: str,
        html_body: str,
        text_body: str,
        recipients: List[str],
    ) -> Dict[str, int]:
        """캠페인 이메일을 수신자 목록에 발송한다.

        Args:
            campaign_id: 캠페인 ID.
            subject: 이메일 제목.
            html_body: HTML 본문.
            text_body: 텍스트 본문.
            recipients: 수신자 이메일 목록.

        Returns:
            {"sent": int, "failed": int, "total": int}
        """
        sent = 0
        failed = 0
        total = len(recipients)

        batch_size = int(os.getenv("EMAIL_CAMPAIGN_BATCH_SIZE", str(_BATCH_SIZE)))
        delay_sec = int(os.getenv("EMAIL_CAMPAIGN_DELAY_SEC", str(_DELAY_SEC)))

        for i in range(0, total, batch_size):
            batch = recipients[i:i + batch_size]
            for email in batch:
                try:
                    sender = self._get_sender()
                    sender.send(to=email, subject=subject, html_body=html_body, text_body=text_body)
                    self._log_send(campaign_id, email, True, subject)
                    sent += 1
                except Exception as exc:
                    logger.error("이메일 발송 실패 (%s): %s", email, exc)
                    self._log_send(campaign_id, email, False, subject)
                    failed += 1

            if i + batch_size < total:
                time.sleep(delay_sec)

        logger.info("캠페인 %s 발송 완료: 성공 %d / 실패 %d / 전체 %d", campaign_id, sent, failed, total)
        return {"sent": sent, "failed": failed, "total": total}

    def send_segment_campaign(
        self,
        campaign_id: str,
        segment: Optional[str],
        subject: str,
        html_body: str,
    ) -> Dict[str, int]:
        """세그먼트 기반 캠페인 이메일을 발송한다.

        Args:
            campaign_id: 캠페인 ID.
            segment: 대상 세그먼트 (None이면 전체).
            subject: 이메일 제목.
            html_body: HTML 본문.

        Returns:
            {"sent": int, "failed": int, "total": int}
        """
        recipients = self._get_customers_by_segment(segment)
        return self.send_campaign(
            campaign_id=campaign_id,
            subject=subject,
            html_body=html_body,
            text_body="",
            recipients=recipients,
        )
