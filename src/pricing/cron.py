"""src/pricing/cron.py — 자동 재가격 cron 라우트 (Phase 136).

라우트:
    POST /cron/reprice   — Render Cron Job 또는 외부 스케줄러 훅
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

cron_bp = Blueprint("pricing_cron", __name__, url_prefix="/cron")


@cron_bp.post("/reprice")
def reprice():
    """자동 재가격 실행.

    헤더 ``X-Cron-Secret`` 이 ``CRON_SECRET`` 환경변수와 일치해야 실행.
    (Render 크론 잡에서 헤더 없이 호출 가능하도록 키 미설정 시 허용)

    Query Params:
        dry_run=1|0  — 환경변수 PRICING_DRY_RUN 오버라이드
    """
    # 간단한 시크릿 검증
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        provided = request.headers.get("X-Cron-Secret", "")
        if provided != cron_secret:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

    # dry_run 파라미터
    dry_run_param = request.args.get("dry_run")
    if dry_run_param is not None:
        dry_run = dry_run_param == "1"
    else:
        dry_run = None  # 엔진에서 PRICING_DRY_RUN 환경변수 사용

    try:
        from src.pricing.engine import PricingEngine
        engine = PricingEngine()
        results = engine.evaluate(dry_run=dry_run)
    except Exception as exc:
        logger.error("재가격 엔진 오류: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    # 요약 알림 발송
    _send_summary_notification(results)

    return jsonify({"ok": True, "results": results})


def _send_summary_notification(results: dict):
    """재가격 결과 요약을 텔레그램 + 이메일로 발송."""
    evaluated = results.get("evaluated", 0)
    changed = results.get("changed", 0)
    details = results.get("details", [])
    errors = results.get("errors", [])
    dry_run = results.get("dry_run", True)

    if changed == 0 and not errors:
        return  # 변경 없으면 알림 스킵

    # 평균 변동율
    avg_delta = 0.0
    if details:
        avg_delta = sum(d.get("delta_pct", 0) for d in details) / len(details)

    # ±10% 이상 큰 변동
    big_changes = [d for d in details if abs(d.get("delta_pct", 0)) >= 10]

    # 적용된 룰 집계
    rule_counter: dict = {}
    for d in details:
        for rule_name in d.get("rules", []):
            rule_counter[rule_name] = rule_counter.get(rule_name, 0) + 1
    rule_summary = ", ".join(f"{k}({v})" for k, v in sorted(rule_counter.items(), key=lambda x: -x[1]))

    mode_label = "🔵 시뮬레이션" if dry_run else "🟢 실제 적용"
    msg = (
        f"🔁 자동 재가격 완료 {mode_label}\n"
        f"- 평가: {evaluated} SKU\n"
        f"- 변경: {changed} SKU ({avg_delta:+.1f}% 평균)\n"
        f"- 큰 변동 (±10% 이상): {len(big_changes)}건\n"
    )
    if rule_summary:
        msg += f"- 적용 룰: {rule_summary}\n"
    if errors:
        msg += f"- 오류: {len(errors)}건\n"
    msg += "- 상세: /seller/pricing/history"

    try:
        from src.notifications.telegram import send_telegram
        send_telegram(msg, urgency="info")
    except Exception as exc:
        logger.warning("재가격 알림 전송 실패: %s", exc)

    # Resend 이메일 요약
    try:
        from src.notifications.email_resend import send_email
        send_email(
            to=os.getenv("ADMIN_EMAIL", ""),
            subject=f"[proxy-commerce] 자동 재가격 완료 — {changed}건 변경",
            html=f"<pre>{msg}</pre>",
        )
    except Exception as exc:
        logger.debug("재가격 이메일 발송 실패 (무시): %s", exc)
