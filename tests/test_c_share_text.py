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
        assert not state["extra"].get("gate_ready"), "가격 없이 게이트가 열렸다"

        # ② 가격이 실제로 도착 — 그때 열린다(C-F14: 등록 축은 `gate_ready`)
        c.post("/api/v1/collect/enrich", json={"item_id": "it1", "price": "268000", "currency": "KRW"})
        assert state["extra"]["gate_ready"] is True
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
    assert r["gate_ready"] is True          # C-F14: 등록 가능 = 가격 확보
    assert r["enrich_state"] == "pending"   # 보강(이미지·옵션)은 아직
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


def test_never_names_a_vpn_mode_that_does_not_exist():
    """★★★ **없는 UI 이름을 안내하지 않는다.** 세 번 발명했다: `Smart` → `전체(Global)` → `규칙`.

    오너 실측(2026-09-12) — 아스트릴 iOS **2.3.8** 화면에 있는 것:
    **ON/OFF · 서버 · TCP/UDP · Always On · Reconnect.** **모드 선택이 없다.**

    틀린 안내보다 나쁘다 — 유저가 **찾다가 자기를 의심한다.**
    허용 문장은 한 종류뿐이다: 「VPN이 켜져 있으면 끄고 다시 시도」(스위치는 실제로 있다).

    ※ 이 자리에 있던 옛 계약은 **「전체(Global)」가 소스에 있어야 한다**고 요구했다.
      즉 계약이 발명을 강제하고 있었다. 낱말을 핀으로 박으면 그 낱말이 틀리는 날 계약이
      틀린 쪽을 지킨다 — 그래서 이제 **없어야 할 낱말**만 잰다.
    """
    from src.collectors import share_text as st

    invented = ("Smart", "Global", "규칙 모드", "规则")
    faces = list(st._GAP_MESSAGE.values()) + [
        st.link_failure_reason(""), st.link_failure_reason("￥HU591￥"),
        st.link_failure_reason("링크 없는 글"), st.link_failure_reason("http 조각"),
    ]
    for msg in faces:
        for bad in invented:
            assert bad not in msg, f"없는 모드 이름이 사용자 문장에 있다({bad}): {msg}"
        if "VPN" in msg:
            assert "모드" not in msg, f"VPN과 모드를 함께 말한다: {msg}"

    # 사용자 안내 문서도 같은 규칙. (실측 정본 문서는 '발명했다'는 기록을 남기므로 제외)
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    for bad in ("Smart", "Global", "规则"):
        assert bad not in guide, f"가이드가 없는 모드 이름을 안내한다: {bad}"
    assert "모드 선택이라는 것이 없습니다" in guide, "없다는 사실을 적어야 다음 사람이 또 안 만든다"
    assert "켜져 있으면 끄고 다시 시도" in guide, "허용된 한 문장이 없다"


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


# ─────────────────────────────────────────────────────────────────────────────
# C-F9 — 서버가 모르는 것을 단정하지 않는다 · 링크 진단 · 문구 단일화
# ─────────────────────────────────────────────────────────────────────────────

def test_server_never_asserts_the_phones_vpn_state():
    """★★★ 서버는 **폰의 VPN 상태를 모른다** — 그러니 말하지 않는다.

    실측(오너 2026-09-12): VPN이 **꺼진 채로** 가격·상품번호가 비어 왔다.
    그런데 문구는 VPN 설정 때문이라고 단정했다(있지도 않은 앱 모드 이름까지 들며) →
    사용자는 이미 끈 것을 또 끄러 갔다. **오진은 침묵보다 나쁘다** — 엉뚱한 데로 보내니까.

    이 계약은 **서버가 유저에게 내보내는 문장**에 VPN 단정이 없는지만 본다.
    (문서에서 실측 사실로 언급하는 것은 막지 않는다 — 막을 것은 '서버의 진단'이다.)
    """
    import re
    from src.collectors import share_text as st

    faces = list(st._GAP_MESSAGE.values())
    faces.append(st.link_failure_reason(""))
    faces.append(st.link_failure_reason("￥HU591￥"))
    faces.append(st.link_failure_reason("제목만 있고 링크 없음"))
    faces.append(st.link_failure_reason("http로 시작하는 조각"))
    for msg in faces:
        assert "VPN" not in msg, f"서버가 VPN 상태를 단정한다: {msg}"
        assert "Global" not in msg and "Smart" not in msg, f"없는 모드 이름을 댄다: {msg}"
        # 개발 표기(마크다운)가 그대로 토스트에 뜨면 그건 유저에게 보이는 별표다.
        assert "**" not in msg, f"마크다운이 사용자 문장에 남았다: {msg}"
        assert not re.search(r"`[^`]+`", msg), f"백틱이 사용자 문장에 남았다: {msg}"


def test_gap_verdict_says_only_what_the_server_saw():
    """★★ 넷 중 하나 — 서버가 **실제로 본 것**으로만 갈린다."""
    from src.collectors.share_text import resolve_gap

    assert resolve_gap({"price": "199"}) == "ok"
    assert resolve_gap({"price": "", "final_url": ""}) == "no_final_url"
    assert resolve_gap({"price": "", "final_url": "https://m.intl.taobao.com/x"}) == "final_url_without_id"
    assert resolve_gap({"price": "", "final_url": "https://m.intl.taobao.com/x?id=1",
                        "item_id": "1"}) == "id_without_price"


def test_gap_message_has_exactly_one_home():
    """★★★ 문구는 **한 곳**에서만 만든다.

    C-fix F1의 재발 방지: 같은 상황을 단건·일괄·미리보기가 각자 설명하고 있었다.
    호출부가 자기 문장을 들고 있으면 한쪽만 고쳐지고 나머지가 옛말을 계속 한다.
    """
    import re
    from pathlib import Path

    # 옛 문구의 특징적 조각이 소스 어디에도 없어야 한다.
    for rel in ("src/api/extension_api.py", "src/seller_console/views.py"):
        src = Path(rel).read_text(encoding="utf-8")
        assert "Global" not in src or "showGlobal" in src, f"{rel}에 옛 모드 이름이 남았다"
        # '제목과 링크만 담았어요' 같은 완성 문장을 호출부가 직접 들고 있으면 두 벌째다.
        assert "제목과 링크만 담았어요" not in src, f"{rel}이 문구를 직접 들고 있다"


def test_share_draft_carries_its_own_verdict_not_the_row_id():
    """★★★ `item_id`가 **두 뜻**으로 쓰이는 함정 — 반환 dict로 다시 판정하면 늘 오판한다.

    `collect_from_share_text` 반환의 `item_id`는 **이력 행 ID**(항상 있다),
    `share["item_id"]`는 **타오바오 상품번호**(없을 수 있다). 호출부가 반환 dict를
    `resolve_gap`에 그대로 넘기면 언제나 `id_without_price`가 나온다.
    → 판정은 원본 `share`를 아는 곳에서 한 번만 하고, 결과를 실어 보낸다.
    """
    from src.collectors.share_collect import collect_from_share_text

    r = collect_from_share_text(FIX_SWEATER, seller_id="default", translate=False)
    assert r.get("ok") is True
    assert r.get("item_id"), "이력 행 ID가 없다"
    assert r.get("resolve_gap") == "no_final_url", f"판정이 틀렸다: {r.get('resolve_gap')}"
    assert r.get("message"), "문장이 안 실려 왔다"
    assert "펴진 링크가 오지 않아" in r["message"]


def test_link_diag_refuses_non_taobao_hosts():
    """★★★ 임의 주소를 서버가 대신 따 주면 그건 진단이 아니라 **열린 프록시**다."""
    from src.collectors.link_diag import diagnose_link, host_allowed

    assert host_allowed("https://e.tb.cn/h.abc") is True
    assert host_allowed("https://item.taobao.com/item.htm?id=1") is True
    for bad in ("https://example.com/x", "http://169.254.169.254/latest/meta-data/",
                "https://internal.local/admin"):
        assert host_allowed(bad) is False, f"허용목록이 새 준다: {bad}"
        out = diagnose_link(bad)
        assert out["ok"] is False and "타오바오" in out["error"]


def test_link_diag_records_every_hop_and_reports_the_real_error():
    """★★★ 홉마다 **상태코드와 Location 원문**. 실패는 **클래스명 그대로** — 덮지 않는다.

    「진단 실패」로 덮으면 진단을 또 해야 한다. 그게 F7-2가 오래 열려 있던 이유다.
    """
    from unittest.mock import patch, MagicMock
    from src.collectors import link_diag

    def _resp(status, loc=""):
        m = MagicMock()
        m.status_code = status
        m.headers = {"Location": loc} if loc else {}
        return m

    # UA 2종을 각각 재므로 체인도 **2벌** 준다. 한 벌만 주면 두 번째 측정이 StopIteration으로
    #   죽고, 그래도 대표가 첫 벌이라 계약은 초록이 된다 — 우연한 초록을 만들지 않는다.
    chain = [
        _resp(302, "https://m.intl.taobao.com/detail/detail.html?id=993154784090&price=199"),
        _resp(200),
    ] * 2
    with patch.object(link_diag, "MAX_HOPS", 8), \
         patch("requests.get", side_effect=chain):
        out = link_diag.diagnose_link("https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt")
    assert out["ok"] is True
    assert len(out["probes"]) == 2, "UA 2종을 재지 않았다"
    assert [p["ua_label"] for p in out["probes"]] == ["기본", "iOS Safari"]
    assert out["ua_disagree"] is False, "같은 응답인데 다르다고 말한다"
    assert out["hop_count"] == 2
    assert out["hops"][0]["status"] == 302 and out["hops"][0]["location"].startswith("https://m.intl")
    assert out["item_id"] == "993154784090"
    assert out["price"] == "199" and out["currency"] == "CNY"
    # 저장하는 형태는 세션성 값을 뺀 것 — 원문과 나란히 보여 주는 게 진단의 요점이다.
    assert out["final_url_kept"] and "suid" not in out["final_url_kept"]
    assert "펼 수 있습니다" in out["note"]

    class _Refused(Exception):
        pass

    with patch("requests.get", side_effect=_Refused("Connection refused")):
        bad = link_diag.diagnose_link("https://e.tb.cn/h.abc")
    assert bad["ok"] is False
    assert bad["error_class"] == "_Refused", "예외 클래스명을 덮었다"
    assert "Connection refused" in bad["error"], "원문 메시지를 덮었다"
    assert len(bad["probes"]) == 2 and all(p["error_class"] == "_Refused" for p in bad["probes"])


def test_link_diag_keeps_no_trace_of_session_values():
    """★★★ 진단 결과는 **저장하지 않고**, 로그에도 원문 URL을 남기지 않는다.

    최종 URL엔 `suid`(기기 UUID)·`un`(사용자 해시)·`wxsign`이 실려 온다(실측 원문).
    화면에 보여 주는 건 오너 자신의 값이지만 **쌓아 두면 우리가 만든 구멍**이다.
    """
    from pathlib import Path
    src = Path("src/collectors/link_diag.py").read_text(encoding="utf-8")
    for banned in ("history_append", "collect_history_store", "orders_pg", "tx("):
        assert banned not in src, f"진단이 저장한다: {banned}"
    # 로그가 **무엇을 싣는지**를 잰다 — 포맷 문자열을 그대로 핀으로 박지 않는다
    #   (그러면 문구를 다듬는 날 계약이 깨지면서 정작 개인정보는 안 본다).
    call = src.split("logger.info(")[-1].split("return out")[0]
    assert "hostname" in call, "로그가 호스트만 남기는지 확인할 수 없다"
    for leak in ("final_url", "body_title", "body_item_url", ".text"):
        assert leak not in call, f"로그 인자에 {leak}이(가) 실린다"


def test_link_diag_has_two_doors_and_they_are_reachable():
    """★★ 폰(토큰)과 콘솔(세션) 둘 다 — 그리고 **사이드바에 닿는 길**이 있다.

    응답 문구가 「링크 진단」을 가리키므로, 가리키기만 하고 길이 없으면 막다른 골목이다.
    """
    from pathlib import Path
    api = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert '@extension_bp.post("/link-diag")' in api
    assert "_require_token" in api.split('@extension_bp.post("/link-diag")')[1][:400], \
        "토큰 경로가 무인증이다"
    views = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert '"/collect/link-diag"' in views and "_check_auth()" in views
    base = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    assert "/seller/collect/link-diag" in base, "사이드바에서 닿을 수 없다"


def test_link_diag_template_uses_real_class_homes():
    """★★★ 쓴 클래스에 **CSS 홈이 있나.** 없으면 화면에선 맨 텍스트로 뜬다.

    실측 선례(6-l): `pc-pc-badge-*`처럼 규칙 없는 클래스를 뿌려도 잔재 계약은 초록이었다.
    그래서 홈을 직접 센다.
    """
    from pathlib import Path
    import re
    tpl = Path("src/seller_console/templates/collect_link_diag.html").read_text(encoding="utf-8")
    css = "".join(Path(p).read_text(encoding="utf-8") for p in
                  ("src/static/app.css", "src/seller_console/static/console.css"))
    # `class="..."` 안뿐 아니라 **템플릿 전체**에서 우리 접두어 토큰을 훑는다 —
    #   `{% set cls = 'pc-badge-on' %}`처럼 속성 밖으로 빼도 화면엔 그대로 나가니까.
    used = {c for c in re.findall(r"[a-z]+(?:-[a-z0-9]+)+", tpl)
            if c.startswith(("op-", "pc-", "console-"))}
    assert used, "검사할 클래스를 못 찾았다(정규식이 헛돌았다)"
    missing = [c for c in sorted(used) if f".{c}" not in css]
    assert not missing, f"CSS 홈이 없는 클래스: {missing}"


def test_enrich_pending_has_no_consumer_yet_and_we_say_so():
    """★★ **만들었는데 아무도 안 쓰는 큐** — 그 사실이 문서에 적혀 있어야 한다.

    실측(C-F9-2): `GET /enrich/pending`의 소비자가 0이다. 확장은 자기가 벌크수집한 항목만
    보강한다(`enrichTargets`). 폰이 만든 초안은 그 목록에 없다 → `pending`에서 안 움직인다.

    고치는 순서가 「링크 진단」 결과에 달려 있어 **오너 판단 대기**다. 그동안 이 계약이
    "없는 기능을 있다고 적지 않았나"를 지킨다 — 소비자가 생기면 이 계약을 바꿔야 한다.
    """
    from pathlib import Path
    ext = "".join(p.read_text(encoding="utf-8")
                  for p in Path("extensions/chrome-collector").glob("*.js"))
    doc = Path("docs/C_TAOBAO_FIELD_TEST.md").read_text(encoding="utf-8")
    if "enrich/pending" in ext:
        assert "소비자가 0" not in doc, "확장이 이제 폴링한다 — 문서를 갱신해야 한다"
    else:
        assert "소비자가 0" in doc, "안 쓰이는 큐를 안 쓰인다고 적지 않았다"


# ─────────────────────────────────────────────────────────────────────────────
# C-F10 — 최종이 200이면 본문도 본다 · UA 2종 · 계량값만 보고
# ─────────────────────────────────────────────────────────────────────────────

# 200 응답 본문 픽스처 — 안내·중간 페이지처럼 **본문에 상품 링크가 박힌** 형태.
#   실제 타오바오 HTML이 아니다(그건 저작물이고 우리가 가진 실측도 아니다) —
#   재는 것은 "우리 스캐너가 링크를 집어내는가"이므로 구조만 같으면 된다.
BODY_WITH_ITEM = """<!doctype html><html><head><title>淘宝 - 안내</title></head>
<body><div class="wrap">
  <p>계속하려면 아래를 누르세요</p>
  <a href="https://item.taobao.com/item.htm?spm=a1z10.5&id=993154784090">상품으로</a>
  <script>window.__INIT__={"foo":1};</script>
  <script src="/x.js"></script>
</div></body></html>"""

BODY_WALL = """<!doctype html><html><head><title>请登录 - 淘宝</title></head>
<body><div id="app"></div><script src="/a.js"></script><script src="/b.js"></script>
<script>var need_login=true;</script></body></html>"""


def _diag_resp(status, loc="", text=""):
    from unittest.mock import MagicMock
    m = MagicMock()
    m.status_code = status
    m.headers = {"Location": loc} if loc else {}
    m.text = text
    return m


def test_body_scan_finds_the_item_link_a_url_only_read_would_miss():
    """★★★ 최종 URL에 `id`가 없어도 **본문에 상품 링크가 있으면** 그걸 찾는다.

    안 보고 "상품번호 없음"이라 말하면 그건 **덜 보고 단정한 것**이다(F10-1).
    발명이 아니다 — 이미 받아 놓고 안 열어 본 것을 여는 것이다.
    """
    from unittest.mock import patch
    from src.collectors import link_diag

    # 최종 주소엔 id가 없다(안내 페이지). 본문엔 있다.
    chain = [_diag_resp(302, "https://m.intl.taobao.com/notice.html"),
             _diag_resp(200, text=BODY_WITH_ITEM)] * 2
    with patch("requests.get", side_effect=chain):
        out = link_diag.diagnose_link("https://e.tb.cn/h.abc")

    assert out["item_id"] == "", "주소엔 상품번호가 없어야 하는 픽스처다"
    assert out["body_item_id"] == "993154784090", "본문 상품번호를 못 찾았다"
    assert out["body_item_url"].startswith("https://item.taobao.com/item.htm")
    assert out["body_scanned"] is True
    # 출처가 다르면 섞지 않는다 — 주소에서 읽은 값으로 승격시키면 그게 날조다.
    assert out["item_id"] != out["body_item_id"]
    assert "본문에 상품 링크가 있습니다" in out["note"]


def test_body_scan_reports_only_measurements_when_nothing_found():
    """★★★ 못 찾으면 **길이·제목·스크립트 수만** 말한다. 본문 원문은 담지 않는다.

    "왜 못 찾았는지"를 가늠할 최소치다 — 짧고 스크립트 많으면 빈 껍데기,
    제목에 로그인이 보이면 로그인 벽. 그 이상은 진단에 필요 없는데 새면 곤란하다.
    """
    from unittest.mock import patch
    from src.collectors import link_diag

    chain = [_diag_resp(200, text=BODY_WALL)] * 2
    with patch("requests.get", side_effect=chain):
        out = link_diag.diagnose_link("https://item.taobao.com/item.htm")

    assert out["body_item_id"] == "" and out["body_item_url"] == ""
    assert out["body_len"] == len(BODY_WALL)
    assert out["body_title"] == "请登录 - 淘宝"
    assert out["body_script_count"] == 3
    # 본문 원문이 결과 어디에도 실리지 않는다.
    import json
    blob = json.dumps(out, ensure_ascii=False)
    assert "need_login=true" not in blob and "<div id=\"app\">" not in blob
    assert "빈 껍데기" in out["note"] or "로그인 벽" in out["note"]


def test_body_is_read_only_on_a_200_final_hop():
    """★★ 200이 아니면 본문을 읽지 않는다 — 읽을 것이 없고, 읽으면 그게 낭비다."""
    from unittest.mock import patch
    from src.collectors import link_diag

    chain = [_diag_resp(403, text=BODY_WITH_ITEM)] * 2
    with patch("requests.get", side_effect=chain):
        out = link_diag.diagnose_link("https://item.taobao.com/item.htm")
    assert out["final_status"] == 403
    assert out["body_scanned"] is False
    assert out["body_item_id"] == "" and out["body_len"] == 0


def test_ua_gating_is_measured_not_guessed():
    """★★★ 타오바오는 **UA로 응답을 가른다** — 그러니 두 번 재고 둘 다 돌려준다(F10-2).

    한 UA로만 재면 「막혔다」가 *서버 위치* 때문인지 *UA* 때문인지 구별이 안 된다.
    구별이 안 되는 측정으로 원인을 말하면 그게 F9-1에서 걸린 그 단정이다.
    """
    from unittest.mock import patch
    from src.collectors import link_diag

    assert [lbl for lbl, _ in link_diag.UA_PROBES] == ["기본", "iOS Safari"]
    assert link_diag.UA_PROBES[0][1] == "", "'기본'은 UA 미지정이어야 비교가 된다"

    # 기본 UA는 막히고, iOS Safari는 통과하는 경우 — 실제로 가리는 상황.
    calls = []

    def _get(u, **kw):
        ua = (kw.get("headers") or {}).get("User-Agent", "")
        calls.append(ua)
        if "iPhone" in ua:
            return _diag_resp(200, text=BODY_WITH_ITEM)
        return _diag_resp(403, text="")

    with patch("requests.get", side_effect=_get):
        out = link_diag.diagnose_link("https://item.taobao.com/item.htm")

    assert len(out["probes"]) == 2
    assert out["ua_disagree"] is True, "응답이 갈렸는데 갈렸다고 말하지 않는다"
    # 대표는 **더 멀리 간 쪽** — 상품번호를 얻은 측정이다.
    assert out["best_ua"] == "iOS Safari"
    assert out["body_item_id"] == "993154784090"
    # 두 측정이 각자 자기 결과를 갖고 있어야 비교가 된다(대표로 덮어쓰지 않는다).
    by = {p["ua_label"]: p for p in out["probes"]}
    assert by["기본"]["final_status"] == 403 and by["기본"]["body_item_id"] == ""
    assert by["iOS Safari"]["final_status"] == 200
    assert "" in calls, "UA 미지정 측정이 없었다"


def test_link_diag_page_shows_both_probes_and_the_body_verdict():
    """★★ 화면이 **둘 다** 보여 주는가 — 결과를 하나로 뭉개면 비교할 수 없다."""
    from unittest.mock import patch
    from src.order_webhook import app

    def _get(u, **kw):
        ua = (kw.get("headers") or {}).get("User-Agent", "")
        return _diag_resp(200, text=BODY_WITH_ITEM) if "iPhone" in ua else _diag_resp(403)

    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "default"
    with patch("requests.get", side_effect=_get):
        r = c.post("/seller/collect/link-diag",
                   data={"url": "https://e.tb.cn/h.8IcTrtZuTU19ieN"})
    body = r.data.decode()
    assert r.status_code == 200
    assert "UA 기본" in body and "UA iOS Safari" in body, "두 측정이 화면에 없다"
    assert "993154784090" in body, "본문에서 찾은 상품번호가 화면에 없다"
    assert "UA에 따라 응답이 달랐습니다" in body, "갈렸다는 사실을 화면이 말하지 않는다"


# ─────────────────────────────────────────────────────────────────────────────
# C-F11 — 서버가 단축 링크를 편다(실측이 문을 다시 열었다) · 마크다운은 사용자 면 전체 금지
# ─────────────────────────────────────────────────────────────────────────────

# 오너 실측 2026-09-12(링크 진단 라이브): `e.tb.cn` → **200**(UA 무관) → 본문에 상품 링크.
#   픽스처는 캡처 원문에서 `un`·`suid`·`bxsign`·`ut_sk`·`sp_tk`를 **뺀** 형태다 —
#   기기 UUID·사용자 해시·세션 서명은 열쇠가 아니고, 레포에 남기면 우리가 만든 구멍이다.
BODY_F11 = """<!doctype html><html><head><title>淘宝</title></head><body>
<a href="https://item.taobao.com/item.htm?spm=a1z10.3-c.w4002&amp;id=1060535477134&amp;price=76.86&amp;sourceType=item">去看看</a>
<script>var x=1;</script></body></html>"""


def test_server_can_open_the_short_link_after_all():
    """★★★ **실측이 닫았던 문을 실측이 다시 열었다.**

    F9까지 우리는 「서버는 타오바오를 못 읽는다」고 적었다. 그건 **리다이렉트 쿼리만 봤기
    때문**이다 — 쿼리엔 `id`가 없었고, **본문에는 있었다.** 덜 보고 닫은 문이었다.

    이 계약이 지키는 것: 단축 링크를 펴서 **상품번호와 공유 시점 가격**을 얻고,
    URL을 **정규형**으로 바꾼다(추적 파라미터 0). 페이지 수집은 여전히 안 한다.
    """
    from unittest.mock import patch
    from src.collectors import link_diag

    chain = [_diag_resp(302, "https://main.m.taobao.com/mid.html"),
             _diag_resp(200, text=BODY_F11)]
    with patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "1"}), \
         patch("requests.get", side_effect=chain):
        r = link_diag.resolve_short_link("https://e.tb.cn/h.8reU77YYNhKOUuE?tk=EYAGT7vTcVD")

    assert r["ok"] is True, f"펴지 못했다: {r}"
    assert r["item_id"] == "1060535477134"
    assert r["price"] == "76.86" and r["currency"] == "CNY"
    assert r["reason"] == "ok"
    # 정규형 — 추적 파라미터가 **하나도** 남지 않는다.
    assert r["canonical_url"] == "https://item.taobao.com/item.htm?id=1060535477134"
    for junk in ("spm", "tk", "sourceType", "price", "un", "suid"):
        assert junk not in r["canonical_url"], f"{junk}가 정규형에 남았다"


def test_resolver_failure_branches_ride_resolve_gap_verbatim():
    """★★★ 실패는 **갈래 그대로** 실린다 — 원인을 짐작해 붙이지 않는다.

    200인데 본문에 상품이 없는 것과, 아예 열지 못한 것은 **다른 사실**이다.
    한 문장으로 뭉개면 다음 사람이 또 재야 한다.
    """
    from unittest.mock import patch
    from src.collectors import link_diag
    from src.collectors.share_text import resolve_gap

    short = "https://e.tb.cn/h.abc"
    with patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "1"}), \
         patch("requests.get", side_effect=[_diag_resp(200, text="<html><body>없음</body></html>")]):
        r = link_diag.resolve_short_link(short)
    assert r["ok"] is False and r["reason"] == "no_item_in_body"
    assert resolve_gap({"price": "", "resolve_reason": r["reason"]}) == "server_opened_no_item"

    class _Refused(Exception):
        pass

    with patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "1"}), \
         patch("requests.get", side_effect=_Refused("nope")):
        r2 = link_diag.resolve_short_link(short)
    assert r2["reason"] == "error:_Refused"
    assert resolve_gap({"price": "", "resolve_reason": r2["reason"]}) == "server_could_not_open"

    # **안 해 본 것은 실패가 아니다.** 끈 상태·단축 링크가 아닌 경우를 실패로 적으면 날조다.
    for not_tried in ("disabled", "not_short_link", ""):
        assert resolve_gap({"price": "", "resolve_reason": not_tried}) == "no_final_url"


def test_a_bare_short_link_becomes_a_draft_with_price():
    """★★★ 맨 단축 URL 하나로도 **가격까지 담긴 초안**이 선다 → `uncollected`에서 price 탈락.

    이게 F9-2의 세 겹 막힘 중 1번을 푼다: 가격이 오면 등록 게이트가 열린다.
    """
    from unittest.mock import patch
    from src.collectors.share_collect import collect_from_share_text
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass

    chain = [_diag_resp(200, text=BODY_F11)]
    with patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "1"}), \
         patch("requests.get", side_effect=chain):
        r = collect_from_share_text("https://e.tb.cn/h.8reU77YYNhKOUuE?tk=EYAGT7vTcVD",
                                    seller_id="default", translate=False)

    assert r["ok"] is True, f"초안이 안 섰다: {r}"
    assert r["item_id_taobao"] == "1060535477134"
    assert r["price"] == "76.86" and r["currency"] == "CNY"
    assert "price" not in r["uncollected"], f"가격이 왔는데 미수집에 남았다: {r['uncollected']}"
    # C-F14: 등록 가능 여부는 `gate_ready`다. `enrich_state`는 **보강**(이미지·옵션) 진행이라
    #   가격만 왔을 땐 여전히 `pending`이다 — 한 필드에 두 뜻을 지우지 않는다.
    assert r["gate_ready"] is True, "가격이 왔으면 등록 게이트가 열려야 한다"
    assert r["enrich_state"] == "pending", "이미지가 없는데 보강 완료로 적는다"
    assert r["resolve_gap"] == "ok"
    # 저장 URL이 정규형 — 같은 상품이 단축/편 링크로 두 번 담겨도 한 키로 합쳐진다.
    assert r["url"] == "https://item.taobao.com/item.htm?id=1060535477134"
    from src.collectors.product_key import normalize_product_key
    assert normalize_product_key(r["url"]) == normalize_product_key(
        "https://m.intl.taobao.com/detail/detail.html?id=1060535477134&price=76.86")


def test_phone_supplied_values_win_over_the_server_probe():
    """★★ 폰이 이미 펴 줬으면 **다시 나가지 않는다** — 같은 값을 두 번 재지 않는다.

    폰이 준 값이 더 가까운 시점이고, 요청 안에서 한 번 더 밖으로 나가면 그건 낭비다.
    """
    from unittest.mock import patch
    from src.collectors.share_collect import collect_from_share_text
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass

    with patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "1"}), \
         patch("requests.get") as spy:
        r = collect_from_share_text(SHARE_FIXTURE, seller_id="default", translate=False,
                                    final_url=FINAL_URL_FIXTURE)
    assert spy.call_count == 0, "폰이 이미 펴 줬는데 서버가 또 나갔다"
    assert r["item_id_taobao"] == "993154784090" and r["price"] == "199"


def test_no_markdown_anywhere_a_user_can_see_it():
    """★★★ 마크다운 금지를 **사용자 도달면 전체**로 넓힌다 — 소스가 아니라 결과를 잰다.

    F8-a에서 내가 넣은 `**…**`가 토스트에 별표로 그대로 떴다. 소스 문자열로 재면
    docstring과 구별이 안 되니(39건 중 대부분이 주석) **렌더된 화면·API 응답·토스트 호출**을 본다.
    """
    import json
    import re
    from unittest.mock import patch
    from src.order_webhook import app

    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "default"

    # ① 렌더된 화면 — `<script>`·`<style>` 걷어낸 **보이는 글**에 `**`가 없어야 한다.
    for path in ("/seller/collect/link-diag", "/seller/collect/history", "/seller/collect"):
        html = c.get(path).data.decode()
        visible = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "", html, flags=re.S | re.I)
        assert "**" not in visible, f"{path} 보이는 글에 마크다운이 있다"

    # ② API 응답의 사람 문장
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}):
        for body in ({"share_text": ""}, {"share_text": "￥HU591￥"},
                     {"share_text": FIX_SWEATER}):
            d = c.post("/api/v1/collect/one", json=body).get_json() or {}
            for key in ("message", "error"):
                val = str(d.get(key) or "")
                assert "**" not in val, f"API {key}에 마크다운: {val}"
                assert not re.search(r"`[^`]+`", val), f"API {key}에 백틱: {val}"

    # ③ 수집 함수들이 내는 **error 문장** — 실측(C-F11): `collect_input`의 거절 문장에
    #   `**통째로**`가 살아 있었는데 ①②로는 안 잡혔다. 그 경로가 안 밟혔기 때문이다.
    #   그래서 실패 갈래를 **직접 불러** 문장을 꺼낸다.
    from src.collectors.share_collect import collect_from_share_text, collect_input
    probes = [
        lambda: collect_input("", seller_id="default"),
        lambda: collect_input("￥HU591￥", seller_id="default"),
        lambda: collect_input("링크 없는 글입니다", seller_id="default"),
        lambda: collect_input("https://e.tb.cn/h.zzz", seller_id="default", translate=False),
        lambda: collect_from_share_text("", seller_id="default"),
        lambda: collect_from_share_text("https://e.tb.cn/h.zzz", seller_id="default",
                                        translate=False),
    ]
    for fn in probes:
        out = fn() or {}
        for key in ("error", "message"):
            val = str(out.get(key) or "")
            assert "**" not in val, f"수집 {key}에 마크다운: {val}"
            assert not re.search(r"`[^`]+`", val), f"수집 {key}에 백틱: {val}"

    # ④ 토스트 호출 인자
    from pathlib import Path
    for p in list(Path("src").rglob("*.js")) + list(Path("extensions").rglob("*.js")):
        t = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"(?:pcToast|showGlobalToast|kgpToast)\s*\(\s*([\"'`])(.*?)\1", t, re.S):
            assert "**" not in m.group(2), f"{p.name} 토스트에 마크다운: {m.group(2)[:80]}"
    del json


def test_diag_price_card_reads_the_body_price():
    """★★ 본문에 가격이 있는데 화면이 「없음」이라 적으면 그것도 **덜 보고 단정**한 것이다."""
    from unittest.mock import patch
    from src.order_webhook import app

    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "default"
    with patch("requests.get", side_effect=[_diag_resp(200, text=BODY_F11)] * 2):
        r = c.post("/seller/collect/link-diag", data={"url": "https://e.tb.cn/h.abc"})
    body = r.data.decode()
    assert "76.86" in body, "본문에서 읽은 가격이 화면에 없다"
    assert "1060535477134" in body


# ─────────────────────────────────────────────────────────────────────────────
# C-F12 — 어디서 오래 걸렸나(timings) · 일곱 번째 입구 · 기준을 사실로 위장하지 않기
# ─────────────────────────────────────────────────────────────────────────────

# 오너 실물(2026-09-12): 소싱 URL 검수에 붙인 tmall **풀링크**. 상품번호가 URL에 박혀 있다.
#   세션성 값은 넣지 않는다(`un`·`suid`·`bxsign`·`ut_sk`·`sp_tk` 제외 — F11과 같은 규율).
FIX_TMALL_FULL = ("https://detail.tmall.com/item.htm"
                  "?spm=a1z10.5-b&id=1060535477134&price=76.86&sourceType=item")


def test_response_says_where_the_time_went():
    """★★★ 폰이 「요청한 시간이 초과되었습니다」로 죽었는데 **어디서** 느렸는지 알 길이 없었다.

    모르는 채 예산을 조이면 엉뚱한 데를 조인다. 그래서 단계별 밀리초를 응답에 싣는다 —
    **밀리초만** 싣는다(원문·URL 0).
    """
    from unittest.mock import patch
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    c = app.test_client()
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}), \
         patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "1"}), \
         patch("requests.get", side_effect=[_diag_resp(200, text=BODY_F11)]):
        d = c.post("/api/v1/collect/one", json={"share_text": "https://e.tb.cn/h.abc"}).get_json()

    t = d.get("timings") or {}
    assert t, f"timings가 없다: {d}"
    for stage in ("parse", "resolve", "save", "total"):
        assert stage in t, f"{stage} 구간이 없다: {t}"
        assert isinstance(t[stage], int) and t[stage] >= 0
    assert t["total"] >= max(t[k] for k in t if k != "total"), "total이 구간 합보다 작다"
    # 실패 응답에도 실린다 — 느려서 죽는 건 실패할 때도 마찬가지다.
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}):
        bad = c.post("/api/v1/collect/one", json={"share_text": ""}).get_json()
    assert (bad.get("timings") or {}).get("total") is not None, "실패 응답에 timings가 없다"
    # 밀리초 말고 아무것도 들어가지 않는다(원문 유출 금지).
    import json
    assert all(isinstance(v, int) for v in t.values()), f"timings에 숫자 아닌 값: {t}"
    del json


def test_the_seventh_entry_point_is_registered():
    """★★★ **일곱 번째 입구.** 검수표가 코어를 직접 주입해 쓰는데 목록에 없었다.

    그래서 「타오바오는 초안으로」 규율이 여기만 안 서 있었고, tmall 풀링크가
    「수집 실패(실데이터 못 얻음)」로 떨어졌다 — F8에서 배운 것과 **같은 모양**이다.
    """
    from src.collectors.share_text import COLLECT_ENTRY_POINTS

    labels = [lbl for lbl, _, _ in COLLECT_ENTRY_POINTS]
    assert "소싱 URL 검수" in labels, "검수표 입구가 목록에 없다"
    assert len(COLLECT_ENTRY_POINTS) == 7


def test_a_full_tmall_link_is_not_called_a_collection_failure():
    """★★★ 상품번호가 **URL에 박혀 있는데** 「실데이터 못 얻음」이라 적으면 그건 거짓이다.

    실측(오너 2026-09-12): 소싱 URL 검수에 tmall 풀링크를 넣으니 수집 실패로 떨어졌다.
    못 얻은 게 아니라 **안 본 것**이었다.
    """
    from src.seller_console.views import build_review_for_urls

    r = build_review_for_urls([FIX_TMALL_FULL])
    assert len(r["failed"]) == 0, f"아직 수집 실패로 떨어진다: {r['failed']}"
    assert len(r["review_pass"]) == 1

    row = r["review_pass"][0]
    assert row["item_id_taobao"] == "1060535477134"
    # 없는 것은 **없다고 적는다** — 통과 숫자만 보고 등록 가능으로 읽지 않게.
    assert row["partial"] is True and row["needs_enrich"] is True
    assert set(row["missing"]) == {"제목", "이미지"}
    assert len(r["needs_enrich"]) == 1, "보강 필요 집계가 없다"


def test_image_zero_is_a_registration_bar_not_a_collection_failure():
    """★★★ 이미지 0장은 **등록 기준 미달**이다. 「수집 실패」라 적으면 오너가 수집기를 고치러 간다.

    기준을 사실로 위장하면 엉뚱한 데를 고치게 만든다 — 그게 이 문장이 나쁜 이유다.
    """
    from pathlib import Path
    from src.pipeline.register_pipe import register_source_rows

    # 소스 문자열이 아니라 **오너가 읽는 문장**을 잰다 — 소스로 재면 내가 단 주석(옛 문구 인용)을
    #   읽고 빨개진다(실측: 그렇게 한 번 헛돌았다).
    row = {"url": "https://item.taobao.com/item.htm?id=1", "title_ko": "제목",
           "sale_krw": 30000, "excluded": False, "category_code": "GEN"}
    out = register_source_rows([row], dispatch_fn=lambda *a, **k: {"success": True},
                               enrich_fn=lambda r: {"images": [], "description_html": ""},
                               approved=True, n=1, sleep_fn=lambda *_: None)
    reasons = [r.get("reason", "") for r in (out.get("results") or [])]
    assert reasons, f"행 결과가 없다: {out}"
    joined = " ".join(reasons)
    assert "이미지 0장" in joined, f"이미지 0장 갈래가 아니다: {joined}"
    assert "수집 실패" not in joined, f"이미지 0장을 수집 실패라 부른다: {joined}"
    assert "등록 기준 미달" in joined, f"무엇이 기준 미달인지 안 말한다: {joined}"

    # 「검수 통과」의 정의는 **취급판정**이다(완성도가 아니다) — 그 사실이 코드에 남아 있어야 한다.
    src = Path("src/pipeline/register_pipe.py").read_text(encoding="utf-8")
    assert '"review_pass": [r for r in review if not r["excluded"]]' in src
    assert '"needs_enrich"' in src, "완성도를 따로 세지 않는다"


def test_titles_lose_full_width_brackets_but_keep_their_content():
    """★★ 전각 괄호 문자는 떼고 **내용은 남긴다.** 짝이 맞는 괄호는 건드리지 않는다.

    실측 2026-09-12: `【淘宝】…`는 이미 통째로 지워졌는데 `「제목」`은 괄호가 그대로 남았다.
    공유 파서가 「」를 구분자로 쓰므로 제목의 일부일 수 없다.
    반대로 `（2개입）`처럼 **짝이 맞는** 것은 실제 스펙일 수 있어 남긴다 — 내용 훼손 금지.
    """
    from src.pipeline.coupang_replicate import clean_title_ko

    assert clean_title_ko("「新中式双人书桌」")["title"] == "新中式双人书桌"
    assert clean_title_ko("『일본판』 상품명")["title"] == "일본판 상품명"
    assert clean_title_ko("【淘宝】新中式双人书桌")["title"] == "新中式双人书桌"
    # 짝 안 맞는 괄호 = 잘린 흔적 → 제거
    assert "】" not in clean_title_ko("商品名】잘린 괄호")["title"]
    assert "（" not in clean_title_ko("（未閉 商品名")["title"]
    # 짝이 맞으면 그대로 — 스펙을 지우지 않는다
    assert clean_title_ko("상품명（2개입）")["title"] == "상품명（2개입）"
    # 전부 지워지는 입력이면 원문 보존(빈 제목 금지)
    assert clean_title_ko("「」")["title"] == "「」"


def test_blacklist_applies_at_review_not_only_at_register():
    """★★ 금칙어는 **검수 단계에서** 걸린다 — 등록까지 가서 걸리는 게 아니다.

    F12-B 질문에 대한 답을 코드로 못 박는다: `build_source_review_row`가 `is_forbidden(title)`을
    불러 `excluded`를 세우고, 검수표가 그걸로 「취급 제외」를 가른다.
    """
    from pathlib import Path
    src = Path("src/pipeline/register_pipe.py").read_text(encoding="utf-8")
    row_fn = src[src.index("def build_source_review_row("):src.index("def build_source_review(")]
    assert "is_forbidden(title" in row_fn, "검수 행에서 금칙어를 안 본다"
    assert '"excluded": bool(fb)' in row_fn

    # 제목이 비면 금칙어로 걸릴 수 없다 — 부분 초안이 '취급 제외'로 오분류되지 않아야 한다.
    from src.pipeline.register_pipe import is_forbidden
    assert not is_forbidden("", blacklist=["담배"]), "빈 제목을 금칙어로 잡는다"


def test_the_six_second_budget_is_wall_clock_not_per_hop():
    """★★★ 「6초 예산」이 **문서에만** 있었다 — 코드엔 홉당 타임아웃뿐이었다.

    실측(C-F12-A): `MAX_HOPS=8` × 6s = **최악 48초.** 폰이 「요청한 시간이 초과되었습니다」로
    죽은 것이 그대로 설명된다. 예산은 **전체 시간**이어야 하고, 넘기면 **해석 없이 초안**을
    돌려준다 — 요청이 죽는 것보다 부분 초안이 낫다.
    """
    import time
    from unittest.mock import MagicMock, patch
    from src.collectors import link_diag
    from src.collectors.share_text import gap_message, resolve_gap

    hops = {"n": 0}

    def _slow(u, **kw):
        hops["n"] += 1
        time.sleep(0.4)
        m = MagicMock()
        m.status_code = 302
        m.headers = {"Location": f"https://main.m.taobao.com/x{hops['n']}"}
        m.text = ""
        return m

    t0 = time.monotonic()
    with patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "1"}), \
         patch("requests.get", side_effect=_slow):
        r = link_diag.resolve_short_link("https://e.tb.cn/h.abc", timeout=1)
    elapsed = time.monotonic() - t0

    assert elapsed < 2.5, f"예산 1s인데 {elapsed:.1f}s 걸렸다(홉당으로 새고 있다)"
    assert r["reason"] == "timeout", f"예산 초과 갈래가 아니다: {r}"
    assert r["ok"] is False

    # 오너 지정 갈래 — 초안은 그대로 서고, 화면이 왜 반쪽인지 말한다.
    assert resolve_gap({"price": "", "resolve_reason": "timeout"}) == "server_timeout"
    msg = gap_message({"price": "", "resolve_reason": "timeout"})
    assert "시간이 너무 걸려" in msg
    assert "다시 보내실 필요는 없습니다" in msg, "담긴 것이 남아 있다는 사실을 말해야 한다"
    assert "**" not in msg and "VPN" not in msg


def test_connect_and_read_budgets_are_separate():
    """★★ 한 숫자로 주면 연결 단계에서 예산을 전부 태울 수 있다 — 그래서 튜플로 준다."""
    from unittest.mock import MagicMock, patch
    from src.collectors import link_diag

    seen = []

    def _cap(u, **kw):
        seen.append(kw.get("timeout"))
        m = MagicMock()
        m.status_code = 200
        m.headers = {}
        m.text = BODY_F11
        return m

    with patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "1"}), \
         patch("requests.get", side_effect=_cap):
        link_diag.resolve_short_link("https://e.tb.cn/h.abc", timeout=6)

    assert seen and isinstance(seen[0], tuple), f"timeout이 튜플이 아니다: {seen}"
    connect, read = seen[0]
    assert connect <= link_diag.CONNECT_TIMEOUT_SEC
    assert read <= 6


def test_the_expand_action_is_documented_as_optional():
    """★★ 서버가 펴 주게 된 뒤로 폰이 한 번 더 나갈 이유가 줄었다 — 가이드가 그걸 말해야 한다.

    실측: 그 액션이 있는 채로 단축어가 타임아웃으로 죽었다. 권장을 안 바꾸면
    유저는 계속 느린 쪽을 조립한다.
    """
    from pathlib import Path
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    seg = guide[guide.index("### 액션 3"):guide.index("### 액션 4")]
    assert "선택" in seg, "선택이라고 말하지 않는다"
    assert "빼시는 쪽을 권합니다" in seg or "빼도 됩니다" in seg
    assert "final_url" in seg, "무엇을 지우면 되는지 말해야 한다"
    assert "timings" in guide, "느릴 때 무엇을 보는지 적혀 있지 않다"


# ─────────────────────────────────────────────────────────────────────────────
# C-F13 — 정제기가 수집 경로도 탄다 · 보강 소비자(폴러·막힘·가격 2종) · 원본 보존
# ─────────────────────────────────────────────────────────────────────────────

def test_api_response_title_is_cleaned_not_just_the_review_table():
    """★★★ 계약을 **함수가 아니라 API 응답 title**로 잰다(오너 지정).

    실측(라이브): 응답 제목이 「iPhone 17 신제품**】**」이었다. 정제기는 있었지만
    **등록·검수 파이프에서만** 불렸다 — 같은 결함이 두 화면에서 다르게 보인 이유다.
    함수를 재면 "정제기는 잘 돈다"는 초록이 나오고 경로는 계속 새어 있다.
    """
    from unittest.mock import patch
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    c = app.test_client()
    fix = "【淘宝】https://e.tb.cn/h.zz?tk=ABC\n「iPhone 17 신제품】」\n点击链接"
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}):
        d = c.post("/api/v1/collect/one", json={"share_text": fix, "translate": False}).get_json()

    assert d.get("ok") is True, f"수집이 실패했다: {d}"
    title = d.get("title") or ""
    assert title == "iPhone 17 신제품", f"정제되지 않은 제목: {title!r}"
    for junk in ("】", "【", "「", "」"):
        assert junk not in title, f"{junk}가 응답 제목에 남았다"


def test_pending_queue_hides_blocked_and_carries_attempts():
    """★★★ `blocked`는 대기가 아니다 — 큐가 같은 벽에 계속 머리를 박지 않게 뺀다.

    상한(`ENRICH_MAX_ATTEMPTS`)을 **서버가** 들고 있어야 확장 판본이 달라도 지켜진다.
    """
    from unittest.mock import patch
    from src.api.extension_api import ENRICH_MAX_ATTEMPTS
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    assert ENRICH_MAX_ATTEMPTS == 3, "오너 지정 상한(3회)"
    try:
        chs._in_memory.clear()
    except Exception:
        pass
    c = app.test_client()
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}), \
         patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "0"}):
        made = c.post("/api/v1/collect/one",
                      json={"share_text": "【淘宝】https://e.tb.cn/h.q1?tk=T\n「책상」",
                            "translate": False}).get_json()
        item_id = made["item_id"]
        assert made.get("enrich_state") == "pending"

        pend = c.get("/api/v1/collect/enrich/pending").get_json()
        ids = [i["item_id"] for i in pend["items"]]
        assert item_id in ids, "대기 목록에 없다"
        assert pend["items"][ids.index(item_id)]["attempts"] == 0

        # 상한 미달 — 아직 대기로 남는다(한 번 막혔다고 포기하지 않는다).
        r1 = c.post("/api/v1/collect/enrich/blocked",
                    json={"item_id": item_id, "reason": "로그인 벽"}).get_json()
        assert r1["attempts"] == 1 and r1["state"] == "pending"
        assert item_id in [i["item_id"] for i in c.get("/api/v1/collect/enrich/pending").get_json()["items"]]

        for _ in range(ENRICH_MAX_ATTEMPTS - 1):
            rN = c.post("/api/v1/collect/enrich/blocked",
                        json={"item_id": item_id, "reason": "로그인 벽"}).get_json()
        assert rN["attempts"] == ENRICH_MAX_ATTEMPTS and rN["state"] == "blocked"
        # 굳은 뒤엔 대기 목록에서 빠진다.
        assert item_id not in [i["item_id"] for i in
                              c.get("/api/v1/collect/enrich/pending").get_json()["items"]]


def test_two_taobao_prices_are_kept_apart():
    """★★★ 타오바오는 가격을 **둘** 보여 준다(优惠前 / 补贴后). 합치면 어느 쪽인지 영영 모른다.

    마진의 분모는 **실제로 내는 값**이라 补贴后가 우선이고, 무엇을 썼는지 `price_basis`로 남긴다.
    """
    import json
    from unittest.mock import patch
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    c = app.test_client()
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}), \
         patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "0"}):
        made = c.post("/api/v1/collect/one",
                      json={"share_text": "【淘宝】https://e.tb.cn/h.q2?tk=T\n「의자」",
                            "translate": False}).get_json()
        item_id = made["item_id"]
        r = c.post("/api/v1/collect/enrich",
                   json={"item_id": item_id, "price_list": "199", "price_final": "76.86",
                         "currency": "CNY", "gallery": ["https://img.alicdn.com/a.jpg"]}).get_json()
    assert r["ok"] is True

    row = chs.get(item_id, seller_ids={"default"})
    ex = json.loads(row["extra_json"])
    assert ex["price_list"] == "199", "할인 전 가격이 사라졌다"
    assert ex["price_final"] == "76.86", "보조금 후 가격이 사라졌다"
    assert ex["price"] == "76.86", "마진 분모는 실제 내는 값이어야 한다"
    assert ex["price_basis"] == "보조금 후", "무엇을 썼는지 안 적었다"
    # 가격이 왔으니 등록 게이트가 열린다(보강 축과 별개).
    assert ex["gate_ready"] is True


def test_originals_survive_and_stored_copies_are_never_faked():
    """★★★ 원본 URL은 **그대로** 남는다(D트랙 재번역 대비). 저장본이 없으면 없다고 적는다.

    CDN 미설정 시 파이프라인은 원본 URL을 그대로 돌려준다 — 그 값을 「저장본」이라 적으면
    같은 URL을 두 번 적는 셈이고, 화면은 저장된 줄 안다.
    """
    import json
    from unittest.mock import patch
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    c = app.test_client()
    orig = ["https://img.alicdn.com/one.jpg", "https://img.alicdn.com/two.jpg"]
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}), \
         patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "0"}):
        made = c.post("/api/v1/collect/one",
                      json={"share_text": "【淘宝】https://e.tb.cn/h.q3?tk=T\n「램프」",
                            "translate": False}).get_json()
        c.post("/api/v1/collect/enrich",
               json={"item_id": made["item_id"], "gallery": orig}).get_json()

    ex = json.loads(chs.get(made["item_id"], seller_ids={"default"})["extra_json"])
    assert ex["images"] == orig, "원본 URL이 바뀌었다"
    assert not ex.get("images_stored"), "CDN 미설정인데 저장본이 생겼다(가짜)"
    assert ex.get("images_stored_note"), "왜 저장본이 없는지 안 적었다"
    assert orig[0] not in (ex.get("images_stored") or []), "원본을 저장본이라 적었다"


def test_the_extension_actually_polls_the_pending_queue():
    """★★★ F9-2가 찾은 마지막 막힘 — `/enrich/pending`의 **소비자가 0**이었다.

    만들어 둔 큐에 소비자가 없으면 그건 기능이 아니라 장식이다.
    폴러는 ①콘솔 탭 열림 ②5분 주기(`alarms` — MV3 서비스워커는 잠들므로 setInterval 불가).
    """
    from pathlib import Path
    bg = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")

    assert "enrich/pending" in bg, "대기 목록을 조회하지 않는다"
    assert "chrome.alarms" in bg and "periodInMinutes" in bg, "주기 폴링이 없다"
    assert "KGP_ENRICH_POLL_MIN = 5" in bg, "오너 지정 5분 주기"
    assert "chrome.tabs.onUpdated" in bg and "_kgpIsConsoleUrl" in bg, "콘솔 탭 열림 감지가 없다"
    # 주기 폴링이 `alarms`로 도는지는 위에서 쟀다. "근처에 setInterval이 없다" 같은
    #   **소스 위치** 검사는 하지 않는다 — 무관한 코드가 옆에 오면 깨지고, 정작 폴링은 안 본다.
    # 중복 투입 방지 — 5분마다 도는데 같은 상품을 또 열면 그게 봇 신호다.
    assert "KgpEnrich.queued" in bg, "같은 항목 중복 투입을 막지 않는다"
    # 막힘 보고 경로
    assert "enrich/blocked" in bg and "_kgpReportBlocked" in bg
    # 오너 지정: 동시 1탭 · 3~8초 · 재시도 3회
    assert "KGP_ENRICH_MAX_RETRIES = 3" in bg
    assert "3000 + Math.floor(r * 5000)" in bg, "항목 간 간격이 3~8초가 아니다"
    # alarms 권한이 실제로 선언돼 있어야 주기 폴링이 돈다
    import json
    mani = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
    assert "alarms" in mani["permissions"], "alarms 권한 없이 주기 폴링은 안 돈다"


def test_the_extension_detects_walls_and_does_not_try_to_break_them():
    """★★★ 로그인 벽·캡차는 **감지만** 한다. 뚫는 코드는 우회이고 오너가 금지했다."""
    from pathlib import Path
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")

    assert "_kgpDetectWall" in cs, "벽 감지가 없다"
    seg = cs[cs.index("function _kgpDetectWall"):]
    seg = seg[:seg.index("function _kgpSitePdp")]
    # 감지 근거는 화면에 보이는 것뿐 — 쿠키·헤더·토큰을 만지면 그건 우회다.
    for banned in ("document.cookie", "localStorage.setItem", "XMLHttpRequest", "fetch("):
        assert banned not in seg, f"벽 감지가 {banned}를 만진다(우회 금지)"
    assert "captcha" in seg and "登录" in seg, "실제 벽 표시를 안 본다"

    # 타오바오 옵션·가격 2종 추출이 있다
    assert "price_list" in cs and "price_final" in cs
    assert "补贴后" in cs and "优惠前" in cs, "두 가격 라벨을 안 본다"


def test_queue_screen_shows_real_state_not_a_hardcoded_zero():
    """★★★ 전엔 `queue_size: 0`이 **하드코딩**돼 무엇을 하든 「대기 중 0건」이었다.

    화면이 있는데 아무것도 말하지 않으면 없는 것보다 나쁘다 — 믿고 안 보게 된다.
    """
    from unittest.mock import patch
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "default"
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}), \
         patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "0"}):
        made = c.post("/api/v1/collect/one",
                      json={"share_text": "【淘宝】https://e.tb.cn/h.q4?tk=T\n「선반」",
                            "translate": False}).get_json()
        # 한 번 막힌 것(아직 재시도 남음)도 **지난 시도 사유**가 보여야 한다 —
        #   기록해 두고 안 보여 주면 없는 것과 같다.
        c.post("/api/v1/collect/enrich/blocked",
               json={"item_id": made["item_id"], "reason": "로그인 벽 감지"})
        mid = c.get("/seller/media/queue").data.decode()
        assert "로그인 벽 감지" in mid, "재시도 남은 항목의 지난 사유가 화면에 없다"
        assert "1/3" in mid, "시도 횟수가 안 보인다"
        # 상한까지 막히면 「막힘」으로 굳는다.
        for _ in range(2):
            c.post("/api/v1/collect/enrich/blocked",
                   json={"item_id": made["item_id"], "reason": "로그인 벽 감지"})

    body = c.get("/seller/media/queue").data.decode()
    assert "로그인 벽 감지" in body, "막힌 사유가 화면에 없다"
    assert "선반" in body, "막힌 항목이 화면에 없다"
    assert "3/3" in body, "상한에 닿은 시도 횟수가 안 보인다"
    # 개발 표기·이모지·v2 문법이 함께 사라졌는지(이 화면은 스텁이었다)
    assert "Phase 144" not in body and "🖼" not in body
    assert "bg-success" not in body and "alert-info" not in body


# ─────────────────────────────────────────────────────────────────────────────
# C-F14 — 한 필드에 두 뜻 · 목록이 성공을 실패로 읽었다
# ─────────────────────────────────────────────────────────────────────────────

def _seed_owner_screen():
    """오너 실측 화면(2026-09-12 15:08)을 그대로 모사한다.

    소파 78 CNY / iPhone17 469 / iPhone18 469 — 셋 다 **F11 잔재**(`done` + 이미지 0장).
    회전 큐브 — F11 이전(가격 없음, `pending`).
    """
    from src.seller_console import collect_history_store as chs
    try:
        chs._in_memory.clear()
    except Exception:
        pass
    rows = [
        ("소파 뒤쪽 수납 선반", "78", "done", [], None),
        ("iPhone17 신제품", "469", "done", [], None),
        ("iPhone18 필수템", "469", "done", [], None),
        ("회전 큐브", "", "pending", [], None),
    ]
    ids = []
    for t, p, st, imgs, reason in rows:
        ex = {"title": t, "price": p, "currency": "CNY", "images": imgs, "mode": "share",
              "enrich_state": st, "uncollected": ["images", "options", "description"]}
        if reason:
            ex["enrich_blocked_reason"] = reason
            ex["enrich_attempts"] = 3
        ids.append(chs.append(source="mobile",
                              url=f"https://item.taobao.com/item.htm?id={abs(hash(t)) % 10**12}",
                              title=t, image="", price=p, currency="CNY", seller_id="default",
                              status=("ok" if p else "보강 대기"), extra=ex))
    return ids


def test_a_draft_with_price_is_never_called_a_collection_failure():
    """★★★ 제목·상품번호·가격이 **다 담긴** 셋이 목록에 「실패 · 추출 실패」로 떴다(오너 실측).

    이미지가 없다는 이유였다. 그런데 초안은 **아직 반쪽인 게 정상**이고, 「실패」는
    초안 자체가 없을 때 쓰는 말이다. 완전 수집 잣대(7필드)를 부분 초안에 들이댄 것이다.

    **계약은 목록 렌더 응답 HTML로 잰다**(오너 지정 — F3 재발 방지).
    함수를 재면 "판정기는 잘 돈다"는 초록이 나오고 화면은 계속 거짓말을 한다.
    """
    from src.order_webhook import app

    _seed_owner_screen()
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "default"
    html = c.get("/seller/collect/history").data.decode()

    assert "실패 · 추출 실패" not in html, "가격까지 담긴 초안을 아직 실패라 부른다"
    # 넷 다 보강 대기여야 한다(가격 유무는 등록 축이지 보강 축이 아니다).
    assert html.count("보강 대기") >= 4, "초안이 보강 대기로 안 보인다"
    for title in ("소파 뒤쪽 수납 선반", "iPhone17 신제품", "iPhone18 필수템", "회전 큐브"):
        assert title in html, f"{title} 행이 없다"


def test_list_badges_follow_the_owner_spec():
    """★★★ 배지 규칙(오너 지정) — 목록 렌더 HTML로 잰다.

    `gate_ready & pending` → 「보강 대기」 / `blocked` → 「막힘 · <사유>」 / `done` → 「완료」.
    사유는 **서버가 적은 그대로** — 지어내지 않는다.
    """
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    cases = [
        ("완료된 상품", "100", "pending", ["u1", "u2", "u3"], None),
        ("막힌 상품", "50", "blocked", [], "로그인 벽 감지"),
        ("대기 상품", "70", "pending", [], None),
    ]
    for t, p, st, imgs, reason in cases:
        ex = {"title": t, "price": p, "currency": "CNY", "images": imgs, "mode": "share",
              "enrich_state": st}
        if reason:
            ex["enrich_blocked_reason"] = reason
            ex["enrich_attempts"] = 3
        chs.append(source="mobile", url=f"https://item.taobao.com/item.htm?id={abs(hash(t)) % 10**9}",
                   title=t, image="", price=p, currency="CNY", seller_id="default",
                   status="ok", extra=ex)

    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "default"
    html = c.get("/seller/collect/history").data.decode()

    assert "막힘 · 로그인 벽 감지" in html, "막힌 사유를 서버 기록 그대로 안 보여 준다"
    assert "보강 대기" in html
    assert "완료" in html
    assert "실패" not in html.split("막힘 · 로그인 벽 감지")[0][-2000:], "막힘을 실패라 부른다"


def test_the_two_axes_never_share_a_field():
    """★★★ **한 필드에 두 뜻을 지우지 않는다** — 이게 세 화면에서 성공→실패를 뒤집은 뿌리다.

    F3(결과 카드) · F12(검수표) · F14(목록) — 세 번 같은 자리에서 났다.
    `gate_ready`(등록 가능) 와 `enrich_state`(보강 진행)는 **다른 축**이다.
    """
    from src.collectors.collect_status import enrich_axes

    # 가격만 있고 이미지 없음 = 등록은 되지만 보강은 안 됐다.
    ax = enrich_axes({"price": "78", "images": []})
    assert ax["gate_ready"] is True and ax["enrich_state"] != "done"

    # F11 잔재 — 저장된 `done`을 그대로 믿지 않는다(이미지가 없으면 보강은 안 끝났다).
    legacy = enrich_axes({"price": "78", "enrich_state": "done", "images": []})
    assert legacy["gate_ready"] is True, "가격이 있으면 등록 축은 열려 있어야 한다"
    assert legacy["enrich_state"] == "pending", "이미지 0장인데 보강 완료로 읽는다"

    # 이미지가 실제로 왔을 때만 done.
    ok = enrich_axes({"price": "78", "enrich_state": "pending", "images": ["a"]})
    assert ok["enrich_state"] == "done"

    # 막힘은 덮어쓰지 않는다(사람이 개입해야 풀리는 상태다).
    blocked = enrich_axes({"price": "78", "enrich_state": "blocked", "images": []})
    assert blocked["enrich_state"] == "blocked"


def test_legacy_rows_reach_the_poller_without_a_manual_migration():
    """★★★ 이관 스크립트를 **손으로 돌려야만** 고쳐진다면, 안 돌린 동안 화면은 계속 거짓말한다.

    그리고 폴러가 저장된 원값(`done`)을 보고 건너뛰면 그 행들은 **영영 이미지가 안 들어온다** —
    라이브 판정이 설계상 불가능해진다(오너 지적).
    """
    from unittest.mock import patch
    from src.order_webhook import app

    _seed_owner_screen()
    c = app.test_client()
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}):
        d = c.get("/api/v1/collect/enrich/pending").get_json()

    titles = [i["title"] for i in d["items"]]
    for t in ("소파 뒤쪽 수납 선반", "iPhone17 신제품", "iPhone18 필수템"):
        assert t in titles, f"F11 잔재 {t}가 폴러 대상에 없다 — 영영 보강 안 된다"
    assert d["total"] == 4


def test_lean_projection_carries_what_the_list_needs():
    """★★ 목록은 `lean` projection만 받는다 — 거기 없는 필드는 **화면이 알 수 없다.**

    실측: 보강 축을 추가했는데 lean 허용목록에 안 넣어서 배지가 안 떴다.
    그리고 lean은 이미지를 **첫 장만** 싣는다 → 개수를 세면 늘 1이라 "1장 · 완료"가 된다.
    """
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    chs.append(source="mobile", url="https://item.taobao.com/item.htm?id=7", title="x", image="",
               price="78", currency="CNY", seller_id="default", status="ok",
               extra={"title": "x", "price": "78", "images": ["a", "b", "c"],
                      "mode": "share", "enrich_state": "pending"})
    import json as _json
    row = chs.list_items(seller_ids={"default"}, days=90, limit=5, lean=True)[0]
    ex = _json.loads(row["extra_json"])
    for key in ("gate_ready", "enrich_state", "enrich_blocked_reason", "enrich_attempts",
                "images_count", "price"):
        assert key in ex, f"lean에 {key}가 없어 목록이 못 읽는다"
    assert ex["images_count"] == 3, "lean이 첫 장만 싣는데 개수를 안 세 보낸다"

    from src.collectors.collect_status import enrich_axes
    assert enrich_axes(ex)["images"] == 3, "배지가 '1장'이라 적게 된다"


def test_a_taobao_short_link_draft_is_not_suspected_of_being_a_non_product():
    """★★ 「비상품 의심」의 근거가 **가격·이미지 없음**이면 그건 초안에 그대로 해당된다.

    실측: 타오바오 **공식 단축 도메인**(`tb.cn`)이 쇼핑 호스트 목록에서 빠져 있어,
    폰으로 담은 초안이 「소싱처 화이트리스트 밖」으로 70점을 받았다 —
    쇼핑몰인데 쇼핑몰이 아니라고 읽은 것이다.
    """
    import json
    from src.seller_console.collect_hygiene import classify_row

    short = classify_row({"url": "https://e.tb.cn/h.8reU?tk=ABC",
                          "extra_json": json.dumps({"title": "회전 큐브"})})
    assert short["is_candidate"] is False, f"단축 링크 초안을 비상품으로 의심한다: {short}"

    draft = classify_row({"url": "https://item.taobao.com/item.htm?id=1",
                          "extra_json": json.dumps({"title": "x", "enrich_state": "pending"})})
    assert draft["is_candidate"] is False, "보강 대기 초안을 비상품으로 의심한다"

    # 진짜 비상품은 그대로 잡혀야 한다(오탐을 줄이려다 검출을 죽이지 않는다).
    mail = classify_row({"url": "https://mail.google.com/mail/u/0",
                         "extra_json": json.dumps({"title": "받은편지함"})})
    assert mail["is_candidate"] is True, "진짜 비상품을 놓친다"


def test_extension_banner_only_on_desktop_chromium():
    """★★ 확장은 **데스크톱 크롬 계열에만** 있다.

    모바일·사파리에서 「확장이 감지되지 않았어요」는 고칠 수 없는 일을 고치라는 말이라
    안내가 아니라 소음이다(오너 실측: 폰에서 떴다).
    """
    from pathlib import Path
    html = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
    seg = html[html.index("extFreshBanner"):]
    seg = seg[:seg.index("function paint")]
    assert "navigator.userAgent" in seg, "UA를 안 본다"
    assert "_isMobile" in seg and "_isChromium" in seg
    assert "return;" in seg, "확장을 설치할 수 없는 환경에서 빠져나오지 않는다"

    # 판정 자체를 node로 실증한다(정규식이 맞는지 눈으로 믿지 않는다).
    import re
    import subprocess
    m = re.search(r"var _isMobile = (/.+?/i)\.test\(_ua\);", seg)
    m2 = re.search(r"var _isChromium = (.+?);", seg)
    assert m and m2
    js = f"""
    const chk=(u)=>{{const _ua=u;const _isMobile={m.group(1)}.test(_ua);
      const _isChromium={m2.group(1)};return (_isMobile||!_isChromium)?'숨김':'표시';}};
    const out=[chk('Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/128.0 Safari/537.36'),
               chk('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'),
               chk('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36'),
               chk('Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15')];
    console.log(JSON.stringify(out));
    """
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    import json as _j
    assert _j.loads(r.stdout.strip()) == ["표시", "숨김", "숨김", "숨김"], r.stdout


# ─────────────────────────────────────────────────────────────────────────────
# C-F15 — 네 번째 화면이 원값을 읽었다 · 계정이 갈렸는데 아무 화면도 말하지 않았다
# ─────────────────────────────────────────────────────────────────────────────

def test_the_enrich_queue_screen_does_not_read_raw_state():
    """★★★ **네 번째 화면.** F14에서 목록·게이트·폴러 셋을 보정했는데, 내가 F13에서 만든
    「이미지 처리 대기」를 빠뜨렸다 — 그래서 이미지 0장인 F11 잔재가 그 화면에서만 「완료」로 떴다.

    실측(오너 폰 콘솔 2026-09-12 16:53): 대기 1 · **완료 3**(전부 이미지 0장).
    계약은 렌더 HTML로 잰다(오너 지정).
    """
    import re
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    # 오너 화면 4행 — 회전 큐브(가격 없음) + F11 잔재 3(가격 있고 이미지 0장, 원값 `done`)
    for t, p, st in [("회전 큐브", "", "pending"), ("소파 뒤쪽 수납 선반", "78", "done"),
                     ("iPhone17 신제품", "469", "done"), ("iPhone18 필수템", "469", "done")]:
        chs.append(source="mobile",
                   url=f"https://item.taobao.com/item.htm?id={abs(hash(t)) % 10**12}",
                   title=t, image="", price=p, currency="CNY", seller_id="default",
                   status=("ok" if p else "보강 대기"),
                   extra={"title": t, "price": p, "images": [], "mode": "share",
                          "enrich_state": st,
                          "uncollected": ["images", "options", "description"]})

    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "default"
    html = c.get("/seller/media/queue").data.decode()

    def kpi(label):
        m = re.search(re.escape(label) + r'</div>\s*<div class="op-kpi-v mt-1">(\d+)', html)
        return int(m.group(1)) if m else -1

    assert kpi("보강 완료") == 0, "이미지 0장인데 「완료」로 센다"
    assert kpi("보강 대기") == 4, "잔재가 대기로 안 잡힌다"


def test_every_enrich_state_reader_goes_through_the_helper():
    """★★★ 세 곳을 고치고 네 번째를 놓쳤다 — 그래서 **읽는 자리를 상수로** 둔다.

    F8 입구 전수와 같은 방식: 계약이 목록을 순회하며 "그 파일이 `enrich_axes`를 부르는가"를
    본다. 새 읽는 자리가 생기면 계약이 먼저 깨진다.
    """
    from pathlib import Path
    from src.collectors.collect_status import ENRICH_STATE_READERS

    assert len(ENRICH_STATE_READERS) >= 6
    for label, path, marker in ENRICH_STATE_READERS:
        src = Path(path).read_text(encoding="utf-8")
        assert marker in src, f"{label}: 표식 {marker!r}가 {path}에 없다(이름이 바뀌었나)"
        assert "enrich_axes" in src, f"{label}({path})가 보정 함수를 안 쓴다 — 원값을 읽는다"


def test_the_poller_hands_the_extension_corrected_values():
    """★★ 확장도 **원값을 믿지 않게** 보정값을 함께 받는다.

    확장이 저장된 `enrich_state`를 다시 읽어 판단하면 같은 잔재에 또 걸린다.
    """
    from unittest.mock import patch
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    chs.append(source="mobile", url="https://item.taobao.com/item.htm?id=5", title="책상",
               image="", price="78", currency="CNY", seller_id="default", status="ok",
               extra={"title": "책상", "price": "78", "images": [], "mode": "share",
                      "enrich_state": "done"})           # F11 잔재
    c = app.test_client()
    with patch("src.api.extension_api._require_token", return_value={"user_id": "default"}):
        d = c.get("/api/v1/collect/enrich/pending").get_json()

    assert d["total"] == 1, "잔재가 큐에 안 올라온다"
    it = d["items"][0]
    assert it["gate_ready"] is True, "등록 가능 여부를 확장에 안 알려 준다"
    assert it["images_count"] == 0, "이미지 개수를 안 알려 준다"


def test_every_console_screen_says_which_account_it_is_showing():
    """★★★ **계정은 보이지 않는 필터다.**

    실측(오너 2026-09-12 16:53): PC 콘솔 대기 0건, 폰 콘솔 4건. 단축어 토큰이 **다른 계정**으로
    발급돼 있었고 **어느 화면도 그 사실을 말하지 않았다** — 사람은 목록이 비어 보이는 이유를
    알 길이 없고, PC 확장은 폰 초안을 영영 못 본다.
    """
    from src.order_webhook import app

    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "shanks8@hanmail.net"

    for path in ("/seller/media/queue", "/seller/collect/history", "/seller/me/tokens"):
        html = c.get(path).data.decode()
        assert "shanks8@hanmail.net" in html, f"{path}가 어느 계정인지 말하지 않는다"

    # 발급 화면의 안내는 토큰이 없을 때도 보여야 한다(발급 **전에** 알아야 하는 정보다).
    tok = c.get("/seller/me/tokens").data.decode()
    assert "고가수집기가 도는 크롬에 로그인한 계정" in tok, "어느 계정에서 발급해야 하는지 안 말한다"

    # 토큰이 있으면 **발급 계정 열**과 「다른 계정」 표시가 뜬다.
    from unittest.mock import patch
    other = [{"token_hash": "h1", "token_hash_prefix": "kgp_ab", "user_id": "other@example.com",
              "scopes": ["collect.write"], "created_at": "2026-09-12T00:00:00",
              "last_used_at": "", "expires_at": "", "revoked": False}]
    with patch("src.auth.personal_tokens.list_tokens", return_value=other):
        tok2 = c.get("/seller/me/tokens").data.decode()
    assert "발급 계정" in tok2, "토큰 목록에 발급 계정 열이 없다"
    assert "other@example.com" in tok2, "발급 계정을 안 보여 준다"
    assert "다른 계정" in tok2, "세션과 다른 계정인데 표시하지 않는다"


def test_the_collect_response_says_where_it_landed():
    """★★ 「담았어요」만으로는 **어디에** 담겼는지 모른다 — 계정이 갈리면 그게 전부다."""
    from unittest.mock import patch
    from src.order_webhook import app
    from src.seller_console import collect_history_store as chs

    try:
        chs._in_memory.clear()
    except Exception:
        pass
    c = app.test_client()
    with patch("src.api.extension_api._require_token",
               return_value={"user_id": "shanks8@hanmail.net"}), \
         patch.dict("os.environ", {"KGP_SHORT_LINK_RESOLVE": "0"}):
        d = c.post("/api/v1/collect/one",
                   json={"share_text": "【淘宝】https://e.tb.cn/h.zz?tk=A\n「책상」",
                         "translate": False}).get_json()

    assert d["account"] == "shanks8@hanmail.net"
    assert "shanks8@hanmail.net 계정에 담았어요" in d["message"]
    assert "**" not in d["message"]


def test_the_guide_leads_with_the_account_rule():
    """★★ 가이드가 **조립보다 먼저** 계정을 말한다 — 다 만들고 나서 알면 늦다(오너 지정).

    C-F17: 이 계약이 절 제목(「## 1. 준비」·「## 2. iOS 단축어」)을 글자로 박고 있었다.
    폰 기본 입구가 텔레그램으로 바뀌면서 절 번호가 밀리자, **옳은 변경인데 빨개졌다** —
    계약이 글자를 박으면 진실을 막는 문이 된다([[계약이 글자를 박으면 옳은 변경도 막는다]]).
    그래서 번호가 아니라 **순서**를 잰다.
    """
    from pathlib import Path
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    i_rule = guide.find("고가수집기가 도는 크롬에 로그인한 계정")
    i_build = guide.find("액션 1 —")          # 단축어 조립이 시작되는 자리
    assert i_rule != -1, "가이드가 계정 규칙을 말하지 않는다"
    assert i_build == -1 or i_rule < i_build, "조립 설명이 계정 규칙보다 먼저 나온다"
    head = guide[i_rule:i_rule + 600]
    assert "서로 다른 목록" in head or "다른 목록으로" in head or "PC 목록에 보이지 않" in head, \
        "계정이 여럿이면 안 되는 이유가 없다"


def test_the_token_screen_is_named_by_its_real_nav_path():
    """★★ 화면 이름은 **나브에 적힌 그대로** 쓴다 — 「내 토큰」은 실제로 없는 이름이었다.

    실측(오너 2026-09-12): 가이드·안내가 「내 토큰」이라 적었는데 사이드바엔 그 항목이 없다.
    실제 경로는 **설정 → 「내 정보·설정」 / 「API 토큰」**이다. 없는 메뉴 이름을 안내하면
    유저가 찾다가 자기를 의심한다 — [[모드 이름을 세 번 발명했다]]와 같은 종류의 오류다.
    """
    from pathlib import Path

    # ① 나브에 두 이름이 실제로 있다(우리가 쓰는 이름이 화면에 있는지 먼저 확인).
    base = Path("src/seller_console/templates/_base.html").read_text(encoding="utf-8")
    assert "<span>API 토큰</span>" in base, "나브에 'API 토큰' 항목이 없다"
    assert "<span>내 정보·설정</span>" in base, "나브에 '내 정보·설정' 항목이 없다"

    # ② 「내 토큰」은 **어디에도 남지 않는다**(사용자 문장·문서·주석 전부 — 오너 지시 '전수').
    roots = [Path("src"), Path("docs"), Path("tests"), Path("extensions")]
    hits = []
    for root in roots:
        for p in root.rglob("*"):
            if p.suffix not in (".py", ".html", ".js", ".md") or "__pycache__" in str(p):
                continue
            # 이 계약 자신은 제외한다 — 금지어를 설명하려면 그 낱말을 써야 한다.
            if p.resolve() == Path(__file__).resolve():
                continue
            try:
                if "내 토큰" in p.read_text(encoding="utf-8"):
                    hits.append(str(p))
            except Exception:
                continue
    assert not hits, f"없는 메뉴 이름 「내 토큰」이 남았다: {hits}"

    # ③ 사용자가 찾아갈 자리를 안내하는 곳은 **실명 + 경로**를 함께 준다.
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    assert "내 정보·설정 → API 토큰" in guide and "/seller/me/tokens" in guide
    api = Path("src/api/extension_api.py").read_text(encoding="utf-8")
    assert "내 정보·설정 → API 토큰" in api, "401 안내가 옛 이름을 쓴다"


# ---------------------------------------------------------------------------
# C-F17-A — 계정은 **사람이 읽는 이름**으로. UUID는 응답에 없다.
#   실측(오너 2026-09-13, PC curl): `collect/one`이 account·message에 UUID를 실었다.
#   근원은 `user_store`의 깨진 import(늘 ImportError → find_by_id가 언제나 None)였고,
#   앞 판의 폴백 「못 찾으면 user_id를 그대로」가 늘 발동했다.
# ---------------------------------------------------------------------------

_UUID_LIKE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


@pytest.fixture()
def client():
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


@pytest.fixture()
def _fake_user_store(monkeypatch):
    """사용자 저장소를 살아 있는 것으로 바꿔 끼운다(시트 없이도 이름을 찾게)."""
    from src.auth import account_label as al

    class _U:
        email = "shanks8@hanmail.net"
        name = "고가브릿지"

    class _S:
        def __init__(self, hit=True):
            self.hit = hit

        def find_by_id(self, uid):
            return _U() if self.hit else None

    def _install(hit=True):
        import src.auth.user_store as us
        monkeypatch.setattr(us, "get_store", lambda: _S(hit), raising=False)
        al.reset_cache()

    al.reset_cache()
    yield _install
    al.reset_cache()


def _collect_one(client, token, text):
    return client.post("/api/v1/collect/one", json={"text": text},
                       headers={"Authorization": f"Bearer {token}"})


def test_collect_one_names_the_account_by_email_not_uuid(client, _fake_user_store):
    """계약은 **API 응답**으로 잰다 — 함수가 아니라 사람이 받는 것이 답이다(F3 재발 방지)."""
    from src.auth import personal_tokens as pt
    uid = "f275b60d-0000-4000-8000-00000000f17a"
    raw = pt.generate_token(user_id=uid, scopes=["collect.write"])["raw_token"]

    _fake_user_store(hit=True)
    r = _collect_one(client, raw, "https://item.taobao.com/item.htm?id=1060535477134")
    body = json.dumps(r.get_json() or {}, ensure_ascii=False)

    assert (r.get_json() or {}).get("account") == "shanks8@hanmail.net"
    assert "shanks8@hanmail.net 계정에 담았어요" in (r.get_json() or {}).get("message", "")
    assert not _UUID_LIKE.search(body), f"응답에 UUID가 남았다: {body[:400]}"


def test_collect_one_omits_the_account_line_when_it_cannot_name_it(client, _fake_user_store):
    """못 찾으면 **줄을 뺀다** — 읽을 수 없는 값으로 채우지 않는다."""
    from src.auth import personal_tokens as pt
    uid = "f275b60d-0000-4000-8000-00000000f17b"
    raw = pt.generate_token(user_id=uid, scopes=["collect.write"])["raw_token"]

    _fake_user_store(hit=False)
    r = _collect_one(client, raw, "https://item.taobao.com/item.htm?id=1060535477135")
    d = r.get_json() or {}

    assert "account" not in d, "이름을 못 찾았는데 계정 칸을 만들었다"
    assert "계정에 담았어요" not in d.get("message", "")
    assert not _UUID_LIKE.search(json.dumps(d, ensure_ascii=False))


def test_the_user_store_import_is_not_broken():
    """근원 — `user_store`가 없는 이름을 import하면 계정 이름을 **영영** 못 찾는다."""
    import importlib
    import src.utils.sheets as sheets
    src_text = Path("src/auth/user_store.py").read_text(encoding="utf-8")
    names = re.findall(r"from src\.utils\.sheets import ([^\n]+)", src_text)
    assert names, "user_store가 sheets에서 무엇을 가져오는지 못 읽었다"
    for chunk in names:
        for n in [x.strip() for x in chunk.split(",") if x.strip()]:
            assert hasattr(sheets, n), f"src.utils.sheets에 {n}이(가) 없다 — 저장소가 죽는다"
    importlib.reload(sheets)


def test_the_token_screen_shows_a_readable_issuing_account(client, _fake_user_store):
    """계약은 **렌더된 HTML**로 잰다 — 칸이 있어도 값이 안 오면 사람에겐 없는 것이다."""
    from src.auth import personal_tokens as pt
    uid = "f275b60d-0000-4000-8000-00000000f17c"
    pt.generate_token(user_id=uid, scopes=["collect.write"])

    _fake_user_store(hit=True)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["user_email"] = "shanks8@hanmail.net"
        s["user_role"] = "seller"
    html = client.get("/seller/me/tokens").get_data(as_text=True)

    assert "발급 계정" in html
    assert "shanks8@hanmail.net" in html
    assert not _UUID_LIKE.search(html), "토큰 화면에 UUID가 찍혔다"


def test_console_header_never_prints_a_uuid_as_the_account(client, _fake_user_store):
    """세션에 이메일이 없어도 머리줄은 UUID를 말하지 않는다(C-F15가 남긴 폴백)."""
    uid = "f275b60d-0000-4000-8000-00000000f17d"
    _fake_user_store(hit=True)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["user_role"] = "seller"
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert not _UUID_LIKE.search(html), "수집 목록 머리줄이 UUID를 찍었다"


# ---------------------------------------------------------------------------
# C-F17-B — 폰 **기본 입구**는 텔레그램 봇이다(단축어는 선택).
#   실측(오너 2026-09-13): 폰 단축어가 VPN on/off·서버 무관 「네트워크 연결 유실」.
#   같은 순간 PC curl은 HTTP 200 · 2.5초 — 서버는 멀쩡했다. 앞단 Cloudflare까지의
#   중국 셀룰러 도달성은 우리 통제 밖이라, 우리가 못 고치는 구간을 지나는 길을 기본으로 삼는다.
# ---------------------------------------------------------------------------

_TG_SECRET = "f17-secret"


@pytest.fixture()
def tg(client, monkeypatch):
    """봇 웹훅 호출기 + 봇이 **실제로 보낸 문장**을 모으는 통."""
    import src.api.telegram_collect as tc
    from src.db import telegram_links_pg as tl

    monkeypatch.setenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", _TG_SECRET)
    monkeypatch.delenv("TELEGRAM_COLLECT_CHAT_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_COLLECT_SELLER_ID", raising=False)
    tl.reset_for_tests()

    sent: list = []

    def _fake_api(method, payload):
        sent.append((method, payload))
        return {"ok": True}

    monkeypatch.setattr(tc, "_api", _fake_api)

    def _send(text, chat_id="777", message_id=42, secret=_TG_SECRET):
        return client.post(
            "/webhooks/telegram/collect",
            json={"message": {"text": text, "message_id": message_id, "chat": {"id": chat_id}}},
            headers={"X-Telegram-Bot-Api-Secret-Token": secret})

    _send.sent = sent
    _send.texts = lambda: [p["text"] for m, p in sent if m == "sendMessage"]
    return _send


def test_bot_refuses_to_collect_before_the_chat_is_linked(tg):
    """묶이지 않은 chat은 **담지 않는다** — 아무 스코프에나 쓰면 남의 목록에 섞인다."""
    r = tg(SHARE_FIXTURE)
    assert r.status_code == 403 and (r.get_json() or {}).get("error") == "not_linked"
    assert any("/link" in t for t in tg.texts()), "무엇을 해야 하는지 말해 주지 않았다"


def test_link_binds_the_chat_and_never_stores_the_token(tg, _fake_user_store):
    """`/link <토큰>` 1회 → 바인딩. 토큰 **원문은 저장되지 않고** 메시지는 지워진다."""
    from src.auth import personal_tokens as pt
    from src.db import telegram_links_pg as tl
    uid = "f275b60d-0000-4000-8000-00000000f17e"
    raw = pt.generate_token(user_id=uid, scopes=["collect.write"])["raw_token"]

    _fake_user_store(hit=True)
    r = tg(f"/link {raw}")
    assert r.status_code == 200 and (r.get_json() or {}).get("linked")
    assert tl.user_id_for("777") == uid, "바인딩이 저장되지 않았다"

    assert any(m == "deleteMessage" for m, _ in tg.sent), "토큰이 적힌 메시지를 지우려 하지 않았다"
    joined = "\n".join(tg.texts())
    assert raw not in joined, "회신이 토큰 원문을 되뱉었다"
    assert "shanks8@hanmail.net 계정에 연결" in joined
    assert not _UUID_LIKE.search(joined), "회신에 UUID가 남았다"


def test_bot_reply_carries_title_item_id_and_account_in_one_wording(tg, _fake_user_store):
    """픽스처 → 핸들러 → **응답 텍스트**. 문장은 단축어와 같은 한 곳에서 나온다."""
    from src.auth import personal_tokens as pt
    from src.db import telegram_links_pg as tl
    uid = "f275b60d-0000-4000-8000-00000000f17f"
    pt.generate_token(user_id=uid, scopes=["collect.write"])
    tl.link("777", uid)
    _fake_user_store(hit=True)

    r = tg(SHARE_FIXTURE)
    assert r.status_code == 200 and (r.get_json() or {}).get("ok")
    text = "\n".join(tg.texts())

    assert text.startswith("담았어요 — "), f"첫 줄이 다르다: {text[:80]}"
    assert "新中式双人书桌" in text or (r.get_json() or {}).get("title"), "제목을 말하지 않았다"
    assert "가격 미수집" in text, "공유 글엔 가격이 없다 — 없다고 말해야 한다"
    assert "(shanks8@hanmail.net 계정에 담았어요)" in text
    assert "**" not in text and "__" not in text, "마크다운은 평문에서 그냥 기호로 보인다"
    assert not _UUID_LIKE.search(text)


def test_bot_answers_the_sender_in_plain_text(tg, _fake_user_store):
    """소스가 아니라 **보낸 것**으로 잰다 — 주석을 읽는 계약은 옳은 변경도 막는다(C-F10 교훈).

    예전 답장은 `notifications.send_telegram`을 거쳐 고정 알림방(`TELEGRAM_CHAT_ID`)으로 갔고
    앞에 이모지와 내부 표기를 붙였다. 둘 다 페이로드로 확인한다.
    """
    from src.auth import personal_tokens as pt
    from src.db import telegram_links_pg as tl
    uid = "f275b60d-0000-4000-8000-00000000f180"
    pt.generate_token(user_id=uid, scopes=["collect.write"])
    tl.link("888", uid)
    _fake_user_store(hit=True)

    tg(SHARE_FIXTURE, chat_id="888")
    msgs = [p for m, p in tg.sent if m == "sendMessage"]
    assert msgs, "답장을 보내지 않았다"
    for p in msgs:
        assert str(p["chat_id"]) == "888", "보낸 사람이 아니라 다른 방으로 답했다"
        assert "parse_mode" not in p, "평문으로 보낸다(마크다운 해석 금지)"
        assert "[proxy-commerce]" not in p["text"], "일반 사용자에게 내부 표기가 노출된다"
        assert not re.match(r"^[\u2139\u26a0\U0001F000-\U0001FAFF]", p["text"]), "이모지 접두 금지"


def test_bot_and_shortcut_say_the_same_sentence(tg, client, _fake_user_store):
    """같은 상품을 두 입구로 담으면 **같은 문장**이 와야 한다 — 아니면 다른 일이 난 줄 안다."""
    from src.auth import personal_tokens as pt
    from src.db import telegram_links_pg as tl
    uid = "f275b60d-0000-4000-8000-00000000f181"
    raw = pt.generate_token(user_id=uid, scopes=["collect.write"])["raw_token"]
    tl.link("999", uid)
    _fake_user_store(hit=True)

    tg(SHARE_FIXTURE, chat_id="999")
    bot_text = "\n".join(p["text"] for m, p in tg.sent if m == "sendMessage")

    # 같은 상품을 두 번 담으면 뒤엣것은 「이미 수집한 상품」이 된다 — 그래서 단축어 쪽은
    # **다른 상품**의 같은 형태 공유 글로 잰다(둘의 사연이 같으면 문장도 같아야 한다).
    shortcut = (_collect_one(client, raw, SHARE_FIXTURE_SOFA).get_json() or {}).get("message", "")
    core = shortcut.split(" (")[0].strip()          # 계정 괄호는 봇이 제 줄로 따로 붙인다
    assert core and core in bot_text, f"봇 문장이 단축어와 다르다\n봇: {bot_text}\n단축어: {core}"


def test_telegram_is_listed_as_a_collect_entry_point():
    """입구 상수에 있어야 한다 — 목록에 없는 입구는 코어 가드를 안 받는지 아무도 모른다."""
    from src.collectors.share_text import COLLECT_ENTRY_POINTS
    rows = [e for e in COLLECT_ENTRY_POINTS if "telegram" in e[1]]
    assert rows, "텔레그램이 수집 입구 목록에 없다"
    assert rows[0][2] == "collect_input", "봇이 단일 판단점을 타는지 목록이 말해야 한다"


def test_bot_without_a_webhook_secret_does_nothing(tg, monkeypatch):
    """잠금 장치가 없으면 열어 두지 않는다."""
    monkeypatch.delenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", raising=False)
    assert tg(SHARE_FIXTURE).status_code == 503
    monkeypatch.setenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", _TG_SECRET)
    assert tg(SHARE_FIXTURE, secret="wrong").status_code == 403


def test_guide_puts_the_bot_first_and_the_shortcut_second():
    """가이드 순서가 곧 권고다 — 되는 길을 1번에 둔다."""
    g = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    i_bot, i_sc = g.find("텔레그램"), g.find("단축어")
    assert i_bot != -1 and i_sc != -1, "가이드에 두 경로가 다 있어야 한다"
    assert i_bot < i_sc, "단축어가 텔레그램보다 먼저 나온다(실측상 되는 길이 뒤에 있다)"
    assert "VPN" in g


# ---------------------------------------------------------------------------
# C-F17b — 봇 하나는 수신구 하나. 수집 봇은 따로 판다(오너 결정).
# ---------------------------------------------------------------------------

def test_reply_goes_to_the_sender_chat_not_a_fixed_room(monkeypatch, client):
    """★ 발신 chat_id로 **직접** 보낸다 — 고정 알림방(`TELEGRAM_CHAT_ID`)으로 가지 않는다.

    `_api`가 아니라 **HTTP 한 겹 아래**(requests.post)에서 잡아, 어느 봇 토큰으로
    어느 chat에 갔는지 URL·본문으로 확인한다.
    """
    import src.api.telegram_collect as tc
    from src.auth import personal_tokens as pt
    from src.db import telegram_links_pg as tl

    monkeypatch.setenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", "f17b")
    monkeypatch.setenv("TELEGRAM_COLLECT_BOT_TOKEN", "COLLECTBOT:zzz")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TRENDBOT:aaa")       # 폴링으로 도는 공용 봇
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "고정알림방")
    monkeypatch.delenv("TELEGRAM_COLLECT_CHAT_IDS", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    tl.reset_for_tests()

    uid = "f275b60d-0000-4000-8000-00000000f17b"
    pt.generate_token(user_id=uid, scopes=["collect.write"])
    tl.link("55501", uid)

    calls: list = []

    class _R:
        ok = True
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    import requests
    monkeypatch.setattr(requests, "post",
                        lambda url, **kw: (calls.append((url, kw.get("json") or {})), _R)[1])

    client.post("/webhooks/telegram/collect",
                json={"message": {"text": SHARE_FIXTURE, "message_id": 7, "chat": {"id": "55501"}}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "f17b"})

    sends = [(u, b) for u, b in calls if u.endswith("/sendMessage")]
    assert sends, f"sendMessage를 부르지 않았다: {calls}"
    for url, body in sends:
        assert "COLLECTBOT:zzz" in url, f"수집 전용 봇이 아니라 다른 토큰으로 보냈다: {url}"
        assert "TRENDBOT" not in url, "공용(폴링) 봇 토큰으로 보냈다"
        assert str(body.get("chat_id")) == "55501", f"발신 chat이 아니다: {body.get('chat_id')}"
        assert body.get("chat_id") != "고정알림방"


def test_collect_bot_token_wins_over_the_shared_one(monkeypatch):
    """전용 토큰이 있으면 그것을 쓰고, 없을 때만 공용으로 떨어진다(그때는 경고를 남긴다)."""
    import src.api.telegram_collect as tc

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SHARED:1")
    monkeypatch.setenv("TELEGRAM_COLLECT_BOT_TOKEN", "OWN:2")
    assert tc._bot_token() == "OWN:2"

    monkeypatch.delenv("TELEGRAM_COLLECT_BOT_TOKEN", raising=False)
    tc._bot_token._warned = False
    assert tc._bot_token() == "SHARED:1", "전용 토큰이 없으면 공용으로 보내기는 한다"

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert tc._bot_token() == "", "토큰이 없으면 없다고 말한다(추측 금지)"


def test_repo_has_more_telegram_receivers_than_one_bot_can_serve():
    """★ 이 레포 안에만 텔레그램 수신구가 셋이다 — 한 봇에 다 걸 수 없다.

    텔레그램은 봇당 웹훅 **하나**만 기억한다(폴링과도 양립 불가). 수신구가 늘 때
    「토큰도 따로」라는 규율이 같이 따라오지 않으면, 나중에 건 웹훅이 앞의 것을 말없이 덮는다.
    """
    routes = {
        "봇 명령": ("src/bot/telegram_bot.py", "/webhook/telegram"),
        "CS 인바운드": ("src/cs_bot/inbound_telegram.py", "/webhooks/telegram/cs"),
        "수집": ("src/api/telegram_collect.py", "/webhooks/telegram/collect"),
    }
    for label, (path, route) in routes.items():
        assert route in Path(path).read_text(encoding="utf-8"), f"{label} 수신구가 사라졌다"

    # 수집 입구만은 **제 토큰**을 먼저 본다 — 공용 토큰에 웹훅을 걸라고 유도하지 않는다.
    src = Path("src/api/telegram_collect.py").read_text(encoding="utf-8")
    assert "TELEGRAM_COLLECT_BOT_TOKEN" in src

    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    assert "TELEGRAM_COLLECT_BOT_TOKEN" in guide, "가이드가 전용 토큰을 말하지 않는다"


def test_guide_names_the_two_bots_and_forbids_the_webhook_on_the_polling_one():
    """★ 봇을 **실명**으로 적는다 — 「전용 봇」이라고만 하면 어느 봇인지 사람이 고른다.

    오너 확정(2026-09-13): 수집 = `@gogaBridz_bot`(웹훅), 트렌드 = `KOHGANE시장동향`(폴링 유지).
    폴링 봇에 웹훅을 걸면 `getUpdates`가 409로 막혀 **GO 승인이 죽는다** —
    그래서 금지를 말로만 두지 않고 **어느 봇인지 이름으로** 못 박는다.
    """
    guide = Path("docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    assert "@gogaBridz_bot" in guide, "수집 봇 실명이 없다"
    assert "KOHGANE시장동향" in guide, "트렌드 봇 실명이 없다"

    # 트렌드 봇 이름 근처에 '폴링 유지'와 '금지'가 함께 서 있어야 한다.
    i = guide.find("KOHGANE시장동향")
    near = guide[max(0, i - 400):i + 400]
    assert "폴링" in near and ("금지" in near or "걸면 안" in near), \
        "트렌드 봇이 폴링이고 웹훅을 걸면 안 된다는 말이 이름 옆에 없다"
    assert "409" in guide, "왜 죽는지(409)를 말하지 않는다"

    # 1번 절이 수집 봇 실명 기준으로 쓰여 있는지 — 섹션 제목에 이름이 있다.
    assert "## 1. 텔레그램 `@gogaBridz_bot`" in guide, "1번 절이 봇 실명 기준이 아니다"
