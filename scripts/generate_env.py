"""Generate a .env file by substituting placeholders from environment variables.

Reads a template (.env.staging or .env.production), replaces ${VAR} style
placeholders with values from os.environ, and writes the result to an output file.
Warns about any placeholders that remain unresolved.
"""

import argparse
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r'\$\{([^}]+)\}')

TEMPLATE_MAP = {
    'staging': '.env.staging',
    'production': '.env.production',
}


def substitute_placeholders(template_text: str) -> tuple[str, list[str]]:
    """Replace ${VAR} placeholders with values from os.environ.

    Args:
        template_text: Raw template content.

    Returns:
        Tuple of (substituted_text, list_of_unresolved_placeholder_names).
    """
    unresolved = []

    def replacer(match):
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            unresolved.append(var_name)
            return match.group(0)
        return value

    result = PLACEHOLDER_RE.sub(replacer, template_text)
    return result, unresolved


def generate_env(env: str, output_path: str) -> bool:
    """Read the env template for *env* and write a resolved .env to *output_path*.

    Args:
        env: One of 'staging' or 'production'.
        output_path: Destination file path.

    Returns:
        True if all placeholders were resolved, False if any remain.
    """
    template_path = TEMPLATE_MAP[env]

    if not os.path.exists(template_path):
        logger.error('Template file not found: %s', template_path)
        sys.exit(1)

    with open(template_path, 'r', encoding='utf-8') as fh:
        template_text = fh.read()

    resolved, unresolved = substitute_placeholders(template_text)

    for var in unresolved:
        logger.warning('Unreplaced placeholder: ${%s}', var)

    with open(output_path, 'w', encoding='utf-8') as fh:
        fh.write(resolved)

    logger.info('Written %d bytes to %s', len(resolved), output_path)
    return len(unresolved) == 0


def main(argv=None):
    """Entry point for CLI usage."""
    parser = argparse.ArgumentParser(description='Generate .env from template')
    parser.add_argument('--env', choices=['staging', 'production'], required=True,
                        help='Target environment')
    parser.add_argument('--output', default='.env',
                        help='Output file path (default: .env)')
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    all_resolved = generate_env(args.env, args.output)
    sys.exit(0 if all_resolved else 1)


if __name__ == '__main__':
    main()
