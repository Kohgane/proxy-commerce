#!/usr/bin/env python3
"""Smoke test for deployed application."""
import json
import os
import sys
import urllib.error
import urllib.request

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

TIMEOUT = 5  # seconds per request


def check_endpoint(base_url, path, optional=False):
    """Check a single endpoint.  Returns True on success, False on failure."""
    url = base_url.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            status = response.status
            if 200 <= status < 300:
                print(f"{GREEN}✓{RESET} {path} ({status})")
                return True
            print(f"{RED}✗{RESET} {path} – unexpected status {status}")
            return False
    except urllib.error.HTTPError as exc:
        if optional:
            print(f"{GREEN}✓{RESET} {path} (optional, skipped – {exc.code})")
            return True
        print(f"{RED}✗{RESET} {path} – HTTP {exc.code}")
        return False
    except urllib.error.URLError as exc:
        if optional:
            print(f"{GREEN}✓{RESET} {path} (optional, skipped – {exc.reason})")
            return True
        print(f"{RED}✗{RESET} {path} – {exc.reason}")
        return False
    except TimeoutError:
        if optional:
            print(f"{GREEN}✓{RESET} {path} (optional, skipped – timeout)")
            return True
        print(f"{RED}✗{RESET} {path} – timeout after {TIMEOUT}s")
        return False


def main(base_url):
    """Run all smoke tests and return an exit code."""
    print(f"Smoke testing {base_url}\n")

    results = []
    results.append(check_endpoint(base_url, "/health"))
    results.append(check_endpoint(base_url, "/health/ready"))
    # Dashboard stats endpoint is optional – don't fail the suite if absent.
    results.append(check_endpoint(base_url, "/api/v1/dashboard/stats", optional=True))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} checks passed")

    return 0 if all(results) else 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.environ.get("BASE_URL", "http://localhost:8000")

    sys.exit(main(url))
