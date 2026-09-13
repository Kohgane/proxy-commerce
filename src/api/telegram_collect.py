"""src/api/telegram_collect.py — **폰 기본 수집 입구**(C-F17-B). 봇에 붙여넣으면 담긴다.

## 왜 기본 입구가 됐나 (실측)

폰 단축어가 상하이에서 VPN on/off·서버 변경과 **무관하게** 「네트워크 연결 유실」이었다.
같은 순간 PC curl은 **HTTP 200 · 2.5초**였다 — 서버는 멀쩡했다. 우리 앞단은 Cloudflare(Render)고
중국 셀룰러에서 거기까지 닿느냐는 **우리 통제 밖**이다. 그래서 우리가 못 고치는 구간을 통과하는
경로를 기본으로 삼는다: 폰 → 텔레그램 → (텔레그램 인프라) → 우리 웹훅.
단축어는 남겨 두되 **선택**이다.

## 왜 CS 웹훅과 따로인가

`/webhooks/telegram/cs`는 **고객** 문의를 인박스에 쌓는 경로다. 여기는 **셀러가 자기 봇에게**
상품을 던지는 경로 — 쓰기 권한도 대상도 완전히 다르다. 한 핸들러에 섞으면 고객 문의가
수집으로, 수집이 CS 티켓으로 새어 나간다.

## 두 겹 잠금

  ① 웹훅 시크릿 — 텔레그램이 보낸 게 맞는지(`X-Telegram-Bot-Api-Secret-Token`).
     미설정이면 **아무것도 하지 않는다**(열어두지 않는다).
  ② 계정 바인딩 — `/link <API 토큰>` 1회로 chat을 계정에 묶는다. **묶이지 않은 chat은 못 담는다.**
     토큰은 검증에만 쓰고 **저장하지 않는다**(원문 저장 0). 바인딩 사실만 남는다.

`TELEGRAM_COLLECT_CHAT_IDS`(선택)를 두면 그 chat들로 **더 좁힐** 수 있다 — 넓히지는 않는다.

## 수집은 새로 만들지 않는다

`collect_input()` 한 함수만 부른다(C-F1의 단일 판단점). 회신 문장도
`share_text.collect_reply_text()` 한 곳에서 만든다 — 입구가 둘이어도 문장은 하나여야
같은 상품을 두 경로로 담았을 때 사람이 오해하지 않는다.
"""
from __future__ import annotations

import logging
import os
import time

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

bp = Blueprint("telegram_collect", __name__)

# 메시지에 이 말이 섞여 있으면 검수 판정까지(없으면 수집만 — 판정은 느리다).
_REVIEW_WORDS = ("검수", "판정", "review")

# `/link` 토큰 무차별 대입 완화 — chat별 실패 횟수(프로세스 내, 워커별).
#   완벽한 잠금이 아니다(워커가 여럿이면 각자 센다). 토큰이 60자 hex라 추측 자체가 어렵고,
#   이건 "무한히 두드릴 수는 없게" 하는 얕은 턱이다. 그 이상이라고 말하지 않는다.
_LINK_FAILS: dict[str, list] = {}
_LINK_FAIL_MAX = 5
_LINK_FAIL_WINDOW_SEC = 600

_HELP = (
    "고가브릿지 수집 봇입니다.\n"
    "1) 처음 한 번: /link 다음에 콘솔에서 발급한 API 토큰을 붙여 주세요.\n"
    "   (콘솔 → 설정 → 내 정보·설정 → API 토큰)\n"
    "2) 그다음부터: 타오바오 앱에서 복사한 공유 글을 그대로 붙여넣으면 담깁니다.\n"
    "중국에서는 VPN을 켜고 보내 주세요."
)


def _allowed_chat_ids() -> set:
    """더 좁히고 싶을 때만 쓰는 선택 허용목록. 비어 있으면 **좁히지 않는다**(바인딩이 잠금이다)."""
    raw = os.getenv("TELEGRAM_COLLECT_CHAT_IDS", "")
    return {c.strip() for c in raw.replace(";", ",").split(",") if c.strip()}


def _seller_id_for(chat_id: str) -> str:
    """chat_id → 저장 스코프(seller_id).

    정본은 `/link` 바인딩이다. `TELEGRAM_COLLECT_SELLER_ID`는 바인딩 이전에 쓰던 레거시 —
    바인딩이 있으면 그쪽이 이긴다. 둘 다 없으면 빈 문자열 → 호출부가 **정직 거절**한다
    (아무 스코프에나 쓰면 남의 수집 이력에 섞인다).
    """
    try:
        from src.db.telegram_links_pg import user_id_for
        bound = user_id_for(chat_id)
        if bound:
            return bound
    except Exception as exc:
        logger.warning("텔레그램 바인딩 조회 실패: %s", exc)
    return os.getenv("TELEGRAM_COLLECT_SELLER_ID", "").strip()


def _bot_token() -> str:
    """이 입구가 쓸 봇 토큰. **수집 전용 봇**(`TELEGRAM_COLLECT_BOT_TOKEN`)이 정본이다.

    C-F17b: **봇 하나는 웹훅이든 폴링이든 업데이트 수신구를 하나만 갖는다**(텔레그램 규칙).
    한 토큰을 나눠 쓰면 나중에 건 쪽이 앞의 것을 **말없이 덮는다**:

      · 폴링으로 도는 봇(오너 트렌드 봇의 GO 승인)에 웹훅을 걸면 `getUpdates`가 409로 죽는다.
      · 이 레포 안에도 수신구가 셋이다 — `/webhook/telegram`(봇 명령)·`/webhooks/telegram/cs`(CS)·
        `/webhooks/telegram/collect`(수집). 한 봇에 셋을 다 걸 수는 없다.

    그래서 수집 봇은 **따로 판다**(오너 결정). 전용 토큰이 없으면 공용 토큰으로 보내기는 하되,
    그건 '보내기'만 안전하고 **웹훅 등록이 위험하다**는 걸 로그로 남긴다(조용히 넘어가지 않는다).
    """
    tok = os.getenv("TELEGRAM_COLLECT_BOT_TOKEN", "").strip()
    if tok:
        return tok
    shared = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if shared and not _bot_token._warned:
        logger.warning("수집 전용 봇 토큰(TELEGRAM_COLLECT_BOT_TOKEN) 미설정 — 공용 봇으로 답장한다. "
                       "공용 봇에 수집 웹훅을 걸면 그 봇의 기존 수신구(폴링·다른 웹훅)가 죽는다.")
        _bot_token._warned = True
    return shared


_bot_token._warned = False       # 매 요청 같은 경고를 쌓지 않는다


def _api(method: str, payload: dict) -> dict:
    """봇 API 한 번. 실패는 삼키되 **무엇이 실패했는지는 남긴다**(토큰 값은 로그에 없다)."""
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        logger.info("ADAPTER_DRY_RUN=1 — 텔레그램 %s 차단", method)
        return {}
    token = _bot_token()
    if not token:
        logger.warning("봇 토큰 미설정(TELEGRAM_COLLECT_BOT_TOKEN) — 봇 답장 불가")
        return {}
    try:
        import requests
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=5)
        if not r.ok:
            logger.warning("텔레그램 %s 실패 HTTP %s", method, r.status_code)
            return {}
        return r.json() or {}
    except Exception as exc:
        logger.warning("텔레그램 %s 오류: %s", method, exc)
        return {}


def _reply(chat_id: str, text: str) -> bool:
    """**보낸 사람에게** 답한다.

    예전엔 `notifications.send_telegram`을 썼는데 그건 `TELEGRAM_CHAT_ID`(고정 알림방)로 가고
    앞에 이모지와 `[proxy-commerce]`를 붙인다 — 답장이 엉뚱한 방으로 가고, 일반 사용자에게
    내부 표기가 노출된다. 여기선 요청한 chat으로 **평문 그대로** 보낸다(`parse_mode` 없음 —
    마크다운을 해석시키지 않는다).
    """
    if not chat_id:
        return False
    return bool(_api("sendMessage", {"chat_id": chat_id, "text": text}).get("ok"))


def _delete_message(chat_id: str, message_id) -> bool:
    """토큰이 적힌 메시지를 지운다. **지워졌는지는 응답으로 확인**한다(지웠다고 단정하지 않는다)."""
    if not (chat_id and message_id):
        return False
    return bool(_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id}).get("ok"))


def _link_rate_limited(chat_id: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _LINK_FAILS.get(chat_id, []) if now - t < _LINK_FAIL_WINDOW_SEC]
    _LINK_FAILS[chat_id] = hits
    return len(hits) >= _LINK_FAIL_MAX


def _handle_link(chat_id: str, text: str, message_id) -> tuple:
    """`/link <API 토큰>` — chat을 계정에 묶는다. 토큰은 검증만 하고 **저장하지 않는다**."""
    raw = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
    if not raw:
        _reply(chat_id, "사용법: /link 다음에 콘솔에서 발급한 API 토큰을 붙여 주세요.\n"
                        "콘솔 → 설정 → 내 정보·설정 → API 토큰 (/seller/me/tokens)")
        return jsonify({"ok": True, "skipped": "no_token"})

    if _link_rate_limited(chat_id):
        _reply(chat_id, "연결 시도가 너무 잦습니다. 10분 뒤에 다시 시도해 주세요.")
        return jsonify({"ok": False, "error": "rate_limited"}), 429

    from src.auth.personal_tokens import validate_token
    info = validate_token(raw, ["collect.write"]) or {}
    uid = str(info.get("user_id") or "").strip()
    # 토큰이 적힌 메시지는 성패와 무관하게 지운다 — 채팅 기록에 남기지 않는다.
    deleted = _delete_message(chat_id, message_id)
    tail = ("방금 보낸 토큰 메시지는 지웠습니다."
            if deleted else "방금 보낸 토큰 메시지는 직접 지워 주세요(봇이 지우지 못했습니다).")
    if not uid:
        _LINK_FAILS.setdefault(chat_id, []).append(time.monotonic())
        _reply(chat_id, f"토큰이 유효하지 않거나 만료됐습니다. 콘솔에서 새로 발급해 주세요.\n{tail}")
        return jsonify({"ok": False, "error": "invalid_token"}), 403

    from src.db.telegram_links_pg import link
    if not link(chat_id, uid):
        _reply(chat_id, f"연결을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.\n{tail}")
        return jsonify({"ok": False, "error": "link_not_saved"}), 503

    from src.auth.account_label import account_label
    label = account_label(uid)
    who = f"{label} 계정에 연결됐습니다." if label else "계정에 연결됐습니다."
    _reply(chat_id, f"{who}\n이제 타오바오 공유 글을 그대로 붙여넣으면 담깁니다.\n{tail}")
    return jsonify({"ok": True, "linked": True})


@bp.post("/webhooks/telegram/collect")
def telegram_collect():
    """봇에 붙여넣은 공유 글을 담는다(+'검수'가 섞였으면 판정까지).

    설정이 빠져 있으면 **담지 않고 무엇이 빠졌는지 답한다** — 조용히 삼키지 않는다.
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
    message_id = message.get("message_id")
    if not chat_id:
        return jsonify({"ok": True, "skipped": "no_chat"})

    allowed = _allowed_chat_ids()
    if allowed and chat_id not in allowed:
        # 좁히기로 한 경우에만 막는다. 답장도 하지 않는다(누가 두드리는지 알려줄 필요 없다).
        logger.warning("텔레그램 수집: 허용목록 밖 chat")
        return jsonify({"ok": False, "error": "not_allowed"}), 403

    low = text.lower()
    if low.startswith("/link"):
        return _handle_link(chat_id, text, message_id)
    if low.startswith("/unlink"):
        from src.db.telegram_links_pg import unlink
        _reply(chat_id, "연결을 해제했습니다." if unlink(chat_id) else "연결돼 있지 않습니다.")
        return jsonify({"ok": True})
    if low.startswith("/start") or low.startswith("/help"):
        _reply(chat_id, _HELP)
        return jsonify({"ok": True})
    if low.startswith("/whoami"):
        from src.auth.account_label import account_label
        label = account_label(_seller_id_for(chat_id))
        _reply(chat_id, f"{label} 계정에 연결돼 있습니다." if label
               else "연결된 계정이 없습니다. /link 다음에 API 토큰을 붙여 주세요.")
        return jsonify({"ok": True})

    # 링크가 아예 없는 말(인사·잡담)은 **실패가 아니다.** 연결 여부를 따지기 전에
    #   무엇을 보내면 되는지 알려 준다 — 「연결 안 됨」이라고 답하면 엉뚱한 데를 고치게 된다.
    from src.collectors.share_text import parse_share_text
    if not parse_share_text(text).get("url"):
        _reply(chat_id, "상품 링크를 찾지 못했어요. 링크나 앱 공유 텍스트를 그대로 보내주세요. "
                        "'검수'를 같이 쓰면 판매가·마진까지 알려드려요.")
        return jsonify({"ok": True, "skipped": "no_url"})

    seller_id = _seller_id_for(chat_id)
    if not seller_id:
        _reply(chat_id, "아직 계정에 연결돼 있지 않아 담지 않았습니다.\n" + _HELP)
        return jsonify({"ok": False, "error": "not_linked"}), 403

    # 중복 — 기존 정규화 키(v42 1-3) 그대로. 같은 상품을 두 번 쌓지 않는다.
    #   (`collect_input`은 중복을 보지 않는다 — 그건 호출부 몫이다.)
    try:
        from src.seller_console.collect_history_store import find_by_product_key
        dup = find_by_product_key(parse_share_text(text)["url"], seller_ids={seller_id})
        if dup:
            _reply(chat_id, f"이미 수집한 상품입니다 — {dup.get('title') or ''}".strip(" —"))
            return jsonify({"ok": True, "duplicate": True, "item_id": dup.get("id")})
    except Exception as exc:
        logger.warning("텔레그램 수집 중복 조회 실패: %s", exc)

    # 갈래 판단·수집·문장은 전부 공용 코어가 한다 — 여기 제 사본을 두면 입구마다 갈라진다.
    from src.collectors.share_collect import collect_input
    res = collect_input(text, seller_id=seller_id, source="telegram")
    if not res.get("ok"):
        _reply(chat_id, _reply_text(res, seller_id))
        return jsonify({"ok": False, "error": res.get("error")}), 502

    try:
        from src.db.telegram_links_pg import touch
        touch(chat_id)
    except Exception:
        pass

    verdict = None
    out = _reply_text(res, seller_id)
    if any(w in low for w in _REVIEW_WORDS):
        from src.api.extension_api import _review_verdict
        verdict = _review_verdict(res.get("url", ""))
        out = f"{out}\n{_format_verdict(verdict)}"
    _reply(chat_id, out)
    return jsonify({"ok": True, "item_id": res.get("item_id"),
                    "title": res.get("title_ko") or res.get("title", ""),
                    "kind": res.get("kind", ""), "review": verdict})


def _reply_text(res: dict, seller_id: str) -> str:
    """회신 문장 — 단축어와 **같은 한 곳**에서 만든다. 계정은 실명, 못 찾으면 그 줄 생략."""
    from src.auth.account_label import account_label
    from src.collectors.share_text import collect_reply_text
    return collect_reply_text(res, account=account_label(seller_id))


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
