"""src/messaging/channels/wechat_channel.py — WeChat 공식계정 채널 (Phase 134).

WECHAT_APP_ID, WECHAT_APP_SECRET 환경변수 필요.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from src.messaging.channels.base import MessageChannel, _dry_run
from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)

# Access token 캐시
_access_token: Optional[str] = None
_token_expires: float = 0.0


def _get_access_token() -> Optional[str]:
    """WeChat Access Token 취득 (캐시 포함)."""
    global _access_token, _token_expires
    if _access_token and time.time() < _token_expires:
        return _access_token

    app_id = os.getenv("WECHAT_APP_ID", "")
    app_secret = os.getenv("WECHAT_APP_SECRET", "")
    if not app_id or not app_secret:
        return None

    try:
        import requests
        resp = requests.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={"grant_type": "client_credential", "appid": app_id, "secret": app_secret},
            timeout=10,
        )
        data = resp.json()
        token = data.get("access_token")
        expires_in = data.get("expires_in", 7200)
        if token:
            _access_token = token
            _token_expires = time.time() + expires_in - 300  # 5분 여유
            return token
    except Exception as exc:
        logger.warning("WeChat access token 취득 오류: %s", exc)
    return None


class WeChatChannel(MessageChannel):
    """WeChat 공식계정 채널."""

    name = "wechat"

    @property
    def is_active(self) -> bool:
        return bool(
            os.getenv("WECHAT_APP_ID") and os.getenv("WECHAT_APP_SECRET")
        )

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        if not self.is_active:
            return SendResult(sent=False, channel=self.name, error="not_configured")

        if not recipient.wechat_openid:
            return SendResult(sent=False, channel=self.name, error="no_wechat_openid")

        token = _get_access_token()
        if not token:
            return SendResult(sent=False, channel=self.name, error="no_access_token")

        try:
            import requests
            payload = {
                "touser": recipient.wechat_openid,
                "msgtype": "text",
                "text": {"content": template_body},
            }
            resp = requests.post(
                f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={token}",
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if data.get("errcode") == 0:
                return SendResult(sent=True, channel=self.name)
            return SendResult(
                sent=False,
                channel=self.name,
                error=f"errcode={data.get('errcode')} {data.get('errmsg', '')}",
            )
        except Exception as exc:
            logger.warning("WeChat 채널 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {
            "name": self.name,
            "status": status,
            "detail": "WECHAT_APP_ID + WECHAT_APP_SECRET",
        }
