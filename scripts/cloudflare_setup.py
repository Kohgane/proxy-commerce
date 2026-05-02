#!/usr/bin/env python3
"""scripts/cloudflare_setup.py — Cloudflare DNS + SSL 자동 설정 스크립트.

필요 환경변수:
    CF_API_TOKEN  — Cloudflare API 토큰 (Zone:Edit, DNS:Edit 권한)

사용법:
    # 기본 실행 (kohganepercenti.com → Render)
    python scripts/cloudflare_setup.py

    # 다른 apex 도메인 지정
    python scripts/cloudflare_setup.py --apex mysite.com --target myapp.onrender.com

    # 실제 변경 없이 미리 확인
    python scripts/cloudflare_setup.py --dry-run

    # 로그 파일 저장
    python scripts/cloudflare_setup.py 2>&1 | tee docs/deployment/cloudflare_apply.log

기능:
    - Zone 조회 / 존재 확인
    - DNS 레코드 idempotent upsert (apex CNAME-flatten, www CNAME)
    - SSL/TLS 모드 "full" 설정
    - "Always Use HTTPS" 켜기
    - --dry-run 지원 (실제 변경 없이 예상 동작 출력)

제약:
    - stdlib urllib만 사용 (외부 라이브러리 없음)
    - 토큰은 환경변수에서만 읽음 (코드 내 하드코딩 금지)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CF_API_BASE = "https://api.cloudflare.com/client/v4"

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


# ──────────────────────────────────────────────
# HTTP 유틸
# ──────────────────────────────────────────────

def _cf_request(
    method: str,
    path: str,
    token: str,
    payload: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Cloudflare API 요청을 전송하고 JSON 응답을 반환합니다."""
    url = CF_API_BASE + path
    data = json.dumps(payload).encode() if payload else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if dry_run and method != "GET":
        print(f"{YELLOW}[dry-run]{RESET} {method} {url}")
        if payload:
            print(f"         payload: {json.dumps(payload, ensure_ascii=False)}")
        return {"success": True, "result": {}, "dry_run": True}

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"{RED}✗ HTTP {exc.code} — {url}{RESET}")
        print(f"  응답: {body[:500]}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"{RED}✗ URL 에러 — {exc.reason}{RESET}")
        sys.exit(1)


# ──────────────────────────────────────────────
# Zone 관련
# ──────────────────────────────────────────────

def get_zone_id(apex: str, token: str, dry_run: bool) -> str:
    """apex 도메인의 Cloudflare Zone ID를 반환합니다."""
    resp = _cf_request("GET", f"/zones?name={urllib.parse.quote(apex)}&status=active", token, dry_run=False)
    if not resp.get("success"):
        print(f"{RED}✗ Zone 조회 실패: {resp}{RESET}")
        sys.exit(1)
    results = resp.get("result", [])
    if not results:
        print(f"{RED}✗ Zone을 찾을 수 없습니다: {apex}{RESET}")
        print("  Cloudflare 대시보드에서 해당 도메인이 추가되어 있는지 확인하세요.")
        sys.exit(1)
    zone_id = results[0]["id"]
    print(f"{GREEN}✓{RESET} Zone ID: {zone_id}  ({apex})")
    return zone_id


# ──────────────────────────────────────────────
# DNS 레코드 upsert
# ──────────────────────────────────────────────

def _list_dns_records(zone_id: str, name: str, token: str) -> list:
    """주어진 name의 DNS 레코드 목록을 반환합니다."""
    resp = _cf_request("GET", f"/zones/{zone_id}/dns_records?name={urllib.parse.quote(name)}", token, dry_run=False)
    return resp.get("result", [])


def upsert_dns_record(
    zone_id: str,
    name: str,
    record_type: str,
    content: str,
    proxied: bool,
    token: str,
    dry_run: bool,
) -> None:
    """DNS 레코드를 생성하거나 업데이트합니다 (idempotent)."""
    existing = _list_dns_records(zone_id, name, token)
    payload = {
        "type": record_type,
        "name": name,
        "content": content,
        "ttl": 1,  # auto
        "proxied": proxied,
    }

    if existing:
        record_id = existing[0]["id"]
        print(f"{BLUE}↻{RESET} DNS 업데이트: {record_type} {name} → {content}  proxied={proxied}")
        _cf_request("PUT", f"/zones/{zone_id}/dns_records/{record_id}", token, payload, dry_run)
    else:
        print(f"{GREEN}+{RESET} DNS 생성: {record_type} {name} → {content}  proxied={proxied}")
        _cf_request("POST", f"/zones/{zone_id}/dns_records", token, payload, dry_run)


# ──────────────────────────────────────────────
# SSL / HTTPS
# ──────────────────────────────────────────────

def set_ssl_mode(zone_id: str, mode: str, token: str, dry_run: bool) -> None:
    """SSL/TLS 모드를 설정합니다 (off/flexible/full/strict)."""
    payload = {"value": mode}
    resp = _cf_request("PATCH", f"/zones/{zone_id}/settings/ssl", token, payload, dry_run)
    if dry_run or resp.get("success"):
        print(f"{GREEN}✓{RESET} SSL 모드 설정: {mode}")
    else:
        print(f"{RED}✗ SSL 모드 설정 실패: {resp}{RESET}")


def set_always_use_https(zone_id: str, enabled: bool, token: str, dry_run: bool) -> None:
    """Always Use HTTPS 설정을 켜거나 끕니다."""
    payload = {"value": "on" if enabled else "off"}
    resp = _cf_request("PATCH", f"/zones/{zone_id}/settings/always_use_https", token, payload, dry_run)
    if dry_run or resp.get("success"):
        status = "ON" if enabled else "OFF"
        print(f"{GREEN}✓{RESET} Always Use HTTPS: {status}")
    else:
        print(f"{RED}✗ Always Use HTTPS 설정 실패: {resp}{RESET}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cloudflare DNS + SSL 자동 설정 스크립트"
    )
    parser.add_argument(
        "--apex",
        default="kohganepercenti.com",
        help="루트 도메인 (기본: kohganepercenti.com)",
    )
    parser.add_argument(
        "--target",
        default="kohganemultishop.onrender.com",
        help="Render 서비스 호스트명 (CNAME 대상)",
    )
    parser.add_argument(
        "--proxied",
        action="store_true",
        default=False,
        help="Cloudflare 프록시(주황 구름) 활성화 (기본: OFF — Render Free tier 호환)",
    )
    parser.add_argument(
        "--ssl-mode",
        default="full",
        choices=["off", "flexible", "full", "strict"],
        help="SSL/TLS 모드 (기본: full)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="실제 변경 없이 예상 동작만 출력",
    )
    args = parser.parse_args()

    token = os.environ.get("CF_API_TOKEN", "")
    if not token:
        print(f"{RED}✗ CF_API_TOKEN 환경변수가 설정되지 않았습니다.{RESET}")
        print("  export CF_API_TOKEN=<your-token>")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n{'='*60}")
    print(f"  Cloudflare Setup  —  {args.apex}  [{ts}]")
    if args.dry_run:
        print(f"  {YELLOW}DRY-RUN 모드: 실제 변경 없음{RESET}")
    print(f"{'='*60}\n")

    # 1. Zone ID 조회
    zone_id = get_zone_id(args.apex, token, args.dry_run)

    # 2. DNS 레코드 upsert
    #    apex (@) → CNAME (Cloudflare CNAME flattening으로 루트에서도 동작)
    upsert_dns_record(
        zone_id,
        name=args.apex,
        record_type="CNAME",
        content=args.target,
        proxied=args.proxied,
        token=token,
        dry_run=args.dry_run,
    )
    #    www → CNAME
    upsert_dns_record(
        zone_id,
        name=f"www.{args.apex}",
        record_type="CNAME",
        content=args.target,
        proxied=args.proxied,
        token=token,
        dry_run=args.dry_run,
    )

    # 3. SSL 모드 설정
    set_ssl_mode(zone_id, args.ssl_mode, token, args.dry_run)

    # 4. Always Use HTTPS
    set_always_use_https(zone_id, enabled=True, token=token, dry_run=args.dry_run)

    print(f"\n{GREEN}{'='*60}")
    print(f"  완료!")
    if args.dry_run:
        print(f"  (dry-run — 실제 DNS 변경 없음)")
    print(f"{'='*60}{RESET}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
