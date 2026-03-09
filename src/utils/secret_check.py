"""
환경변수/시크릿 설정 상태 진단 유틸리티.
CI/CD 또는 로컬에서 실행하여 필수 환경변수가 설정되어 있는지 확인.
"""

import os
import logging

logger = logging.getLogger(__name__)

REQUIRED_SECRETS = {
    'core': [
        'GOOGLE_SERVICE_JSON_B64',
        'GOOGLE_SHEET_ID',
    ],
    'shopify': [
        'SHOPIFY_SHOP',
        'SHOPIFY_ACCESS_TOKEN',
        'SHOPIFY_CLIENT_SECRET',
    ],
    'woocommerce': [
        'WOO_BASE_URL',
        'WOO_CK',
        'WOO_CS',
    ],
    'optional': [
        'DEEPL_API_KEY',
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_CHAT_ID',
    ],
}


def check_secrets(group: str = None) -> dict:
    """
    환경변수 설정 상태 확인.

    Args:
        group: 특정 그룹만 확인 (None이면 전체)

    Returns:
        {'group_name': {'set': [...], 'missing': [...]}}
    """
    if group is not None and group not in REQUIRED_SECRETS:
        raise ValueError(
            f"Unknown group: {group!r}. Valid groups: {list(REQUIRED_SECRETS.keys())}"
        )
    results = {}
    groups = {group: REQUIRED_SECRETS[group]} if group else REQUIRED_SECRETS

    for grp, keys in groups.items():
        set_keys = [k for k in keys if os.getenv(k)]
        missing_keys = [k for k in keys if not os.getenv(k)]
        results[grp] = {'set': set_keys, 'missing': missing_keys}

        if missing_keys:
            level = logging.WARNING if grp == 'optional' else logging.ERROR
            logger.log(level, "[%s] Missing: %s", grp, ', '.join(missing_keys))
        else:
            logger.info("[%s] All secrets configured ✅", grp)

    return results


def check_all() -> bool:
    """전체 필수 시크릿 확인. 모두 설정되어 있으면 True."""
    results = check_secrets()
    for grp, data in results.items():
        if grp != 'optional' and data['missing']:
            return False
    return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    ok = check_all()
    print(f"\n{'✅ All required secrets configured' if ok else '❌ Some required secrets missing'}")
