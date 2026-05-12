from __future__ import annotations

import os


def get_brand_name() -> str:
    return (os.getenv("BRAND_NAME") or "Proxy Commerce").strip() or "Proxy Commerce"
