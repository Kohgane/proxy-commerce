import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import requests

BOT = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT = os.getenv('TELEGRAM_CHAT_ID')


def send_tele(text: str):
    if not BOT or not CHAT:
        print('[telegram disabled]', text[:200])
        return
    requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", json={"chat_id": CHAT, "text": text}, timeout=15)


def send_fx_summary(current_rates: dict, previous_rates: dict = None):
    """환율 업데이트 후 텔레그램 요약 발송.

    Args:
        current_rates: FXProvider.get_rates() 반환값
            {'USDKRW': Decimal, 'JPYKRW': Decimal, 'EURKRW': Decimal, 'CNYKRW': Decimal, ...}
        previous_rates: 이전 환율 (변동률 계산용, 없으면 변동률 생략)
    """
    if not BOT or not CHAT:
        return

    alert_pct = float(os.getenv('FX_CHANGE_ALERT_PCT', '3.0'))
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst).strftime('%Y-%m-%d %H:%M KST')
    provider = current_rates.get('provider', 'unknown')

    pairs = [
        ('USDKRW', '🇺🇸', '달러', '$/'),
        ('JPYKRW', '🇯🇵', '엔', '¥/'),
        ('CNYKRW', '🇨🇳', '위안', '元/'),
        ('EURKRW', '🇪🇺', '유로', '€/'),
    ]

    has_alert = False
    lines = []

    for pair, flag, name, symbol in pairs:
        rate = current_rates.get(pair)
        if rate is None:
            continue

        rate_f = float(rate)

        # 환율 표시
        if pair == 'JPYKRW':
            rate_str = f"{rate_f * 100:,.2f}원/100¥"
        else:
            rate_str = f"{rate_f:,.2f}원/{symbol[0]}"

        # 변동률
        change_str = ""
        if previous_rates and pair in previous_rates:
            prev_f = float(previous_rates[pair])
            if prev_f > 0:
                change = ((rate_f - prev_f) / prev_f) * 100
                if change > 0:
                    arrow = "📈"
                    change_str = f" {arrow} +{change:.2f}%"
                elif change < 0:
                    arrow = "📉"
                    change_str = f" {arrow} {change:.2f}%"
                else:
                    change_str = " ➖"

                if abs(change) >= alert_pct:
                    has_alert = True
                    change_str += " ⚠️"

        lines.append(f"{flag} {name}: {rate_str}{change_str}")

    if has_alert:
        header = f"🚨 환율 급변 알림\n📅 {now_kst}"
    else:
        header = f"💱 환율 업데이트\n📅 {now_kst}"

    body = "\n".join(lines)
    footer = f"[{provider}] 급변 기준: ±{alert_pct}%"
    msg = f"{header}\n\n{body}\n\n{footer}"

    send_tele(msg)
