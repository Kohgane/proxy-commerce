"""Y11-R 보강(오너 2026-10-16 모바일) — 쿠팡 줄 「지금 갱신」 · 상세 번역 DeepL 우선·과금 기록 · 이미지 블록 거부 자동 처리.

운영 근거(읽기 전용, 10-16): 배포 뒤에도 `coupang_detail_refresh:queue` 2건 「번역 대기」 그대로 · `detail_translate:recent`
마지막 19:20 UTC(텐센트 zh_to_ko 미지원) — 크론이 아직 없어 체인·쿠팡 갱신이 한 번도 안 돌았다. 번역 제공자 일 집계엔
papago_ok만 있고 deepl은 한 번도 없다. 그리고 DeepL은 2026-01-15부터 본문 `auth_key` 인증을 403으로 막는다(공지) —
우리 DeepL 호출 7곳이 전부 그 방식이었다.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "src" / "seller_console" / "templates"


@pytest.fixture
def state(monkeypatch):
    import src.db.image_translate_queue_pg as st
    box = {}
    monkeypatch.setattr(st, "state_get", lambda k: json.loads(json.dumps(box.get(k) or {})))
    monkeypatch.setattr(st, "state_set", lambda k, v: box.__setitem__(k, json.loads(json.dumps(v))))
    from src.uploaders.coupang_uploader import CoupangUploader
    CoupangUploader._IMG_VERDICT.update(at=0.0, v=None)
    yield box
    CoupangUploader._IMG_VERDICT.update(at=0.0, v=None)


# ── DeepL 헤더 인증(같은 유형 7곳) ────────────────────────────────────────────────────────────────

class _Resp:
    status_code = 200
    ok = True

    def __init__(self, texts):
        self._t = texts

    def raise_for_status(self):
        pass

    def json(self):
        return {"translations": [{"text": t} for t in self._t]}


def _capture(monkeypatch, n=2):
    import requests
    seen = {}

    def post(url, data=None, headers=None, timeout=None, **kw):
        seen.update(url=url, data=data, headers=headers or {})
        return _Resp(["번역"] * n)
    monkeypatch.setattr(requests, "post", post)
    return seen


def test_translator_deepl_uses_auth_header(monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "k-123:fx")
    seen = _capture(monkeypatch)
    from src.seller_console.ai.translator import AITranslator
    out = AITranslator()._translate_deepl("t", "d")
    assert out["provider"] == "deepl"
    assert seen["headers"]["Authorization"] == "DeepL-Auth-Key k-123:fx" and "auth_key" not in (seen["data"] or {})
    assert seen["url"].startswith("https://api-free.deepl.com/")


@pytest.mark.parametrize("call", [
    lambda: __import__("src.translate", fromlist=["x"])._deepl_translate("你好", "zh", "ko"),
    lambda: __import__("src.services.export_translate", fromlist=["x"])._deepl(["안녕"]),
    lambda: __import__("src.cs_bot.replier", fromlist=["x"])._call_deepl_polish("안녕", "ko"),
    lambda: __import__("src.cs_bot.translator", fromlist=["x"])._call_deepl_translate("hi", "en", "ko"),
])
def test_other_deepl_callers_use_auth_header(monkeypatch, call):
    monkeypatch.setenv("DEEPL_API_KEY", "k-9:fx")
    seen = _capture(monkeypatch, n=1)
    call()
    assert seen["headers"].get("Authorization") == "DeepL-Auth-Key k-9:fx"
    assert "auth_key" not in (seen["data"] or {})


def test_deepl_usage_reads_header_and_caches(monkeypatch):
    import requests
    import src.seller_console.ai.translator as T
    monkeypatch.setenv("DEEPL_API_KEY", "k:fx")
    T._DEEPL_USAGE.update(at=0.0, v=None)
    n = {"c": 0}

    class R:
        status_code = 200

        def json(self):
            return {"character_count": 1234, "character_limit": 500000}

    def get(url, headers=None, timeout=None):
        n["c"] += 1
        assert url == "https://api-free.deepl.com/v2/usage" and headers["Authorization"] == "DeepL-Auth-Key k:fx"
        return R()
    monkeypatch.setattr(requests, "get", get)
    assert T.deepl_usage() == {"count": 1234, "limit": 500000, "free": True}
    T.deepl_usage()
    assert n["c"] == 1
    T._DEEPL_USAGE.update(at=0.0, v=None)


# ── 상세 번역 체인: DeepL 먼저 · 제공자·과금 기록 ───────────────────────────────────────────────────

def test_prefer_reorders_chain_without_adding_missing(monkeypatch):
    monkeypatch.setenv("ADAPTER_DRY_RUN", "0")                 # 다른 테스트가 남긴 dry-run이면 체인을 안 탄다
    monkeypatch.setenv("TRANSLATE_REQUEST_BUDGET_SEC", "8")
    from src.seller_console.ai.translator import AITranslator
    tr = AITranslator()
    monkeypatch.setattr(tr, "_provider_chain", lambda src_lang=None: ["papago", "deepl", "openai"])
    order = []
    for n in ("papago", "deepl", "openai", "azure"):
        monkeypatch.setattr(tr, f"_translate_{n}", (lambda name: (lambda *a, **k: (order.append(name), {"provider": name + "-fallback", "error": "x"})[1]))(n))
    tr.translate_product({"title": "", "description": "材质"}, prefer=["deepl", "azure"])
    assert order == ["deepl", "papago", "openai"]                         # azure는 체인에 없어 끼우지 않는다


def test_detail_chain_prefers_deepl(monkeypatch):
    import src.uploaders.detail_translate as dt
    got = {}

    class T:
        def translate_product(self, src, prefer=None):
            got["prefer"] = prefer
            return {"provider": "deepl", "description_ko": "소재: 원목", "attempts": [{"provider": "deepl", "ok": True}]}
    monkeypatch.setattr("src.seller_console.ai.translator.AITranslator", T)
    r = dt._chain("材质：实木")
    assert got["prefer"] == ["deepl"] and r["ok"] and r["provider"] == "deepl" and r["tried"] == ["deepl:ok"]


def test_billing_labels(monkeypatch):
    from src.uploaders.detail_translate import billing_of
    monkeypatch.setenv("DEEPL_API_KEY", "k:fx")
    assert billing_of("deepl").startswith("무료")
    monkeypatch.setenv("DEEPL_API_KEY", "k")
    assert billing_of("deepl").startswith("유료")
    assert billing_of("papago").startswith("유료") and billing_of("mymemory").startswith("무료")


def test_call_records_billing_and_usage(monkeypatch, state):
    import src.uploaders.detail_translate as dt
    monkeypatch.setenv("DEEPL_API_KEY", "k:fx")
    monkeypatch.setattr("src.seller_console.ai.translator.deepl_usage", lambda: {"count": 51, "limit": 500000, "free": True})
    dt._call("材质：实木", lambda t: {"ok": True, "text": "소재: 원목", "provider": "deepl", "tried": ["deepl:ok"]})
    row = state[dt.RECENT_KEY]["rows"][-1]
    assert row["provider"] == "deepl" and row["billing"].startswith("무료") and row["deepl_usage"]["count"] == 51


def test_leftover_tallies_lines_by_provider(state):
    import src.uploaders.detail_translate as dt
    dt._CACHE.clear(); dt._FAIL.clear()
    out = dt.translate_leftover("材质：实木\n尺寸：80cm\n한국어 줄",
                                translate_fn=lambda t: {"ok": True, "text": "소재: 원목\n크기: 80cm", "provider": "deepl"})
    assert out["providers"] == {"deepl": 2} and out["translated"] == 2
    dt._CACHE.clear(); dt._FAIL.clear()


def test_providers_line():
    from src.services.coupang_detail_refresh import providers_line
    assert providers_line({}) == ""
    assert providers_line({"papago": 51}) == "상세 번역: papago 51줄(유료(NCP Papago 글자당))"


# ── 쿠팡 이미지 블록: 첫 응답 판정 · 거부면 글만 재전송 · 이후 자동 끔 ─────────────────────────────────

IMG = [{"contentsType": "IMAGE", "contentDetails": [{"content": "https://cdn/1.jpg", "detailType": "IMAGE"}]},
       {"contentsType": "TEXT", "contentDetails": [{"content": "소재: 원목", "detailType": "TEXT"}]}]


def _up(responses):
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader.__new__(CoupangUploader)
    sent = []

    def api(method, path, data=None, **kw):
        sent.append(json.loads(json.dumps(data)))
        return responses.pop(0)
    up._api_request = api
    up.last_sign = {"status": 200}
    return up, sent


def _body():
    return {"sellerProductId": 16415921785, "items": [{"itemName": "a", "contents": json.loads(json.dumps(IMG))}]}


def test_image_block_accepted_records_first_raw(state):
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    up, sent = _up([{"code": "SUCCESS", "message": "", "data": 16415921785}])
    res = up.modify_product(_body())
    assert res["success"] and res["detail_image"]["state"] == "accepted" and len(sent) == 1
    v = state[CU.DETAIL_IMG_VERDICT_KEY]
    assert v["state"] == "accepted" and '"SUCCESS"' in v["first"]["raw"]


def test_image_block_rejected_resends_text_and_turns_off(state, monkeypatch):
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    monkeypatch.delenv("COUPANG_DETAIL_IMAGES", raising=False)
    rej = {"code": "ERROR", "message": "상세컨텐츠(contentsType) 값이 올바르지 않습니다."}
    up, sent = _up([rej, {"code": "SUCCESS", "data": 1}])
    res = up.modify_product(_body())
    assert res["success"] and len(sent) == 2
    assert CU.has_image_block(sent[0]["items"][0]["contents"]) and not CU.has_image_block(sent[1]["items"][0]["contents"])
    assert res["detail_image"]["state"] == "rejected" and "contentsType" in res["detail_image"]["raw"]
    assert res["contents_sent"] == sent[1]["items"][0]["contents"]
    assert state[CU.DETAIL_IMG_VERDICT_KEY]["state"] == "rejected"
    # 이후 빌드는 글만(오너가 판정을 풀기 전까지)
    assert [b["contentsType"] for b in up._build_contents({"title": "t", "description_html": "본문",
                                                           "detail_images": ["https://cdn/1.jpg"]})] == ["TEXT"]
    # accepted가 와도 rejected는 그대로
    CU.note_detail_image_verdict("accepted", raw="x")
    assert state[CU.DETAIL_IMG_VERDICT_KEY]["state"] == "rejected"


def test_unrelated_rejection_is_not_retried(state):
    up, sent = _up([{"code": "ERROR", "message": "판매가는 10원 이상이어야 합니다"}])
    res = up.modify_product(_body())
    assert not res["success"] and len(sent) == 1 and res["detail_image"]["state"] == "other_error"


def test_text_also_rejected_same_way_is_unclear_not_off(state):
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    rej = {"code": "ERROR", "message": "상세 내용을 확인해 주세요"}
    up, sent = _up([dict(rej), dict(rej)])
    res = up.modify_product(_body())
    assert not res["success"] and len(sent) == 2 and res["detail_image"]["state"] == "unclear"
    assert state[CU.DETAIL_IMG_VERDICT_KEY]["state"] != "rejected"
    assert "contents_sent" in res and CU.has_image_block(res["contents_sent"])  # 받아진 게 아니니 원래 몸통 기준


def test_refresh_item_hashes_what_was_accepted(state, monkeypatch):
    """글만 재전송으로 받아졌으면 그 상세로 해시 — 다음 회전이 「같은 상세」로 보고 다시 안 보낸다."""
    import src.services.coupang_detail_refresh as R
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    text_only = CU.text_only(IMG)
    monkeypatch.setattr(R, "target", lambda item, up, sid="": {
        "ready": True, "contents": IMG, "hash": R._hash(IMG), "translated": 51, "failed": 0, "why": "",
        "detail_images": 1, "providers": {"deepl": 51}})

    class Up:
        def get_product(self, sid):
            return {"sellerProductId": int(sid), "statusName": "승인대기중", "items": [{"contents": []}]}

        def modify_product(self, body):
            return {"success": True, "market_status": 200, "body": "{}", "contents_sent": text_only,
                    "detail_image": {"state": "rejected", "raw": "contentsType 오류", "retry_raw": "SUCCESS"}}
    ex = {"uploaded": [{"market": "coupang:gogane", "product_id": "16415921785"}]}
    saved = {}
    rows = R.refresh_item({"id": "it", "extra_json": json.dumps(ex)}, make_up=lambda a: Up(), save=saved.update)
    r = rows[0]
    assert r["ok"] and r["detail_image"]["state"] == "rejected" and r["translate_line"].startswith("상세 번역: deepl 51줄")
    assert saved["coupang_detail_sync"]["coupang:gogane"]["hash"] == R._hash({"contents": text_only, "sku_images": {}, "list_price": R._list_rule(), "img": 2})


# ── 「지금 갱신」 버튼 · 잡 ─────────────────────────────────────────────────────────────────────────

def test_refresh_now_route_runs_job_and_poll_returns_row(monkeypatch, state):
    import time
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    import src.services.coupang_detail_refresh as R
    ex = {"uploaded": [{"market": "coupang:gogane", "product_id": "16415921785"}]}
    iid = S.append(source="extension", url="https://x/1", seller_id="cap-r2", title="t", price="1", currency="CNY", extra=ex)
    iid = iid[0] if isinstance(iid, tuple) else iid
    calls = []
    monkeypatch.setattr(R, "refresh_item", lambda item, **kw: (calls.append(kw["markets"]),
                        [{"market": "coupang:gogane", "sent": True, "ok": False, "error": "쿠팡 수정 거부: 승인 대기 상품",
                          "market_status": 400, "body": '{"code":"ERROR"}'}])[1])
    monkeypatch.setattr("src.seller_console.views._account_codes_forbidden", lambda m: None)
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id="cap-r2", user_email="cap-r2@example.com", user_role="seller")
    r = c.post(f"/seller/collect/{iid}/coupang-detail-refresh", json={"market": "coupang:gogane"})
    assert r.status_code == 202 and r.get_json()["job"]
    job = r.get_json()["job"]
    for _ in range(50):
        p = c.get(f"/seller/collect/{iid}/coupang-detail-refresh?job={job}").get_json()
        if p.get("state") == "done":
            break
        time.sleep(0.05)
    assert p["state"] == "done" and p["row"]["body"] == '{"code":"ERROR"}' and calls == [["coupang:gogane"]]
    assert c.post(f"/seller/collect/{iid}/coupang-detail-refresh", json={"market": "smartstore:chezgoga"}).status_code == 400
    assert c.post(f"/seller/collect/{iid}/coupang-detail-refresh", json={"market": "coupang:woojoo"}).status_code == 404


def test_popup_has_refresh_now_two_tap_and_raw():
    ms = (TPL / "_market_status.html").read_text(encoding="utf-8")
    assert 'data-role="mst-refresh-now"' in ms and 'data-role="mst-refresh-out"' in ms
    assert "한 번 더 누르면 보내요" in ms and "data-role=\"mst-refresh-raw\"" in ms and "?job=" in ms
