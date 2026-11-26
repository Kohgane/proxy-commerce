from __future__ import annotations

import re
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "src" / "seller_console" / "templates"
MOBILE_TEMPLATES = (
    "_m5_flow.html",
    "_risk_block.html",
    "mobile_home.html",
    "mobile_list_flow.html",
    "_coupang_exposure.html",
)


def _tags(text: str, tag: str) -> list[str]:
    return re.findall(rf"<{tag}\b[^>]*>", text, flags=re.IGNORECASE)


def test_mobile_templates_exist() -> None:
    for name in MOBILE_TEMPLATES:
        assert (TEMPLATE_DIR / name).is_file(), f"{name} missing"


def test_mobile_templates_have_no_empty_link_targets() -> None:
    for name in MOBILE_TEMPLATES:
        text = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
        for tag in _tags(text, "a"):
            assert not re.search(r"""href\s*=\s*["'](?:#|javascript:(?:void)?\(0\))["']""", tag, re.IGNORECASE), (
                f"{name}: empty or JavaScript-only link: {tag}"
            )


def test_mobile_buttons_have_an_action_contract() -> None:
    for name in MOBILE_TEMPLATES:
        text = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
        for tag in _tags(text, "button"):
            compact = re.sub(r"\s+", " ", tag)
            has_type_submit = re.search(r"""type\s*=\s*["']submit["']""", compact, re.IGNORECASE)
            has_contract = (
                re.search(r"\b(?:id|onclick|data-role|data-mode)\s*=", compact, re.IGNORECASE)
                or has_type_submit
            )
            assert has_contract, f"{name}: button without id, onclick, submit type, or data-role: {compact}"
