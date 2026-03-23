"""Post-deployment health check script.

Polls /health and /health/ready endpoints after a deploy and sends a Telegram
notification with the outcome.  Supports configurable retry count and interval.
"""

import argparse
import json
import logging
import os
import sys
import time

import requests

logger = logging.getLogger(__name__)


def send_telegram(text: str) -> None:
    """Send a Telegram message using BOT_TOKEN and CHAT_ID from the environment.

    Args:
        text: Message text to send.
    """
    bot = os.getenv('TELEGRAM_BOT_TOKEN')
    chat = os.getenv('TELEGRAM_CHAT_ID')
    if not bot or not chat:
        logger.info('[telegram disabled] %s', text[:200])
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{bot}/sendMessage',
            json={'chat_id': chat, 'text': text},
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.warning('Telegram notification failed: %s', exc)


def check_endpoint(url: str, retries: int, interval: int) -> tuple[bool, str]:
    """Poll *url* up to *retries* times, waiting *interval* seconds between attempts.

    Args:
        url: Full URL to GET.
        retries: Maximum number of attempts.
        interval: Seconds to wait between attempts.

    Returns:
        Tuple of (success, error_detail).  error_detail is empty on success.
    """
    last_error = ''
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                logger.info('OK %s (attempt %d)', url, attempt)
                return True, ''
            last_error = f'HTTP {resp.status_code} from {url}'
            logger.warning('Attempt %d/%d: %s', attempt, retries, last_error)
        except requests.RequestException as exc:
            last_error = str(exc)
            logger.warning('Attempt %d/%d: %s', attempt, retries, last_error)

        if attempt < retries:
            time.sleep(interval)

    return False, last_error


def run_healthcheck(base_url: str, env: str, retries: int, interval: int) -> tuple[bool, str]:
    """Run health and readiness checks against *base_url*.

    Args:
        base_url: Service base URL (no trailing slash).
        env: Environment label for logging.
        retries: Max attempts per endpoint.
        interval: Seconds between retries.

    Returns:
        Tuple of (all_ok, error_detail).
    """
    base_url = base_url.rstrip('/')

    health_ok, health_err = check_endpoint(f'{base_url}/health', retries, interval)
    if not health_ok:
        return False, f'/health failed: {health_err}'

    ready_ok, ready_err = check_endpoint(f'{base_url}/health/ready', retries, interval)
    if not ready_ok:
        return False, f'/health/ready failed: {ready_err}'

    return True, ''


def main(argv=None):
    """Entry point for CLI usage."""
    parser = argparse.ArgumentParser(description='Post-deploy healthcheck with Telegram notification')
    parser.add_argument('--url', required=True, help='Base URL of the deployed service')
    parser.add_argument('--env', required=True, help='Environment label (staging/production)')
    parser.add_argument('--retries', type=int, default=5, help='Number of retry attempts (default: 5)')
    parser.add_argument('--interval', type=int, default=15, help='Seconds between retries (default: 15)')
    parser.add_argument('--notify-only', action='store_true',
                        help='Skip checks; send success notification only')
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    version = os.getenv('APP_VERSION', 'unknown')

    if args.notify_only:
        msg = f'✅ [{args.env}] 배포 완료 - v{version}, 모든 체크 정상'
        send_telegram(msg)
        logger.info(msg)
        sys.exit(0)

    ok, error_detail = run_healthcheck(args.url, args.env, args.retries, args.interval)

    if ok:
        msg = f'✅ [{args.env}] 배포 완료 - v{version}, 모든 체크 정상'
        send_telegram(msg)
        logger.info(msg)
        sys.exit(0)
    else:
        msg = f'❌ [{args.env}] 배포 실패 - {error_detail}'
        send_telegram(msg)
        logger.error(msg)
        result = {'env': args.env, 'passed': False, 'error': error_detail, 'version': version}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
