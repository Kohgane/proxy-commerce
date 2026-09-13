"""src/api/telegram_collect.py — **폰 기본 수집 입구**(C-F17/F18). 봇에 붙여넣으면 담긴다.

## 왜 기본 입구가 됐나 (실측)

폰 단축어가 상하이에서 VPN on/off·서버 변경과 **무관하게** 「네트워크 연결 유실」이었다.
같은 순간 PC curl은 **HTTP 200 · 2.5초**였다 — 서버는 멀쩡했다. 우리 앞단은 Cloudflare(Render)고
중국 셀룰러에서 거기까지 닿느냐는 **우리 통제 밖**이다. 그래서 우리가 못 고치는 구간을 통과하는
경로를 기본으로 삼는다: 폰 → 텔레그램 → (텔레그램 인프라) → 우리 웹훅.
단축어는 남겨 두되 **선택**이다.

## 누가 쓰나 (F18)

**고가브릿지 계정이 있는 누구나.** 자기 봇 채팅에서 담으면 **자기 계정**에 저장된다.
`/link <API 토큰>` 1회가 그 chat을 계정에 묶는다. 묶이지 않은 chat은 담지 못한다 —
「연결된 chat이 곧 허용목록」이고, 서버 env로 사람을 하나하나 적어 두지 않는다.

## 왜 키가 (봇, chat_id)인가

한 사람이 봇 둘로 **콘솔 로그인 둘**(고가네/우주대행)을 따로 쓴다. 같은 텔레그램 계정이라
chat_id는 같은데 담길 계정이 다르다 — chat_id만으로 키를 잡으면 둘 중 하나가 다른 하나를
덮는다. 그래서 웹훅 경로가 `/webhooks/telegram/collect/<bot_slug>`이고, 봇마다
토큰·시크릿 env가 따로다.

## 왜 CS 웹훅과 따로인가

`/webhooks/telegram/cs`는 **고객** 문의를 인박스에 쌓는 경로다. 여기는 **셀러가 자기 봇에게**
상품을 던지는 경로 — 쓰기 권한도 대상도 완전히 다르다. 한 핸들러에 섞으면 고객 문의가
수집으로, 수집이 CS 티켓으로 새어 나간다.

## 두 겹 잠금

  ① 웹훅 시크릿 — 텔레그램이 보낸 게 맞는지(`X-Telegram-Bot-Api-Secret-Token`).
     미설정이면 **아무것도 하지 않는다**(열어두지 않는다).
  ② 계정 바인딩 — `/link`로 묶인 chat만 담을 수 있다. 토큰은 **해시만** 남기고
     매번 다시 확인한다 — 콘솔에서 토큰을 폐기하면 **매핑도 따라 무효**여야 한다.
     (지웠는데 봇이 계속 담기면, 지운 사람이 믿는 것이 사실이 아니게 된다.)

## 수집은 새로 만들지 않는다

`collect_input()` 한 함수만 부른다(C-F1의 단일 판단점). 회신 문장도
`share_text.collect_reply_text()` 한 곳에서 만든다 — 입구가 둘이어도 문장은 하나여야
같은 상품을 두 경로로 담았을 때 사람이 오해하지 않는다.
"""
from __future__ import annotations

import logging
import os
import re
import time

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

bp = Blueprint("telegram_collect", __name__)

# ---------------------------------------------------------------------------
# 사용자에게 나가는 문장 — **여기 한 곳**. 회신 언어는 한국어 고정(오너 2026-09-13).
#   언어 감지·계정 언어 참조는 하지 않는다. 나중에 다국어를 붙일 자리도 여기 한 곳이다.
#   (문장이 코드 곳곳에 흩어지면 말투가 갈리고, 고칠 때 한 군데를 빼먹는다 —
#    `gap_message`를 한 곳에 둔 것과 같은 이유.)
# ---------------------------------------------------------------------------
MSG = {
    "help": ("고가브릿지 수집 봇입니다.\n"
             "1) 처음 한 번: /link 다음에 콘솔에서 발급한 API 토큰을 붙여 주세요.\n"
             "   (콘솔 → 설정 → 내 정보·설정 → API 토큰)\n"
             "2) 그다음부터: 타오바오 앱에서 복사한 공유 글을 그대로 붙여넣으면 담깁니다.\n"
             "중국에서는 VPN을 켜고 보내 주세요."),
    "link_usage": ("사용법: /link 다음에 콘솔에서 발급한 API 토큰을 붙여 주세요.\n"
                   "콘솔 → 설정 → 내 정보·설정 → API 토큰 (/seller/me/tokens)"),
    "link_ok": "{account} 계정에 연결됐어요.\n이제 타오바오 공유 글을 그대로 붙여넣으면 담깁니다.\n{tail}",
    "link_ok_noname": "계정에 연결됐어요.\n이제 타오바오 공유 글을 그대로 붙여넣으면 담깁니다.\n{tail}",
    "link_bad_token": "토큰이 유효하지 않거나 만료됐습니다. 콘솔에서 새로 발급해 주세요.\n{tail}",
    "link_not_saved": "연결을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.\n{tail}",
    "link_locked": "연결 시도가 너무 잦습니다. 10분 뒤에 다시 시도해 주세요.",
    "token_msg_deleted": "이 메시지의 토큰은 지웠습니다.",
    "token_msg_delete_yourself": "이 메시지의 토큰은 직접 삭제하세요(봇이 지우지 못했습니다).",
    "unlinked": "연결을 해제했어요.",
    "not_linked_at_all": "연결돼 있지 않습니다.",
    "whoami": "{account} 계정에 연결돼 있어요.",
    "whoami_none": "연결된 계정이 없습니다. /link 다음에 API 토큰을 붙여 주세요.",
    "need_link": ("/link 토큰 으로 계정을 먼저 연결하세요 "
                  "(콘솔 → 내 정보·설정 → API 토큰)."),
    "token_revoked": ("연결에 쓰던 토큰이 콘솔에서 삭제돼 연결이 풀렸습니다.\n"
                      "/link 다음에 새 토큰을 붙여 다시 연결해 주세요."),
    "no_url": ("상품 링크를 찾지 못했어요. 링크나 앱 공유 텍스트를 그대로 보내주세요. "
               "'검수'를 같이 쓰면 판매가·마진까지 알려드려요."),
    "duplicate": "이미 수집한 상품입니다 — {title}",
    "duplicate_noname": "이미 수집한 상품입니다.",
    "rate_minute": "잠시만요 — 1분에 {limit}건까지 담을 수 있어요. 조금 뒤에 다시 보내 주세요.",
    "rate_day": "오늘은 {limit}건까지 담았습니다. 내일 다시 이어서 담아 주세요.",
    # 검수 판정 한 줄 — 숫자가 없으면 **없다고 쓴다**(0으로 채우지 않는다).
    "verdict_failed": "검수 판정 실패 — {reason}",
    "verdict_excluded": "취급 제외 — {reason}",
    "verdict_head": "검수 통과",
    "verdict_reason_unknown": "사유 미상",
    "verdict_sale": "판매가 {won:,}원",
    "verdict_sale_none": "판매가 미산출",
    "verdict_margin": "실마진 {pct}%",
    "verdict_margin_none": "마진 미반영",
    "verdict_ship": "배송 {status}",
}

# 메시지에 이 말이 섞여 있으면 검수 판정까지(없으면 수집만 — 판정은 느리다).
_REVIEW_WORDS = ("검수", "판정", "review")

# 봇 이름표 — 경로 조각이 곧 env 이름이 되므로 **엄격히** 제한한다.
#   (임의 문자열이 환경변수 조회로 들어가면 안 된다.)
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
DEFAULT_BOT_SLUG = "default"

# 남용 방어 — (봇, chat)별. **프로세스 안에서만** 센다(워커가 여럿이면 각자 센다) —
#   완벽한 잠금이 아니라 "무한히 두드릴 수는 없게" 하는 얕은 턱이다. 그 이상이라고 말하지 않는다.
RATE_PER_MINUTE = 10
RATE_PER_DAY = 300
_RATE: dict[tuple, list] = {}

# `/link` 토큰 무차별 대입 — 실패 5회면 10분 잠금(같은 얕은 턱).
LINK_FAIL_MAX = 5
LINK_FAIL_WINDOW_SEC = 600
_LINK_FAILS: dict[tuple, list] = {}

# 미연결 chat에게는 **한 번만** 안내하고 그다음부터 침묵한다 —
#   모르는 사람이 두드릴 때마다 답하면 그게 곧 확성기가 된다.
_GUIDED: set = set()


def reset_runtime_state() -> None:
    """프로세스 내 카운터·안내 기록 비우기(계약·테스트용)."""
    _RATE.clear()
    _LINK_FAILS.clear()
    _GUIDED.clear()
    _bot_token._warned = False


# ---------------------------------------------------------------------------
# 봇 식별 — 경로 조각(bot_slug) → 토큰·시크릿
# ---------------------------------------------------------------------------

def _env_suffix(slug: str) -> str:
    return slug.upper().replace("-", "_")


def _bot_token(slug: str = DEFAULT_BOT_SLUG) -> str:
    """이 봇이 답장에 쓸 토큰.

    C-F17b: **봇 하나는 웹훅이든 폴링이든 업데이트 수신구를 하나만** 갖는다(텔레그램 규칙).
    한 토큰을 나눠 쓰면 나중에 건 쪽이 앞의 것을 **말없이 덮는다**:

      · 폴링으로 도는 `KOHGANE시장동향`에 웹훅을 걸면 `getUpdates`가 409로 죽는다.
      · 이 레포 안에도 수신구가 셋이다 — `/webhook/telegram`(봇 명령)·`/webhooks/telegram/cs`(CS)·
        `/webhooks/telegram/collect`(수집). 한 봇에 셋을 다 걸 수는 없다.

    찾는 순서: `TELEGRAM_COLLECT_BOT_TOKEN_<SLUG>` → `TELEGRAM_COLLECT_BOT_TOKEN`(기본 봇)
    → 공용 `TELEGRAM_BOT_TOKEN`. 마지막 폴백은 **보내기만** 안전하고 웹훅 등록은 위험하다 —
    그걸 로그로 남긴다(조용히 넘어가지 않는다).
    """
    tok = os.getenv(f"TELEGRAM_COLLECT_BOT_TOKEN_{_env_suffix(slug)}", "").strip()
    if tok:
        return tok
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


def _webhook_secret(slug: str = DEFAULT_BOT_SLUG) -> str:
    """이 봇의 웹훅 시크릿. 봇별 값이 없으면 공용 값."""
    return (os.getenv(f"TELEGRAM_COLLECT_WEBHOOK_SECRET_{_env_suffix(slug)}", "").strip()
            or os.getenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", "").strip())


# ---------------------------------------------------------------------------
# 봇 API
# ---------------------------------------------------------------------------

def _api(method: str, payload: dict, *, slug: str = DEFAULT_BOT_SLUG) -> dict:
    """봇 API 한 번. 실패는 삼키되 **무엇이 실패했는지는 남긴다**(토큰 값은 로그에 없다)."""
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        logger.info("ADAPTER_DRY_RUN=1 — 텔레그램 %s 차단", method)
        return {}
    token = _bot_token(slug)
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


def _reply(chat_id: str, text: str, *, slug: str = DEFAULT_BOT_SLUG) -> bool:
    """**보낸 사람에게** 답한다.

    예전엔 `notifications.send_telegram`을 썼는데 그건 `TELEGRAM_CHAT_ID`(고정 알림방)로 가고
    앞에 이모지와 내부 표기를 붙인다 — 답장이 엉뚱한 방으로 가고, 일반 사용자에게
    개발 표기가 노출된다. 여기선 요청한 chat으로 **평문 그대로** 보낸다(`parse_mode` 없음 —
    마크다운을 해석시키지 않는다).
    """
    if not chat_id:
        return False
    return bool(_api("sendMessage", {"chat_id": chat_id, "text": text}, slug=slug).get("ok"))


def _delete_message(chat_id: str, message_id, *, slug: str = DEFAULT_BOT_SLUG) -> bool:
    """토큰이 적힌 메시지를 지운다. **지워졌는지는 응답으로 확인**한다(지웠다고 단정하지 않는다)."""
    if not (chat_id and message_id):
        return False
    return bool(_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id},
                     slug=slug).get("ok"))


# ---------------------------------------------------------------------------
# 바인딩
# ---------------------------------------------------------------------------

def _legacy_seller_id(chat_id: str) -> str:
    """마이그레이션 기간 폴백 — 옛 env(`TELEGRAM_COLLECT_CHAT_IDS`/`SELLER_ID`).

    F18에서 허용목록 env는 폐지됐다(연결된 chat이 곧 허용). 다만 이미 그 env로 쓰던
    오너 chat이 배포 직후 막히면 안 되므로, **그 조합일 때만** 계정을 알려 주고
    호출부가 그 자리에서 바인딩으로 옮긴다(자동 매핑). 한쪽만 있으면 아무것도 안 한다.
    """
    raw = os.getenv("TELEGRAM_COLLECT_CHAT_IDS", "")
    allowed = {c.strip() for c in raw.replace(";", ",").split(",") if c.strip()}
    seller = os.getenv("TELEGRAM_COLLECT_SELLER_ID", "").strip()
    return seller if (seller and str(chat_id) in allowed) else ""


def _resolve_account(chat_id: str, slug: str) -> tuple:
    """`(user_id, 사유)` — 담을 수 있으면 user_id, 아니면 빈 문자열 + 왜인지.

    사유: `""`(정상) · `"not_linked"` · `"token_revoked"`.
    **토큰 해시로 매번 다시 확인한다** — 콘솔에서 폐기한 토큰의 매핑이 살아 있으면,
    지운 사람이 지웠다고 믿는 것이 사실이 아니게 된다.
    """
    from src.db import telegram_links_pg as tl

    row = {}
    try:
        row = tl.get(chat_id, bot_slug=slug)
    except Exception as exc:
        logger.warning("텔레그램 바인딩 조회 실패: %s", exc)

    if not row:
        legacy = _legacy_seller_id(chat_id)
        if legacy:
            # 옛 env로 쓰던 chat을 **그 자리에서** 바인딩으로 옮긴다(해시 없음 = 재확인 면제).
            try:
                tl.link(chat_id, legacy, bot_slug=slug, token_hash="")
                logger.info("텔레그램 레거시 env chat을 바인딩으로 이관했다(bot=%s)", slug)
            except Exception as exc:
                logger.warning("레거시 바인딩 이관 실패: %s", exc)
            return legacy, ""
        return "", "not_linked"

    uid, th = row.get("user_id", ""), row.get("token_hash", "")
    if th:
        try:
            from src.auth.personal_tokens import token_active
            if not token_active(uid, th):
                try:
                    tl.unlink(chat_id, bot_slug=slug)
                except Exception:
                    pass
                return "", "token_revoked"
        except Exception as exc:
            # 확인 자체가 실패한 것은 **폐기됐다는 뜻이 아니다** — 끊지 않는다.
            logger.warning("토큰 활성 확인 실패(연결 유지): %s", exc)
    return uid, ""


# ---------------------------------------------------------------------------
# 남용 방어
# ---------------------------------------------------------------------------

def _rate_block(slug: str, chat_id: str) -> str:
    """상한 초과면 안내 문장, 아니면 빈 문자열. 통과하면 그 시각을 기록한다."""
    now = time.monotonic()
    key = (slug, chat_id)
    hits = [t for t in _RATE.get(key, []) if now - t < 86400]
    if len([t for t in hits if now - t < 60]) >= RATE_PER_MINUTE:
        _RATE[key] = hits
        return MSG["rate_minute"].format(limit=RATE_PER_MINUTE)
    if len(hits) >= RATE_PER_DAY:
        _RATE[key] = hits
        return MSG["rate_day"].format(limit=RATE_PER_DAY)
    hits.append(now)
    _RATE[key] = hits
    return ""


def _link_locked(slug: str, chat_id: str) -> bool:
    now = time.monotonic()
    key = (slug, chat_id)
    hits = [t for t in _LINK_FAILS.get(key, []) if now - t < LINK_FAIL_WINDOW_SEC]
    _LINK_FAILS[key] = hits
    return len(hits) >= LINK_FAIL_MAX


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------

def _handle_link(slug: str, chat_id: str, text: str, message_id) -> tuple:
    """`/link <API 토큰>` — chat을 계정에 묶는다. 토큰은 **해시만** 남긴다."""
    parts = text.split(maxsplit=1)
    raw = parts[1].strip() if len(parts) > 1 else ""
    if not raw:
        _reply(chat_id, MSG["link_usage"], slug=slug)
        return jsonify({"ok": True, "skipped": "no_token"})

    if _link_locked(slug, chat_id):
        _reply(chat_id, MSG["link_locked"], slug=slug)
        return jsonify({"ok": False, "error": "rate_limited"}), 429

    from src.auth.personal_tokens import _hash_token, validate_token
    info = validate_token(raw, ["collect.write"]) or {}
    uid = str(info.get("user_id") or "").strip()

    # 토큰이 적힌 메시지는 성패와 무관하게 지운다 — 채팅 기록에 남기지 않는다.
    tail = (MSG["token_msg_deleted"] if _delete_message(chat_id, message_id, slug=slug)
            else MSG["token_msg_delete_yourself"])
    if not uid:
        _LINK_FAILS.setdefault((slug, chat_id), []).append(time.monotonic())
        _reply(chat_id, MSG["link_bad_token"].format(tail=tail), slug=slug)
        return jsonify({"ok": False, "error": "invalid_token"}), 403

    from src.db.telegram_links_pg import link
    if not link(chat_id, uid, bot_slug=slug, token_hash=info.get("token_hash") or _hash_token(raw)):
        _reply(chat_id, MSG["link_not_saved"].format(tail=tail), slug=slug)
        return jsonify({"ok": False, "error": "link_not_saved"}), 503

    _GUIDED.discard((slug, chat_id))
    from src.auth.account_label import account_label
    label = account_label(uid)
    body = (MSG["link_ok"].format(account=label, tail=tail) if label
            else MSG["link_ok_noname"].format(tail=tail))
    _reply(chat_id, body, slug=slug)
    return jsonify({"ok": True, "linked": True})


# ---------------------------------------------------------------------------
# 웹훅
# ---------------------------------------------------------------------------

@bp.post("/webhooks/telegram/collect")
def telegram_collect_default():
    """봇 이름표 없는 옛 경로 — 기본 봇으로 처리한다(기존 웹훅 등록을 깨지 않는다)."""
    return _handle_update(DEFAULT_BOT_SLUG)


@bp.post("/webhooks/telegram/collect/<bot_slug>")
def telegram_collect_for_bot(bot_slug: str):
    """봇마다 제 경로. 한 사람이 봇 둘로 **콘솔 로그인 둘**을 따로 쓰기 위한 것이다."""
    slug = str(bot_slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        # 경로 조각이 env 이름이 된다 — 모르는 모양은 받지 않는다.
        return jsonify({"ok": False, "error": "bad_bot_slug"}), 404
    return _handle_update(slug)


def _handle_update(slug: str):
    """봇에 붙여넣은 공유 글을 담는다(+'검수'가 섞였으면 판정까지).

    설정이 빠져 있으면 **담지 않고 무엇이 빠졌는지 답한다** — 조용히 삼키지 않는다.
    """
    expected = _webhook_secret(slug)
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected:
        # 시크릿 미설정 = 잠금 장치가 없다 → 열어두지 않는다(정직 거절).
        logger.warning("텔레그램 수집 웹훅 시크릿 미설정 — 요청 거절(bot=%s)", slug)
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

    low = text.lower()
    if low.startswith("/link"):
        return _handle_link(slug, chat_id, text, message_id)
    if low.startswith("/unlink"):
        from src.db.telegram_links_pg import unlink
        ok = unlink(chat_id, bot_slug=slug)
        _GUIDED.discard((slug, chat_id))
        _reply(chat_id, MSG["unlinked"] if ok else MSG["not_linked_at_all"], slug=slug)
        return jsonify({"ok": True})
    if low.startswith("/start") or low.startswith("/help"):
        _reply(chat_id, MSG["help"], slug=slug)
        return jsonify({"ok": True})
    if low.startswith("/whoami"):
        from src.auth.account_label import account_label
        uid, _why = _resolve_account(chat_id, slug)
        label = account_label(uid) if uid else ""
        _reply(chat_id, MSG["whoami"].format(account=label) if label else MSG["whoami_none"],
               slug=slug)
        return jsonify({"ok": True})

    # 링크가 아예 없는 말(인사·잡담)은 **실패가 아니다.** 연결 여부를 따지기 전에
    #   무엇을 보내면 되는지 알려 준다 — 「연결 안 됨」이라고 답하면 엉뚱한 데를 고치게 된다.
    from src.collectors.share_text import parse_share_text
    url = parse_share_text(text).get("url", "")
    if not url:
        _reply(chat_id, MSG["no_url"], slug=slug)
        return jsonify({"ok": True, "skipped": "no_url"})

    seller_id, why = _resolve_account(chat_id, slug)
    if not seller_id:
        # 토큰 폐기는 **상태가 바뀐 사건**이라 매번 말해 준다(사람이 다시 연결해야 하니까).
        #   그냥 미연결인 chat에는 **한 번만** 안내하고 이후 침묵한다 —
        #   모르는 사람이 두드릴 때마다 답하면 그게 곧 확성기가 된다.
        if why == "token_revoked":
            _reply(chat_id, MSG["token_revoked"], slug=slug)
        elif (slug, chat_id) not in _GUIDED:
            _GUIDED.add((slug, chat_id))
            _reply(chat_id, MSG["need_link"], slug=slug)
        return jsonify({"ok": False, "error": why or "not_linked"}), 403

    blocked = _rate_block(slug, chat_id)
    if blocked:
        _reply(chat_id, blocked, slug=slug)
        return jsonify({"ok": False, "error": "rate_limited"}), 429

    # 중복 — 기존 정규화 키(v42 1-3) 그대로. 같은 상품을 두 번 쌓지 않는다.
    #   (`collect_input`은 중복을 보지 않는다 — 그건 호출부 몫이다.)
    try:
        from src.seller_console.collect_history_store import find_by_product_key
        dup = find_by_product_key(url, seller_ids={seller_id})
        if dup:
            title = dup.get("title") or ""
            _reply(chat_id, MSG["duplicate"].format(title=title) if title
                   else MSG["duplicate_noname"], slug=slug)
            return jsonify({"ok": True, "duplicate": True, "item_id": dup.get("id")})
    except Exception as exc:
        logger.warning("텔레그램 수집 중복 조회 실패: %s", exc)

    # 갈래 판단·수집·문장은 전부 공용 코어가 한다 — 여기 제 사본을 두면 입구마다 갈라진다.
    from src.collectors.share_collect import collect_input
    res = collect_input(text, seller_id=seller_id, source="telegram")
    if not res.get("ok"):
        _reply(chat_id, _reply_text(res, seller_id), slug=slug)
        return jsonify({"ok": False, "error": res.get("error")}), 502

    try:
        from src.db.telegram_links_pg import touch
        touch(chat_id, bot_slug=slug)
    except Exception:
        pass

    verdict = None
    out = _reply_text(res, seller_id)
    if any(w in low for w in _REVIEW_WORDS):
        from src.api.extension_api import _review_verdict
        verdict = _review_verdict(res.get("url", ""))
        out = f"{out}\n{_format_verdict(verdict)}"
    _reply(chat_id, out, slug=slug)
    return jsonify({"ok": True, "item_id": res.get("item_id"),
                    "title": res.get("title_ko") or res.get("title", ""),
                    "kind": res.get("kind", ""), "review": verdict})


def _reply_text(res: dict, seller_id: str) -> str:
    """회신 문장 — 단축어와 **같은 한 곳**(`share_text.collect_reply_text`)에서 만든다.

    이 한 종류만 `MSG` 바깥에 있다. 일부러다 — 단축어 응답과 **글자 하나까지 같아야** 해서,
    입구별 상수가 아니라 **입구를 가로지르는 한 곳**에 둔다(C-F17-B).
    계정은 실명, 못 찾으면 그 줄 생략.
    """
    from src.auth.account_label import account_label
    from src.collectors.share_text import collect_reply_text
    return collect_reply_text(res, account=account_label(seller_id))


def _format_verdict(rv: dict) -> str:
    """검수 판정 → 한 줄 요약. 숫자가 없으면 없다고 쓴다(0으로 채우지 않는다).

    문장 조각도 전부 `MSG`에서 가져온다 — 여기 리터럴을 두면 말투가 갈리는 자리가 하나 늘어난다.
    """
    rv = rv or {}
    unknown = MSG["verdict_reason_unknown"]
    if not rv.get("ok"):
        return MSG["verdict_failed"].format(reason=rv.get("error") or rv.get("reason") or unknown)
    if rv.get("excluded"):
        return MSG["verdict_excluded"].format(reason=rv.get("reason") or unknown)

    sale, margin = rv.get("sale_krw"), rv.get("margin_pct")
    parts = [MSG["verdict_head"]]
    parts.append(MSG["verdict_sale"].format(won=sale)
                 if isinstance(sale, (int, float)) and sale else MSG["verdict_sale_none"])
    parts.append(MSG["verdict_margin"].format(pct=margin) if margin is not None
                 else MSG["verdict_margin_none"])
    if rv.get("ship_status"):
        parts.append(MSG["verdict_ship"].format(status=rv["ship_status"]))
    return " · ".join(parts)
