"""Z 후속2(오너 2026-10-04 20:39 실측).

1. /admin/diagnostics/taobao-mtop — 공유 문구 통째 입력이 InvalidSchema/InvalidURL → 공유 수집과 같은 추출로 링크 하나만.
2. 「옵션 값 1개 미해석」이 「번역하고 다시 검증」 뒤에도 남을 때 — **어떤 값이 왜**(번역기 응답 원문·시도 이력)와
   Papago 오늘 남은 몫을 보류 문구에 그대로.
"""
from __future__ import annotations

import json

SHARE = "【淘宝】7天无理由退货 https://e.tb.cn/h.TzQ8xyz?tk=AbCd HU926 「格斯潘懒人沙发单人」\n点击链接直接打开 或者 淘宝搜索直接打开"


class _R:
    status_code, url, text = 200, "https://item.taobao.com/item.htm?id=733241700286", ""


def test_mtop_probe_picks_the_link_out_of_share_text():
    from src.collectors import taobao_mtop as T
    got = []

    class S:
        def get(self, u, **k):
            got.append(u)
            return _R()
    iid, how = T.item_id_from(SHARE, S())
    assert got == ["https://e.tb.cn/h.TzQ8xyz?tk=AbCd"]                 # 문구 전체가 아니라 링크만 연다
    assert iid == "733241700286" and how.startswith("뽑은 링크 https://e.tb.cn/")
    assert T.item_id_from("링크 없는 글", S()) == ("", "입력에서 링크를 찾지 못했어요(https://… 또는 숫자 상품 ID)")
    assert T.item_id_from("733241700286") == ("733241700286", "직접 입력")


def test_translate_options_records_why_each_value_failed(monkeypatch):
    from src.seller_console.ai import translator as T
    monkeypatch.setattr(T.AITranslator, "translate_product", lambda self, p: {
        "provider": "none", "description_ko": p["description"],
        "attempts": [{"provider": "papago", "ok": False, "error": "HTTP 429 · Quota Exceeded"},
                     {"provider": "deepl", "ok": False, "error": "키 없음"}]})
    out = T.AITranslator().translate_options([{"name": "", "values": ["朦胧月光款"]}])
    assert out["options"][0]["values_ko"] == ["朦胧月光款"]                    # 가짜 번역 0
    assert out["diag"]["朦胧月光款"] == "번역기 실패(none) — papago: HTTP 429 · Quota Exceeded · deepl: 키 없음"
    monkeypatch.setattr(T.AITranslator, "translate_product", lambda self, p: {
        "provider": "papago", "description_ko": "두꺼운\n여분 줄"})
    out = T.AITranslator().translate_options([{"name": "", "values": ["朦胧月光款"]}])
    assert "응답 줄 수 어긋남(보낸 1줄 · 받은 2줄)" in out["diag"]["朦胧月光款"] and "「두꺼운\n여분 줄」" in out["diag"]["朦胧月光款"]


def test_hold_line_names_the_value_the_reason_and_papago_left(monkeypatch):
    """번역하고 다시 검증 → 그래도 남은 값: 보류 문구에 값·번역기 원문·Papago 잔량."""
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.seller_console.ai import translator as T
    from src.seller_console.upload_dispatcher import UploadDispatcher
    monkeypatch.setattr(T.AITranslator, "translate_product", lambda self, p: {
        "provider": "none", "description_ko": p["description"],
        "attempts": [{"provider": "papago", "ok": False, "error": "HTTP 429 · {\"errorCode\":\"010\",\"message\":\"Quota Exceeded\"}"}]})
    monkeypatch.setattr(T, "papago_chars_today", lambda: 100000)
    monkeypatch.setenv("PAPAGO_DAILY_CHAR_LIMIT", "100000")
    seller = "owner-z6-2"
    ex = {"title": "格斯潘懒人沙发", "title_ko": "격스판 빈백 소파", "price": "780", "currency": "CNY",
          "images": ["https://img.alicdn.com/a.jpg"],
          "options": [{"name": "颜色", "values": ["加厚款星空蓝"]}],
          "skus": [{"spec": ["加厚款星空蓝"], "price": "780", "stock": 5}]}
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=733241700286", seller_id=seller,
                   title="격스판 빈백 소파", price="780", currency="CNY", extra=ex)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    c.post(f"/seller/collect/{iid}/translate-now", json={})
    stored = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert "加厚款星空蓝" in stored["option_translate_diag"]["values"]
    from src.seller_console.product_builder import build_product
    pd = build_product(S.get(iid, seller_ids={seller}), seller_id=seller)
    h = next(h for h in UploadDispatcher.readiness_holds(pd, "coupang") if h["fix"] == "translate")
    assert h["short"].startswith("옵션 값 1개 미해석(「加厚款星空蓝」")
    assert "「加厚款星空蓝」 — " in h["line"] and "번역기: 번역기 실패(none) — papago: HTTP 429" in h["line"] and "Quota Exceeded" in h["line"]
    assert "마지막 시도" in h["line"] and "KST" in h["line"]
    assert "Papago 오늘 남은 몫 0/100,000자(PAPAGO_DAILY_CHAR_LIMIT)" in h["line"]


def test_hold_line_without_any_attempt_says_so(monkeypatch):
    from src.seller_console import upload_dispatcher as U
    monkeypatch.setenv("PAPAGO_DAILY_CHAR_LIMIT", "0")
    line = U.unresolved_why_line({}, ["加厚款"])
    assert line.startswith("「加厚款」 — ") and "번역기 기록 없음(아직 번역기에 안 보냄)" in line and "Papago 일한도 없음" in line


def test_y8_long_translated_value_says_30_char_limit():
    """Y8 1): 번역은 됐는데 30자를 넘어 남은 값 — 「1개 미해석」이 아니라 값·글자 수·한도를 그대로."""
    from src.seller_console import upload_dispatcher as U
    v = "朦胧月光款星河渐变氛围限定版"
    ko = "몽롱한 달빛 스타일 은하수 그라데이션 분위기 한정판 무드 조명 세트"
    pd = {"options": [{"name": "颜色", "values": [v], "values_ko": [ko]}], "skus": [{"spec": [v], "price": "99"}]}
    un = U.unresolved_option_values(pd)
    assert un == [v]
    line = U.unresolved_why_line(pd, un)
    assert "쿠팡 옵션 값 한도 30자를 넘습니다" in line and "자)" in line and "번역기 기록 없음" not in line


def test_mtop_page_measures_only_lines_with_a_link(monkeypatch):
    """공유 문구를 통째로 붙여도 「点击链接直接打开」 줄은 한 건이 되지 않는다."""
    from src.collectors import taobao_mtop as T
    seen = []
    monkeypatch.setattr(T, "probe", lambda q, via="direct": (seen.append(q), {"input": q[:80], "item_id": "", "how": "x",
                                                                               "log": [], "detail": None, "desc_images": None})[1])
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["user_role"] = "owner", "admin"
    c.get("/admin/diagnostics/taobao-mtop", query_string={"q": SHARE})
    assert len(seen) == 1 and "https://e.tb.cn/" in seen[0]
