#!/usr/bin/env python3
"""scripts/render_domain_attach.py — Render 커스텀 도메인 추가 & 검증 스크립트.

필요 환경변수:
    RENDER_API_TOKEN  — Render API 토큰

사용법:
    # kohganepercenti.com + www 를 srv-d78d5rfkijhs73868f8g 서비스에 추가
    python scripts/render_domain_attach.py

    # 서비스 ID와 도메인 직접 지정
    python scripts/render_domain_attach.py \
        --service-id srv-d78d5rfkijhs73868f8g \
        --domains kohganepercenti.com www.kohganepercenti.com

    # 검증 상태 polling만 (이미 추가된 경우)
    python scripts/render_domain_attach.py --check-only

제약:
    - stdlib urllib만 사용 (외부 라이브러리 없음)
    - 토큰은 환경변수에서만 읽음
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

RENDER_API_BASE = "https://api.render.com/v1"
DEFAULT_SERVICE_ID = "srv-d78d5rfkijhs73868f8g"
DEFAULT_DOMAINS = ["kohganepercenti.com", "www.kohganepercenti.com"]
POLL_INTERVAL = 10  # seconds
POLL_MAX = 30       # max polling attempts (~5 minutes)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


def _render_request(
    method: str,
    path: str,
    token: str,
    payload: dict | None = None,
) -> dict:
    """Render API 요청을 전송하고 JSON 응답을 반환합니다."""
    url = RENDER_API_BASE + path
    data = json.dumps(payload).encode() if payload else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        if exc.code == 409:
            # 이미 추가된 도메인 — 정상 처리
            return {"status": "already_exists", "raw": body}
        print(f"{RED}✗ HTTP {exc.code} — {url}{RESET}")
        print(f"  응답: {body[:500]}")
        return {"error": True, "code": exc.code, "body": body}
    except urllib.error.URLError as exc:
        print(f"{RED}✗ URL 에러 — {exc.reason}{RESET}")
        sys.exit(1)


def add_custom_domain(service_id: str, domain: str, token: str) -> str | None:
    """커스텀 도메인을 Render 서비스에 추가하고 도메인 ID를 반환합니다."""
    resp = _render_request(
        "POST",
        f"/services/{service_id}/custom-domains",
        token,
        {"name": domain},
    )
    if resp.get("status") == "already_exists":
        print(f"{YELLOW}○{RESET} {domain} — 이미 추가됨 (skip)")
        return None
    if resp.get("error"):
        print(f"{RED}✗ {domain} 추가 실패 (HTTP {resp['code']}){RESET}")
        print(f"  {resp.get('body', '')[:300]}")
        return None
    domain_id = resp.get("id") or resp.get("customDomain", {}).get("id")
    print(f"{GREEN}+{RESET} {domain} 추가 완료  (id: {domain_id})")
    return domain_id


def poll_verification(service_id: str, domain: str, token: str) -> bool:
    """도메인 검증이 완료될 때까지 polling합니다."""
    print(f"{BLUE}⏳{RESET} {domain} 검증 대기 중 (최대 {POLL_MAX * POLL_INTERVAL}s)…")
    for i in range(1, POLL_MAX + 1):
        resp = _render_request("GET", f"/services/{service_id}/custom-domains", token)
        domains = resp if isinstance(resp, list) else resp.get("customDomains", [])
        for d in domains:
            name = d.get("name") or d.get("domain")
            if name == domain:
                status = d.get("verificationStatus") or d.get("status", "unknown")
                if status == "verified":
                    print(f"{GREEN}✓{RESET} {domain} 검증 완료!")
                    return True
                if status in ("failed", "error"):
                    print(f"{RED}✗{RESET} {domain} 검증 실패 (status: {status})")
                    print("  → DNS 레코드를 확인하고 다시 시도하세요.")
                    return False
                print(f"  [{i}/{POLL_MAX}] {domain} 상태: {status} — {POLL_INTERVAL}s 후 재확인")
        time.sleep(POLL_INTERVAL)
    print(f"{YELLOW}⚠{RESET} {domain} 검증 시간 초과. Render 대시보드에서 직접 확인하세요.")
    return False


def list_custom_domains(service_id: str, token: str) -> None:
    """현재 등록된 커스텀 도메인 목록을 출력합니다."""
    resp = _render_request("GET", f"/services/{service_id}/custom-domains", token)
    domains = resp if isinstance(resp, list) else resp.get("customDomains", [])
    if not domains:
        print("  (등록된 커스텀 도메인 없음)")
        return
    for d in domains:
        name = d.get("name") or d.get("domain", "unknown")
        status = d.get("verificationStatus") or d.get("status", "unknown")
        icon = GREEN + "✓" if status == "verified" else YELLOW + "○"
        print(f"  {icon}{RESET}  {name}  [{status}]")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render 커스텀 도메인 추가 & 검증 스크립트"
    )
    parser.add_argument(
        "--service-id",
        default=DEFAULT_SERVICE_ID,
        help=f"Render 서비스 ID (기본: {DEFAULT_SERVICE_ID})",
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        default=DEFAULT_DOMAINS,
        help="추가할 도메인 목록 (기본: kohganepercenti.com www.kohganepercenti.com)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        default=False,
        help="도메인 추가 없이 검증 상태만 확인",
    )
    parser.add_argument(
        "--no-poll",
        action="store_true",
        default=False,
        help="추가 후 검증 polling을 건너뜀",
    )
    args = parser.parse_args()

    token = os.environ.get("RENDER_API_TOKEN", "")
    if not token:
        print(f"{RED}✗ RENDER_API_TOKEN 환경변수가 설정되지 않았습니다.{RESET}")
        print("  export RENDER_API_TOKEN=<your-token>")
        return 1

    print(f"\n{'='*60}")
    print(f"  Render Domain Attach — {args.service_id}")
    print(f"{'='*60}\n")

    if args.check_only:
        print("[현재 도메인 목록]")
        list_custom_domains(args.service_id, token)
        return 0

    success = True
    for domain in args.domains:
        add_custom_domain(args.service_id, domain, token)
        if not args.no_poll:
            ok = poll_verification(args.service_id, domain, token)
            if not ok:
                success = False

    print(f"\n{'='*60}")
    if success:
        print(f"{GREEN}  완료! 모든 도메인이 검증되었습니다.{RESET}")
        print("\n  다음 단계:")
        print("  1. Cloudflare DNS에서 CNAME이 올바른지 확인")
        print("  2. curl -I https://kohganepercenti.com/health")
        print("  3. python scripts/render_smoke.py https://kohganepercenti.com")
    else:
        print(f"{YELLOW}  일부 도메인 검증이 완료되지 않았습니다.{RESET}")
        print("  → DNS 전파에 최대 24시간이 걸릴 수 있습니다.")
        print("  → 나중에 --check-only 옵션으로 다시 확인하세요.")
    print(f"{'='*60}\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
