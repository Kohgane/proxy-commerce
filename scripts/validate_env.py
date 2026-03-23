"""Validate environment variables for staging or production deployment.

Checks that required secrets are set and not placeholder values, and validates
known secret formats (e.g. Shopify token prefixes).
"""

import argparse
import json
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)

STAGING_SECRETS = {
    'core': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID'],
    'shopify': ['SHOPIFY_SHOP', 'SHOPIFY_ACCESS_TOKEN', 'SHOPIFY_CLIENT_SECRET'],
}

PRODUCTION_SECRETS = {
    **STAGING_SECRETS,
    'woocommerce': ['WOO_BASE_URL', 'WOO_CK', 'WOO_CS'],
    'optional': ['DEEPL_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'],
}

FORMAT_VALIDATORS = {
    'SHOPIFY_ACCESS_TOKEN': re.compile(r'^shpat_'),
    'SHOPIFY_CLIENT_SECRET': re.compile(r'^shpss_'),
}

PLACEHOLDER_RE = re.compile(r'^\$\{')


def is_placeholder(value: str) -> bool:
    """Return True if the value looks like an unreplaced template placeholder."""
    return bool(PLACEHOLDER_RE.match(value))


def validate_secrets(env: str) -> dict:
    """Validate required secrets for the given environment.

    Args:
        env: One of 'staging' or 'production'.

    Returns:
        A dict with keys 'env', 'passed', 'errors', and 'warnings'.
    """
    secret_map = STAGING_SECRETS if env == 'staging' else PRODUCTION_SECRETS
    errors = []
    warnings = []

    for group, keys in secret_map.items():
        for key in keys:
            value = os.getenv(key, '')
            if not value:
                if group == 'optional':
                    warnings.append(f'{key}: not set (optional)')
                else:
                    errors.append(f'{key}: missing or empty')
                continue

            if is_placeholder(value):
                if group == 'optional':
                    warnings.append(f'{key}: unreplaced placeholder')
                else:
                    errors.append(f'{key}: unreplaced placeholder ({value!r})')
                continue

            if key in FORMAT_VALIDATORS:
                if not FORMAT_VALIDATORS[key].match(value):
                    errors.append(
                        f'{key}: invalid format (expected pattern {FORMAT_VALIDATORS[key].pattern!r})'
                    )

    passed = len(errors) == 0
    return {
        'env': env,
        'passed': passed,
        'errors': errors,
        'warnings': warnings,
    }


def main(argv=None):
    """Entry point for CLI usage."""
    parser = argparse.ArgumentParser(description='Validate deployment environment variables')
    parser.add_argument('--env', choices=['staging', 'production'], required=True,
                        help='Target environment to validate')
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    result = validate_secrets(args.env)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    for warning in result['warnings']:
        logger.warning(warning)

    if result['errors']:
        for error in result['errors']:
            logger.error(error)
        sys.exit(1)

    logger.info('All required secrets are valid for %s', args.env)
    sys.exit(0)


if __name__ == '__main__':
    main()
