"""src/wholesale/application_manager.py — B2B 가입 신청 승인 큐 (Phase 148).

신청 플로우:
  pending → approved / rejected
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)

_APPLICATIONS_PATH = os.getenv(
    "WHOLESALE_APPLICATIONS_PATH", "data/wholesale_applications.jsonl"
)


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class WholesaleApplication:
    application_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    business_name: str = ""
    business_reg_number: str = ""
    contact_email: str = ""
    status: ApplicationStatus = ApplicationStatus.PENDING
    submitted_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    reviewed_at: str | None = None
    reviewer_note: str = ""
    cert_file_path: str = ""  # 사업자등록증 업로드 경로


class WholesaleApplicationManager:
    """B2B 가입 신청 승인 큐."""

    def __init__(self, path: str = _APPLICATIONS_PATH) -> None:
        self._path = path

    @property
    def require_business_cert(self) -> bool:
        return os.getenv("WHOLESALE_REQUIRE_BUSINESS_CERT", "1") == "1"

    def _load(self) -> List[WholesaleApplication]:
        apps: List[WholesaleApplication] = []
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    d["status"] = ApplicationStatus(d.get("status", "pending"))
                    apps.append(WholesaleApplication(**d))
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("wholesale applications 로드 실패: %s", exc)
        return apps

    def _save(self, apps: List[WholesaleApplication]) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                for app in apps:
                    d = asdict(app)
                    d["status"] = app.status.value
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.warning("wholesale applications 저장 실패: %s", exc)

    def submit(self, application: WholesaleApplication) -> WholesaleApplication:
        apps = self._load()
        apps.append(application)
        self._save(apps)
        logger.info("B2B 신청 접수: %s (%s)", application.business_name, application.application_id)
        return application

    def list_applications(
        self, status: ApplicationStatus | None = None
    ) -> List[WholesaleApplication]:
        apps = self._load()
        if status is not None:
            apps = [a for a in apps if a.status == status]
        return apps

    def approve(self, application_id: str, reviewer_note: str = "") -> bool:
        apps = self._load()
        for app in apps:
            if app.application_id == application_id:
                app.status = ApplicationStatus.APPROVED
                app.reviewed_at = datetime.now(timezone.utc).isoformat()
                app.reviewer_note = reviewer_note
                self._save(apps)
                logger.info("B2B 신청 승인: %s", application_id)
                return True
        return False

    def reject(self, application_id: str, reviewer_note: str = "") -> bool:
        apps = self._load()
        for app in apps:
            if app.application_id == application_id:
                app.status = ApplicationStatus.REJECTED
                app.reviewed_at = datetime.now(timezone.utc).isoformat()
                app.reviewer_note = reviewer_note
                self._save(apps)
                logger.info("B2B 신청 거절: %s", application_id)
                return True
        return False

    def count(self, status: ApplicationStatus | None = None) -> int:
        return len(self.list_applications(status=status))

    def summary(self) -> dict:
        return {
            "total": self.count(),
            "pending": self.count(ApplicationStatus.PENDING),
            "approved": self.count(ApplicationStatus.APPROVED),
            "rejected": self.count(ApplicationStatus.REJECTED),
            "require_business_cert": self.require_business_cert,
        }
