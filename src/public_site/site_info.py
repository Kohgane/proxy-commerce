"""L1 — 사업자·문의·문서 버전 정보(공개 페이지·콘솔 공통 푸터의 단일 출처).

고정값(오너 제공 2026-10-05): 상호 고가네 · 대표 고우진 · 사업자등록번호 217-21-25749.
env(비면 그 칸을 **숨긴다** — 플레이스홀더·env 이름을 화면에 내지 않음):
  BIZ_MAILORDER_NO(통신판매업신고번호) · BIZ_ADDRESS · CONTACT_EMAIL(없으면 LEGAL_OWNER_EMAIL) · CONTACT_TELEGRAM_URL
  LEGAL_EFFECTIVE_DATE(약관·개인정보 시행일, 기본 2026-10-06) · LEGAL_VERSION(기본 v1.0) · PLAN_FREE_MONTHLY_ITEMS(기본 100)
"""
from __future__ import annotations

import os
from typing import Dict

BIZ_NAME = "고가네"
BIZ_CEO = "고우진"
BIZ_REG_NO = "217-21-25749"
PRIVACY_OFFICER = "고우진"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def contact_email() -> str:
    return _env("CONTACT_EMAIL") or _env("LEGAL_OWNER_EMAIL")


def telegram_url() -> str:
    u = _env("CONTACT_TELEGRAM_URL")
    return u if u.startswith("https://t.me/") else ""


def plan_free_items() -> int:
    try:
        return max(0, int(_env("PLAN_FREE_MONTHLY_ITEMS", "100")))
    except ValueError:
        return 100


def info() -> Dict[str, str]:
    eff = _env("LEGAL_EFFECTIVE_DATE", "2026-10-06")
    ver = _env("LEGAL_VERSION", "v1.0")
    return {"name": BIZ_NAME, "ceo": BIZ_CEO, "reg_no": BIZ_REG_NO, "mailorder_no": _env("BIZ_MAILORDER_NO"),
            "address": _env("BIZ_ADDRESS"), "email": contact_email(), "telegram": telegram_url(),
            "privacy_officer": PRIVACY_OFFICER, "effective_date": eff, "legal_version": ver,
            "legal_label": f"약관·개인정보처리방침 {ver} (시행 {eff})"}
