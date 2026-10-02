"""R0(오너 2026-10-01) — 번역 체인 순서 · 중국어 원문 판정 · 비용 가드 · 「번역됨」 판정 단일화.

## 실측(운영 읽기 전용, 2026-10-01)
- 기본 체인(비-ja)이 `mymemory → papago → …`라 무료 단이 거의 늘 이겼다.
- 타오바오 제목(가나 0·간체)은 `ja`로 판정돼 Papago에 `source=ja`로 갔다(papago 46건 — 「懒人」→「일레븐」).
- /admin/diagnostics 「호출 0」은 **워커 메모리** 카운터다(재시작·다른 워커면 0). 같은 기간 DB엔 papago 46건.
- 확장 수집 API가 「번역됨」을 `("mymemory","openai","deepl")`로만 판정 → papago 46건 전부 `translated=false`.
- 번역 체인의 OpenAI 호출은 서버 월 예산(AI_MONTHLY_BUDGET_USD)을 **확인도 기록도 안 했다**.

## 계약
  1 기본 순서 Papago → DeepL → Azure → OpenAI → MyMemory(언어 무관) · `TRANSLATE_CHAIN_ORDER`가 우선 · 옛 이름도 읽음
  2 중국어(간체) → zh, Papago `source=zh-CN` · 일본어 한자 제목(玉渕·手帳·本革財布)은 ja 그대로
  3 Papago 하루 글자 상한을 넘으면 부르지 않고 DeepL로(건너뜀 표시) · NCP 429 한도 초과면 그날 Papago 중지
  4 OpenAI: 예산 초과면 부르지 않고 다음 단(MyMemory)으로 · 성공하면 토큰 비용을 예산 장부에 기록(note=translate)
  5 프로바이더별 오늘 집계는 공유 저장소에 쌓이고 진단 화면에 표로 나온다
  6 「번역됨」 = 실제 번역기(papago·azure 포함) + 실패 사유 없음 · 옛 오기록 행도 화면에선 번역됨
"""
from __future__ import annotations

import json

import pytest

_KEYS = ["NCP_PAPAGO_CLIENT_ID", "NCP_PAPAGO_CLIENT_SECRET", "DEEPL_API_KEY", "AZURE_TRANSLATOR_KEY", "OPENAI_API_KEY"]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in _KEYS + ["TRANSLATE_CHAIN_ORDER", "TRANSLATE_PROVIDER_CHAIN", "TRANSLATE_DISABLE_MYMEMORY",
                      "PAPAGO_DAILY_CHAR_LIMIT", "ADAPTER_DRY_RUN"]:
        monkeypatch.delenv(k, raising=False)
    from src.db import image_translate_queue_pg as st
    from src.db import option_translate_queue_pg as oq
    st.reset_for_tests()
    oq.reset_for_tests()
    yield


def _all_keys(monkeypatch):
    for k in _KEYS:
        monkeypatch.setenv(k, "x")


class _R:
    def __init__(self, payload=None, status=200, text=""):
        self._p, self.status_code, self.text = payload or {}, status, text

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def json(self):
        return self._p


def test_default_order_and_env_override(monkeypatch):
    from src.seller_console.ai.translator import AITranslator
    _all_keys(monkeypatch)
    want = ["papago", "deepl", "azure", "openai", "mymemory"]
    for lang in (None, "zh", "ja", "en"):
        assert AITranslator()._provider_chain(src_lang=lang) == want
    monkeypatch.setenv("TRANSLATE_PROVIDER_CHAIN", "mymemory,openai")           # 옛 이름도 읽는다
    assert AITranslator()._provider_chain() == ["mymemory", "openai"]
    monkeypatch.setenv("TRANSLATE_CHAIN_ORDER", "deepl,papago,deepl")             # 새 이름이 우선 · 중복 1번만
    assert AITranslator()._provider_chain() == ["deepl", "papago"]
    monkeypatch.setenv("TRANSLATE_CHAIN_ORDER", "papago,deepl,azure,openai")      # MyMemory 제외
    assert "mymemory" not in AITranslator()._provider_chain()


@pytest.mark.parametrize("text,lang", [
    ("脚凳沙发脚踏办公室脚踏午睡搁脚凳", "zh"), ("布里甘丁懒人沙发设计师单人沙发", "zh"),
    ("创意Magsafe磁吸手机支架无线充电器底座", "zh"), ("实木书桌", "zh"),
    ("玉渕", "ja"), ("SUPERONE 手帳", "ja"), ("本革財布 長財布", "ja"), ("高級感 牛革 二つ折り財布", "ja"),
    ("TSUMUGI 紬 レコード", "ja"), ("스마트폰", "ko"), ("phone grip", "en"),
])
def test_source_language(text, lang):
    from src.seller_console.ai.translator import _route_src_lang
    assert _route_src_lang(text) == lang


def test_papago_gets_zh_cn_for_chinese(monkeypatch):
    import requests
    from src.seller_console.ai.translator import AITranslator
    _all_keys(monkeypatch)
    seen = []
    monkeypatch.setattr(requests, "post", lambda url, **k: seen.append((url, k.get("data"))) or
                        _R({"message": {"result": {"translatedText": "게으른 소파"}}}))
    res = AITranslator().translate_product({"title": "布里甘丁懒人沙发设计师单人沙发", "description": ""})
    assert res["provider"] == "papago" and res["detected_lang"] == "zh"
    assert seen[0][0].startswith("https://papago.") and seen[0][1]["source"] == "zh-CN"
    assert [a["provider"] for a in res["attempts"]] == ["papago"]                # 1순위에서 끝


def test_papago_daily_limit_steps_down_to_deepl(monkeypatch):
    import requests
    from src.seller_console.ai import translator as T
    _all_keys(monkeypatch)
    monkeypatch.setenv("PAPAGO_DAILY_CHAR_LIMIT", "12")
    calls = []

    def _post(url, **k):
        calls.append(url)
        if "papago" in url:
            return _R({"message": {"result": {"translatedText": "번역"}}})
        if "deepl" in url:
            return _R({"translations": [{"text": "디플 번역"}, {"text": ""}]})
        raise AssertionError(url)
    monkeypatch.setattr(requests, "post", _post)
    r1 = T.AITranslator().translate_product({"title": "实木书桌", "description": ""})   # 4자 — 상한 안
    assert r1["provider"] == "papago" and T.papago_chars_today() == 4
    r2 = T.AITranslator().translate_product({"title": "布里甘丁懒人沙发设计师单人沙发", "description": ""})  # 15자 — 넘음
    assert r2["provider"] == "deepl"
    assert r2["attempts"][0]["provider"] == "papago" and r2["attempts"][0].get("skipped") is True
    assert "오늘 사용 상한" in r2["attempts"][0]["error"]
    assert sum("papago" in u for u in calls) == 1                                 # 넘는 건은 Papago를 안 불렀다
    monkeypatch.setenv("PAPAGO_DAILY_CHAR_LIMIT", "0")                             # 0 = 우리 쪽 상한 없음
    assert T.AITranslator().translate_product({"title": "布里甘丁懒人沙发设计师单人沙发", "description": ""})["provider"] == "papago"


def test_papago_quota_429_stops_papago_for_the_day(monkeypatch):
    import requests
    from src.seller_console.ai import translator as T
    _all_keys(monkeypatch)
    calls = []

    def _post(url, **k):
        calls.append(url)
        if "papago" in url:
            return _R(status=429, text='{"error":{"errorCode":"429","message":"Quota Exceeded"}}')
        return _R({"translations": [{"text": "디플"}, {"text": ""}]})
    monkeypatch.setattr(requests, "post", _post)
    assert T.AITranslator().translate_product({"title": "实木书桌", "description": ""})["provider"] == "deepl"
    r2 = T.AITranslator().translate_product({"title": "实木书桌", "description": ""})
    assert r2["provider"] == "deepl" and r2["attempts"][0].get("skipped") is True
    assert sum("papago" in u for u in calls) == 1


def test_openai_respects_budget_and_records_cost(monkeypatch):
    import requests
    import src.ai.budget as B
    from src.seller_console.ai.translator import AITranslator
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("TRANSLATE_CHAIN_ORDER", "openai,mymemory")
    recorded = []
    monkeypatch.setattr(B.BudgetGuard, "record", lambda self, **kw: recorded.append(kw))
    posts = []
    monkeypatch.setattr(requests, "post", lambda url, **k: posts.append(url) or _R({
        "choices": [{"message": {"content": json.dumps({"title_ko": "책상", "description_ko": ""})}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}))
    monkeypatch.setattr(requests, "get", lambda url, **k: _R({"responseStatus": 200,
                                                              "responseData": {"translatedText": "원목 책상"}}))
    # ① 예산 여유 → 부르고 기록
    monkeypatch.setattr(B.BudgetGuard, "can_spend", lambda self, estimated_cost_usd=None: True)
    r = AITranslator().translate_product({"title": "实木书桌", "description": ""})
    assert r["provider"] == "openai" and len(posts) == 1
    assert recorded and recorded[0]["provider"] == "openai" and recorded[0]["note"] == "translate"
    assert float(recorded[0]["cost_usd"]) == pytest.approx(1000 * 0.00000015 + 100 * 0.0000006)
    # ② 예산 초과 → OpenAI 안 부르고 MyMemory로, 사유는 「서버 월 예산」
    monkeypatch.setattr(B.BudgetGuard, "can_spend", lambda self, estimated_cost_usd=None: False)
    monkeypatch.setattr(B.BudgetGuard, "summary", lambda self: {"limit_usd": 1, "used_usd": 1})
    r2 = AITranslator().translate_product({"title": "实木书桌", "description": ""})
    assert len(posts) == 1 and r2["provider"] == "mymemory"
    assert "서버 월 예산" in r2["attempts"][0]["error"]


def test_provider_day_counts_are_shared_and_shown(monkeypatch):
    import requests
    from src.seller_console.ai import translator as T
    _all_keys(monkeypatch)
    monkeypatch.setattr(requests, "post", lambda url, **k: _R({"message": {"result": {"translatedText": "책상"}}}))
    T.AITranslator().translate_product({"title": "实木书桌", "description": ""})
    T.reset_translate_stats()                                   # 워커 메모리 카운터가 0이 돼도
    assert T.provider_day_counts()["papago"] == {"ok": 1, "fail": 0}   # 공유 집계는 남는다
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    h = c.get("/admin/diagnostics").get_data(as_text=True)
    assert 'data-role="provider-day"' in h and 'data-role="chain-order"' in h
    assert "papago → deepl → azure → openai → mymemory" in h
    assert 'data-role="papago-today"' in h and "상한 100,000자" in h


def test_translated_flag_single_judgment(monkeypatch):
    from src.seller_console.ai.translator import is_real_translation, translated_flag
    for p in ("papago", "azure", "deepl", "openai", "mymemory"):
        assert is_real_translation(p) is True
    for p in ("papago-fallback", "stub", "none", "", "rules"):
        assert is_real_translation(p) is False
    assert is_real_translation("papago", "Papago: 실패") is False
    assert translated_flag({"translated": False, "translation_provider": "papago", "translate_error": ""}) is True
    assert translated_flag({"translated": False, "translation_provider": "papago-fallback"}) is False


def test_extension_collect_marks_papago_translated(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.api.extension_api as ext
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": "u-r0", "scopes": ["collect.write"]})
    monkeypatch.setattr(ext, "_translate_payload", lambda p: {
        "title_ko": "원목 책상", "description_ko": "", "provider": "papago",
        "attempts": [{"provider": "papago", "ok": True, "error": ""}]})
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    with app.test_client() as c:
        j = c.post("/api/v1/collect/extension", json={
            "url": "https://item.taobao.com/item.htm?id=1", "title": "实木书桌", "price": "10", "currency": "CNY",
            "images": ["https://i/a.jpg"], "translate": True}).get_json()
    assert j["translated"] is True and j["translation_provider"] == "papago"
    ex = json.loads(ch.get(j["item_id"], seller_id="u-r0")["extra_json"])
    assert ex["translated"] is True
