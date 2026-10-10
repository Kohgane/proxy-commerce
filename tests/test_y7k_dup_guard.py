"""Y7-K(오너 2026-10-10) — 후속 3건.

1. 중복 등록 — 18:09 KST 셰고가에 13742149801 새로 생성(13741121333 이미 있음). 결과 모달 「다시 등록」은 체크된 채 선택 화면으로,
   「실패 마켓 재시도」는 선택 화면을 건너뛰어 M7 가드(이미 등록된 마켓 체크 해제 + 확인)를 타지 않았다.
   게다가 등록 기록이 **마켓당 1건으로 덮어써** 옛 번호가 사라졌다(중복이 보이지도 않았다).
   → 입구 한 곳(서버 `/collect/upload`)에서 확인 없이는 다시 올리지 않음(409 needs_dup_confirm) · 기록은 번호가 다르면 쌓음 ·
     칩은 마켓당 하나 + 「중복 n건 — 정리」 · 팝업 「이 기록 빼기」(우리 기록만 — 마켓 상품 삭제는 판매자센터, 삭제 표시로 보존).
2. 「■ 원문 상세」가 제목 한 줄만 달고 남음 → 상품명과 같은 줄은 섹션 내용이 아니다.
3. OpenAI 429(크레딧 0)를 「요청 속도 제한(결제 아님)」으로 오분류·재시도 → 본문(insufficient_quota)으로 판별, 재시도 안 함,
   카드 「AI 초안 대신 기본 문장을 썼어요 — OpenAI 크레딧 없음」, 영문 원문은 관리 기록·로그에만.
"""
from __future__ import annotations

import json

import pytest

NEW = {"market": "smartstore:chezgoga", "account": "chezgoga", "product_id": "13742149801", "channel_product_no": "13803311539",
       "external_url": "https://smartstore.naver.com/chezgoga/products/13803311539", "market_label": "스마트스토어 — 셰고가",
       "at": "2026-10-10T09:09:11+00:00"}
OLD = {"market": "smartstore:chezgoga", "account": "chezgoga", "product_id": "13741121333", "channel_product_no": "13802276439",
       "external_url": "https://smartstore.naver.com/chezgoga/products/13802276439", "market_label": "스마트스토어 — 셰고가",
       "at": "2026-10-09T22:31:22+00:00"}
FAM = "fam-y7k@example.com"


def _item(uid, uploaded):
    from src.seller_console import collect_history_store as CH
    iid = CH.append(source="test", url="https://detail.tmall.com/item.htm?id=1556", title="플리츠", price="168", currency="CNY",
                    extra={"title_ko": "플리츠", "images": ["https://img.alicdn.com/a.jpg"], "uploaded": uploaded}, seller_id=uid)
    return iid[0] if isinstance(iid, tuple) else iid


def _client(uid):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, user_email=FAM, user_role="seller")
    return c


@pytest.fixture
def disp(monkeypatch):
    import src.seller_console.views as V
    from src.seller_console.upload_dispatcher import DispatchResult, UploadResult
    monkeypatch.setenv("FAMILY_EMAILS", FAM)
    monkeypatch.setattr("src.services.image_reachability.check_all", lambda urls, labels=None: {"ok": True, "bad": []})
    from src.seller_console import market_pick as MP
    monkeypatch.setattr(MP, "save_last", lambda *a, **k: None)     # 「지난 선택」 공유 기록을 남기지 않는다(다른 테스트 기본 체크 오염)
    calls = []

    class _D:
        def dispatch(self, product, markets):
            calls.append(list(markets))
            return DispatchResult(product_url="", total=1, succeeded=1, results=[UploadResult(
                market=markets[0], success=True, message="ok", external_product_id="13742149801",
                external_url=NEW["external_url"], channel_product_no="13803311539")])
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: _D())
    return calls


# ── 1. 중복 등록 가드 · 기록 ─────────────────────────────────────────────────────────────────────

def test_1_registered_market_needs_confirmation_on_the_server(disp):
    iid = _item("y7k-a", [OLD])
    c = _client("y7k-a")
    body = {"product": {"title": "플리츠", "price": 168, "currency": "CNY", "images": ["https://img.alicdn.com/a.jpg"]},
            "markets": ["smartstore:chezgoga"], "item_id": iid}
    r = c.post("/seller/collect/upload", json=body)
    d = r.get_json()
    assert r.status_code == 409 and d["needs_dup_confirm"] is True and disp == []            # 네이버에 안 보냄
    assert d["registered"][0]["shown_no"] == "13802276439" and "하나 더 생겨요" in d["error"]
    # 「다시 등록」·「실패 마켓 재시도」도 같은 입구 — 확인하면 그 한 번만 보낸다
    d2 = c.post("/seller/collect/upload", json={**body, "confirm_duplicate": True}).get_json()
    assert d2["ok"] and disp == [["smartstore:chezgoga"]]


def test_1_records_accumulate_and_chip_shows_duplicate_badge(disp):
    iid = _item("y7k-b", [OLD])
    c = _client("y7k-b")
    c.post("/seller/collect/upload", json={"product": {"title": "플리츠", "price": 168, "currency": "CNY",
                                                      "images": ["https://img.alicdn.com/a.jpg"]},
                                          "markets": ["smartstore:chezgoga"], "item_id": iid, "confirm_duplicate": True})
    from src.seller_console import collect_history_store as CH
    from src.seller_console import listing_status as MS
    ex = json.loads(CH.get(iid, seller_ids={"y7k-b"})["extra_json"])
    assert [u["product_id"] for u in ex["uploaded"]] == ["13741121333", "13742149801"]     # 예전엔 덮어써 옛 번호가 사라졌다
    chips = MS.chips(ex)
    assert len(chips) == 1 and chips[0]["product_id"] == "13742149801" and chips[0]["dup_count"] == 2
    assert MS.duplicates(ex) == [{"market": "smartstore:chezgoga", "chip": "셰고가", "count": 2,
                                  "numbers": ["13802276439", "13803311539"]}]
    html = c.get("/seller/collect/history").get_data(as_text=True)
    assert 'data-role="mk-dup-badge"' in html and "중복 2건 — 정리" in html
    m5 = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="mk-dup-badge"' in m5


def test_1_same_number_updates_in_place():
    import src.seller_console.views as V
    iid = _item("y7k-c", [NEW])
    from src.order_webhook import app
    with app.test_request_context():
        from flask import session
        session["user_id"] = "y7k-c"
        V._persist_upload_status(iid, {"results": [{"market": "smartstore:chezgoga", "success": True,
                                                    "external_product_id": "13742149801", "channel_product_no": "13803311539"}]})
    from src.seller_console import collect_history_store as CH
    ex = json.loads(CH.get(iid, seller_ids={"y7k-c"})["extra_json"])
    assert len(ex["uploaded"]) == 1


def test_1_remove_one_record_keeps_it_marked_and_never_calls_the_market(monkeypatch):
    monkeypatch.setenv("FAMILY_EMAILS", FAM)
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    monkeypatch.setattr(SS, "_api_request", lambda *a, **k: pytest.fail("네이버를 부르면 안 된다(삭제는 오너가 판매자센터에서)"))
    iid = _item("y7k-d", [OLD, NEW])
    c = _client("y7k-d")
    d = c.post(f"/seller/collect/{iid}/upload-record/remove", json={"market": "smartstore:chezgoga", "product_id": "13741121333"}).get_json()
    assert d["ok"] and "판매자센터" in d["message"]
    assert "13802276439" in d["message"] and "13741121333" not in d["message"]       # 화면엔 채널 번호만(오너 2026-10-10)
    from src.seller_console import collect_history_store as CH
    ex = json.loads(CH.get(iid, seller_ids={"y7k-d"})["extra_json"])
    assert [u["product_id"] for u in ex["uploaded"]] == ["13742149801"]
    assert ex["uploaded_removed"][0]["product_id"] == "13741121333" and ex["uploaded_removed"][0]["removed_at"]
    # 하나 남았으면 더는 빼지 않는다(중복 정리 전용)
    r = c.post(f"/seller/collect/{iid}/upload-record/remove", json={"market": "smartstore:chezgoga", "product_id": "13742149801"})
    assert r.status_code == 409


def test_1_status_popup_remembers_per_number():
    from src.seller_console import listing_status as MS
    ex = {"uploaded": [dict(OLD), dict(NEW)]}
    MS.remember(ex, {"market": "smartstore:chezgoga", "product_id": "13742149801", "state": "approved", "label": "판매중"})
    assert "review" not in ex["uploaded"][0] and ex["uploaded"][1]["review"]["label"] == "판매중"


def test_1_client_paths_go_through_the_guard():
    from pathlib import Path
    t = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "goToStep('stepMarkets')" not in t                     # 없는 단계 id — 확인 창이 TypeError로 안 떴다
    assert 'data-role="re-register" onclick="reRegister()"' in t and "confirm_duplicate: _confirmDup" in t
    assert "needs_dup_confirm" in t and "_markRegistered(_lastUploadOk)" in t
    m = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
    assert "needs_dup_confirm" in m and "confirm_duplicate: !!confirmDup" in m
    # 오너 2026-10-10: 등록 결과·결과 모달도 네이버는 채널 번호(원상품번호는 내부용)
    assert "esc(r.channel_product_no || r.external_product_id" in m
    assert "r.channel_product_no || r.external_product_id" in t


# ── 2. 제목만 남은 섹션 ─────────────────────────────────────────────────────────────────────────

def test_2_title_only_section_is_dropped():
    from src.seller_console.upload_dispatcher import market_description
    t = "플리츠 미니멀 세트\n\n■ 옵션·상세\n· 색상은 블랙 한 가지예요.\n\n■ 원문 상세\n플리츠 미니멀 세트\n\n■ 배송·구매대행 안내\n· 안내"
    out = market_description(t)
    assert "■ 원문 상세" not in out and out.count("플리츠 미니멀 세트") == 1 and "■ 옵션·상세" in out
    from src.seller_console.ai.translator import _structured_draft
    d = _structured_draft("플리츠 미니멀 세트", "CLO", [], [], [{"name": "색상", "values": ["블랙"]}], "", "플리츠 미니멀 세트")
    assert "■ 원문 상세" not in d and d.count("플리츠 미니멀 세트") == 1


# ── 3. OpenAI 크레딧 0 ─────────────────────────────────────────────────────────────────────────

BODY_429 = json.dumps({"error": {"message": "You have no credits remaining. Add credits to continue using the API at "
                                            "https://platform.openai.com/settings/organization/billing/.",
                                 "type": "insufficient_quota", "param": None, "code": "credit_balance_exhausted"}})


def _http_429():
    import requests
    resp = requests.Response()
    resp.status_code = 429
    resp._content = BODY_429.encode()
    return requests.exceptions.HTTPError("429 Client Error: Too Many Requests for url: https://api.openai.com/v1/chat/completions",
                                         response=resp)


def test_3_credit_429_is_quota_not_rate_limit_and_not_retried(monkeypatch):
    from src.seller_console.ai import translator as T
    assert T.classify_translate_reason(_http_429())[0] == "quota"
    import requests
    n = {"post": 0}

    class R:
        status_code = 429

        def raise_for_status(self):
            raise _http_429()
    monkeypatch.setattr(requests, "post", lambda *a, **k: n.__setitem__("post", n["post"] + 1) or R())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    res = T.AITranslator().generate_description({"title": "플리츠", "category": "CLO",
                                                  "options": [{"name": "색상", "values": ["블랙"]}]})
    assert n["post"] == 1                                                                   # 크레딧 0은 재시도 안 함
    assert res["draft_status"] == "openai_error" and res["draft_code"] == "quota"
    assert res["draft_error"] == "OpenAI 크레딧 없음(HTTP 429)" and "credits" not in res["draft_error"]   # 화면엔 한국어만
    assert "no credits remaining" in res["ai_call"]["error"] or "credit" in res["ai_call"]["response_head"]   # 관리 기록엔 원문
    assert "색상은 블랙 한 가지예요." in res["text"] and "해외 정품" not in res["text"]         # 기본 문장 품질 그대로


def test_3_card_line_and_legacy_draft(monkeypatch):
    from src.seller_console.upload_dispatcher import detail_auto_note
    note = detail_auto_note({"detail_auto": {"text": "x", "provider": "stub", "draft_status": "openai_error", "draft_code": "quota"},
                             "item_id": "i"})
    assert note["line"] == "AI 초안 대신 기본 문장을 썼어요 — OpenAI 크레딧 없음 — 확인(바꾸기)"
    # Y7-J 때 저장된 초안(코드 없음 · 운영 ae9cee70 모양) — 남은 응답 원문에서 읽는다
    legacy = {"text": "x", "provider": "stub", "draft_status": "openai_error",
              "draft_error": "요청 속도 제한에 걸렸어요(결제 아님 · 잠시 후 자동 재시도) · OpenAI HTTP 429",
              "ai_call": {"response_head": BODY_429}}
    assert detail_auto_note({"detail_auto": legacy, "item_id": "i"})["line"].endswith("OpenAI 크레딧 없음 — 확인(바꾸기)")
