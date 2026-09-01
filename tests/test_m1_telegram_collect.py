"""tests/test_m1_telegram_collect.py — M1-3: 텔레그램 수집 인바운드.

**왜 CS 웹훅과 따로인가:** `/webhooks/telegram/cs`는 **고객** 문의를 인박스에 쌓는다.
여기는 **오너가 자기 봇에게** 상품 URL을 던지는 경로 — 대상도 쓰기 권한도 다르다.
한 핸들러에 섞으면 고객 문의가 수집으로, 수집이 CS 티켓으로 새어 나간다.

**쓰기 경로라 두 겹으로 잠근다:** 웹훅 시크릿 + 발신자 허용목록.
시크릿만으로는 URL을 아는 누구나 우리 수집 이력에 쓸 수 있다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.api import telegram_collect as tg

SECRET = "s3cr3t-webhook"
CHAT = "123456789"


@pytest.fixture
def client(monkeypatch):
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    monkeypatch.setenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_COLLECT_CHAT_IDS", CHAT)
    monkeypatch.setenv("TELEGRAM_COLLECT_SELLER_ID", "u1")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    """실제 텔레그램 전송 차단 + 답장 캡처."""
    sent = []
    monkeypatch.setattr(tg, "_reply", lambda chat_id, text: sent.append(text) or True)
    tg._sent = sent
    yield sent


def _post(client, text, *, secret=SECRET, chat=CHAT):
    return client.post("/webhooks/telegram/collect",
                       json={"message": {"text": text, "chat": {"id": chat}}},
                       headers={"X-Telegram-Bot-Api-Secret-Token": secret})


def _ok_collect(monkeypatch, title="PopSockets 그립톡"):
    monkeypatch.setattr("src.api.extension_api.collect_one_url",
                        lambda url, seller_id="", source="": {
                            "url": url, "ok": True, "item_id": "it-1", "title": title})


# ── 잠금 두 겹 ────────────────────────────────────────────────────────────────

def test_wrong_secret_is_rejected(client):
    assert _post(client, "https://x.com/dp/1", secret="nope").status_code == 403


def test_missing_secret_config_refuses_instead_of_opening(client, monkeypatch):
    """★ 시크릿 미설정 = 잠금 장치 없음 → **열어두지 않는다**(503)."""
    monkeypatch.delenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", raising=False)
    r = _post(client, "https://x.com/dp/1", secret="")
    assert r.status_code == 503 and "시크릿" in r.get_json()["error"]


def test_unknown_sender_is_rejected(client, monkeypatch):
    """★ 시크릿을 통과해도 **허용된 chat_id가 아니면** 쓰지 않는다."""
    _ok_collect(monkeypatch)
    r = _post(client, "https://x.com/dp/1", chat="999")
    assert r.status_code == 403 and r.get_json()["error"] == "not_allowed"


def test_empty_allowlist_allows_nobody(client, monkeypatch):
    """허용목록 미설정 = 아무도 못 쓴다(기본이 '열림'이 아니다)."""
    monkeypatch.setenv("TELEGRAM_COLLECT_CHAT_IDS", "")
    assert _post(client, "https://x.com/dp/1").status_code == 403


# ── 수집 ──────────────────────────────────────────────────────────────────────

def test_url_in_message_is_collected(client, monkeypatch, _quiet):
    _ok_collect(monkeypatch)
    r = _post(client, "이거 좀 봐줘 https://www.amazon.com/dp/B0T1 어때?")
    d = r.get_json()
    assert d["ok"] is True and d["item_id"] == "it-1"
    assert "수집됨" in _quiet[0]


def test_no_url_gets_guidance_not_silence(client, _quiet):
    """URL이 없으면 조용히 삼키지 않고 **무엇을 보내야 하는지** 알려준다."""
    r = _post(client, "안녕")
    assert r.get_json()["skipped"] == "no_url"
    assert "URL" in _quiet[0] and "검수" in _quiet[0]


def test_missing_seller_scope_refuses_to_guess(client, monkeypatch, _quiet):
    """★ 저장 스코프 미설정이면 **아무 스코프에나 쓰지 않는다** — 남의 이력에 섞인다."""
    monkeypatch.delenv("TELEGRAM_COLLECT_SELLER_ID", raising=False)
    r = _post(client, "https://x.com/dp/1")
    assert r.status_code == 503 and r.get_json()["error"] == "seller_scope_missing"
    assert "저장하지 않았습니다" in _quiet[0]


def test_collect_failure_is_honest(client, monkeypatch, _quiet):
    """수집 실패는 사유를 그대로 전하고 다음 행동을 알려준다(가짜 성공 0)."""
    monkeypatch.setattr("src.api.extension_api.collect_one_url",
                        lambda url, seller_id="", source="": {
                            "url": url, "ok": False, "error": "봇 차단(403)"})
    r = _post(client, "https://x.com/dp/1")
    assert r.status_code == 502
    assert "봇 차단" in _quiet[0] and "확장" in _quiet[0]


def test_duplicate_uses_existing_key(client, monkeypatch, _quiet):
    """중복은 기존 정규화 키로 잡는다 — 같은 상품을 두 번 쌓지 않는다."""
    monkeypatch.setattr("src.seller_console.collect_history_store.find_by_product_key",
                        lambda url, seller_id=None, seller_ids=None: {"id": "old-1",
                                                                      "title": "이미 있음"})
    r = _post(client, "https://x.com/dp/1")
    assert r.get_json()["duplicate"] is True
    assert "이미 수집한 상품" in _quiet[0]


# ── 검수 판정(M1-2 연결) ──────────────────────────────────────────────────────

def test_review_is_opt_in_by_keyword(client, monkeypatch, _quiet):
    """'검수'가 섞였을 때만 판정까지 — 판정은 느리다."""
    _ok_collect(monkeypatch)
    monkeypatch.setattr("src.api.extension_api._review_verdict",
                        lambda url: {"ok": True, "excluded": False, "sale_krw": 19900,
                                     "margin_pct": 27.4, "ship_status": "배송가능"})
    plain = _post(client, "https://x.com/dp/1").get_json()
    assert plain.get("review") is None

    _quiet.clear()
    withrv = _post(client, "https://x.com/dp/2 검수").get_json()
    assert withrv["review"]["ok"] is True
    assert "판매가 19,900원" in _quiet[0] and "27.4%" in _quiet[0]


def test_excluded_verdict_carries_reason(client, monkeypatch, _quiet):
    _ok_collect(monkeypatch)
    monkeypatch.setattr("src.api.extension_api._review_verdict",
                        lambda url: {"ok": True, "excluded": True, "reason": "금지어 '레플리카'"})
    _post(client, "https://x.com/dp/3 검수")
    assert "취급 제외" in _quiet[0] and "레플리카" in _quiet[0]


def test_missing_numbers_are_not_faked(client, monkeypatch, _quiet):
    """★ 숫자가 없으면 **없다고 쓴다** — 0으로 채우지 않는다."""
    _ok_collect(monkeypatch)
    monkeypatch.setattr("src.api.extension_api._review_verdict",
                        lambda url: {"ok": True, "excluded": False,
                                     "sale_krw": None, "margin_pct": None})
    _post(client, "https://x.com/dp/4 검수")
    assert "판매가 미산출" in _quiet[0] and "마진 미반영" in _quiet[0]
    assert "0원" not in _quiet[0]


# ── 구조 ──────────────────────────────────────────────────────────────────────

def test_separate_from_cs_webhook_and_reuses_core():
    """★ CS 경로와 분리 + 수집·검수 코어 재사용(이중 구현 0)."""
    src = Path("src/api/telegram_collect.py").read_text(encoding="utf-8")
    assert "/webhooks/telegram/collect" in src
    assert "cs_bot" not in src and "InboxStore" not in src      # CS 인박스와 섞이지 않는다
    assert "collect_one_url" in src and "_review_verdict" in src
    for reinvented in ("history_append", "build_source_review", "dispatcher_collect"):
        assert reinvented not in src, reinvented
