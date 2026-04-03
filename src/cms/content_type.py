"""src/cms/content_type.py — 콘텐츠 타입 Enum."""
from __future__ import annotations

from enum import Enum


class ContentType(str, Enum):
    page = "page"
    notice = "notice"
    faq = "faq"
    blog = "blog"
    banner = "banner"
