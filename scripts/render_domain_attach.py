#!/usr/bin/env python3
"""scripts/render_domain_attach.py — Render 커스텀 도메인 추가 & 검증 스크립트.

필요 환경변수:
    RENDER_API_TOKEN  — Render API 토큰

사용법:
    # kohganepercentiii.com + www 를 srv-d78d5rfkijhs73868f8g 서비스에 추가
    python scripts/render_domain_attach.py

    # 서비스 ID와 도메인 직접 지정
    python scripts/render_domain_attach.py \
        --service-id srv-d78d5rfkijhs73868f8g \
        --domains kohganepercentiii.com www.kohganepercentiii.com

    # 현재 등록된 도메인 목록만 조회 (슬롯 사용량 포함)
    python scripts/render_domain_attach.py --list-domains

    # 검증 상태 polling만 (이미 추가된 경우)
    python scripts/render_domain_attach.py --check-only

    # 기존 도메인 제거 (Hobby Tier 슬롯 확보)
    python scripts/render_domain_attach.py --remove-domain kohganemultishop.org

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
DEFAULT_DOMAINS = ["kohganepercentiii.com", "www.kohganepercentiii.com"]
POLL_INTERVAL = 10  # seconds
POLL_MAX = 30       # max polling attempts (~5 minutes)
HOBBY_TIER_LIMIT = 2  # Render Hobby Tier 커스텀 도메인 최대 개수

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
        if exc.code == 204:
            # DELETE 성공 — 빈 응답
            return {"status": "deleted"}
        print(f"{RED}✗ HTTP {exc.code} — {url}{RESET}")
        print(f"  응답: {body[:500]}")
        return {"error": True, "code": exc.code, "body": body}
    except urllib.error.URLError as exc:
        print(f"{RED}✗ URL 에러 — {exc.reason}{RESET}")
        sys.exit(1)


def get_service_info(service_id: str, token: str) -> dict:
    """서비스 정보를 조회하고 실제 onrender.com 호스트명을 포함하여 반환합니다."""
    resp = _render_request("GET", f"/services/{service_id}", token)
    return resp


def get_onrender_host(service_id: str, token: str) -> str | None:
    """Render API에서 실제 서비스 URL(onrender.com 호스트)을 자동으로 가져옵니다."""
    info = get_service_info(service_id, token)
    # serviceDetails.url 또는 service.url 필드에서 추출
    url = (
        info.get("serviceDetails", {}).get("url")
        or info.get("service", {}).get("url")
        or info.get("url")
        or ""
    )
    if not url:
        return None
    # "https://proxy-commerce-h5x2.onrender.com" → "proxy-commerce-h5x2.onrender.com"
    host = url.replace("https://", "").replace("http://", "").rstrip("/")
    return host if host else None


def get_current_domains(service_id: str, token: str) -> list[dict]:
    """현재 등록된 커스텀 도메인 목록을 반환합니다."""
    resp = _render_request("GET", f"/services/{service_id}/custom-domains", token)
    return resp if isinstance(resp, list) else resp.get("customDomains", [])


def check_slot_availability(service_id: str, token: str) -> tuple[int, list[dict]]:
    """Hobby Tier 슬롯 사용량을 확인하고 (현재 개수, 도메인 목록)을 반환합니다."""
    domains = get_current_domains(service_id, token)
    return len(domains), domains


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
        code = resp["code"]
        body = resp.get("body", "")
        # Hobby Tier 도메인 슬롯 가득 찬 경우 특별 처리
        if code == 400 and "Hobby Tier" in body:
            return None  # 호출자에서 별도 처리
        print(f"{RED}✗ {domain} 추가 실패 (HTTP {code}){RESET}")
        print(f"  {body[:300]}")
        return None
    domain_id = resp.get("id") or resp.get("customDomain", {}).get("id")
    print(f"{GREEN}+{RESET} {domain} 추가 완료  (id: {domain_id})")
    return domain_id


def remove_custom_domain(service_id: str, domain: str, token: str) -> bool:
    """Render 서비스에서 커스텀 도메인을 제거합니다.

    Args:
        service_id: Render 서비스 ID
        domain: 제거할 도메인 이름
        token: Render API 토큰

    Returns:
        True이면 제거 성공, False이면 실패
    """
    # 도메인 ID를 먼저 조회
    domains = get_current_domains(service_id, token)
    domain_id = None
    for d in domains:
        name = d.get("name") or d.get("domain", "")
        if name == domain:
            domain_id = d.get("id")
            break

    if not domain_id:
        print(f"{YELLOW}⚠{RESET} {domain} — 등록된 도메인에서 찾을 수 없습니다.")
        return False

    resp = _render_request(
        "DELETE",
        f"/services/{service_id}/custom-domains/{domain_id}",
        token,
    )
    if resp.get("error"):
        print(f"{RED}✗ {domain} 제거 실패 (HTTP {resp['code']}){RESET}")
        return False

    print(f"{GREEN}✓{RESET} {domain} 제거 완료")
    return True


def poll_verification(service_id: str, domain: str, token: str) -> bool:
    """도메인 검증이 완료될 때까지 polling합니다."""
    print(f"{BLUE}⏳{RESET} {domain} 검증 대기 중 (최대 {POLL_MAX * POLL_INTERVAL}s)…")
    for i in range(1, POLL_MAX + 1):
        domains = get_current_domains(service_id, token)
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
                # pending 상태일 때 verification 메서드 안내
                verify_type = d.get("verificationType") or d.get("verificationMethod", "")
                if verify_type:
                    print(f"  [{i}/{POLL_MAX}] {domain} 상태: {status} (검증방식: {verify_type}) — {POLL_INTERVAL}s 후 재확인")
                else:
                    print(f"  [{i}/{POLL_MAX}] {domain} 상태: {status} — {POLL_INTERVAL}s 후 재확인")
        time.sleep(POLL_INTERVAL)
    print(f"{YELLOW}⚠{RESET} {domain} 검증 시간 초과. Render 대시보드에서 직접 확인하세요.")
    return False


def list_custom_domains(service_id: str, token: str) -> int:
    """현재 등록된 커스텀 도메인 목록과 슬롯 사용량을 출력합니다.

    Returns:
        현재 등록된 도메인 개수
    """
    domains = get_current_domains(service_id, token)
    count = len(domains)
    print(f"  도메인 슬롯: {count}/{HOBBY_TIER_LIMIT} 사용 중 (Hobby Tier 기준)")
    if not domains:
        print("  (등록된 커스텀 도메인 없음)")
        return 0
    for d in domains:
        name = d.get("name") or d.get("domain", "unknown")
        status = d.get("verificationStatus") or d.get("status", "unknown")
        icon = GREEN + "✓" if status == "verified" else YELLOW + "○"
        print(f"  {icon}{RESET}  {name}  [{status}]")
    return count


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
        help="추가할 도메인 목록 (기본: kohganepercentiii.com www.kohganepercentiii.com)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        default=False,
        help="도메인 추가 없이 검증 상태만 확인 (--list-domains 별칭)",
    )
    parser.add_argument(
        "--list-domains",
        action="store_true",
        default=False,
        help="현재 등록된 도메인 목록과 슬롯 사용량만 출력",
    )
    parser.add_argument(
        "--remove-domain",
        metavar="DOMAIN",
        help="지정한 도메인을 Render 서비스에서 제거 (Hobby Tier 슬롯 확보용)",
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

    # --list-domains 또는 --check-only: 목록만 조회
    if args.list_domains or args.check_only:
        print("[현재 도메인 목록]")
        list_custom_domains(args.service_id, token)
        # 실제 onrender.com 호스트도 함께 출력
        host = get_onrender_host(args.service_id, token)
        if host:
            print(f"\n  Cloudflare Target: {BLUE}{host}{RESET}")
        return 0

    # --remove-domain: 도메인 제거
    if args.remove_domain:
        print(f"[도메인 제거] {args.remove_domain}")
        ok = remove_custom_domain(args.service_id, args.remove_domain, token)
        return 0 if ok else 1

    # 사전 점검: 슬롯 사용량 확인
    print("[사전 점검] 현재 도메인 슬롯 확인 중…")
    current_count, current_domains = check_slot_availability(args.service_id, token)
    print(f"  슬롯: {current_count}/{HOBBY_TIER_LIMIT} 사용 중")

    # Hobby Tier 2/2 만석이면 친절한 에러 출력 후 exit code 2
    available_slots = HOBBY_TIER_LIMIT - current_count
    if available_slots <= 0:
        print(f"\n{RED}❌ Hobby Tier 도메인 슬롯이 가득 찼습니다 ({current_count}/{HOBBY_TIER_LIMIT}).{RESET}")
        print("\n  현재 등록된 도메인:")
        for d in current_domains:
            name = d.get("name") or d.get("domain", "unknown")
            print(f"    - {name}")
        print("\n  다음 명령으로 기존 도메인을 먼저 제거하세요:")
        for d in current_domains:
            name = d.get("name") or d.get("domain", "unknown")
            print(f"    python scripts/render_domain_attach.py --service-id {args.service_id} --remove-domain {name}")
        print("\n  또는 Render Pro로 업그레이드하면 도메인 제한이 해제됩니다.")
        return 2

    # 추가하려는 도메인이 슬롯을 초과하는지 확인
    new_domains = [d for d in args.domains if d not in {
        (x.get("name") or x.get("domain", "")) for x in current_domains
    }]
    if len(new_domains) > available_slots:
        print(f"{YELLOW}⚠ 추가하려는 도메인 {len(new_domains)}개 중 {available_slots}개만 슬롯이 남아있습니다.{RESET}")
        print(f"  추가 가능 도메인: {new_domains[:available_slots]}")

    # 실제 onrender.com 호스트 자동 조회
    host = get_onrender_host(args.service_id, token)
    if host:
        print(f"\n  Cloudflare Target: {BLUE}{host}{RESET}")
    else:
        print(f"{YELLOW}  ⚠ onrender.com 호스트를 자동으로 가져오지 못했습니다.{RESET}")
        print("    Render 대시보드 → Settings에서 직접 확인하세요.")

    print()
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
        if host:
            print(f"     CNAME Target: {host}")
        print("  2. curl -I https://kohganepercentiii.com/health")
        print("  3. python scripts/render_smoke.py https://kohganepercentiii.com")
    else:
        print(f"{YELLOW}  일부 도메인 검증이 완료되지 않았습니다.{RESET}")
        print("  → DNS 전파에 최대 24시간이 걸릴 수 있습니다.")
        print("  → 나중에 --list-domains 옵션으로 다시 확인하세요.")
    print(f"{'='*60}\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
