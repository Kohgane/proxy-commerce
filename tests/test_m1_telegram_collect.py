"""tests/test_m1_telegram_collect.py — M1-3: 텔레그램 수집 인바운드.

**왜 CS 웹훅과 따로인가:** `/webhooks/telegram/cs`는 **고객** 문의를 인박스에 쌓는다.
여기는 **오너가 자기 봇에게** 상품 URL을 던지는 경로 — 대상도 쓰기 권한도 다르다.
한 핸들러에 섞으면 고객 문의가 수집으로, 수집이 CS 티켓으로 새어 나간다.

**쓰기 경로라 두 겹으로 잠근다:** 웹훅 시크릿 + **계정 바인딩**(`/link <API 토큰>`).
시크릿만으로는 URL을 아는 누구나 우리 수집 이력에 쓸 수 있다.

C-F17-B에서 두 번째 겹이 **발신자 허용목록 → 계정 바인딩**으로 바뀌었다. 이유:
폰 기본 입구가 텔레그램이 되면서 셀러가 **스스로** 연결할 수 있어야 하는데, 허용목록은
오너가 서버 env에 chat_id를 미리 적어 둬야 열린다(자기 chat_id를 알 방법부터가 없다).
토큰 검증은 env 목록보다 **강한 증거**다 — 그 계정의 토큰을 가진 사람만 통과한다.
지키던 규율은 그대로다: **기본은 '열림'이 아니고, 스코프를 추측하지 않는다.**
허용목록(`TELEGRAM_COLLECT_CHAT_IDS`)은 남아 있되 **더 좁힐 때만** 쓴다.
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
    # C-F18: `_reply`가 봇 이름표(slug)를 함께 받는다 — 목도 그 모양이어야 한다.
    monkeypatch.setattr(tg, "_reply",
                        lambda chat_id, text, slug="default": sent.append(text) or True)
    tg._sent = sent
    yield sent


@pytest.fixture(autouse=True)
def _link_chat(monkeypatch):
    """C-F17-B: 저장 스코프의 정본은 `/link` 바인딩이다. 기존 계약들은 env 스코프를 전제로
    쓰였는데, 바인딩이 우선이라 **레거시 env가 그대로 먹히는지**도 함께 지키게 된다."""
    from src.db import telegram_links_pg as tl
    tl.reset_for_tests()
    tg.reset_runtime_state()
    yield
    tl.reset_for_tests()
    tg.reset_runtime_state()


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
    """★ 시크릿을 통과해도 **연결되지 않은 chat**이면 쓰지 않는다.

    C-F18: 허용목록 env는 폐지됐다 — 「연결된 chat이 곧 허용목록」이다(사유=헤더 주석).
    레거시 env 조합(`CHAT_IDS`+`SELLER_ID`)에 든 chat만 마이그레이션 폴백을 받는다.
    """
    _ok_collect(monkeypatch)
    r = _post(client, "https://x.com/dp/1", chat="999")
    assert r.status_code == 403 and r.get_json()["error"] == "not_linked"


def test_empty_allowlist_still_does_not_open_the_door(client, monkeypatch):
    """★ 허용목록을 비워도 **기본은 '열림'이 아니다** — 이제 잠그는 것은 계정 바인딩이다.

    C-F17-B 전에는 허용목록이 비면 403이었다. 지금은 바인딩(`/link`)이 없으면 담지 않는다.
    지키는 규율은 같다: 잠금 장치 없이 열어 두지 않는다.
    """
    monkeypatch.setenv("TELEGRAM_COLLECT_CHAT_IDS", "")
    monkeypatch.delenv("TELEGRAM_COLLECT_SELLER_ID", raising=False)
    r = _post(client, "https://x.com/dp/1")
    assert r.status_code == 403 and r.get_json()["error"] == "not_linked"


# ── 수집 ──────────────────────────────────────────────────────────────────────

def test_url_in_message_is_collected(client, monkeypatch, _quiet):
    """회신 문구는 C-F17-B에서 **단축어와 같은 제조기**(`collect_reply_text`)로 통일됐다."""
    _ok_collect(monkeypatch)
    r = _post(client, "이거 좀 봐줘 https://www.amazon.com/dp/B0T1 어때?")
    d = r.get_json()
    assert d["ok"] is True and d["item_id"] == "it-1"
    assert _quiet[0].startswith("담았어요 — "), _quiet[0]
    assert "PopSockets" in _quiet[0]


def test_no_url_gets_guidance_not_silence(client, monkeypatch, _quiet):
    """URL이 없으면 조용히 삼키지 않고 **무엇을 보내야 하는지** 알려준다.

    C-F17-B: 링크 없는 인사는 **실패도, 미연결도 아니다** — 연결 여부보다 먼저 답한다.
    (연결 안 됐다고 답하면 사람이 엉뚱한 데를 고치러 간다.)
    """
    monkeypatch.delenv("TELEGRAM_COLLECT_SELLER_ID", raising=False)
    r = _post(client, "안녕")
    assert r.get_json()["skipped"] == "no_url"
    # 낱말이 아니라 **안내가 있는가**를 본다(문구는 셀러 언어로 바뀔 수 있다).
    assert ("링크" in _quiet[0] or "URL" in _quiet[0]), "무엇이 없는지 말해야 한다"
    assert "검수" in _quiet[0], "검수 힌트가 사라지면 그 기능을 아무도 모른다"


def test_missing_seller_scope_refuses_to_guess(client, monkeypatch, _quiet):
    """★ 저장 스코프가 없으면 **아무 스코프에나 쓰지 않는다** — 남의 이력에 섞인다.

    C-F17-B: 스코프의 정본이 env에서 `/link` 바인딩으로 바뀌었다(사유=헤더 주석).
    C-F18: 안내 문구도 `MSG["need_link"]` 한 곳으로 모였다 — 그래서 **낱말이 아니라
    무엇을 하라고 하는지**를 잰다(문구는 오너가 바꿀 수 있다).
    규율은 그대로 — 모르면 **담지 않고**, 무엇을 하면 되는지 말한다.
    """
    monkeypatch.delenv("TELEGRAM_COLLECT_SELLER_ID", raising=False)
    r = _post(client, "https://x.com/dp/1")
    assert r.status_code == 403 and r.get_json()["error"] == "not_linked"
    assert r.get_json().get("item_id") is None, "담지 않았어야 한다"
    assert "/link" in _quiet[0] and "API 토큰" in _quiet[0], _quiet[0]


def test_collect_failure_is_honest(client, monkeypatch, _quiet):
    """수집 실패는 사유를 그대로 전하고 다음 행동을 알려준다(가짜 성공 0)."""
    monkeypatch.setattr("src.api.extension_api.collect_one_url",
                        lambda url, seller_id="", source="": {
                            "url": url, "ok": False, "error": "봇 차단(403)"})
    r = _post(client, "https://x.com/dp/1")
    assert r.status_code == 502
    assert "봇 차단" in _quiet[0] and "확장" in _quiet[0]
    assert "담지 못했어요" in _quiet[0]


def test_duplicate_uses_existing_key(client, monkeypatch, _quiet):
    """중복은 기존 정규화 키로 잡는다 — 같은 상품을 두 번 쌓지 않는다."""
    monkeypatch.setattr("src.seller_console.collect_history_store.find_by_product_key",
                        lambda url, seller_id=None, seller_ids=None: {"id": "old-1",
                                                                      "title": "이미 있음"})
    r = _post(client, "https://x.com/dp/1")
    assert r.get_json()["duplicate"] is True
    assert "이미 수집한 상품" in _quiet[0]


# ── 검수 판정(M1-2 연결) ──────────────────────────────────────────────────────

def _draft(monkeypatch, extra: dict, *, title="PopSockets 그립톡"):
    """판정이 읽을 **저장된 초안**. F24부터 판정은 여기서 나온다 — 다시 수집하지 않는다."""
    import json as _json
    row = {"id": "it-1", "title": title, "url": "https://x.com/dp/1",
           "price": extra.get("price", ""), "currency": extra.get("currency", ""),
           "extra_json": _json.dumps(extra, ensure_ascii=False)}
    monkeypatch.setattr("src.seller_console.collect_history_store.get",
                        lambda item_id, seller_ids=None, seller_id=None: dict(row))
    monkeypatch.setattr("src.seller_console.collect_history_store.update",
                        lambda item_id, **kw: True)


def test_verdict_is_always_attached_and_keyword_expands_it(client, monkeypatch, _quiet):
    """F24: 판정은 **늘** 붙는다. '검수'는 그걸 **항목별로 펼치는** 말이다.

    옛 계약은 '검수'가 있어야만 판정이 붙었다(판정이 느렸으니까). 이제 판정은 저장된
    초안으로만 재기 때문에 느리지 않다 — 그래서 담는 자리에서 바로 말한다.
    """
    _ok_collect(monkeypatch)
    _draft(monkeypatch, {"price": "60", "currency": "USD", "images": ["a.jpg"]})

    plain = _post(client, "https://x.com/dp/1").get_json()
    assert plain["verdict"] in ("ok", "hold", "no"), "판정이 안 붙었다"
    plain_text = _quiet[0]

    _quiet.clear()
    _post(client, "https://x.com/dp/2 검수")
    detail_text = _quiet[0]
    # 펼친 쪽이 항목을 이름으로 말한다(요약 쪽엔 없다).
    assert "마진율" in detail_text and "배송비율" in detail_text
    assert len(detail_text.splitlines()) > len(plain_text.splitlines())


def test_excluded_verdict_carries_reason(client, monkeypatch, _quiet):
    """취급 제외는 **사유와 함께** 나간다 — 조용한 탈락 금지(옛 계약의 뜻 그대로)."""
    _ok_collect(monkeypatch, title="레플리카 가방")
    _draft(monkeypatch, {"price": "60", "currency": "USD"}, title="레플리카 가방")
    _post(client, "https://x.com/dp/3 검수")
    text = _quiet[0]
    assert "금칙어" in text and "레플리카" in text


def test_missing_numbers_are_not_faked(client, monkeypatch, _quiet):
    """★ 숫자가 없으면 **없다고 쓴다** — 0으로 채우지 않는다."""
    _ok_collect(monkeypatch)
    _draft(monkeypatch, {})          # 가격·통화 없음
    _post(client, "https://x.com/dp/4 검수")
    text = _quiet[0]
    assert "산출 불가" in text or "미상" in text or "환산 불가" in text
    assert "0원" not in text and "0%" not in text


def test_verdict_command_reads_a_saved_draft(client, monkeypatch, _quiet):
    """`/verdict 상품번호` — 담아 둔 것의 판정만 다시 본다(다시 담지 않는다)."""
    import json as _json
    monkeypatch.setattr("src.seller_console.collect_history_store.list_items",
                        lambda **kw: [{"id": "it-1", "url": "https://item.taobao.com/item.htm?id=1060535477134",
                                       "extra_json": _json.dumps({"item_id_taobao": "1060535477134"})}])
    _draft(monkeypatch, {"price": "60", "currency": "USD", "item_id_taobao": "1060535477134"})
    r = _post(client, "/verdict 1060535477134")
    assert r.get_json()["ok"] is True
    assert "마진율" in _quiet[0]


def test_verdict_command_says_when_it_cannot_find_it(client, monkeypatch, _quiet):
    monkeypatch.setattr("src.seller_console.collect_history_store.list_items", lambda **kw: [])
    r = _post(client, "/verdict 999")
    assert r.status_code == 404
    assert "못 찾았어요" in _quiet[0]


# ── 구조 ──────────────────────────────────────────────────────────────────────

def test_separate_from_cs_webhook_and_reuses_core():
    """★ CS 경로와 분리 + 수집·검수 코어 재사용(이중 구현 0)."""
    src = Path("src/api/telegram_collect.py").read_text(encoding="utf-8")
    assert "/webhooks/telegram/collect" in src
    assert "cs_bot" not in src and "InboxStore" not in src      # CS 인박스와 섞이지 않는다
    # C-F17-B: 코어를 `collect_one_url`에서 **`collect_input`**(단일 판단점)으로 올렸다.
    #   그 안에서 여전히 `collect_one_url`을 부른다 — 판단이 한 벌이 됐을 뿐이다.
    assert "collect_input" in src
    # F24: 판정도 **콘솔 검수표와 같은 빌더**를 부른다(`build_source_review_row`).
    #   부르는 것은 재사용이고, 여기서 마진·금지어를 **다시 계산하면** 이중 구현이다.
    assert "build_source_review_row" in src
    #   공용 로더를 **부르는 것**은 재사용이다(`load_blacklist85()`). 재구현은 이런 것들이다:
    #   제 금지어 목록을 들고 있거나, 마진 공식을 다시 쓰거나, 수집을 제 손으로 하는 것.
    for reinvented in ("history_append", "dispatcher_collect", "MarginCalculator",
                       "_calc_margin", "recalc_channel_price"):
        assert reinvented not in src, reinvented
