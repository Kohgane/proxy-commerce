"""F24 계약 — 소싱 원칙 + 자동 판정 + 봇별 기본 등록 계정.

## 원칙은 사람이 정하고 봇은 재서 말한다 — 판정은 사장님

여기서 재는 것은 **재는 일이 제대로 되는가**이지 「무엇을 사야 하는가」가 아니다.
그래서 계약도 두 갈래다:

  ① 원칙을 사람이 바꿀 수 있는가(파싱·저장·스코프) — 잘못 바꾸면 뒤의 모든 판정이 조용히 틀린다.
  ② 잴 수 없는 것을 **잴 수 없다고 말하는가** — 있는 척하면 그 숫자로 결정이 내려진다.

라이브 호출 0: 공급사도 소싱처도 부르지 않는다. 판정은 **저장된 초안**으로만 한다.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean():
    from src.sourcing import rules as R
    R.reset_for_tests()
    yield
    R.reset_for_tests()


# ---------------------------------------------------------------------------
# ① 원칙 — 사람이 한 줄로 바꾼다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("line,field,value", [
    ("원가 50", "cost_min_usd", 50.0),
    ("배송비율 35", "ship_cost_max_pct", 35.0),
    ("마진 25", "target_margin_pct", 25.0),
    ("국내갭 3", "domestic_gap_max", 3),
    ("니치브랜드 예", "niche_brand_required", True),
    ("국내수요 아니오", "domestic_demand_required", False),
    ("상표권 예", "trademark_block", True),
    ("cost 50", "cost_min_usd", 50.0),          # 영문 별칭도 받는다
    ("마진율 25.5", "target_margin_pct", 25.5),
])
def test_rules_parse(line, field, value):
    from src.sourcing.rules import parse_command
    assert parse_command(line) == (field, value)


@pytest.mark.parametrize("line,why", [
    ("", "empty"),
    ("원가", "no_value"),
    ("없는항목 3", "unknown_field"),
    ("원가 비싸게", "bad_number"),
    ("마진 250", "bad_percent"),
    ("니치브랜드 글쎄", "bad_flag"),
])
def test_rules_reject_instead_of_guessing(line, why):
    """못 알아들으면 **짐작해서 바꾸지 않는다.**

    원칙을 잘못 바꾸면 그 뒤 모든 판정이 조용히 틀린다 — 되묻는 편이 싸다.
    """
    from src.sourcing.rules import parse_command
    field, reason = parse_command(line)
    assert field is None and reason == why


def test_rules_defaults_inherit_old_constants():
    """기본값은 **옛 코드 상수를 그대로** 승계한다 — 새 숫자를 지어내지 않는다."""
    from src.pipeline.coupang_replicate import DEFAULT_MARGIN_RATE
    from src.sourcing.rules import defaults
    d = defaults()
    assert d["target_margin_pct"] == float(DEFAULT_MARGIN_RATE)
    assert d["ship_cost_max_pct"] == 35.0          # register_pipe의 `0.35 * cost_krw`
    # 오너가 정한 적 없는 값은 **정한 적 없음**으로 둔다(0으로 채우면 판정이 생긴다).
    assert d["cost_min_usd"] is None
    assert d["domestic_gap_max"] is None


def test_rules_are_scoped_per_bot_and_user():
    """한 사람이 봇 둘로 사업 둘을 굴린다 — **원가 하한도 마진도 사업마다 다르다.**"""
    from src.sourcing import rules as R
    R.set_one("u1", "cost_min_usd", 50, bot_slug="gogabridz")
    R.set_one("u1", "cost_min_usd", 80, bot_slug="kohujoo")
    assert R.get("u1", bot_slug="gogabridz")["cost_min_usd"] == 50
    assert R.get("u1", bot_slug="kohujoo")["cost_min_usd"] == 80
    # 다른 사람에겐 새지 않는다.
    assert R.get("u2", bot_slug="gogabridz")["cost_min_usd"] is None


def test_console_and_bot_read_the_same_store():
    """두 벌 금지 — 콘솔 검수표가 **이 표**에서 마진·배송 상한을 받아 간다."""
    src = (ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
    body = src.split("def build_review_for_urls", 1)[1][:1600]
    assert "from src.sourcing import rules as sourcing_rules" in body
    assert "ship_cost_max_pct=rules.get(\"ship_cost_max_pct\")" in body
    assert "margin_rate=rules.get(\"target_margin_pct\")" in body


def test_ship_limit_is_no_longer_hardcoded():
    """배송비 상한이 코드 상수에서 **원칙**으로 옮겨졌다(기본값은 같다 — 무회귀)."""
    from src.pipeline.register_pipe import build_source_review_row
    draft = {"title": "테스트 가방", "price": "100", "currency": "KRW"}
    row = build_source_review_row(draft, url="https://item.taobao.com/item.htm?id=1",
                                  ship_cost_fn=lambda **kw: 40, ship_cost_max_pct=50)
    assert row["ship_over_35pct"] is False, "상한 50%인데 40%가 위반으로 잡혔다"
    row2 = build_source_review_row(draft, url="https://item.taobao.com/item.htm?id=1",
                                   ship_cost_fn=lambda **kw: 40, ship_cost_max_pct=30)
    assert row2["ship_over_35pct"] is True


def test_volumetric_weight_needs_all_three_dimensions():
    """부피무게는 치수 셋이 다 있어야 나온다 — 하나라도 없으면 **None**(미측정)."""
    from src.sourcing.rules import VOLUMETRIC_DIVISOR, volumetric_kg
    assert VOLUMETRIC_DIVISOR == 5000
    assert volumetric_kg(30, 20, 10) == 1.2
    assert volumetric_kg(30, 20, None) is None
    assert volumetric_kg(30, 0, 10) is None


# ---------------------------------------------------------------------------
# ② 판정 — 잴 수 없는 것은 잴 수 없다고 쓴다
# ---------------------------------------------------------------------------

def _row(**kw):
    base = {"currency": "USD", "price_original": 60.0, "cost_krw": 81000,
            "sale_krw": 150000, "margin_pct": 30.0, "ship_cost_krw": None,
            "excluded": False, "forbidden_detail": {}, "brand": "SPORTLINK",
            "warnings": [], "cost_basis": "환산 완료"}
    base.update(kw)
    return base


def test_verdict_has_all_six_axes():
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rv = evaluate(_row(), defaults(), distributors=set())
    names = [i["name"] for i in rv["items"]]
    for want in ("원가", "예상 판매가", "마진율", "배송비율", "금칙어", "상표권"):
        assert want in names, f"{want} 항목이 없다"


def test_unmeasurable_axes_say_so_instead_of_guessing():
    """국내 갭·국내 수요는 **자동 실측 수단이 없다** — 「수동 확인」이라고 쓴다."""
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rules = defaults()
    rules.update({"domestic_gap_max": 3, "domestic_demand_required": True})
    rv = evaluate(_row(), rules, distributors=set())
    texts = {i["name"]: i["text"] for i in rv["items"]}
    assert "수동 확인" in texts["국내 갭"]
    assert "수동 확인" in texts["국내 수요"]


def test_ship_ratio_is_unmeasured_before_enrichment():
    """치수가 없으면 배송비율은 **미측정**이다 — 0%로 두면 통과로 읽힌다."""
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rv = evaluate(_row(ship_cost_krw=None), defaults(), distributors=set())
    ship = next(i for i in rv["items"] if i["name"] == "배송비율")
    assert ship["state"] == "hold" and "미측정" in ship["text"]


def test_trademark_says_confirm_needed_when_no_list():
    """총판 목록이 없는 것과 총판이 없는 것은 **다른 말**이다."""
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rv = evaluate(_row(), defaults(), distributors=set())
    tm = next(i for i in rv["items"] if i["name"] == "상표권")
    assert tm["state"] == "hold" and "확인 필요" in tm["text"]


def test_trademark_blocks_when_distributor_listed():
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rv = evaluate(_row(brand="ULANZI"), defaults(), distributors={"ulanzi"})
    tm = next(i for i in rv["items"] if i["name"] == "상표권")
    assert tm["state"] == "no"
    assert rv["verdict"] == "no"


def test_cost_floor_rejects_below_minimum():
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rules = defaults()
    rules["cost_min_usd"] = 100
    rv = evaluate(_row(price_original=60.0), rules, distributors={"x"})
    cost = next(i for i in rv["items"] if i["name"] == "원가")
    assert cost["state"] == "no" and rv["verdict"] == "no"


def test_margin_below_target_rejects():
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rules = defaults()
    rules["target_margin_pct"] = 40
    rv = evaluate(_row(margin_pct=30.0), rules, distributors={"x"})
    assert rv["verdict"] == "no"


def test_all_clear_is_a_candidate_not_a_promise():
    """전부 통과면 「등록 후보」다 — 「팔린다」가 아니다(말이 그렇게 돼 있어야 한다)."""
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rules = defaults()
    rv = evaluate(_row(ship_cost_krw=20000, cost_krw=81000), rules, distributors={"other"})
    assert rv["verdict"] == "ok"
    assert rv["verdict_ko"] == "등록 후보"


def test_no_arbitrary_currency_conversion():
    """환산할 수 없으면 **환산하지 않는다** — 임의 환산 금지."""
    from src.sourcing.rules import defaults
    from src.sourcing.verdict import evaluate
    rv = evaluate(_row(currency="CNY", cost_krw=None, price_original=500),
                  defaults(), fx_rates={}, distributors={"x"})
    cost = next(i for i in rv["items"] if i["name"] == "원가")
    assert cost["state"] == "hold" and "환산 불가" in cost["text"]


def test_badge_is_none_without_a_verdict():
    """판정이 없으면 뱃지도 없다 — 「판정 없음」 뱃지가 제일 쓸모없다."""
    from src.sourcing.verdict import badge
    assert badge(None) is None
    assert badge({}) is None
    assert badge({"verdict": "ok"})["kind"] == "on"


def test_console_badge_uses_tokens_not_emoji():
    """콘솔은 이모지 0 — 텔레그램 답장의 기호와 **다른 자리**다.

    주석에도 두지 않는다. Jinja 주석은 렌더되지 않지만, 같은 파일 안에 기호가 있으면
    다음 사람이 「여기선 써도 되나 보다」로 읽는다(내가 이번에 그렇게 썼다).
    """
    tpl = (ROOT / "src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    for e in ("✅", "⚠️", "❌"):
        assert e not in tpl, f"콘솔 템플릿에 {e}"
    seg = tpl.split("it.sourcing_badge", 1)[1][:400]
    assert "pc-badge-" in seg and "bi-" in seg


# ---------------------------------------------------------------------------
# ③ 봇별 기본 등록 계정
# ---------------------------------------------------------------------------

def test_account_list_comes_from_one_place():
    """계정 축을 봇 안에 다시 적지 않는다 — 쿠팡과 스마트스토어는 **다른 축**이다."""
    from src.pipeline.ops_snapshot import account_choices
    rows = account_choices()
    assert len(rows) == 4
    by = {r["account"]: r for r in rows}
    assert by["gogane"]["label"] == "고가네" and by["gogane"]["market"] == "coupang"
    assert by["woojoo"]["label"] == "우주대행"
    assert by["chezgoga"]["market"] == "smartstore"


def test_four_accounts_are_two_businesses_times_two_markets():
    """오너 2026-09-14: 계정 넷은 따로 서 있는 게 아니라 **사업체 2 × 마켓 2**다."""
    from src.pipeline.ops_snapshot import BUSINESSES, account_for, business_of
    assert {b["business"] for b in BUSINESSES} == {"gogane", "woojoo"}
    assert account_for("woojoo", "coupang") == "woojoo"
    assert account_for("woojoo", "smartstore") == "gocosmos"
    assert account_for("gogane", "smartstore") == "chezgoga"
    # 거꾸로도 참이어야 한다 — 계정 하나를 보면 어느 사업체인지 안다.
    assert business_of("gocosmos") == "woojoo"
    assert business_of("chezgoga") == "gogane"
    assert business_of("없는계정") == ""


def test_smartstore_accounts_carry_the_real_korean_names():
    """오너가 준 상호를 쓴다(chezgoga=고가네·gocosmos=우주대행) — 지어낸 값이 아니다."""
    from src.pipeline.ops_snapshot import account_choices
    by = {r["account"]: r for r in account_choices()}
    assert by["chezgoga"]["business_ko"] == "고가네"
    assert by["gocosmos"]["business_ko"] == "우주대행"


@pytest.mark.parametrize("name,business", [
    ("우주대행", "woojoo"), ("고가네", "gogane"), ("woojoo", "woojoo"),
    ("chezgoga", "gogane"),          # 계정명으로 불러도 **그 사업체**다
    ("gocosmos", "woojoo"),
])
def test_business_resolves_by_real_name(name, business):
    from src.pipeline.ops_snapshot import resolve_business
    assert resolve_business(name)["business"] == business


def test_one_word_means_both_markets():
    """「우주대행」은 쿠팡 A01504840 **과** 스마트스토어 gocosmos 둘 다를 뜻한다."""
    from src.pipeline.ops_snapshot import resolve_business
    accts = resolve_business("우주대행")["accounts"]
    assert accts == {"coupang": "woojoo", "smartstore": "gocosmos"}


def test_business_does_not_guess():
    """계정을 잘못 고르면 남의 스토어에 올라간다 — 모르면 고르지 않는다."""
    from src.pipeline.ops_snapshot import resolve_business
    assert resolve_business("우주") == {}
    assert resolve_business("") == {}


def test_bot_default_accounts_match_the_owner_statement():
    from src.api.telegram_collect import BOT_DEFAULT_ACCOUNT
    assert BOT_DEFAULT_ACCOUNT["default"] == "gogane"      # gogaBridz_bot
    assert BOT_DEFAULT_ACCOUNT["kohujoo"] == "woojoo"      # KohujooBot


def test_default_account_prefers_what_a_person_chose(monkeypatch):
    """사람이 정한 값 > env > 봇 기본값. 사람이 고른 것을 코드가 덮지 않는다."""
    from src.api import telegram_collect as T
    monkeypatch.setenv("TELEGRAM_BOT_ACCOUNT_KOHUJOO", "gogane")
    with patch("src.db.telegram_links_pg.get", return_value={"default_market_account": "woojoo"}):
        assert T._default_account("kohujoo", "1") == "woojoo"
    with patch("src.db.telegram_links_pg.get", return_value={}):
        assert T._default_account("kohujoo", "1") == "gogane"
        monkeypatch.delenv("TELEGRAM_BOT_ACCOUNT_KOHUJOO")
        assert T._default_account("kohujoo", "1") == "woojoo"


def test_register_screen_preselects_only_when_unanimous():
    """행마다 사업체가 다르면 **고르지 않는다** — 절반만 맞는 기본값은 찾기 더 어렵다."""
    src = (ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
    seg = src.split("preferred_business", 1)[1][:500]
    assert "len(bizs) == 1" in seg


def test_register_screen_resolves_business_per_market():
    """사업체를 **고른 마켓에 맞는 계정**으로 푼다 — 축을 섞으면 남의 스토어에 올라간다."""
    tpl = (ROOT / "src/seller_console/templates/register_pipe.html").read_text(encoding="utf-8")
    seg = tpl.split("function p3SyncAccounts()", 1)[1][:800]
    assert "P3_BIZ_ACCOUNTS[P3_BUSINESS][market]" in seg
    # 그 마켓의 선택지에 실제로 있을 때만 고른다.
    assert "P3_ACCOUNTS[market] || []" in seg


# ---------------------------------------------------------------------------
# ④ 봇 문장·배선
# ---------------------------------------------------------------------------

def test_all_user_facing_sentences_live_in_MSG():
    """문장이 흩어지면 말투가 갈리고 고칠 때 한 군데를 빼먹는다(F17 갱신 규율)."""
    from src.api.telegram_collect import MSG
    for k in ("rules_head", "rules_tail", "rules_saved", "rules_bad",
              "account_now", "account_set", "account_unknown",
              "sourcing_head", "sourcing_item", "verdict_usage"):
        assert k in MSG and MSG[k].strip()


def test_rules_tail_states_who_decides():
    """「원칙은 사장님이 정하고, 봇은 그 기준으로 재서 말합니다」 — 이 구분이 흐려지면 안 된다."""
    from src.api.telegram_collect import MSG
    assert "사장님" in MSG["rules_tail"]


def test_verdict_never_recollects_inside_the_webhook():
    """판정은 **저장된 초안**으로 한다.

    응답 안에서 남의 서버를 다시 부르면 그 서버가 느린 날 우리가 죽는다(F22에서 그렇게 502가 났다).
    """
    src = (ROOT / "src/api/telegram_collect.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_sourcing_block")
    mods = {n.module or "" for n in ast.walk(fn) if isinstance(n, ast.ImportFrom)}
    assert not any("share_collect" in m or "dispatcher" in m for m in mods), \
        "판정 안에서 다시 수집하고 있다"
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "collect_input" not in called


def test_no_live_calls_in_this_contract_file():
    """이 파일은 **아무 곳에도 나가지 않는다** — 계약이 돈을 쓰거나 소싱처를 두드리면 안 된다."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert "requests" not in mods and "urllib" not in mods


def test_collect_reply_carries_the_verdict_block():
    """담은 **그 자리에서** 판정이 같은 답장에 붙는다(따로 물어보게 하지 않는다)."""
    src = (ROOT / "src/api/telegram_collect.py").read_text(encoding="utf-8")
    seg = src.split("res = collect_input(", 1)[1][:1400]
    assert "_sourcing_block(" in seg and "_save_verdict(" in seg


def test_named_bot_never_falls_back_to_the_default_bot_token(monkeypatch):
    """F24b: **이름표 붙은 봇은 기본 봇 토큰으로 떨어지지 않는다.** 다른 봇이기 때문이다.

    떨어지면 KohujooBot에 보낸 글을 gogaBridz_bot이 답하려 들고, 그 chat은 그 봇과
    대화한 적이 없어 텔레그램이 거절한다 — **담기긴 담기는데 답장이 조용히 사라진다.**
    사람은 「봇이 죽었다」고 읽는다. 그게 제일 나쁜 실패다.
    """
    from src.api import telegram_collect as T
    T.reset_runtime_state()
    monkeypatch.setenv("TELEGRAM_COLLECT_BOT_TOKEN", "111:default-bot")
    monkeypatch.delenv("TELEGRAM_COLLECT_BOT_TOKEN_KOHUJOO", raising=False)
    assert T._bot_token("kohujoo") == "", "다른 봇 토큰으로 답장하려 한다"
    # 기본 봇은 그대로 동작한다(무회귀).
    assert T._bot_token("default") == "111:default-bot"
    # 제 토큰이 있으면 그걸 쓴다.
    monkeypatch.setenv("TELEGRAM_COLLECT_BOT_TOKEN_KOHUJOO", "222:kohujoo-bot")
    assert T._bot_token("kohujoo") == "222:kohujoo-bot"


def test_named_bot_can_reuse_the_shared_webhook_secret(monkeypatch):
    """시크릿은 공용 값 재사용이 된다 — 토큰과 달리 **봇을 가리지 않는 잠금**이라서다."""
    from src.api import telegram_collect as T
    monkeypatch.setenv("TELEGRAM_COLLECT_WEBHOOK_SECRET", "shared-secret")
    monkeypatch.delenv("TELEGRAM_COLLECT_WEBHOOK_SECRET_KOHUJOO", raising=False)
    assert T._webhook_secret("kohujoo") == "shared-secret"
    monkeypatch.setenv("TELEGRAM_COLLECT_WEBHOOK_SECRET_KOHUJOO", "own-secret")
    assert T._webhook_secret("kohujoo") == "own-secret"


def test_guide_carries_the_exact_values_for_kohujoo():
    """오너가 붙이려면 **실값 셋**이 문서에 있어야 한다(슬러그·토큰 env·setWebhook)."""
    g = (ROOT / "docs/MOBILE_COLLECT_GUIDE.md").read_text(encoding="utf-8")
    assert "/webhooks/telegram/collect/kohujoo" in g
    assert "TELEGRAM_COLLECT_BOT_TOKEN_KOHUJOO" in g
    assert "setWebhook" in g and "secret_token" in g
    # 사업체 표(오너가 준 상호)도 문서에 있어야 한다.
    assert "chezgoga" in g and "gocosmos" in g


def test_tencent_region_still_has_no_default(monkeypatch):
    """리전 실값을 알게 됐어도 **기본값으로 박지 않는다** — 리전은 계정마다 다르다.

    박아 두면 다른 계정을 쓰는 날 env가 비어도 조용히 싱가포르로 나가고, 어긋난 줄도 모른다.
    """
    from src.services import image_translate_tencent as tc
    monkeypatch.delenv("TENCENT_REGION", raising=False)
    assert tc.region() == ""
    monkeypatch.setenv("TENCENT_REGION", "ap-singapore")
    assert tc.region() == "ap-singapore"


def test_verdict_is_saved_on_the_draft():
    from src.api import telegram_collect as T
    saved = {}
    row = {"id": "i1", "extra_json": json.dumps({"images": []})}
    with patch("src.seller_console.collect_history_store.get", return_value=row), \
         patch("src.seller_console.collect_history_store.update",
               side_effect=lambda i, **kw: saved.update(kw) or True):
        T._save_verdict("i1", "u1", {"verdict": "hold", "verdict_ko": "보류", "items": []},
                        "woojoo")
    ex = json.loads(saved["extra_json"])
    assert ex["sourcing_verdict"]["verdict"] == "hold"
    assert ex["default_business"] == "woojoo"


def test_review_keyword_still_works():
    """'검수'는 유지 — 상세 판정을 다시 펼친다."""
    from src.api.telegram_collect import _REVIEW_WORDS
    assert "검수" in _REVIEW_WORDS


def test_stage10_is_applied_at_boot():
    src = (ROOT / "src/db/pg.py").read_text(encoding="utf-8")
    assert "schema_stage10.sql" in src
    sql = (ROOT / "src/db/schema_stage10.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS sourcing_rules" in sql
    # 이미 만들어진 telegram_links에도 붙어야 한다(재적용 안전).
    assert "ADD COLUMN IF NOT EXISTS default_market_account" in sql
