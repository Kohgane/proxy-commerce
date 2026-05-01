"""cs_automation/renderer.py — CS template renderer with variable substitution.

Covers issue #93: load markdown templates and substitute ``{{variable}}``
placeholders with provided values.

Supported templates (from ``cs_automation/templates/``):
    - return
    - exchange
    - refund
    - delay

Example:
    from cs_automation.renderer import CSRenderer

    renderer = CSRenderer()
    body = renderer.render("return", {
        "customer_name": "홍길동",
        "order_id": "ORD-20240501-001",
        "return_window_days": "30",
        "refund_processing_days": "3",
        "return_address": "서울시 강남구 ...",
        "refund_method": "신용카드 원결제",
        "support_email": "cs@example.com",
        "brand_name": "ProxyCommerce",
    })
    print(body)
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")

AVAILABLE_TEMPLATES = ("return", "exchange", "refund", "delay")


class MissingVariableError(ValueError):
    """Raised when a required template variable is not supplied."""


class TemplateNotFoundError(FileNotFoundError):
    """Raised when the requested template file does not exist."""


class CSRenderer:
    """Loads and renders CS email/message templates.

    Parameters
    ----------
    templates_dir:
        Directory containing ``*.md`` template files.
        Defaults to ``cs_automation/templates/`` relative to this file.
    strict:
        If ``True`` (default), raise :class:`MissingVariableError` when a
        placeholder is not found in *variables*.
        If ``False``, leave unresolved placeholders as-is.
    """

    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        strict: bool = True,
    ) -> None:
        self.templates_dir = Path(templates_dir) if templates_dir else _TEMPLATES_DIR
        self.strict = strict
        self._cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, template_name: str, variables: Dict[str, str]) -> str:
        """Render *template_name* with the given *variables*.

        Parameters
        ----------
        template_name:
            One of ``"return"``, ``"exchange"``, ``"refund"``, ``"delay"``
            (without the ``.md`` extension).
        variables:
            Mapping of placeholder name → replacement value.

        Returns
        -------
        str
            The rendered markdown string.

        Raises
        ------
        TemplateNotFoundError
            If the template file does not exist.
        MissingVariableError
            If ``strict=True`` and a placeholder has no value in *variables*.
        """
        template = self._load(template_name)
        return self._substitute(template, variables, template_name)

    def required_variables(self, template_name: str) -> Set[str]:
        """Return the set of placeholder names in *template_name*."""
        template = self._load(template_name)
        return set(_PLACEHOLDER_RE.findall(template))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self, template_name: str) -> str:
        if template_name in self._cache:
            return self._cache[template_name]

        path = self.templates_dir / f"{template_name}.md"
        if not path.exists():
            raise TemplateNotFoundError(
                f"Template '{template_name}' not found at {path}. "
                f"Available: {AVAILABLE_TEMPLATES}"
            )
        text = path.read_text(encoding="utf-8")
        self._cache[template_name] = text
        logger.debug("[CSRenderer] Loaded template '%s' from %s", template_name, path)
        return text

    def _substitute(self, template: str, variables: Dict[str, str], template_name: str) -> str:
        missing: Set[str] = set()

        def replacer(match: re.Match) -> str:
            key = match.group(1)
            if key in variables:
                return str(variables[key])
            missing.add(key)
            return match.group(0)  # keep original placeholder

        rendered = _PLACEHOLDER_RE.sub(replacer, template)

        if missing and self.strict:
            raise MissingVariableError(
                f"Template '{template_name}' has unresolved placeholders: {sorted(missing)}"
            )
        if missing:
            logger.warning(
                "[CSRenderer] Template '%s' has unresolved placeholders: %s",
                template_name,
                sorted(missing),
            )

        return rendered
