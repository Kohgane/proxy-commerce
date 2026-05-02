#!/usr/bin/env python3
"""scripts/render_smoke.py — Render 배포 후 헬스체크 자동 실행.

사용법:
    python scripts/render_smoke.py [BASE_URL]
    BASE_URL 미지정 시 환경변수 RENDER_APP_URL → http://localhost:10000 순으로 사용.

종료 코드:
    0 — 모든 체크 통과
    1 — 하나 이상 실패
"""
from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

TIMEOUT = 10  # seconds per request

ENDPOINTS = [
    ("/health", False),
    ("/health/ready", False),
    ("/api/v1/dashboard/stats", True),   # optional
    ("/api/v1/delivery-notifications/status", True),  # optional Phase 117
]


def check_endpoint(base_url: str, path: str, optional: bool = False) -> bool:
    """단일 엔드포인트를 확인하고 성공 여부를 반환합니다."""
    url = base_url.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            status = response.status
            if 200 <= status < 300:
                print(f"{GREEN}✓{RESET} {path} ({status})")
                return True
            label = f"{YELLOW}(optional){RESET} " if optional else ""
            print(f"{RED}✗{RESET} {label}{path} – unexpected status {status}")
            return optional
    except urllib.error.HTTPError as exc:
        if optional:
            print(f"{YELLOW}○{RESET} {path} (optional, skipped – HTTP {exc.code})")
            return True
        print(f"{RED}✗{RESET} {path} – HTTP {exc.code}")
        return False
    except urllib.error.URLError as exc:
        if optional:
            print(f"{YELLOW}○{RESET} {path} (optional, skipped – {exc.reason})")
            return True
        print(f"{RED}✗{RESET} {path} – {exc.reason}")
        return False
    except TimeoutError:
        if optional:
            print(f"{YELLOW}○{RESET} {path} (optional, skipped – timeout)")
            return True
        print(f"{RED}✗{RESET} {path} – timeout after {TIMEOUT}s")
        return False


def wait_for_ready(base_url: str, retries: int = 10, interval: int = 15) -> bool:
    """서비스가 준비될 때까지 헬스체크를 반복합니다."""
    print(f"\n[smoke] {base_url}/health 준비 대기 중 (최대 {retries}회, {interval}s 간격)…")
    for i in range(1, retries + 1):
        try:
            with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=TIMEOUT) as r:
                if 200 <= r.status < 300:
                    print(f"{GREEN}✓{RESET} 서비스 준비 완료 ({i}회차)")
                    return True
        except Exception:
            pass
        print(f"  [{i}/{retries}] 아직 준비 중… {interval}s 후 재시도")
        time.sleep(interval)
    return False


def main(base_url: str) -> int:
    """전체 스모크 테스트를 실행하고 종료 코드를 반환합니다."""
    print(f"\n{'='*60}")
    print(f"  Render Smoke Test — {base_url}")
    print(f"{'='*60}\n")

    # 서비스 준비 대기 (Render cold start 고려)
    if not wait_for_ready(base_url):
        print(f"\n{RED}✗ 서비스가 준비되지 않았습니다. 배포 실패 가능성이 있습니다.{RESET}")
        return 1

    print("\n[smoke] 엔드포인트 체크 시작…\n")
    results = []
    for path, optional in ENDPOINTS:
        results.append(check_endpoint(base_url, path, optional))

    passed = sum(results)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"  결과: {passed}/{total} 체크 통과")
    print(f"{'='*60}")

    return 0 if all(results) else 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.environ.get("RENDER_APP_URL", os.environ.get("BASE_URL", "http://localhost:10000"))

    sys.exit(main(url))
