from __future__ import annotations
import email
import imaplib
import logging
import os
import re
from datetime import datetime, timezone
from email.header import decode_header
from .base import InboundChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

class EmailImapAdapter(InboundChannelAdapter):
    name = "email_imap"

    def is_active(self) -> bool:
        return bool(
            os.getenv("CS_EMAIL_IMAP_HOST")
            and os.getenv("CS_EMAIL_IMAP_USER")
            and os.getenv("CS_EMAIL_IMAP_PASS")
        )

    def poll(self, since: str | None = None) -> list[InboundMessage]:
        if not self.is_active():
            return []
        host = os.getenv("CS_EMAIL_IMAP_HOST", "")
        port = int(os.getenv("CS_EMAIL_IMAP_PORT", "993"))
        user = os.getenv("CS_EMAIL_IMAP_USER", "")
        passwd = os.getenv("CS_EMAIL_IMAP_PASS", "")
        folder = os.getenv("CS_EMAIL_IMAP_FOLDER", "INBOX")
        messages: list[InboundMessage] = []
        try:
            conn = imaplib.IMAP4_SSL(host, port)
            conn.login(user, passwd)
            conn.select(folder)
            # Build search criteria
            if since:
                try:
                    dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    date_str = dt.strftime("%d-%b-%Y")
                    _, data = conn.search(None, f'(UNSEEN SINCE "{date_str}")')
                except Exception:
                    _, data = conn.search(None, "UNSEEN")
            else:
                _, data = conn.search(None, "UNSEEN")
            ids = data[0].split() if data and data[0] else []
            for uid in ids[:50]:  # max 50 per poll
                try:
                    _, msg_data = conn.fetch(uid, "(RFC822)")
                    if not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    from_header = msg.get("From", "")
                    customer_name, customer_id = _parse_from(from_header)
                    subject = _decode_header_str(msg.get("Subject", ""))
                    body = _extract_body(msg)
                    if not body:
                        body = subject
                    date_str2 = msg.get("Date", "")
                    received_at = _parse_email_date(date_str2)
                    msg_id = msg.get("Message-ID", uid.decode())
                    # Extract order number from body/subject
                    order_no = _extract_order_no(body + " " + subject)
                    messages.append(InboundMessage(
                        raw_id=str(msg_id),
                        customer_id=customer_id,
                        customer_name=customer_name,
                        body=body,
                        received_at=received_at,
                        metadata={"subject": subject, "order_no": order_no, "source_uid": uid.decode()},
                    ))
                except Exception as exc:
                    logger.warning("email_imap 메시지 파싱 실패: %s", exc)
            conn.logout()
        except Exception as exc:
            logger.warning("email_imap 폴링 실패: %s", exc)
        return messages

    def send_reply(self, customer_id: str, message: str, *, ref: str = "") -> bool:
        if not self.is_active():
            return False
        # Try Resend first
        resend_key = os.getenv("RESEND_API_KEY", "")
        from_email = os.getenv("CS_EMAIL_FROM", os.getenv("CS_EMAIL_IMAP_USER", ""))
        if resend_key and from_email:
            try:
                import requests
                resp = requests.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                    json={"from": from_email, "to": [customer_id], "subject": "CS 답변", "text": message},
                    timeout=8,
                )
                return resp.ok
            except Exception as exc:
                logger.warning("email_imap Resend 발송 실패: %s", exc)
        # SMTP fallback
        smtp_host = os.getenv("CS_SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("CS_SMTP_PORT", "587"))
        smtp_user = os.getenv("CS_EMAIL_IMAP_USER", "")
        smtp_pass = os.getenv("CS_EMAIL_IMAP_PASS", "")
        if not (smtp_user and smtp_pass and from_email):
            return False
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(message, "plain", "utf-8")
            msg["From"] = from_email
            msg["To"] = customer_id
            msg["Subject"] = "CS 답변"
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [customer_id], msg.as_string())
            return True
        except Exception as exc:
            logger.warning("email_imap SMTP 발송 실패: %s", exc)
            return False


def _parse_from(from_header: str) -> tuple[str, str]:
    """From 헤더에서 (이름, 이메일) 파싱."""
    from email.utils import parseaddr
    name, addr = parseaddr(from_header)
    name = _decode_header_str(name) or addr.split("@")[0] if addr else "고객님"
    return name or "고객님", addr or from_header


def _decode_header_str(value: str) -> str:
    if not value:
        return ""
    parts = []
    for bstr, charset in decode_header(value):
        if isinstance(bstr, bytes):
            parts.append(bstr.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(bstr))
    return "".join(parts)


def _extract_body(msg) -> str:
    """멀티파트 메시지에서 텍스트 본문 추출."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                try:
                    return part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    continue
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            return msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            return ""
    return ""


def _parse_email_date(date_str: str) -> str:
    """이메일 Date 헤더를 ISO8601 변환."""
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _extract_order_no(text: str) -> str:
    """주문번호 패턴 추출."""
    m = re.search(r'(?:주문번호|order[_ ]*no\.?|order[_ ]*id)[:\s#]*([A-Z0-9\-]{6,20})', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'\b([A-Z]{2,4}\d{6,15})\b', text)
    if m:
        return m.group(1)
    return ""
