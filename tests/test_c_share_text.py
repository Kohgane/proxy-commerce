"""tests/test_c_share_text.py — C-트랙: 타오바오 공유 텍스트 → 상품.

## 정본 픽스처 (오너 실측 2026-09-11, 상하이 · 아이폰 타오바오 앱)

붙여넣었더니 웹 폼이 **"유효한 http/https URL"로 거부**했다. 유저가 손으로 URL만
골라내야 했다는 뜻이다 — 공유 시트는 이 형태로만 주는데.

세 가지를 지킨다.

**① 공유 텍스트 통째를 받는다.** 입력구(웹 폼·`/api/v1/collect/one`·텔레그램·단축어)가
   **같은 파서 하나**를 쓴다. 실측: 제 정규식이 3벌 있었고, 셋이 서로 다르게 틀리면
   "텔레그램은 되는데 웹은 안 되는" 갈래가 생긴다.

**② 없는 값을 만들지 않는다.** 공유 글엔 제목·링크뿐이다.
   가격 0·이미지 [] 을 "수집됨"으로 앉히면 그건 수집이 아니라 오염이다.

**③ 못 폈으면 사유를 보인다.** 단축 링크 해석 실패를 성공으로 위장하지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# 오너가 실제로 받은 공유 텍스트 — 한 글자도 고치지 않는다.
SHARE_FIXTURE = (
    "【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt CZ356\n"
    "「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」\n"
    "点击链接直接打开 或者 淘宝搜索直接打开"
)


# ── ① 파서 ───────────────────────────────────────────────────────────────────
def test_owner_fixture_parses():
    """★ 이 픽스처가 깨지면 C-트랙 전체가 무의미하다 — 유저가 실제로 붙여넣는 형태다."""
    from src.collectors.share_text import parse_share_text
    r = parse_share_text(SHARE_FIXTURE)
    assert r["url"] == "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt"
    assert r["tk"] == "nyXpT7VA7lt", "tk 토큰이 URL에서 떨어져 나가면 앱이 상품을 못 찾는다"
    assert r["title"].startswith("新中式双人书桌"), "「」 안이 제목이다(【淘宝】는 플랫폼 태그)"
    assert r["share_code"] == "CZ356"
    assert r["is_short"] is True


def test_url_does_not_swallow_cjk_punctuation():
    """★ 맨 `https?://[^\\s]+`는 「」·。 을 URL에 물고 들어간다 — 그게 3벌 정규식의 실제 증상이었다."""
    from src.collectors.share_text import parse_share_text
    r = parse_share_text("【天猫】https://detail.tmall.com/item.htm?id=123456789。「책상」")
    assert r["url"] == "https://detail.tmall.com/item.htm?id=123456789"
    assert r["item_id"] == "123456789"
    assert r["title"] == "책상"


def test_no_link_returns_empty_not_guess():
    from src.collectors.share_text import parse_share_text
    r = parse_share_text("그냥 아무 말이나 적었어요")
    assert r["url"] == "" and r["item_id"] == ""


def test_item_id_is_never_invented():
    """★ id가 없으면 빈 문자열이다. 만들어 넣으면 엉뚱한 상품에 붙는다."""
    from src.collectors.share_text import extract_item_id
    assert extract_item_id("https://e.tb.cn/h.8IcTrtZuTU19ieN") == ""
    assert extract_item_id("https://item.taobao.com/item.htm?id=987654321012") == "987654321012"


# ── ② 입력구가 전부 같은 파서를 쓴다 ─────────────────────────────────────────
@pytest.mark.parametrize("path", [
    "src/api/extension_api.py",
    "src/api/telegram_collect.py",
    "src/seller_console/views.py",
])
def test_entry_points_use_the_one_parser(path):
    """★ 입력구가 제 정규식을 되살리면 또 갈라진다 — 파서는 한 곳이다."""
    s = Path(path).read_text(encoding="utf-8")
    assert "share_text" in s, f"{path}가 공용 파서를 안 쓴다"


def test_no_entry_point_keeps_its_own_url_regex():
    """★ 실측 3벌(`collect_one` 인라인 · `telegram._URL_RE` · 웹 폼)을 되살리지 않는다."""
    for path in ("src/api/telegram_collect.py",):
        s = Path(path).read_text(encoding="utf-8")
        assert not re.search(r'_URL_RE\s*=\s*re\.compile', s), f"{path}에 제 URL 정규식이 돌아왔다"


def test_web_form_accepts_share_text():
    """★ `type="url"`이면 **브라우저가** JS 전에 거부한다 — 오너가 실제로 막힌 지점."""
    raw = Path("src/seller_console/templates/manual_collect.html").read_text(encoding="utf-8")
    # 주석을 걷어내고 본다 — 안 그러면 **이 결함을 설명한 내 주석**이 결함으로 잡힌다
    #   (볼트 「정규식이 설명문을 선언으로 읽는다」: 읽기 전에 "빼고 볼 것"을 정한다).
    html = re.sub(r"\{#.*?#\}|<!--.*?-->", "", raw, flags=re.S)
    i = html.index('id="productUrl"')
    block = html[i - 300: i + 300]
    assert 'type="url"' not in block, "공유 텍스트가 브라우저 검증에 먼저 막힌다"
    assert "공유" in block, "입력칸이 공유 텍스트를 받는다고 말해야 한다"


# ── ③ 없는 값을 만들지 않는다 ────────────────────────────────────────────────
def test_share_draft_leaves_uncollected_fields_empty(monkeypatch):
    """★ 공유 글엔 제목·링크뿐이다. 가격 0·이미지 [] 를 '수집됨'으로 앉히지 않는다."""
    import src.collectors.share_collect as sc
    saved = {}

    def _fake_append(**kw):
        saved.update(kw)
        return ("item-1", True)

    monkeypatch.setattr("src.seller_console.collect_history_store.append", _fake_append)
    r = sc.collect_from_share_text(SHARE_FIXTURE, seller_id="u1", translate=False)

    assert r["ok"] and r["item_id"] == "item-1"
    assert saved["price"] == "" and saved["currency"] == "" and saved["image"] == ""
    assert saved["extra"]["images"] == []
    assert saved["extra"]["price"] == ""
    assert set(saved["extra"]["uncollected"]) == {"price", "images", "options", "description"}
    assert saved["extra"]["share_tk"] == "nyXpT7VA7lt"


def test_bare_url_without_title_is_not_a_collection(monkeypatch):
    """★ 제목 없는 맨 URL로 **빈 항목을 만들지 않는다.**

    실측(이 슬라이스에서 기존 계약 `test_share_failure_is_honest_not_fake`가 잡았다):
    폴백이 "입력이 비지 않았으면" 돌게 돼 있어, 맨 URL 하나로 **제목도 가격도 이미지도 없는 행**이
    '수집됨'으로 앉고 편집 화면까지 넘어갔다. 그게 정확히 가짜 성공이다.

    이 경로의 근거는 "공유 글엔 제목이 있다"이므로, **제목이 없으면 근거도 없다.**
    """
    import src.collectors.share_collect as sc
    called = []
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: called.append(kw) or ("x", True))
    r = sc.collect_from_share_text("https://temu.com/p/x", seller_id="u1",
                                   translate=False)
    assert r["ok"] is False, "제목 없는 링크가 수집으로 둔갑했다"
    assert not called, "저장까지 갔다 — 빈 항목이 목록에 남는다"


def test_share_mode_shows_the_partial_badge():
    """★ '간이' 뱃지 조건은 **한 곳**(SIMPLE_COLLECT_MODES)에서만 정의된다 — 두 벌이 되면 또 어긋난다."""
    from src.api.extension_api import SIMPLE_COLLECT_MODES
    assert "share" in SIMPLE_COLLECT_MODES
    rows = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    assert "'share'" in rows, "공유 수집분 툴팁이 제 사유를 말해야 한다(다른 모드 문구를 빌리면 거짓말)"


def test_review_screen_names_what_is_missing():
    """★ 검수 화면이 **무엇이** 비었는지 이름을 댄다 — '보강 필요'만으론 무엇을 할지 모른다."""
    tpl = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "보강 필요" in tpl
    assert "uncollected" in tpl





def test_short_link_is_the_identity_key():
    """★ itemId를 못 얻으니 **링크 자체가 그 상품**이다 — 중복 판정도 이 키로 한다.

    경로 토큰은 대소문자를 보존해야 한다(소문자로 접으면 다른 공유와 충돌).
    """
    from src.collectors.product_key import normalize_product_key as k
    key = k("https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt")
    assert key == "tbshare:h.8IcTrtZuTU19ieN:nyXpT7VA7lt"
    assert "8IcTrtZuTU19ieN" in key, "대소문자가 접히면 다른 상품과 같은 키가 된다"
    assert k("https://e.tb.cn/h.OTHER?tk=z") != key


def test_registration_is_blocked_before_enrichment():
    """★ 보강 전 등록 차단 — 버튼 숨김이 아니라 **서버**에서 막는다(직접 호출이 남으니까).

    가격이 없으면 마진을 못 낸다. 0으로 채우면 그건 계산이 아니라 날조다.
    """
    src = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    i = src.index("def collect_upload")
    block = src[i: i + 4000]
    assert "enrich_state" in block and "pending" in block, "업로드 라우트에 보강 게이트가 없다"
    assert "enrich_required" in block, "차단 사유를 호출부가 구분할 수 있어야 한다"


def test_gate_opens_only_when_price_actually_arrives(monkeypatch):
    """★ 상세·이미지만 채워도 게이트는 **안 열린다** — 가격이 마진의 전제다.

    소스 문자열이 아니라 **동작**을 잰다(볼트 「자기 주석이 자기 계약이 된다」:
    "이 규칙이 있다"는 리팩터만 해도 깨지고, "게이트가 안 열린다"만 결함을 잡는다).
    """
    import json as _json

    import src.api.extension_api as ext
    from src.order_webhook import app
    from src.seller_console import collect_history_store as store

    monkeypatch.setattr(store, "pg_enabled", lambda: False, raising=False)
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-c"})

    state = {"extra": {"mode": "share", "enrich_state": "pending", "price": "",
                       "uncollected": ["price", "images", "options", "description"]}}

    def _get(item_id, seller_ids=None):
        return {"id": item_id, "title": "책상", "url": "https://e.tb.cn/h.X",
                "extra_json": _json.dumps(state["extra"])}

    def _update(item_id, seller_ids=None, **kw):
        if "extra_json" in kw:
            state["extra"] = _json.loads(kw["extra_json"])
        state.setdefault("cols", {}).update({k: v for k, v in kw.items() if k != "extra_json"})
        return True

    monkeypatch.setattr(store, "get", _get, raising=False)
    monkeypatch.setattr(store, "update", _update, raising=False)

    with app.test_client() as c:
        # ① 상세만 보강 — 가격이 없으니 게이트는 닫힌 채다
        c.post("/api/v1/collect/enrich",
               json={"item_id": "it1", "description": "원목 책상입니다. " * 5})
        assert state["extra"]["enrich_state"] == "pending", "가격 없이 게이트가 열렸다"

        # ② 가격이 실제로 도착 — 그때 열린다
        c.post("/api/v1/collect/enrich", json={"item_id": "it1", "price": "268000", "currency": "KRW"})
        assert state["extra"]["enrich_state"] == "done"
        assert "price" not in state["extra"]["uncollected"]
        assert state["cols"].get("price") == "268000", "행 컬럼이 안 바뀌면 목록은 '-'로 남는다"


def test_extension_can_find_pending_drafts():
    """★ 보강 주체가 확장이면, 확장이 **무엇을 열지** 물을 곳이 있어야 한다."""
    src = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert '@extension_bp.get("/enrich/pending")' in src




# ── ④ 서버는 타오바오에 나가지 않는다 (C-T4'' 최종) ──────────────────────────
def test_no_server_side_taobao_fetch_path_at_all():
    """★ **코드 경로 0.** 플래그조차 없다.

    실측 2026-09-11 상하이: `m.intl.taobao.com` 상세는 **IP 무관 로그인 벽**
    (VPN 온 +82 / 오프 +852 동일), 단축 링크는 해외 IP에서 연결 거부.
    오너 판단 — *"실측이 문을 닫았으니 '혹시' 코드는 부채다."*

    끈 채로 남긴 코드는 보험처럼 보이지만, 다음 사람이 "이게 왜 꺼져 있지" 하고 켜 보고
    **같은 실패를 다시 겪는다.** 그래서 지운다. 이 계약이 되살아나는 걸 막는다.
    """
    assert not Path("src/collectors/taobao_short.py").exists(), \
        "닫힌 문 앞의 해석기가 되살아났다"
    for path in ("src/collectors/share_collect.py", "src/collectors/share_text.py",
                 "src/api/extension_api.py"):
        s = Path(path).read_text(encoding="utf-8")
        assert "TAOBAO_RESOLVE" not in s, f"{path}에 해석 플래그가 돌아왔다"
        assert "taobao_short" not in s, f"{path}가 삭제된 해석기를 부른다"


# ── ⑤ 폰이 편 최종 URL (C-T2'') ──────────────────────────────────────────────
def test_final_url_yields_id_and_price():
    """★ 폰의 「URL 확장」이 펴 준 최종 URL엔 `id`·`price`가 실려 온다(실측).

    ※ 호스트·경로는 **아직 실측 원문이 없다** — 그래서 파라미터만 잰다.
      원문이 오면 이 픽스처를 원문으로 고정한다(호스트를 지어내지 않는다).
    """
    from src.collectors.share_text import parse_final_url
    f = parse_final_url("https://example.invalid/x?id=993154784090&price=199"
                        "&tk=nyXpT7VA7lt&short_name=h.abc")
    assert f["item_id"] == "993154784090"
    assert f["price"] == "199"
    assert f["currency"] == "CNY", "타오바오 공유가는 위안이다 — 비워 두면 USD로 오해된다"
    assert f["tk"] == "nyXpT7VA7lt"


def test_price_only_when_numeric():
    """★ 숫자가 아니면 가격이 아니다 — 값처럼 생긴 것을 값으로 앉히지 않는다."""
    from src.collectors.share_text import parse_final_url
    assert parse_final_url("https://x.invalid/y?price=面议")["price"] == ""
    assert parse_final_url("https://x.invalid/y?price=199.50")["price"] == "199.50"


def test_two_branches_are_not_mixed(monkeypatch):
    """★ 폰이 편 갈래와 못 편 갈래를 섞지 않는다 — 한쪽을 다른 쪽인 척 하면 가짜 성공이다."""
    import src.collectors.share_collect as sc
    saved = {}
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: saved.update(kw) or ("i", True))

    # ① 폰이 폈다 → 가격이 있고 등록 게이트가 열린다
    r = sc.collect_from_share_text(
        SHARE_FIXTURE, seller_id="u1", translate=False,
        final_url="https://example.invalid/x?id=993154784090&price=199")
    assert r["price"] == "199" and r["currency"] == "CNY"
    assert r["enrich_state"] == "done"
    assert "price" not in r["uncollected"]
    assert saved["extra"]["price_source"] == "share_link", "실시간 시세가 아님을 표시해야 한다"
    assert saved["status"] == "ok"

    # ② 못 폈다 → 가격이 없고 게이트는 닫힌 채
    saved.clear()
    r2 = sc.collect_from_share_text(SHARE_FIXTURE, seller_id="u1", translate=False)
    assert r2["price"] == ""
    assert r2["enrich_state"] == "pending"
    assert "price" in r2["uncollected"]
    assert saved["status"] == "보강 대기"


def test_item_id_beats_tk_for_dedup():
    """★ 같은 상품을 단축 링크로도, 편 링크로도 담았을 때 **한 건**이어야 한다.

    tk는 공유마다 달라서 같은 상품을 남남으로 만든다 → itemId가 우선이다.
    타오바오 계열은 **호스트를 키에 안 넣는다**(같은 상품이 여러 호스트로 온다).
    """
    from src.collectors.product_key import normalize_product_key as k
    expanded = k("https://example.invalid/x?id=993154784090")     # 호스트 무관 파라미터만
    assert k("https://e.tb.cn/h.X?id=993154784090&tk=a") == "taobao:item:993154784090"
    assert k("https://item.taobao.com/item.htm?id=993154784090") == "taobao:item:993154784090"
    assert k("https://m.intl.taobao.com/x.htm?id=993154784090") == "taobao:item:993154784090"
    # id가 없을 때만 tk 열쇠로 떨어진다
    assert k("https://e.tb.cn/h.X?tk=a").startswith("tbshare:")
    assert expanded  # 폴백도 키를 만들긴 한다(빈 문자열 금지)


def test_taobao_share_never_triggers_a_server_fetch(monkeypatch):
    """★ 타오바오 공유는 **서버 수집을 한 번도 시도하지 않는다.**

    소스에 "안 나간다"고 적는 걸로는 부족하다 — 실제로 **호출 횟수를 센다**.
    실측이 닫은 문에 요청을 날리면 반드시 실패하고, 그 실패 로그는 진단이 아니라 소음이다.
    (이 계약을 쓰기 전엔 폴백이 `collect_one_url`을 **먼저** 태우고 있었다.)
    """
    import src.api.extension_api as ext
    from src.order_webhook import app

    calls = []
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-tb"})
    monkeypatch.setattr(ext, "collect_one_url",
                        lambda url, **kw: calls.append(url) or {"ok": False, "error": "x"})
    monkeypatch.setattr("src.seller_console.collect_history_store.find_by_product_key",
                        lambda *a, **k: None)
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: ("i", True))

    with app.test_client() as c:
        r = c.post("/api/v1/collect/one", json={"url": SHARE_FIXTURE})
    assert r.status_code == 200, r.get_data(as_text=True)[:200]
    assert r.get_json().get("ok") is True
    assert calls == [], f"타오바오에 서버 수집을 시도했다: {calls}"
