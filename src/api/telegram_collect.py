"""src/api/telegram_collect.py — M1-3: 텔레그램으로 소싱 URL 던지면 수집(+검수)한다.

**왜 CS 웹훅과 따로인가:** `/webhooks/telegram/cs`는 **고객** 문의를 인박스에 쌓는 경로다.
여기는 **오너가 자기 봇에게** 상품 URL을 던지는 경로 — 쓰기 권한도 대상도 완전히 다르다.
한 핸들러에 섞으면 고객 문의가 수집으로, 수집이 CS 티켓으로 새어 나간다.

**쓰기 경로라 두 겹으로 잠근다(둘 다 없으면 아무것도 안 한다):**
  ① 웹훅 시크릿 — 텔레그램이 보낸 게 맞는지(`X-Telegram-Bot-Api-Secret-Token`)
  ② 발신자 허용목록 — 그중에서도 **오너 chat_id만**(`TELEGRAM_COLLECT_CHAT_IDS`)
시크릿만 있으면 URL을 아는 누구나 우리 수집 이력에 쓸 수 있다.

수집·검수는 새로 만들지 않는다 — 확장·벌크·모바일이 쓰는 `collect_one_url`,
콘솔 화면이 쓰는 `build_review_for_urls`를 그대로 부른다(이중 구현 금지).
"""
from __future__ import annotations

import logging
import os
import re

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

bp = Blueprint("telegram_collect", __name__)

_URL_RE = re.compile(r"https?://[^\s]+")
# 메시지에 이 말이 섞여 있으면 검수 판정까지(없으면 수집만 — 판정은 느리다).
_REVIEW_WORDS = ("검수", "판정", "review")


def _allowed_chat_ids() -> set:
    """수집을 허용할 chat_id 집합. 미설정이면 **빈 집합 = 아무도 못 쓴다**(열어두지 않는다)."""
    raw = os.getenv("TELEGRAM_COLLECT_CHAT_IDS", "")
    return {c.strip() for c in raw.replace(";", ",").split(",") if c.strip()}


def _seller_id_for(chat_id: str) -> str:
    """chat_id → 저장 스코프(seller_id). 미설정이면 빈 문자열 → 호출부가 정직 거절한다.

    아무 스코프에나 쓰면 남의 수집 이력에 섞인다 — 추측해서 넣지 않는다.
    """
    return os.getenv("TELEGRAM_COLLECT_SELLER_ID", "").strip()


def _reply(chat_id: str, text: str) -> bool:
    """봇 답장. 실패해도 수집 결과에는 영향을 주지 않는다(알림은 부가)."""
    try:
        from src.notifications.telegram import send_telegram
        return send_telegram(text)
    except Exception as exc:
        logger.warning("텔레그램 답장 실패(chat=%s): %s", chat_id, exc)
        return False


def _format_verdict(rv: dict) -> str:
    """검수 판정 → 한 줄 요약. 숫자가 없으면 없다고 쓴다(0으로 채우지 않는다)."""
    if not rv or not rv.get("ok"):
        return f"검수 판정 실패 — {(rv or {}).get('error') or (rv or {}).get('reason') or '사유 미상'}"
    if rv.get("excluded"):
        return f"취급 제외 — {rv.get('reason') or '사유 미상'}"
    sale = rv.get("sale_krw")
    margin = rv.get("margin_pct")
    parts = ["검수 통과"]
    parts.append(f"판매가 {sale:,}원" if isinstance(sale, (int, float)) and sale else "판매가 미산출")
    parts.append(f"실마진 {margin}%" if margin is not None else "마진 미반영")
    if rv.get("ship_status"):
        parts.append(f"배송 {rv['ship_status']}")
    return " · ".join(parts)


@bp.post("/webhooks/telegram/collect")
def telegram_collect():
    """오너가 봇에게 던진 상품 URL을 수집한다(+'검수'가 섞였으면 판정까지).

    설정이 빠져 있으면 **수집하지 않고 무엇이 빠졌는지 답한다** — 조용히 삼키지 않는다.
    """
    expected = os.getenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", "")
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected:
        # 시크릿 미설정 = 잠금 장치가 없다 → 열어두지 않는다(정직 거절).
        logger.warning("텔레그램 수집 웹훅 시크릿 미설정 — 요청 거절")
        return jsonify({"ok": False, "error": "웹훅 시크릿 미설정"}), 503
    if expected != received:
        return jsonify({"ok": False, "error": "invalid_secret"}), 403

    payload = request.get_json(silent=True) or {}
    message = payload.get("message") or payload.get("edited_message") or {}
    text = str(message.get("text") or message.get("caption") or "").strip()
    chat_id = str((message.get("chat") or {}).get("id") or "")

    allowed = _allowed_chat_ids()
    if not allowed or chat_id not in allowed:
        # 발신자 미허용 — 답장도 하지 않는다(누가 두드리는지 알려줄 필요 없다).
        logger.warning("텔레그램 수집: 허용되지 않은 chat_id=%s", chat_id or "?")
        return jsonify({"ok": False, "error": "not_allowed"}), 403

    m = _URL_RE.search(text)
    if not m:
        _reply(chat_id, "상품 URL을 보내주세요. '검수'를 같이 쓰면 판매가·마진까지 알려드려요.")
        return jsonify({"ok": True, "skipped": "no_url"})

    url = m.group(0).strip()
    seller_id = _seller_id_for(chat_id)
    if not seller_id:
        _reply(chat_id, "수집 대상 계정이 설정돼 있지 않아 저장하지 않았습니다"
                        "(TELEGRAM_COLLECT_SELLER_ID). 설정 후 다시 보내주세요.")
        return jsonify({"ok": False, "error": "seller_scope_missing"}), 503

    # 중복 — 기존 정규화 키(v42 1-3) 그대로. 같은 상품을 두 번 쌓지 않는다.
    try:
        from src.seller_console.collect_history_store import find_by_product_key
        dup = find_by_product_key(url, seller_ids={seller_id})
        if dup:
            _reply(chat_id, f"이미 수집한 상품입니다 — {dup.get('title') or url}")
            return jsonify({"ok": True, "duplicate": True, "item_id": dup.get("id")})
    except Exception as exc:
        logger.warning("텔레그램 수집 중복 조회 실패: %s", exc)

    from src.api.extension_api import collect_one_url
    res = collect_one_url(url, seller_id=seller_id, source="telegram")
    if not res.get("ok"):
        # 정직 실패 — 사유를 그대로 전하고 다음 행동을 알려준다.
        _reply(chat_id, f"수집 실패 — {res.get('error') or '사유 미상'}\n"
                        f"봇 차단 사이트는 PC 확장 수집을 권합니다.")
        return jsonify({"ok": False, "error": res.get("error")}), 502

    lines = [f"수집됨 — {res.get('title') or url}"]
    verdict = None
    if any(w in text.lower() for w in _REVIEW_WORDS):
        from src.api.extension_api import _review_verdict
        verdict = _review_verdict(url)
        lines.append(_format_verdict(verdict))
    _reply(chat_id, "\n".join(lines))
    return jsonify({"ok": True, "item_id": res.get("item_id"),
                    "title": res.get("title", ""), "review": verdict})
