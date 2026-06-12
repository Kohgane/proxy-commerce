#!/usr/bin/env python3
"""scripts/verify_market_connections.py — 마켓 연동 라이브 검증 도구.

각 마켓(쿠팡/스마트스토어/11번가/Shopify/WooCommerce)에 대해
1) 읽기 연결 + 안전한 write dry-run (운영 데이터 변경 없음)
2) 업로드 사전검증(토큰/필수필드)
을 실제로 호출하고, 사람이 한눈에 읽을 수 있는 표로 출력한다.

자격증명이 없으면 'token_missing'으로 정직하게 표기되므로,
운영 환경(Render 셸 등)에서 자격증명을 넣은 뒤 실행하면 실제 연결을 검증할 수 있다.

사용법:
    python -m scripts.verify_market_connections            # 전체 마켓
    python -m scripts.verify_market_connections coupang    # 특정 마켓만
    python -m scripts.verify_market_connections --json     # 기계용 JSON 출력
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 상태별 이모지/한국어 라벨
_STATUS_ICON = {
    "connected": "✅ 연결됨",
    "token_missing": "🪪 자격증명 없음",
    "token_expired": "⏰ 토큰 만료",
    "scope_insufficient": "🔒 권한 부족",
    "api_error": "❌ API 오류",
}

# 검증에 사용할 안전한 샘플 상품 (실제 등록 아님 — 사전검증/ dry-run 용)
_SAMPLE_PRODUCT = {
    "title": "[검증용] 샘플 상품",
    "title_ko": "[검증용] 샘플 상품",
    "sku": "VERIFY-0001",
    "price": 19900,
    "currency": "KRW",
    "sell_price_krw": 19900,
    "images": [],
    "description": "연결 검증용 샘플",
    "category": "GEN",
}


# 진단 서브시스템 키 → 업로드 디스패처 키 (네임스페이스가 다른 경우 변환)
_DISPATCH_MARKET_ALIAS = {"11st": "elevenst"}


def _status_label(status: str) -> str:
    return _STATUS_ICON.get(status, f"❓ {status}")


def verify_market(market: str) -> dict:
    """단일 마켓 연결 진단 + 업로드 사전검증."""
    from src.seller_console.market_integration_diagnostics import run_market_diagnostic
    from src.seller_console.upload_dispatcher import UploadDispatcher

    diag = run_market_diagnostic(market)
    dispatch_market = _DISPATCH_MARKET_ALIAS.get(market, market)

    prevalidation = None
    try:
        results = UploadDispatcher().prevalidate(_SAMPLE_PRODUCT, [dispatch_market])
        if results:
            r = results[0]
            prevalidation = {
                "ok": r.ok,
                "error_code": r.error_code,
                "message": r.message,
                "hint": r.hint,
            }
    except Exception as exc:  # pragma: no cover - 방어적
        prevalidation = {"ok": False, "error_code": "error", "message": str(exc), "hint": ""}

    return {
        "market": market,
        "label": diag.get("label", market),
        "status": diag.get("status"),
        "summary": diag.get("summary"),
        "hint": diag.get("hint"),
        "required_env": diag.get("required_env", []),
        "docs_path": diag.get("docs_path"),
        "prevalidation": prevalidation,
    }


def _print_human(rows: list[dict]) -> None:
    print("\n=== 마켓 연동 라이브 검증 결과 ===\n")
    for row in rows:
        print(f"■ {row['label']} ({row['market']})")
        print(f"   연결 상태 : {_status_label(row['status'])}")
        print(f"   요약      : {row['summary']}")
        pv = row.get("prevalidation") or {}
        if pv:
            pv_icon = "✅ 통과" if pv.get("ok") else f"⚠️ {pv.get('error_code')}"
            print(f"   업로드준비: {pv_icon} — {pv.get('message', '')}")
        if row["status"] != "connected":
            print(f"   해결 방법 : {row['hint']}")
            missing = ", ".join(row.get("required_env") or [])
            if missing:
                print(f"   필요 환경변수: {missing}")
            print(f"   가이드    : {row['docs_path']}")
        print()

    connected = sum(1 for r in rows if r["status"] == "connected")
    print(f"요약: 전체 {len(rows)}개 중 ✅ 연결됨 {connected}개 · 미연결 {len(rows) - connected}개")
    if connected < len(rows):
        print("→ 미연결 마켓은 위 '필요 환경변수'를 설정한 뒤 이 스크립트를 다시 실행하세요.")
        print("  자세한 단계: docs/operations/LIVE_VERIFICATION_GUIDE.md")


def main() -> int:
    parser = argparse.ArgumentParser(description="마켓 연동 라이브 검증 도구")
    parser.add_argument("markets", nargs="*", help="검증할 마켓 (생략 시 전체)")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args()

    from src.seller_console.market_integration_diagnostics import MARKET_GUIDES

    targets = [m.lower() for m in args.markets] or list(MARKET_GUIDES.keys())
    unknown = [m for m in targets if m not in MARKET_GUIDES]
    if unknown:
        print(f"알 수 없는 마켓: {', '.join(unknown)}", file=sys.stderr)
        print(f"지원 마켓: {', '.join(MARKET_GUIDES.keys())}", file=sys.stderr)
        return 2

    rows = [verify_market(m) for m in targets]

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        _print_human(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
