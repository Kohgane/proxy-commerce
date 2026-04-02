#!/usr/bin/env python3
"""Send a pip-audit result summary to Telegram."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def send_telegram(token, chat_id, text):
    """Send *text* to a Telegram chat via the Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def build_message(audit_data):
    """Return a human-readable Telegram message from the pip-audit JSON output."""
    # pip-audit --output=json produces {"dependencies": [...], "vulnerabilities": [...]}
    # Older versions may produce a list directly.
    if isinstance(audit_data, list):
        vulns = audit_data
    else:
        vulns = audit_data.get("vulnerabilities", [])

    if not vulns:
        return "✅ Dependency Security Audit: No vulnerabilities found."

    lines = ["⚠️ <b>Dependency Security Audit – vulnerabilities detected</b>", ""]
    for vuln in vulns:
        pkg = vuln.get("name", "unknown")
        installed = vuln.get("version", "?")
        ids = ", ".join(v.get("id", "") for v in vuln.get("vulns", []))
        lines.append(f"• <b>{pkg}</b> {installed} – {ids}")

    lines.append("")
    lines.append(f"Total affected packages: {len(vulns)}")
    return "\n".join(lines)


def main(audit_file):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set – skipping notification.")
        return 0

    with open(audit_file) as fh:
        content = fh.read().strip()

    # pip-audit may write an empty file or non-JSON on success with no vulns.
    try:
        audit_data = json.loads(content) if content else {}
    except json.JSONDecodeError:
        audit_data = {}

    message = build_message(audit_data)
    print(message)

    try:
        send_telegram(token, chat_id, message)
    except urllib.error.URLError as exc:
        print(f"Failed to send Telegram notification: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: notify_audit.py <audit_results.json>", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
