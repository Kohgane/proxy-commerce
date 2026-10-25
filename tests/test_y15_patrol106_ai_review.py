"""순찰 106-C(오너 2026-10-26) — 등록 전 AI 검수: 한국 손님이 보면 이상한 점 5줄 이내 · 상품당 1회 · 예산 안 · AI는 제안만.

흉내 낸 것: Anthropic 답(`llm.complete`) · 텔레그램 전송. 사전검증 잡 경로(시작 → 카드)는 실제 함수.
"""
import json

import pytest

EX = {"title": "Taffa 唐发发 2025夏季新款真丝连衣裙", "title_ko": "Taffa 여름 신상 실크 원피스",
      "options": [{"name": "尺码", "name_ko": "사이즈", "values": ["36 80-105斤"]}],
      "option_value_overrides": {"36 80-105斤": "36 80-105근"},
      "images": ["https://a/0.jpg", "https://a/1.jpg"], "detail_images": ["https://a/d1.jpg", "https://a/d2.jpg"],
      "detail_images_ko": [{"idx": 0, "status": "done", "target_text": "발발 170cm/49kg/전점 38사이즈"},
                           {"idx": 1, "status": "done", "target_text": "SF 무료 배송 · 7일 무조건 반품"}]}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    from src.db import image_translate_queue_pg as q
    q.reset_for_tests()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("AI_REVIEW", "1")                                 # 테스트 기본은 꺼짐(conftest) — 여기선 켠다
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    yield
    q.reset_for_tests()


def _pd(ex):
    from src.order_webhook import app
    from src.seller_console.product_builder import build_product
    with app.app_context():
        return build_product({"id": "it1", "title": ex["title"], "extra_json": json.dumps(ex, ensure_ascii=False)}, seller_id="s")


def _fake_llm(monkeypatch, answer, calls):
    from src.ai import llm

    def fake(prompt, **kw):
        calls.append({"prompt": prompt, **kw})
        return {"text": json.dumps(answer, ensure_ascii=False), "provider": "anthropic", "model": "claude-haiku-4-5",
                "usd": 0.0012, "tokens_in": 900, "tokens_out": 80}
    monkeypatch.setattr(llm, "complete", fake)


def test_review_sends_text_only_and_caps_five_lines(monkeypatch):
    from src.services import ai_review as R
    calls = []
    _fake_llm(monkeypatch, {"lines": [f"줄 {i} — " + "가" * 120 for i in range(8)]}, calls)
    ex = dict(EX)
    r = R.run(_pd(ex), ex)
    assert r["status"] == "done" and len(r["lines"]) == 5 and all(len(x) <= R.LINE_MAX for x in r["lines"])
    p = calls[0]["prompt"]
    assert "Taffa 여름 신상 실크 원피스" in p and "옵션 사이즈" in p and "사진: 대표·갤러리 2장 · 상세 2장" in p
    assert "상세 1번 사진 글자: 발발 170cm/49kg/전점 38사이즈" in p and "SF 무료 배송" in p
    assert "https://" not in p                                            # 사진 주소는 안 보낸다(글자만)
    assert calls[0]["providers"] == ["anthropic"] and calls[0]["purpose"] == "ai_review" and not calls[0].get("images")


def test_once_per_product_and_skip_without_key(monkeypatch):
    from src.services import ai_review as R
    calls = []
    _fake_llm(monkeypatch, {"lines": ["x"]}, calls)
    ex = dict(EX, ai_review={"status": "done", "lines": ["예전 검수"], "at": "2026-10-26T00:00:00+00:00"})
    r = R.run(_pd(ex), ex)
    assert r["lines"] == ["예전 검수"] and r["cached"] and calls == []                  # 다시 안 부른다
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    ex2 = dict(EX)
    assert R.run(_pd(ex2), ex2)["status"] == "skip" and calls == []
    assert R.cached(dict(EX, ai_review={"status": "failed"})) is None                    # 실패는 다음에 다시
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("AI_REVIEW", "0")
    assert R.run(_pd(ex2), ex2)["status"] == "skip" and calls == []                      # 끄면 안 부른다


def test_budget_or_error_is_failed_not_blocking(monkeypatch):
    from src.ai import llm
    from src.services import ai_review as R
    monkeypatch.setattr(llm, "complete", lambda *a, **k: {"text": "", "error": "BudgetExceededError: 월 예산 초과"})
    ex = dict(EX)
    r = R.run(_pd(ex), ex)
    assert r["status"] == "failed" and "예산" in r["why"] and r["lines"] == []


def test_job_attaches_card_saves_once_and_tells_owner_for_family(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.seller_console import views as V
    from src.seller_console import market_credentials as mc
    from src.notifications import telegram
    calls, sent, upd = [], [], {}
    _fake_llm(monkeypatch, {"lines": ["「발발」은 모델 이름을 음차한 말 같아요", "「7일 무조건 반품」은 중국 가게 약관이에요"]}, calls)
    monkeypatch.setattr(telegram, "send_telegram", lambda msg, urgency="info": sent.append(msg) or True)
    monkeypatch.setattr(mc, "_shared_cache", {})
    monkeypatch.setenv("FAMILY_EMAILS", "fam@example.com")
    monkeypatch.setattr(V, "_pv_update", lambda job_id, **kw: upd.update(kw) or upd)
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=5", seller_id="fam-1",
                   title=EX["title_ko"], price="1058", currency="CNY", extra=dict(EX))
    iid = iid[0] if isinstance(iid, tuple) else iid
    with app.test_request_context("/"):
        from flask import session
        session["user_id"], session["user_email"] = "fam-1", "fam@example.com"
        h = V._pv_ai_review_start("job1", _pd(EX), iid)
        V._pv_ai_review_finish("job1", h, 10 ** 12)
        assert upd["ai_review"]["status"] == "done" and len(upd["ai_review"]["lines"]) == 2
        saved = json.loads(S.get(iid, seller_ids={"fam-1"})["extra_json"])
        assert saved["ai_review"]["lines"][0].startswith("「발발」")
        assert len(sent) == 1 and "AI 제안이에요" in sent[0] and iid[:8] in sent[0]
        upd.clear()
        assert V._pv_ai_review_start("job2", _pd(EX), iid) is None             # 두 번째 사전검증 = 저장본(호출 0)
        assert upd["ai_review"]["cached"] and len(calls) == 1 and len(sent) == 1


def test_not_family_gets_no_telegram(monkeypatch):
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.seller_console import views as V
    from src.seller_console import market_credentials as mc
    from src.notifications import telegram
    sent = []
    _fake_llm(monkeypatch, {"lines": []}, [])
    monkeypatch.setattr(telegram, "send_telegram", lambda msg, urgency="info": sent.append(msg) or True)
    monkeypatch.setattr(mc, "_shared_cache", {})
    monkeypatch.setenv("FAMILY_EMAILS", "fam@example.com")
    monkeypatch.setattr(V, "_pv_update", lambda job_id, **kw: kw)
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=6", seller_id="other",
                   title="x", price="1", currency="CNY", extra=dict(EX))
    iid = iid[0] if isinstance(iid, tuple) else iid
    with app.test_request_context("/"):
        from flask import session
        session["user_id"], session["user_email"] = "other", "x@example.com"
        V._pv_ai_review_finish("j", V._pv_ai_review_start("j", _pd(EX), iid), 10 ** 12)
    assert sent == []


def test_both_cards_render_the_collapsed_row():
    import pathlib
    rb = pathlib.Path("src/seller_console/templates/_risk_block.html").read_text(encoding="utf-8")
    assert "window.kgpAiReviewHtml" in rb and "<details" in rb and "AI 제안이에요, 결정은 직접" in rb
    for t in ("collect_preview.html", "_m5_flow.html"):
        assert "kgpAiReviewHtml(" in pathlib.Path("src/seller_console/templates", t).read_text(encoding="utf-8"), t


def test_job_poll_returns_the_review_card():
    from src.order_webhook import app
    from src.seller_console import views as V
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "owner-x"
    with app.test_request_context("/"):
        from flask import session
        session["user_id"] = "owner-x"
        V._pv_store().state_set(V._PV_JOB_KEY + "jobrv", {"state": "done", "owner": V._seller_id(), "markets": [],
                                                          "results": {}, "ai_review": {"status": "done", "lines": ["줄"]}})
    d = c.get("/seller/collect/prevalidate/job/jobrv").get_json()
    assert d["ok"] and d["ai_review"] == {"status": "done", "lines": ["줄"]}
