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

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# 오너가 실제로 받은 공유 텍스트 — 한 글자도 고치지 않는다.
# 폰(사파리 주소창)이 펴 준 **최종 URL 원문** — 오너 실측 2026-09-11 상하이, VPN 오프.
# 한 글자도 고치지 않는다. 18개 파라미터 중 열쇠는 넷(id·price·tk·short_name)뿐이고
# 나머지(suid·un·wxsign·ut_sk…)는 세션성·개인식별 가능 값이라 **저장하지 않는다.**
FINAL_URL_FIXTURE = (
    "https://m.intl.taobao.com/detail/detail.html"
    "?ut_sk=1.aDvDH5soLl4DAC50nJmz%2BzOW_21380790_1789103987893.Copy.1"
    "&id=993154784090&sourceType=item&price=199"
    "&suid=407B2EFE-24D1-4A3B-A45A-30025F1DF433&shareUniqueId=37255072833"
    "&un=4510f0ec3e1477f4a105b3dacc8633bb&share_crt_v=1&un_site=0"
    "&spm=a2159r.13376460.0.0"
    "&wxsign=tbw3x8Tobj17BFg4OZykA3ilp4i568utWm3_9ob6Sbe46ZAyZTdTgzHtob05qZRJWnOr3wc6D"
    "ktBr0z9EoA23DpC3bsKDuDpMtRxy0MKFvoh78oM-t7xK1gwIyGJ2TGoPHYNgfpLKet3wMnHtnR9Dq-Gw"
    "&tbSocialPopKey=shareItem&sp_tk=bnlYcFQ3VkE3bHQ%3D&cpp=1&shareurl=true"
    "&short_name=h.8IcTrtZuTU19ieN&tk=nyXpT7VA7lt&app=macos_safari"
)

# 오너 2차 실물(소파 건) — `tk`·제목은 오너 제공값, 나머지 형식은 검증된 1차 원문과 같다.
#   형식을 지어내지 않았다: 【淘宝】…「제목」…点击链接 3줄 구조는 1차에서 실측된 것이다.
SHARE_FIXTURE_SOFA = (
    "【淘宝】https://e.tb.cn/h.RZs4T76TlNx?tk=RZs4T76TlNx CZ0000\n"
    "「沙发客厅小户型现代简约北欧布艺沙发」\n"
    "点击链接直接打开 或者 淘宝搜索直接打开"
)

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


# ── ⑥ 최종 URL 원문 (오너 실측 픽스처) ──────────────────────────────────────
def test_owner_final_url_yields_the_four_keys():
    """★ 실측 원문 그대로에서 열쇠 넷이 나온다. 호스트·경로도 이제 실측이다."""
    from urllib.parse import urlparse

    from src.collectors.share_text import parse_final_url
    u = urlparse(FINAL_URL_FIXTURE)
    assert u.hostname == "m.intl.taobao.com" and u.path == "/detail/detail.html"
    f = parse_final_url(FINAL_URL_FIXTURE)
    assert f["item_id"] == "993154784090"
    assert f["price"] == "199" and f["currency"] == "CNY"
    assert f["tk"] == "nyXpT7VA7lt"
    assert f["short_name"] == "h.8IcTrtZuTU19ieN"


def test_sp_tk_and_tk_recover_each_other():
    """★ `sp_tk = base64(tk)` — **검증 가능한 파생 관계**(실측: bnlYcFQ3VkE3bHQ= → nyXpT7VA7lt).

    둘 중 하나만 있어도 열쇠가 복원돼야 한다 — 타오바오가 어느 쪽을 주든 우리는 같은 상품을 가리킨다.
    """
    import base64

    from src.collectors.share_text import parse_final_url
    assert base64.b64decode("bnlYcFQ3VkE3bHQ=").decode() == "nyXpT7VA7lt"
    only_sp = "https://m.intl.taobao.com/detail/detail.html?id=1&sp_tk=bnlYcFQ3VkE3bHQ%3D"
    assert parse_final_url(only_sp)["tk"] == "nyXpT7VA7lt"


def test_session_values_are_never_stored(monkeypatch):
    """★ **세션성·개인식별 값을 우리 이력에 쌓지 않는다.**

    실측 원문엔 `suid`(기기 UUID) · `un`(사용자 해시) · `wxsign` · `ut_sk`가 실려 온다.
    열쇠가 아니고, 남기면 남의 기기·계정 식별자를 우리가 보관하는 셈이다.

    허용목록으로 짠다 — 차단목록이면 타오바오가 새 파라미터를 붙이는 날 그게 그대로 들어온다.
    """
    import src.collectors.share_collect as sc
    saved = {}
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: saved.update(kw) or ("i", True))
    sc.collect_from_share_text(SHARE_FIXTURE, seller_id="u1", translate=False,
                               final_url=FINAL_URL_FIXTURE)
    blob = repr(saved)
    for leak in ("suid", "407B2EFE", "4510f0ec", "wxsign", "ut_sk", "tbSocialPopKey", "spm="):
        assert leak not in blob, f"세션성 값이 저장됐다: {leak}"
    assert "993154784090" in blob and "nyXpT7VA7lt" in blob, "열쇠는 남아야 한다"


def test_pasted_final_url_behaves_like_shortcut_input():
    """★ 같은 값을 **입력 모양과 무관하게** 같게 읽는다.

    유저는 사파리 주소창을 복사해 붙여넣기도 하고, 단축어가 `final_url`로 보내기도 한다.
    둘이 다르게 동작하면 그게 "웹은 되는데 단축어는 안 되는" 갈래의 시작이다(이 트랙의 원 결함).
    """
    from src.collectors.share_text import parse_share_text
    a = parse_share_text("「책상」 " + FINAL_URL_FIXTURE)
    b = parse_share_text("「책상」", final_url=FINAL_URL_FIXTURE)
    for k in ("item_id", "price", "currency", "tk", "short_name"):
        assert a[k] == b[k], f"입력 모양에 따라 {k}가 다르다: {a[k]!r} vs {b[k]!r}"
    assert "suid" not in a["url"] and "suid" not in b["url"]


def test_vpn_guidance_names_the_mode_not_the_switch():
    """★ 안내는 **모드를 이름으로 불러야** 한다 — "VPN을 끄세요"만으론 부족하다.

    처방 자체는 두 번 바뀌었다(오너 실측이 두 번 정정했다):
      ① 「VPN을 끄세요」        → 틀렸다. 규칙 모드면 켜져 있어도 된다.
      ② 「Smart 모드로 바꾸세요」 → iOS 아스트릴엔 **Smart Mode가 없다**(오너 실측).

    그래서 지금 정답은 **둘 다 말하는 것**이다 — "규칙 모드면 그대로, 전체(Global) 모드면 끄기".
    계약이 잴 것은 특정 낱말이 아니라 **어떤 모드가 문제인지 말하는가**이다.
    (이 계약은 ①을 금지하다가 ②에서 스스로 틀렸다 — 낱말을 금지하면 그 낱말이 정답이 되는 날 깨진다.)
    """
    for path in ("src/seller_console/views.py", "src/api/extension_api.py"):
        s = Path(path).read_text(encoding="utf-8")
        assert "전체" in s or "Global" in s, f"{path}가 어떤 모드가 문제인지 안 말한다"
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    for term in ("규칙", "전체"):
        assert term in guide, f"가이드에 '{term} 모드' 안내가 없다"
    # iOS 아스트릴엔 Smart Mode가 없다 — 없는 기능을 쓰라고 하면 유저가 못 찾는다(오너 실측).
    assert "아스트릴은 Smart Mode" not in guide, "iOS에 없는 기능을 안내하고 있다"


# ── ⑦ C-fix: 네 입구가 같은 결과를 낸다 ─────────────────────────────────────
def test_share_block_is_one_item_not_three():
    """★ 공유 텍스트는 **한 상품**이다 — 줄 수만큼 쪼개지 않는다.

    실측(오너 2026-09-11, 폰 웹 폼 「여러 URL 한 번에」): 붙여넣었더니
    **「전체 2개 · 성공 0 · 실패 2」** — `splitlines()`가 한 상품을 둘로 쪼갰고,
    1줄은 단축 링크만 남아 서버가 못 읽고 2줄은 `点击链接…`이라 링크가 아예 없었다.
    """
    from src.collectors.share_text import split_input_blocks
    assert len(split_input_blocks(SHARE_FIXTURE)) == 1, "한 상품이 여러 항목으로 쪼개졌다"
    # 맨 URL을 줄마다 넣던 기존 사용법은 그대로 동작해야 한다
    assert len(split_input_blocks("https://a.invalid/1\nhttps://b.invalid/2")) == 2
    # 공유 블록 둘이 붙어 와도 둘로 나뉜다
    two = SHARE_FIXTURE + "\n" + SHARE_FIXTURE.replace("8IcTrtZuTU19ieN", "OTHERtoken")
    assert len(split_input_blocks(two)) == 2


def test_bulk_path_uses_the_one_entry_function():
    """★ 갈래 판단이 입구마다 있으면 **같은 입력이 입구마다 다른 답**을 낸다(오너 실측)."""
    src = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    i = src.index("def collect_bulk")
    block = src[i: i + 3500]
    assert "split_input_blocks" in block, "일괄이 줄 단위로 자르고 있다"
    assert "collect_input(" in block, "일괄이 공용 입구 함수를 안 쓴다"
    assert "_collect_real_draft" not in block, "일괄이 제 나름의 수집 경로를 다시 갖고 있다"


def test_all_entries_agree_on_the_same_share_text(monkeypatch):
    """★ **같은 공유 텍스트 → 네 입구 같은 결과.** 이 트랙의 원 결함이 정확히 이 불일치였다."""
    import src.collectors.share_collect as sc
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: ("i", True))
    calls = []
    monkeypatch.setattr("src.api.extension_api.collect_one_url",
                        lambda url, **kw: calls.append(url) or {"ok": False, "error": "x"})

    from src.collectors.share_text import split_input_blocks
    blocks = split_input_blocks(SHARE_FIXTURE)
    assert len(blocks) == 1
    results = [sc.collect_input(blocks[0], seller_id="u1", source=src_name, translate=False)
               for src_name in ("bulk", "mobile", "telegram", "share")]
    for r in results:
        assert r["ok"] is True, "입구에 따라 실패했다"
        assert r["kind"] == "share_draft", "타오바오 공유가 초안이 아니다"
    assert calls == [], "타오바오에 서버 수집을 시도했다(일괄 포함 전 입구 0이어야 한다)"


def test_taobao_never_shows_the_read_failure_message():
    """★ 타오바오 링크에 「상품 정보를 읽지 못했어요」가 뜨면 안 된다 — 그 자리는 **초안 생성**이다.

    실측: 오너 화면에 그 문구가 떴다. 서버가 읽으려 했다는 뜻이고, 읽을 수 없는 걸 읽으려 한 것이다.
    """
    import src.collectors.share_collect as sc
    r = sc.collect_input(SHARE_FIXTURE, seller_id="u1", source="bulk", translate=False)
    assert r.get("kind") == "share_draft"
    assert "읽지 못" not in (r.get("error") or ""), "타오바오에 읽기 실패 문구가 나왔다"


def test_second_owner_sample_parses_too():
    """★ 픽스처가 하나면 그 하나에만 맞춘 파서가 된다 — 오너 2차 실물(소파 건)도 잰다."""
    from src.collectors.share_text import parse_share_text, split_input_blocks
    assert len(split_input_blocks(SHARE_FIXTURE_SOFA)) == 1
    r = parse_share_text(SHARE_FIXTURE_SOFA)
    assert r["tk"] == "RZs4T76TlNx"
    assert "沙发" in r["title"]
    assert r["is_short"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_success_copy_is_not_rewritten_as_failure():
    """★ 성공 문구가 실패 문구로 **뒤집히지 않는다.**

    실측(오너 화면): 하단에 「가격을 못 읽었어요」가 떴다. 친절 문구 규칙이 `/가격|price/`로
    너무 넓어, **'가격'이라는 낱말만 있으면** 무엇이든 그 실패 문장으로 바꾸고 있었다.
    초안 성공 문구("…가격까지 담았어요")까지 실패로 뒤집는다 — 한 상태를 두 번, 그것도 반대로.

    소스 위치가 아니라 **함수를 실제로 돌려서** 잰다 — 앞뒤 몇 글자를 읽는 방식은
    내 주석이 그 자리에 들어오면 바로 깨진다(이 계약을 쓰다가 실제로 그랬다).
    """
    js = Path("src/seller_console/static/seller.js").read_text(encoding="utf-8")
    fn = re.search(r"function kgpFriendlyError[\s\S]*?\n\}", js).group(0)
    harness = fn + """
const out = [
  kgpFriendlyError('가격 반영 실패'),
  kgpFriendlyError('제목·상품번호·가격까지 담았어요(공유 시점 가격).'),
  kgpFriendlyError('초안 1건 생성 — 제목 담김 · 가격 199 CNY'),
];
console.log(JSON.stringify(out));
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        fail_msg, ok1, ok2 = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()

    assert "못 읽었어요" in fail_msg, "진짜 실패는 여전히 친절 문구로 바뀌어야 한다"
    for ok in (ok1, ok2):
        assert "못 읽었어요" not in ok, f"성공 문구가 실패로 뒤집혔다: {ok}"


def test_guide_field_names_are_the_ones_the_server_reads():
    """★ 가이드가 쓰라고 한 필드를 **서버가 실제로 읽어야** 한다.

    문서와 코드가 어긋나면 오너가 단축어를 그대로 조립해도 안 된다 — 그리고 왜 안 되는지
    알 길이 없다(서버는 조용히 빈 입력을 받는다). 실물 테스트가 거기서 막힌다.
    """
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    api = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    for field in ("share_text", "final_url"):
        assert field in guide, f"가이드에 {field} 안내가 없다"
        assert f'"{field}"' in api, f"서버가 {field}를 안 읽는다(가이드가 거짓이 된다)"


def test_share_text_field_actually_works(monkeypatch):
    """★ 이름만 읽는 게 아니라 **그 값으로 초안이 선다**(가이드대로 보내면 된다)."""
    import src.api.extension_api as ext
    from src.order_webhook import app
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-g"})
    monkeypatch.setattr("src.seller_console.collect_history_store.find_by_product_key",
                        lambda *a, **k: None)
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: ("i", True))
    with app.test_client() as c:
        r = c.post("/api/v1/collect/one",
                   json={"share_text": SHARE_FIXTURE, "final_url": FINAL_URL_FIXTURE})
    d = r.get_json()
    assert r.status_code == 200 and d.get("ok") is True
    assert d.get("price") == "199", "가이드대로 보냈는데 가격이 안 담겼다"
    assert d.get("item_id_taobao") == "993154784090"


# ── ⑧ C-F6: 인증 실패가 무엇 때문인지 말한다 ────────────────────────────────
def test_auth_failures_are_distinguishable():
    """★ 「인증이 필요합니다」 하나로는 **헤더 이름이 틀린 건지 토큰이 틀린 건지 알 수 없다.**

    실측(오너 단축어 v1): 헤더를 `X-Intake-T…`로 보냈는데 응답은 「토큰을 확인하세요」였다.
    토큰은 멀쩡했다 — 서버가 안 읽는 이름으로 보낸 것뿐이다. 그 한 문장 때문에
    오너는 토큰을 의심하며 시간을 썼다. **응답이 원인을 말해야 고칠 수 있다.**
    """
    from src.order_webhook import app
    with app.test_client() as c:
        no_header = c.post("/api/v1/collect/one", json={"share_text": SHARE_FIXTURE})
        no_bearer = c.post("/api/v1/collect/one", json={"share_text": SHARE_FIXTURE},
                           headers={"Authorization": "kgp_abc"})
        bad_token = c.post("/api/v1/collect/one", json={"share_text": SHARE_FIXTURE},
                           headers={"Authorization": "Bearer kgp_notreal"})
    msgs = [r.get_json()["error"] for r in (no_header, no_bearer, bad_token)]
    assert all(r.status_code == 401 for r in (no_header, no_bearer, bad_token))
    assert len(set(msgs)) == 3, f"세 실패가 같은 문장을 낸다: {msgs}"
    assert "Authorization" in msgs[0], "헤더 이름을 콕 집어 말해야 한다(오너가 막힌 자리)"
    assert "Bearer" in msgs[1]
    assert "발급" in msgs[2]


def test_auth_errors_never_echo_the_token():
    """★ 토큰 값을 응답에 싣지 않는다 — **앞 4자 마스킹도 안 한다.**

    마스킹이라도 로그·스크린샷·채팅으로 새는 경로가 그만큼 늘어난다.
    형식이 틀렸다는 것과 값이 틀렸다는 것만 말하면 유저는 고칠 수 있다.
    """
    from src.order_webhook import app
    secret = "kgp_SUPERSECRETVALUE12345"
    with app.test_client() as c:
        r = c.post("/api/v1/collect/one", json={"share_text": SHARE_FIXTURE},
                   headers={"Authorization": f"Bearer {secret}"})
    body = r.get_data(as_text=True)
    assert secret not in body
    for n in (4, 6, 8):
        assert secret[:n] not in body, f"토큰 앞 {n}자가 응답에 있다(마스킹도 금지)"
    assert "SUPERSECRET" not in body


def test_guide_header_name_matches_what_server_reads():
    """★ `share_text`와 같은 장치 — **가이드가 쓰라는 헤더를 서버가 읽어야** 한다.

    이번엔 가이드가 맞았고(`Authorization`) 단축어에 다른 이름이 들어갔다.
    그래도 계약을 건다: 다음에 **가이드 쪽이** 어긋나면 그때는 아무도 못 잡는다.
    """
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    api = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert 'request.headers.get("Authorization"' in api, "서버가 읽는 헤더 이름이 바뀌었다"
    assert "`Authorization`" in guide, "가이드가 헤더 이름을 명시하지 않는다"
    assert "Bearer" in guide, "가이드가 Bearer 접두를 명시하지 않는다"


# ── ⑨ C-F7: 링크를 못 찾은 이유를 말한다 ────────────────────────────────────
# 오너 2차 실물 픽스처(2026-09-12) — **링크와 제목이 같은 줄**이다(1차와 구조가 다르다).
FIX_SWEATER = (
    "【淘宝】假一赔四 https://e.tb.cn/h.8reU77YYNhKOUuE?tk=EYAGT7vTcVD CZ321 "
    "「藏青色绞花开衫毛衣男春秋慵懒松弛感美式立领针织衫cleanfit外套」\n"
    "点击链接直接打开 或者 淘宝搜索直接打开"
)


def test_single_line_share_text_parses():
    """★ 링크와 제목이 **같은 줄**에 와도 물어야 한다 — 1차 픽스처만 맞춘 파서가 되지 않도록."""
    from src.collectors.share_text import parse_share_text, split_input_blocks
    assert len(split_input_blocks(FIX_SWEATER)) == 1
    r = parse_share_text(FIX_SWEATER)
    assert r["url"] == "https://e.tb.cn/h.8reU77YYNhKOUuE?tk=EYAGT7vTcVD"
    assert r["tk"] == "EYAGT7vTcVD"
    assert r["title"].startswith("藏青色")
    assert r["share_code"] == "CZ321", "링크 뒤 공백 구분 영숫자 코드"
    assert "「" not in r["url"] and "」" not in r["url"], "제목 괄호가 URL에 딸려 왔다"


def test_scheme_less_short_link_is_recovered():
    """★ `https://` 없이 온 단축 도메인도 건진다(앱이 텍스트로 줄 때 빠져 온다).

    **아는 도메인일 때만** 스킴을 붙인다 — 아무 `a/b`에나 붙이면 오탐이 된다.
    """
    from src.collectors.share_text import parse_share_text
    assert parse_share_text("m.tb.cn/h.g9KpLmN")["url"] == "https://m.tb.cn/h.g9KpLmN"
    assert parse_share_text("e.tb.cn/h.ABC?tk=z")["url"].startswith("https://e.tb.cn/")
    assert parse_share_text("사과/바나나")["url"] == "", "아무 슬래시 문자열에 스킴을 붙이면 안 된다"


def test_taokouling_is_named_not_dismissed():
    """★ 淘口令은 **링크가 아니라 앱 전용 코드**다 — "못 찾았다"가 아니라 그렇게 말한다."""
    from src.collectors.share_text import link_failure_reason, parse_share_text
    r = parse_share_text("￥CZ0001abcd￥ 复制打开淘宝App")
    assert r["url"] == "" and r["taokouling"] == "CZ0001abcd"
    msg = link_failure_reason("￥CZ0001abcd￥ 复制打开淘宝App")
    assert "링크 복사" in msg, "무엇을 하면 되는지 말해야 한다"


def test_link_failures_are_distinguishable_and_leak_nothing():
    """★ 왜 못 찾았는지 갈라 말하되 **원문은 안 싣는다**(길이·판정만).

    내용에 상품명·계정 정보가 섞여 올 수 있고, 그게 로그·스크린샷으로 새면 우리가 만든 구멍이다.
    """
    from src.collectors.share_text import link_failure_reason as R
    secret = "비밀상품명ABC 계정12345"
    msgs = [R(""), R("￥CZ0001abcd￥"), R("http 조각만"), R(secret)]
    assert len(set(msgs)) == 4, f"네 경우가 같은 문장을 낸다: {msgs}"
    assert secret not in msgs[3] and "비밀상품명" not in msgs[3], "원문이 새어 나갔다"
    assert str(len(secret)) in msgs[3], "길이는 말해야 진단이 된다"


def test_bare_taobao_url_never_hits_the_server(monkeypatch):
    """★ **제목이 없어도** 타오바오엔 서버가 안 나간다.

    실측(C-F7): 조건이 `is_taobao_family(url) and share.get("title")`이라
    **제목 없는 맨 타오바오 URL**은 그대로 서버 수집으로 떨어졌다 — F2의 "요청 0"에 난 구멍이다.
    서버가 못 읽는 건 제목 유무와 무관하다.

    ※ 거절하느냐 초안을 세우느냐는 **별개 질문**이다(아래 계약). 여기서 재는 건
      "서버로 나가지 않는다" 하나다 — 둘을 한 계약에 섞으면 한쪽을 고칠 때 다른 쪽이 깨진다.
    """
    import src.collectors.share_collect as sc
    calls = []
    monkeypatch.setattr("src.api.extension_api.collect_one_url",
                        lambda url, **kw: calls.append(url) or {"ok": True, "item_id": "x", "title": ""})
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: ("x", True))
    for u in ("https://item.taobao.com/item.htm?id=993154784090",   # id 있음
              "https://item.taobao.com/2",                          # id·제목 둘 다 없음
              "https://e.tb.cn/h.ABC?tk=z"):                        # 단축
        sc.collect_input(u, seller_id="u1", translate=False)
    assert calls == [], f"타오바오에 서버 수집을 시도했다: {calls}"


def test_draft_needs_something_to_continue_from(monkeypatch):
    """★ 초안은 **다음 사람이 이어갈 수 있는 것**이 하나라도 있을 때만 선다.

    제목이 있으면 사람이 알아보고, itemId가 있으면 **확장이 그 링크를 열어 보강**한다.
    둘 다 없으면 남는 건 못 여는 링크 하나 — 그건 목록을 채우는 것이지 수집이 아니다.

    (처음엔 제목만 기준으로 삼았는데, 그러면 `?id=…`가 붙은 진짜 상품 링크까지 거절했다.
     빈 껍데기를 막으려던 규칙이 멀쩡한 재료를 버리고 있었다.)
    """
    import src.collectors.share_collect as sc
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: ("x", True))
    cases = [
        ("제목만", "「책상」 https://e.tb.cn/h.ABC?tk=z", True),
        ("id만", "https://item.taobao.com/item.htm?id=993154784090", True),
        ("둘 다 없음", "https://item.taobao.com/2", False),
    ]
    for label, text, should_ok in cases:
        r = sc.collect_input(text, seller_id="u1", translate=False)
        assert r["ok"] is should_ok, f"{label}: ok={r['ok']} (기대 {should_ok})"
        if not should_ok:
            assert "통째로" in r["error"], "무엇을 하면 되는지 말해야 한다"


def test_expanded_link_finds_the_short_link_draft():
    """★ 같은 상품이 **두 키로 쌓이지 않는다.**

    단축 링크만 담으면 `tbshare:<토큰>:<tk>`, 나중에 편 링크로 담으면 `taobao:item:<id>` —
    키가 달라 남남이 된다. 편 링크가 `short_name`에 그 토큰을 싣고 오므로(실측 원문) 그걸로 잇는다.
    """
    from src.collectors.product_key import normalize_product_key as k
    from src.collectors.share_text import parse_share_text
    final = ("https://m.intl.taobao.com/detail/detail.html?id=812345678901"
             "&short_name=h.8reU77YYNhKOUuE&tk=EYAGT7vTcVD")
    f = parse_share_text("", final_url=final)
    assert f["short_name"] == "h.8reU77YYNhKOUuE", "편 링크가 단축 토큰을 싣고 온다"
    alt = f"https://e.tb.cn/{f['short_name']}?tk={f['tk']}"
    assert k(alt) == k("https://e.tb.cn/h.8reU77YYNhKOUuE?tk=EYAGT7vTcVD"), \
        "복원한 단축 키가 원래 단축 링크와 같은 키여야 이어진다"
    api = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert "short_name" in api and "_alt" in api, "중복 조회가 대체 키를 안 본다"


# ── ⑩ C-F8: 가드는 코어에 있다(입구마다 두면 샌다) ──────────────────────────
def test_taobao_guard_lives_in_the_cores_not_the_callers():
    """★ **여섯 입구 중 둘만 서 있었다**(실측 2026-09-12).

    가드를 호출부마다 두면 입구가 늘 때마다 샌다 — 미리보기·텔레그램·벌크잡·관리자가
    전부 타오바오로 서버 요청을 내고 있었다. F2 계약은 `collect_input`을 타는 둘만 재고 있어 초록이었다.

    가격 정규화 때와 같은 교훈이다: **보증은 코어에 둔다.**
    """
    for path in ("src/seller_console/views.py", "src/api/extension_api.py"):
        s = Path(path).read_text(encoding="utf-8")
        assert "is_taobao_family as _is_tb" in s, f"{path}의 수집 코어에 타오바오 가드가 없다"


@pytest.mark.parametrize("label,path,marker",
                         [(a, b, c) for a, b, c in __import__(
                             "src.collectors.share_text", fromlist=["x"]).COLLECT_ENTRY_POINTS])
def test_every_entry_point_reaches_a_guarded_core(label, path, marker):
    """★ 열거된 입구가 **가드 있는 코어를 타는지** 순회 검사.

    새 입구가 생겼는데 제 나름의 수집을 하면 여기서 걸린다 — 목록을 코드 상수로 둔 이유다.
    """
    s = Path(path).read_text(encoding="utf-8")
    assert marker in s, f"{label}: 입구 표식 '{marker}'이 {path}에 없다(목록이 낡았다)"
    # 그 파일은 반드시 가드 있는 코어 중 하나를 부른다
    assert any(core in s for core in
               ("_collect_real_draft", "collect_one_url", "collect_input")), \
        f"{label}가 어떤 수집 코어도 안 쓴다(제 나름의 경로를 가졌을 수 있다)"


def test_preview_route_accepts_share_text(monkeypatch):
    """★ 미리보기 칸 이름이 「상품 링크 또는 공유 텍스트」인데 **라우트가 공유 텍스트를 안 받았다.**

    실측(오너 라이브 2026-09-12): 공유 글을 붙이자 「상품 정보를 읽지 못했어요」 노랑 배너.
    칸 이름이 받는다고 말하는데 라우트가 안 받으면 **그 이름이 거짓**이 된다.
    """
    from src.order_webhook import app
    monkeypatch.setattr("src.seller_console.collect_history_store.append",
                        lambda **kw: ("p1", True))
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "default"
        r = c.post("/seller/collect/preview", json={"url": FIX_SWEATER})
    d = r.get_json()
    assert r.status_code == 200 and d.get("ok") is True, f"미리보기가 실패로 떨어졌다: {d}"
    assert d.get("kind") == "share_draft"
    assert "藏青色" in (d.get("draft") or {}).get("title", ""), "제목이 안 담겼다"


def test_empty_input_names_the_clipboard_setting():
    """★ 빈 입력의 **가장 흔한 원인**을 콕 집는다 — 클립보드 설정.

    실측(오너 2026-09-12): 타오바오 分享 →「复制链接」은 **타오바오 자체 패널**이라
    iOS 공유 시트를 거치지 않는다(토스트 「已复制，快去粘贴吧」). 단축어를 나중에 실행하면
    넘어오는 입력이 **항상 빈 값**이고, 클립보드가 유일한 입력원이다.

    "변수 칩을 확인하세요"만으론 못 고친다 — 칩은 제대로 꽂혀 있고 **넘어올 값이 없는** 것이니까.
    """
    from src.collectors.share_text import link_failure_reason
    msg = link_failure_reason("")
    assert "클립보드" in msg, "가장 흔한 원인을 안 짚는다"
    assert "复制链接" in msg or "링크 복사" in msg, "어느 버튼을 눌렀을 때인지 말해야 한다"
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    assert "클립보드 가져오기" in guide, "가이드에 그 설정이 필수 단계로 없다"
    assert "更多" in guide, "미측정 경로(更多)를 미측정으로 표기해야 한다"
