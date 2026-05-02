#!/usr/bin/env python3
"""scripts/cloudflare_setup.py — Cloudflare DNS + SSL 자동 설정 스크립트.

필요 환경변수:
    CF_API_TOKEN      — Cloudflare API 토큰 (Zone:Edit, DNS:Edit 권한)
    RENDER_API_TOKEN  — --target auto 모드 사용 시 필요

사용법:
    # 기본 실행 (kohganepercentiii.com → Render, CNAME 직접 지정)
    python scripts/cloudflare_setup.py

    # 다른 apex 도메인 지정
    python scripts/cloudflare_setup.py --apex mysite.com --target myapp.onrender.com

    # --target auto: Render API에서 실제 onrender.com 호스트 자동 조회
    python scripts/cloudflare_setup.py --apex kohganepercentiii.com --target auto \
        --service-id srv-d78d5rfkijhs73868f8g

    # 실제 변경 없이 미리 확인
    python scripts/cloudflare_setup.py --dry-run

    # 로그 파일 저장
    python scripts/cloudflare_setup.py 2>&1 | tee docs/deployment/cloudflare_apply.log

기능:
    - Zone 조회 / 존재 확인
    - DNS 레코드 idempotent upsert (apex CNAME-flatten, www CNAME)
    - SSL/TLS 모드 "full" 설정
    - "Always Use HTTPS" 켜기
    - --target auto: Render API에서 실제 호스트 자동 조회 (placeholder 사용 방지)
    - DNS 전파 1차 확인 (Cloudflare DoH API 사용)
    - --dry-run 지원 (실제 변경 없이 예상 동작 출력)

제약:
    - stdlib urllib만 사용 (외부 라이브러리 없음)
    - 토큰은 환경변수에서만 읽음 (코드 내 하드코딩 금지)
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CF_API_BASE = "https://api.cloudflare.com/client/v4"
RENDER_API_BASE = "https://api.render.com/v1"
DEFAULT_SERVICE_ID = "srv-d78d5rfkijhs73868f8g"

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


def _render_get_service_url(service_id: str, render_token: str) -> str | None:
    """Render API에서 실제 onrender.com 서비스 URL을 자동 조회합니다.

    --target auto 모드에서 사용. placeholder 사용을 방지하기 위해
    RENDER_API_TOKEN과 --service-id를 이용해 실제 호스트를 가져옵니다.
    """
    url = f"{RENDER_API_BASE}/services/{service_id}"
    headers = {
        "Authorization": f"Bearer {render_token}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        # serviceDetails.url 또는 service.url 필드에서 추출
        service_url = (
            data.get("serviceDetails", {}).get("url")
            or data.get("service", {}).get("url")
            or data.get("url")
            or ""
        )
        host = service_url.replace("https://", "").replace("http://", "").rstrip("/")
        return host if host else None
    except Exception as exc:
        print(f"{RED}✗ Render API 서비스 정보 조회 실패: {exc}{RESET}")
        return None


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
    """DNS 레코드를 생성하거나 업데이트합니다 (idempotent).

    기존에 동일 이름의 레코드가 있으면 PUT으로 덮어씁니다.
    placeholder 값(예: proxy-commerce-xxxx.onrender.com)이 들어있어도 자동 정정됩니다.
    """
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
        old_content = existing[0].get("content", "")
        if old_content != content:
            print(f"{BLUE}↻{RESET} DNS 업데이트: {record_type} {name}")
            print(f"     이전 값: {old_content}")
            print(f"     새  값: {content}  proxied={proxied}")
        else:
            print(f"{GREEN}✓{RESET} DNS 이미 최신 상태: {record_type} {name} → {content}")
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
# DNS 전파 검증 (Cloudflare DoH + stdlib socket)
# ──────────────────────────────────────────────

def verify_dns_propagation(domain: str, expected_target: str, dry_run: bool = False) -> bool:
    """DNS 전파를 1차 확인합니다.

    1단계: Cloudflare DNS over HTTPS(DoH) API로 CNAME 조회
    2단계: stdlib socket.getaddrinfo로 IP 리졸빙 확인

    Args:
        domain: 확인할 도메인 (예: kohganepercentiii.com)
        expected_target: 예상 CNAME 대상 (예: proxy-commerce-h5x2.onrender.com)
        dry_run: True이면 실제 조회 없이 dry-run 출력

    Returns:
        True이면 전파 확인됨, False이면 미전파 또는 실패
    """
    if dry_run:
        print(f"{YELLOW}[dry-run]{RESET} DNS 전파 확인 건너뜀: {domain}")
        return True

    print(f"\n{BLUE}[DNS 전파 확인]{RESET} {domain} → {expected_target}")

    # 1단계: Cloudflare DoH CNAME 조회
    doh_url = f"https://cloudflare-dns.com/dns-query?name={urllib.parse.quote(domain)}&type=CNAME"
    try:
        req = urllib.request.Request(
            doh_url,
            headers={"Accept": "application/dns-json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        answers = data.get("Answer", [])
        cname_targets = [a.get("data", "").rstrip(".") for a in answers if a.get("type") == 5]
        if expected_target in cname_targets or any(expected_target in t for t in cname_targets):
            print(f"  {GREEN}✓{RESET} DoH CNAME 확인: {domain} → {cname_targets}")
        elif cname_targets:
            print(f"  {YELLOW}⚠{RESET} DoH CNAME 불일치: {cname_targets} (예상: {expected_target})")
            print("  → DNS 전파에 최대 24시간이 걸릴 수 있습니다.")
            return False
        else:
            print(f"  {YELLOW}⚠{RESET} DoH CNAME 미전파 (아직 응답 없음)")
            return False
    except Exception as exc:
        print(f"  {YELLOW}⚠{RESET} DoH 조회 실패: {exc}")

    # 2단계: stdlib socket으로 IP 리졸빙
    try:
        results = socket.getaddrinfo(domain, None, socket.AF_INET)
        ips = list({r[4][0] for r in results})
        print(f"  {GREEN}✓{RESET} socket 리졸빙 성공: {domain} → {ips}")
        return True
    except socket.gaierror as exc:
        print(f"  {YELLOW}⚠{RESET} socket 리졸빙 실패: {exc}")
        print("  → DNS 전파가 아직 완료되지 않았습니다. 5~30분 후 다시 확인하세요.")
        return False


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cloudflare DNS + SSL 자동 설정 스크립트"
    )
    parser.add_argument(
        "--apex",
        default="kohganepercentiii.com",
        help="루트 도메인 (기본: kohganepercentiii.com)",
    )
    parser.add_argument(
        "--target",
        default="kohganemultishop.onrender.com",
        help=(
            "Render 서비스 호스트명 (CNAME 대상). "
            "'auto'를 지정하면 RENDER_API_TOKEN + --service-id로 자동 조회합니다."
        ),
    )
    parser.add_argument(
        "--service-id",
        default=DEFAULT_SERVICE_ID,
        help=f"--target auto 모드에서 사용할 Render 서비스 ID (기본: {DEFAULT_SERVICE_ID})",
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
    parser.add_argument(
        "--verify-dns",
        action="store_true",
        default=False,
        help="DNS 설정 후 전파 1차 확인 (DoH + socket)",
    )
    args = parser.parse_args()

    token = os.environ.get("CF_API_TOKEN", "")
    if not token:
        print(f"{RED}✗ CF_API_TOKEN 환경변수가 설정되지 않았습니다.{RESET}")
        print("  export CF_API_TOKEN=<your-token>")
        return 1

    # --target auto 처리: Render API에서 실제 호스트 자동 조회
    target = args.target
    if target == "auto":
        render_token = os.environ.get("RENDER_API_TOKEN", "")
        if not render_token:
            print(f"{RED}✗ --target auto 모드에는 RENDER_API_TOKEN이 필요합니다.{RESET}")
            print("  export RENDER_API_TOKEN=<your-token>")
            return 1
        print(f"{BLUE}[auto]{RESET} Render API에서 실제 호스트 조회 중…")
        host = _render_get_service_url(args.service_id, render_token)
        if not host:
            print(f"{RED}✗ Render 서비스 URL을 가져오지 못했습니다.{RESET}")
            print(f"  서비스 ID: {args.service_id}")
            print("  Render 대시보드 → 서비스 → Settings에서 직접 확인하세요.")
            return 1
        target = host
        print(f"{GREEN}✓{RESET} 자동 조회된 Cloudflare Target: {BLUE}{target}{RESET}")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n{'='*60}")
    print(f"  Cloudflare Setup  —  {args.apex}  [{ts}]")
    print(f"  Target: {target}")
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
        content=target,
        proxied=args.proxied,
        token=token,
        dry_run=args.dry_run,
    )
    #    www → CNAME
    upsert_dns_record(
        zone_id,
        name=f"www.{args.apex}",
        record_type="CNAME",
        content=target,
        proxied=args.proxied,
        token=token,
        dry_run=args.dry_run,
    )

    # 3. SSL 모드 설정
    set_ssl_mode(zone_id, args.ssl_mode, token, args.dry_run)

    # 4. Always Use HTTPS
    set_always_use_https(zone_id, enabled=True, token=token, dry_run=args.dry_run)

    # 5. DNS 전파 확인 (선택)
    if args.verify_dns:
        time.sleep(2)  # 짧은 대기 후 조회
        verify_dns_propagation(args.apex, target, args.dry_run)
        verify_dns_propagation(f"www.{args.apex}", target, args.dry_run)

    print(f"\n{GREEN}{'='*60}")
    print(f"  완료!")
    if args.dry_run:
        print(f"  (dry-run — 실제 DNS 변경 없음)")
    else:
        print(f"  다음 단계:")
        print(f"  1. 5~30분 후 SSL 인증서 발급 대기")
        print(f"  2. curl -I https://{args.apex}/health")
        print(f"  3. python scripts/render_smoke.py https://{args.apex}")
    print(f"{'='*60}{RESET}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
