import re
from pathlib import Path


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "src" / "seller_console" / "templates"
TARGET_NAMES = {
    "_m5_flow.html",
    "_risk_block.html",
    "_coupang_exposure.html",
}


def _target_files():
    return sorted(
        [TEMPLATE_DIR / name for name in TARGET_NAMES if (TEMPLATE_DIR / name).exists()]
        + sorted(TEMPLATE_DIR.glob("mobile_*.html")),
        key=lambda path: str(path),
    )


def _includes(text):
    return set(re.findall(r'{%\s*include\s+["\']([^"\']+)["\']', text))


def _button_roles(text):
    roles = set()
    for match in re.finditer(r"<button\b[^>]*\bdata-role\s*=\s*[\"']([^\"']+)[\"']", text, re.I):
        roles.add(match.group(1))
    return roles


def _handler_for(role, text):
    patterns = (
        rf"\[data-role\s*=\s*[\"']?{re.escape(role)}[\"']?\]",
        rf"getAttribute\([\"']data-role[\"']\)\s*={2,3}\s*[\"']{re.escape(role)}[\"']",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _delegated_for(role, text):
    delegated = set()
    button_pattern = r"<button\b[^>]*\bdata-role\s*=\s*[\"']" + re.escape(role) + r"[\"'][^>]*>"
    for match in re.finditer(button_pattern, text, re.I):
        attrs = match.group(0)
        for marker in ("data-act", "data-override", "data-market-status"):
            if re.search(r"\b" + re.escape(marker) + r"\s*=", attrs):
                delegated.add(marker)

    string_markup_pattern = r"<button\b[^>]*\bdata-role\s*=\s*[\"']" + re.escape(role) + r"[\"'][^>]*>"
    for match in re.finditer(string_markup_pattern, text, re.I):
        attrs = match.group(0)
        for marker in ("data-act", "data-override", "data-market-status"):
            if re.search(r"\b" + re.escape(marker) + r"\s*=", attrs):
                delegated.add(marker)

    return sorted(delegated)


def test_mobile_template_button_roles_have_handlers():
    failures = []
    exceptions = []

    for path in _target_files():
        text = path.read_text(encoding="utf-8")
        include_text = text
        for include_name in _includes(text):
            include_path = TEMPLATE_DIR / include_name
            if include_path.exists():
                include_text += "\n" + include_path.read_text(encoding="utf-8")

        for role in sorted(_button_roles(text)):
            if _handler_for(role, include_text):
                continue

            delegated = sorted(set(_delegated_for(role, include_text)))
            if delegated:
                exceptions.append(f"{path.relative_to(TEMPLATE_DIR)} · {role} · delegated: {', '.join(delegated)}")
            else:
                failures.append(
                    f"{path.relative_to(TEMPLATE_DIR)} · {role} · no data-role selector or data-role getAttribute branch"
                )

    message = ""
    if failures:
        message += "Dead data-role buttons:\n" + "\n".join(failures)
    if exceptions:
        message += ("\n\nDelegated-handler exceptions:\n" if message else "Delegated-handler exceptions:\n")
        message += "\n".join(exceptions)
    assert not failures, message
