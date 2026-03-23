"""텔레그램 봇 메인 핸들러 — Flask webhook receiver."""

import hashlib
import hmac
import logging
import os

from flask import Blueprint, request, jsonify

from .commands import cmd_status, cmd_revenue, cmd_stock, cmd_fx, cmd_help
from .formatters import format_message

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
WEBHOOK_SECRET = os.getenv('TELEGRAM_BOT_WEBHOOK_SECRET', '')
BOT_COMMANDS_ENABLED = os.getenv('BOT_COMMANDS_ENABLED', '1') == '1'

# 지원 커맨드 → 핸들러 매핑
_COMMAND_MAP = {
    '/status': lambda _args: cmd_status(),
    '/revenue': lambda args: cmd_revenue(args[0] if args else 'today'),
    '/stock': lambda args: cmd_stock(args[0] if args else 'low'),
    '/fx': lambda _args: cmd_fx(),
    '/help': lambda _args: cmd_help(),
}


def _verify_secret(token: str) -> bool:
    """TELEGRAM_BOT_WEBHOOK_SECRET으로 요청 검증."""
    if not WEBHOOK_SECRET:
        return True  # 시크릿 미설정 시 모든 요청 허용
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, token)


def _send_reply(chat_id: int, text: str) -> None:
    """텔레그램 메시지 발송."""
    import requests as req_lib
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN 미설정 — 메시지 전송 건너뜀")
        return
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown',
    }
    try:
        resp = req_lib.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("텔레그램 메시지 전송 실패: %s", exc)


def _dispatch(text: str) -> str:
    """커맨드 파서 + 디스패처.

    '/revenue week' → cmd_revenue('week') 호출
    미지원 커맨드 → 도움말 반환
    """
    parts = text.strip().split()
    if not parts:
        return format_message('error', '빈 메시지입니다.')

    command = parts[0].lower()
    # '@봇명' 형태 커맨드 처리 (/status@MyBot → /status)
    if '@' in command:
        command = command.split('@')[0]
    args = parts[1:]

    handler = _COMMAND_MAP.get(command)
    if handler is None:
        return format_message('error', f'알 수 없는 커맨드: {command}\n\n') + cmd_help()

    try:
        return handler(args)
    except Exception as exc:
        logger.error("커맨드 '%s' 처리 중 오류: %s", command, exc)
        return format_message('error', f'명령 처리 중 오류가 발생했습니다: {exc}')


def create_bot_blueprint() -> Blueprint:
    """Flask Blueprint 생성 — /webhook/telegram 엔드포인트 등록."""
    bp = Blueprint('bot', __name__)

    @bp.route('/webhook/telegram', methods=['POST'])
    def telegram_webhook():
        """텔레그램 webhook 수신 엔드포인트."""
        if not BOT_COMMANDS_ENABLED:
            return jsonify({'ok': True, 'note': 'bot disabled'}), 200

        # 선택적 시크릿 검증 (X-Telegram-Bot-Api-Secret-Token 헤더)
        secret_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if WEBHOOK_SECRET and secret_header != WEBHOOK_SECRET:
            logger.warning("webhook 시크릿 불일치 — 요청 거부")
            return jsonify({'ok': False, 'error': 'unauthorized'}), 403

        data = request.get_json(silent=True) or {}
        message = data.get('message') or data.get('edited_message', {})
        if not message:
            return jsonify({'ok': True}), 200

        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')

        if not text.startswith('/'):
            return jsonify({'ok': True}), 200

        reply = _dispatch(text)
        if chat_id:
            _send_reply(chat_id, reply)

        return jsonify({'ok': True}), 200

    return bp
