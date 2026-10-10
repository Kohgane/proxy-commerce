"""Y7-N(오너 2026-10-10 22:1x) — 상세설명 칸의 가게 UI 글자 차단 · 「사이즈」 값이 모델명 하나뿐 → 이름 후보 「모델」 ·
사전검증 통과 0건이면 「통과 마켓에 업로드」 회색 비활성.

증거(운영 DB 저장값): BLACKHOLES 블랙홀 미니 벽등 `301c02cd`(타오바오 1077964821879)
  description = 「沉默流浪汉\\n4.5\\n好评率84%\\n平均2天内发货\\n客服满意度94%」 — merge_log 「비어 있음→화면 읽기 (빈 칸 채움)」
  options = 大小: 【BLACKHOLES】 · 颜色分类: Yellow light / White light
대조(변화 0): 플리츠 세트 `ae9cee70` 저장값.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BH_DESC = "沉默流浪汉\n4.5\n好评率84%\n平均2天内发货\n客服满意度94%"
BH_DESC_KO = "침묵 방랑자\n4.5\n호평률 84%\n평균 2일 이내 발송\n고객 만족도 94%"     # 번역본이었다면 남았을 꼴
BH_OPTS = [{"name": "大小", "values": ["【BLACKHOLES】"]},
           {"name": "颜色分类", "values": ["Yellow light", "White light"]}]
BH_TITLE = "BLACKHOLES 블랙홀 미니 벽등, 스타트렉 영화 굿즈, 장식 모델, 피규어, 우주"

PL_DESC = ("플리츠 미니멀 여성 여름 세트, 디자인 감각이 돋보이는 언밸런스 컷팅 주름 상의와 스커트 투피스 세트\n\n"
           "■ 옵션·상세\n· 색상은 블랙 상의, 블랙 스커트, 블루 상의, 블루 스커트, 모스 그린 상의, 모스 그린 스커트, "
           "로열 블루 상의, 로열 블루 스커트 8가지 중에서 고를 수 있어요.\n· 사이즈는 프리사이즈 한 가지예요.\n\n"
           "■ 사이즈·세탁 안내\n· 사이즈는 옵션에 적힌 표기를 기준으로 해요. 실측 치수는 위 사진의 사이즈 안내를 확인해 주세요.\n"
           "· 세탁은 제품에 붙은 라벨 안내를 따라 주세요.\n\n"
           "■ 배송·구매대행 안내\n· 해외 구매대행 상품으로, 주문 후 현지 배송·통관을 거쳐 발송됩니다.\n"
           "· 모니터·조명 환경에 따라 실제 색상과 차이가 있을 수 있습니다.\n· 정확한 사이즈·소재는 위 옵션·상세 정보를 확인해 주세요.\n"
           "· 교환·반품은 판매 마켓과 구매대행 정책을 따릅니다.")
PL_OPTS = [{"name": "颜色分类", "values": ["黑色上衣", "黑色半裙", "蓝色上衣", "蓝色半裙", "苔藓绿上衣", "苔藓绿半裙", "宝蓝上衣", "宝蓝半裙"],
            "name_ko": "색상", "values_ko": ["블랙 상의", "블랙 스커트", "블루 상의", "블루 스커트", "모스 그린 상의", "모스 그린 스커트",
                                           "로열 블루 상의", "로열 블루 스커트"]},
           {"name": "尺码", "values": ["均码"], "name_ko": "사이즈", "values_ko": ["프리사이즈"]}]
AUTO = {"text": "BLACKHOLES 블랙홀 미니 벽등\n\n■ 옵션·상세\n· 색상은 옐로 라이트, 화이트 라이트 2가지예요.",
        "images": ["https://img.alicdn.com/a.jpg"], "provider": "stub", "v": 99}


# ── 1. 판정 · 토큰 파일 ────────────────────────────────────────────────────────────────────────

def test_1_token_file_has_three_languages():
    t = json.loads(Path("src/uploaders/detail_ui_junk.json").read_text(encoding="utf-8"))
    assert set(t["tokens"]) == {"zh", "ko", "en"}
    for tok in ("好评率", "发货", "客服", "满意度", "店铺", "收藏", "关注", "粉丝"):
        assert tok in t["tokens"]["zh"]
    assert t["max_lines"] == 5 and t["rating_re"]


def test_1_blackholes_body_is_empty():
    from src.uploaders.detail_ui_junk import judge
    j = judge(BH_DESC)
    assert j["junk"] is True and j["name"] == "沉默流浪汉"
    assert j["ui"] == ["4.5", "好评率84%", "平均2天内发货", "客服满意度94%"]
    assert judge(BH_DESC_KO)["junk"] is True
    assert judge(" / ".join(BH_DESC.split("\n")))["junk"] is True                 # 한 줄에 이어 붙은 가게 카드


def test_1_real_text_is_not_junk():
    from src.uploaders.detail_ui_junk import is_junk
    assert not is_junk(PL_DESC)
    assert not is_junk("USB 충전식 벽등\n4.5")                                  # 상품 한 줄 + 평점 하나 — 버리지 않는다
    assert not is_junk("Size: 30cm\nMaterial: ABS\n4.5")
    assert not is_junk("\n".join(["好评率99%"] * 6))                            # 5줄 넘음 — 줄 단위 정리(S2)의 일


def test_1_blackholes_goes_to_auto_draft_path():
    """셀러 글이 없는 것으로 → 자동 초안(템플릿) 경로. 번역본이 남긴 「침묵 방랑자 / 평균 2일 이내 발송」이 셀러 글로 읽히던 것."""
    from src.uploaders import naver_detail as nd
    from src.seller_console.upload_dispatcher import market_description, detail_auto_note
    for d in (BH_DESC, BH_DESC_KO):
        assert market_description(d) == ""
        pd = {"description": d, "description_ko": d, "title_ko": BH_TITLE}
        assert nd._text_of(pd) == ""
        html = nd.build({**pd, "detail_auto": AUTO})
        assert "옐로 라이트" in html and "방랑자" not in html and "好评率" not in html
        assert detail_auto_note({**pd, "detail_auto": AUTO, "item_id": "x"})        # 카드 「상세 자동 생성 — 확인(바꾸기)」
    import src.seller_console.views as V
    assert V._pv_needs_auto_text({"description": BH_DESC_KO, "title_ko": BH_TITLE}, ["smartstore:gocosmos"]) is True


def test_1_draft_sources_drop_whole_ui_body():
    from src.seller_console.ai.translator import draft_source_lines
    assert draft_source_lines(BH_DESC, BH_TITLE) == []
    assert draft_source_lines(BH_DESC_KO, BH_TITLE) == []


def test_1_pleats_unchanged(monkeypatch):
    """대조: 플리츠 세트 상세는 판정 전후 같은 결과(변화 0)."""
    from src.seller_console.upload_dispatcher import market_description
    from src.uploaders import naver_detail as nd
    from src.seller_console.ai.translator import draft_source_lines
    import src.uploaders.detail_ui_junk as J
    pd = {"description": PL_DESC, "description_ko": PL_DESC, "options": PL_OPTS}
    now = (market_description(PL_DESC), nd._text_of(pd), nd.build(pd), draft_source_lines(PL_DESC))
    monkeypatch.setattr(J, "is_junk", lambda *_a, **_k: False)
    before = (market_description(PL_DESC), nd._text_of(pd), nd.build(pd), draft_source_lines(PL_DESC))
    assert now == before and now[0]
    assert J.note(pd) == ""


# ── 2. 수집 단계 기록 · 카드 사유 ───────────────────────────────────────────────────────────────

def test_2_merge_drops_and_logs():
    from src.collectors.source_merge import merge_by_source
    ex, chg, kept = merge_by_source({"title": "x"}, {"description": BH_DESC}, {"description": "tier2"}, path="enrich")
    assert "description" not in ex and "description" not in chg
    assert ex["merge_log"][-1]["dropped"] == {"description": "화면 읽기 → UI 글자라 버림"}
    ex2, chg2, _ = merge_by_source({"title": "x"}, {"description": PL_DESC}, {"description": "tier2"}, path="enrich")
    assert ex2["description"] == PL_DESC and "description" in chg2 and "dropped" not in ex2["merge_log"][-1]


def test_2_collect_and_enrich_routes_do_not_store_ui_text(flask_client, monkeypatch):
    """첫 수집(`/collect/extension`)과 보강(`/collect/enrich`) 둘 다 — UI 글자는 저장하지 않고 merge_log에 남긴다.
    보강은 병합 뒤 「20자↑면 빈 칸 채움」 블록도 지난다(BLACKHOLES 30자는 거기로도 들어갈 수 있었다)."""
    from src.seller_console import collect_history_store as store
    monkeypatch.setattr(store, "pg_enabled", lambda: False, raising=False)
    with flask_client.session_transaction() as s:
        s["user_id"] = "u_y7n"
    hdr = {"X-KGP": "1"}
    r = flask_client.post("/api/v1/collect/extension", headers=hdr, json={
        "url": "https://item.taobao.com/item.htm?id=1077964821879", "title": BH_TITLE, "price": "30", "currency": "CNY",
        "description": BH_DESC, "field_sources": {"description": "tier2"}, "translate": False})
    d = r.get_json()
    assert r.status_code == 200 and d.get("ok"), r.get_data(as_text=True)
    ex = json.loads(store.get(d["item_id"], seller_ids={"u_y7n"})["extra_json"])
    assert not ex.get("description")
    assert ex["merge_log"][-1]["dropped"] == {"description": "화면 읽기 → UI 글자라 버림"}
    import src.api.extension_api as EA
    monkeypatch.setattr(EA, "_require_token", lambda *a, **k: {"user_id": "u_y7n", "scopes": ["collect.write"]})
    r2 = flask_client.post("/api/v1/collect/enrich", headers={"Authorization": "Bearer t"}, json={
        "item_id": d["item_id"], "title": BH_TITLE, "description": BH_DESC, "field_sources": {"description": "tier2"},
        "detail_images": ["https://img.alicdn.com/imgextra/d1.jpg"]})
    assert r2.status_code == 200, r2.get_data(as_text=True)
    ex = json.loads(store.get(d["item_id"], seller_ids={"u_y7n"})["extra_json"])
    assert not ex.get("description")
    assert [e["path"] for e in ex["merge_log"] if (e.get("dropped") or {}).get("description") == "화면 읽기 → UI 글자라 버림"] \
        == ["collect", "enrich"]


def test_2_card_reason_line(monkeypatch):
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title": BH_TITLE, "title_ko": BH_TITLE, "price": 30, "currency": "CNY", "description": BH_DESC,
          "description_ko": BH_DESC, "options": BH_OPTS, "images": ["https://img.alicdn.com/a.jpg"]}
    rs = UploadDispatcher().prevalidate(pd, ["elevenst"])
    assert any(d.startswith("상세설명: 화면 읽기 → UI 글자라 버림") for d in (rs[0].details or []))
    rs2 = UploadDispatcher().prevalidate({**pd, "description": PL_DESC, "description_ko": PL_DESC}, ["elevenst"])
    assert not any("UI 글자" in d for d in (rs2[0].details or []))


def test_2_card_reason_when_editor_sent_blank(monkeypatch):
    """편집 화면은 UI 글자를 칸에 채우지 않는다(빈 칸으로 보냄) — 카드 사유는 **저장본**을 보고 낸다."""
    import src.seller_console.views as V
    from src.seller_console.upload_dispatcher import UploadDispatcher, PrevalidationResult
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market",
                        lambda self, pd, m: PrevalidationResult(market=m, ok=False, hold=True, message="카테고리를 먼저 골라 주세요"))
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: UploadDispatcher())
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))
    monkeypatch.setattr(V, "_pv_auto_detail", lambda pd, data, results, force=False: (None, pd))
    from tests._pv_helper import prevalidate
    iid = _bh_item("y7n-card")
    d = prevalidate(_client("y7n-card"), {"product": {"title": BH_TITLE, "description": "", "price": 30, "currency": "CNY"},
                                          "item_id": iid, "markets": ["elevenst"]})
    assert any(x.startswith("상세설명: 화면 읽기 → UI 글자라 버림") for x in d["results"][0]["details"])
    cp = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "renderDetailLines(r.details, r.ok ? 'text-muted' : 'text-danger', r.message)" in cp   # 한 줄이어도 보인다


# ── 3. 옵션 이름 후보 「모델」 ──────────────────────────────────────────────────────────────────

def test_3_model_name_candidate():
    from src.uploaders.option_model_hint import suggestions, looks_like_model
    s = suggestions({"options": BH_OPTS})
    assert len(s) == 1 and s[0]["orig"] == "大小" and s[0]["suggest"] == "모델" and s[0]["label"] == "사이즈"
    assert "【BLACKHOLES】 하나뿐" in s[0]["why"]
    assert suggestions({"options": PL_OPTS}) == []                                # 플리츠: 均码 — 변화 0
    for v in ("XL", "FREE", "3XL", "M", "【大号】", "【30cm】"):                   # 진짜 사이즈 표기
        assert not looks_like_model(v), v
    assert looks_like_model("BLACKHOLES") and looks_like_model("【BLACKHOLES】")
    assert suggestions({"options": [{"name": "尺码", "values": ["BLACKHOLES", "WHITEHOLES"]}]}) == []   # 값 2개 — 아님


def test_3_not_applied_automatically(monkeypatch):
    """후보만 — 옵션 이름·쿠팡 메타 이름 표는 그대로."""
    iid = _bh_item("y7n-opt")
    c = _client("y7n-opt")
    h = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    assert 'data-role="opt-name-hint"' in h and 'data-hint-orig="大小"' in h and 'data-hint-name="모델"' in h
    from src.seller_console import collect_history_store as CH
    ex = json.loads(CH.get(iid, seller_ids={"y7n-opt"})["extra_json"])
    assert ex["options"][0]["name"] == "大小" and not ex.get("option_name_overrides") and not ex.get("coupang_option_names")
    cp = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "function kgpApplyNameHint" in cp and "kgpModelHintsHtml(d.name_suggest)" in cp


def test_3_coupang_panel_gets_candidate(monkeypatch):
    """쿠팡 옵션 블록 응답에 후보가 실린다 — 메타 판정(option_form)은 손대지 않는다."""
    import src.channel_sync.coupang_uploader as CU
    seen = {}

    def fake(product):
        seen["options"] = product.get("options")
        return {"ok": True, "category": "x", "fields": [], "choices": [], "holds": ["옵션 값 미해석: 【BLACKHOLES】"]}
    monkeypatch.setattr(CU, "option_form", fake)
    c = _client("y7n-cp")
    d = c.post("/seller/collect/coupang/options", json={"product": {"title": BH_TITLE, "options": BH_OPTS}}).get_json()
    assert d["holds"] == ["옵션 값 미해석: 【BLACKHOLES】"]                        # 메타 매핑 그대로
    assert d["name_suggest"][0]["suggest"] == "모델" and seen["options"][0]["name"] == "大小"
    d2 = c.post("/seller/collect/coupang/options", json={"product": {"title": "x", "options": PL_OPTS}}).get_json()
    assert d2["name_suggest"] == []


def test_3_editor_does_not_prefill_ui_text():
    iid = _bh_item("y7n-ed")
    h = _client("y7n-ed").get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    import re as _re
    m = _re.search(r'const _DESC_UI_NOTE = (".*?");', h)
    assert m and json.loads(m.group(1)).startswith("상세설명: 화면 읽기 → UI 글자라 버림")


# ── 4. 통과 0건 → 업로드 버튼 회색 비활성 ──────────────────────────────────────────────────────

def test_4_upload_button_gray_when_none_passed():
    cp = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert '<button class="btn btn-success kgp-upload-go" id="btnConfirmUpload" onclick="runUpload()" disabled>' in cp
    assert "통과 마켓에 업로드" in cp                                              # 문구 그대로
    i = cp.index("function renderPrevalidateResults")
    body = cp[i:cp.index("el.innerHTML = html;", i)]
    assert body.count("document.getElementById('btnConfirmUpload').disabled = true;") == 2
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    assert ".kgp-upload-go:disabled" in css and "var(--text-muted)" in css[css.index(".kgp-upload-go:disabled"):][:300]


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────────────────────

def _bh_item(seller):
    from src.seller_console import collect_history_store as S
    ex = {"title": BH_TITLE, "title_ko": BH_TITLE, "description": BH_DESC, "description_ko": BH_DESC,
          "options": json.loads(json.dumps(BH_OPTS)), "price": "30", "currency": "CNY",
          "images": ["https://img.alicdn.com/a.jpg"], "field_sources": {"description": "tier2"}}
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id=seller,
                   title=BH_TITLE, price="30", currency="CNY", extra=ex)
    return iid[0] if isinstance(iid, tuple) else iid


def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c
