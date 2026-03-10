import os
import requests

BOT = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT = os.getenv('TELEGRAM_CHAT_ID')


def send_tele(text: str):
    if not BOT or not CHAT:
        print('[telegram disabled]', text[:200])
        return
    requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", json={"chat_id": CHAT, "text": text}, timeout=15)
