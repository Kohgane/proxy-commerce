"""오너 11-23 23:58 실기기 「버튼 안 눌림 · 보류 예상만 하지 말고 바로 수정되게」 — 폰 카드(M5 `/seller/m/item/<id>`) 계약.

① AI 검수 수락·기각: 상품 번호를 넘긴다 · 번호가 없으면 조용히 끝내지 않는다 · 수락 뒤 다시 검증 훅 하나 · 같은 내용이면 다시 그리지 않는다
② 「편집」: 폰엔 서랍 칸이 없다 → 그 줄 아래 입력칸 → 저장(부분 저장 입구) → 다시 검증
③ 고침 없는 짚을 점: 상세 사진 0장 → 가져오기·올리기 / 스펙이 상품명에 없음 → **원문에 있는 값만** 고침안(없으면 편집만)
④ 쿠팡 대표 500px 보류: 크기만 재서 고르기(자동 변경 0) · 큰 장이 있으면 「그래도 등록」으로 풀지 않는다
⑤ 쿠팡 SKU 빈 값: 공유 초안은 읽어 둔 타오바오 번호로 · 원본 주소 넣기 · 사전검증에서 보류(전송 직전 실패 → 반쪽 등록 금지)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

M5 = Path("src/seller_console/templates/_m5_flow.html").read_text(encoding="utf-8")
RISK = Path("src/seller_console/templates/_risk_block.html").read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def item(monkeypatch):
    from src.seller_console import collect_history_store as S
    ex = {"title_ko": "접이식 원목 수납 박스", "images": ["https://img.example/a.jpg", "https://img.example/b.jpg", "https://img.example/c.jpg"],
          "options": [{"name": "색상", "values": ["원목", "화이트"]}], "description_ko": "용량 20L"}
    iid = S.append(source="share", url="https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=abc", title="접이식 원목 수납 박스", price="89",
                   currency="CNY", image="https://img.example/a.jpg", seller_id="default", extra=ex)
    return iid


# ── ① ────────────────────────────────────────────────────────────────────────

def test_m5_passes_item_id_to_ai_review():
    assert "window.kgpAiReviewHtml(pvAiReview, itemId)" in M5
    assert "window.kgpAiReviewHtml(pvAiReview);" not in M5


def test_missing_item_id_is_not_silent():
    assert "if (!itemId) return;" not in RISK
    assert "if (!itemId) { window.kgpNotice(" in RISK
    assert "window.kgpNotice = window.kgpNotice ||" in RISK and "window.kgpJobLine" in RISK     # 토스트가 없는 폰에서도 보인다


def test_one_after_hook_pc_default_m5_override():
    assert "window.kgpAiReviewAfter(d, action, itemId, box);" in RISK
    assert "window.kgpAiReviewAfter = window.kgpAiReviewAfter ||" in RISK and "runPrevalidate()" in RISK    # PC 기본 그대로
    assert "window.kgpAiReviewAfter = function (d, action) {" in M5 and "recheckAll();" in M5


def test_m5_refreshes_product_from_store_before_recheck():
    """등록은 화면 몸통을 편집값으로 얹는다 — 수락·편집·대표 바꾸기 뒤 낡은 몸통을 들고 있으면 되돌아간다."""
    assert "fetch('/seller/m/item/' + encodeURIComponent(itemId) + '/product'" in M5
    assert "if (d && d.ok && d.product) product = d.product;" in M5


def test_poll_does_not_redraw_same_content():
    assert "if (h !== pvLastHtml && !m5Editing()) { checksEl.innerHTML = h; pvLastHtml = h; }" in M5
    assert "checksEl.innerHTML = h;\n" not in M5.replace("{ checksEl.innerHTML = h; pvLastHtml = h; }", "")


def test_product_route(client, item):
    d = client.get(f"/seller/m/item/{item}/product").get_json()
    assert d["ok"] and d["product"]["title_ko"] == "접이식 원목 수납 박스"


def test_accept_title_fix_changes_stored_title(client, item):
    from src.seller_console import collect_history_store as S
    row = S.get(item, seller_id="default")
    ex = json.loads(row["extra_json"])
    ex["ai_review"] = {"status": "done", "lines": ["x"], "items": [{"issue": "번역투", "field": "title", "fix": "원목 수납함"}]}
    S.update(item, seller_id="default", extra_json=json.dumps(ex, ensure_ascii=False))
    d = client.post(f"/seller/collect/{item}/ai-review-act", json={"idx": 0, "action": "accept"}).get_json()
    assert d["ok"] and d["fields"]["title_ko"] == "원목 수납함"
    assert client.get(f"/seller/m/item/{item}/product").get_json()["product"]["title_ko"] == "원목 수납함"


# ── ② ────────────────────────────────────────────────────────────────────────

def test_edit_opens_inline_on_phone_and_saves_partial():
    assert "if (window.kgpAiReviewEditInline && window.kgpAiReviewEditInline(b, fld, ix, itemId)) return;" in RISK
    assert "window.kgpAiReviewEditInline = function (btn, field, idx) {" in M5
    for role in ("m5-ai-edit-title", "m5-ai-edit-opt", "m5-ai-edit-desc", "m5-ai-edit-save"):
        assert role in M5, role
    assert "post('/seller/collect/preview/' + encodeURIComponent(itemId) + '/save', body)" in M5


def test_pc_edit_without_field_says_why():
    i = RISK.index("window.kgpAiReviewEdit = window.kgpAiReviewEdit ||")
    assert "window.kgpNotice('이 화면엔 그 칸이 없어요" in RISK[i:i + 900]


def test_partial_save_keeps_other_fields(client, item):
    assert client.post(f"/seller/collect/preview/{item}/save", json={"options": [{"name": "색상", "values": "원목, 블랙"}]}).get_json()["ok"]
    p = client.get(f"/seller/m/item/{item}/product").get_json()["product"]
    assert p["options"][0]["values"] == ["원목", "블랙"] and p["title_ko"] == "접이식 원목 수납 박스"


# ── ③ ────────────────────────────────────────────────────────────────────────

def test_detail_zero_gets_verbs():
    from src.services.ai_review import annotate
    out = annotate([{"issue": "상세 이미지 0장이에요", "field": "none", "fix": None}], {"title_ko": "가방"})
    assert out[0]["verbs"] == ["detail_refetch", "photo_upload"]
    assert "verbs" not in annotate([{"issue": "상세 이미지 0장이에요", "field": "none", "fix": None}],
                                   {"title_ko": "가방", "detail_images": ["u"]})[0]               # 이미 있으면 동사 없음


def test_spec_fix_only_from_source():
    from src.services.ai_review import annotate
    ex = {"title_ko": "원목 수납 박스", "description_ko": "재질: 원목 · 용량 20L", "options": [{"values": ["40x30x25cm"]}]}
    x = annotate([{"issue": "상품명에 용량·크기가 없어요", "field": "none", "fix": None}], ex)[0]
    assert x["field"] == "title" and x["fix"] == "원목 수납 박스 20L 40x30x25cm" and "20L" in x["fix_from"]   # 원목은 이미 상품명에 있다
    amb = annotate([{"issue": "상품명에 크기가 없어요", "field": "none", "fix": None}],
                   {"title_ko": "수납함", "options": [{"values": ["S 20x20cm", "L 40x40cm"]}]})[0]
    assert amb["field"] == "title" and not amb.get("fix") and "직접" in amb["fix_note"]                     # 옵션마다 다르면 고침안 없음
    none = annotate([{"issue": "상품명에 재질이 없어요", "field": "none", "fix": None}], {"title_ko": "수납함"})[0]
    assert not none.get("fix")                                                                                # 원문에 없으면 지어내지 않는다


def test_spec_fix_accept_goes_through_decide():
    from src.services.ai_review import decide
    ex = {"title_ko": "원목 수납 박스", "description_ko": "용량 20L",
          "ai_review": {"status": "done", "lines": ["x"], "items": [{"issue": "상품명에 용량이 없어요", "field": "none", "fix": None}]}}
    r = decide(ex, 0, "accept")
    assert r["ok"] and ex["title_ko"] == "원목 수납 박스 20L"


def test_verb_buttons_render():
    assert 'data-role="ai-review-verb" data-verb="detail_refetch">상세 사진 가져오기' in RISK
    assert 'data-role="ai-review-verb" data-verb="photo_upload">사진 올리기' in RISK
    assert "post('/seller/collect/' + encodeURIComponent(itemId) + '/recollect', {mode: 'queue'})" in M5
    assert "document.getElementById('m5Photos')" in M5 and "inp.click()" in M5


# ── ④ ────────────────────────────────────────────────────────────────────────

def test_best_rep_prefers_big_textless_square():
    from src.services.coupang_image_check import best_rep
    c = [{"idx": 0, "ok": False, "w": 300, "h": 300, "long_side": 300, "is_rep": True},
         {"idx": 1, "ok": True, "w": 900, "h": 900, "long_side": 900},
         {"idx": 2, "ok": True, "w": 1200, "h": 500, "long_side": 1200},
         {"idx": 3, "ok": True, "w": 1000, "h": 1000, "long_side": 1000, "text": True}]
    assert best_rep(c) == 1
    assert best_rep([c[0]]) == -1


def test_rep_candidates_route(client, item, monkeypatch):
    from src.services import coupang_image_check as C
    sizes = {"https://img.example/a.jpg": (300, 300), "https://img.example/b.jpg": (900, 900), "https://img.example/c.jpg": (700, 500)}
    monkeypatch.setattr(C, "size_of", lambda u: {"w": sizes[u][0], "h": sizes[u][1], "long_side": max(sizes[u]),
                                                 "ok": max(sizes[u]) >= 500, "text": False})
    d = client.get(f"/seller/collect/{item}/rep-candidates").get_json()
    assert d["ok"] and d["best"] == 1 and d["candidates"][0]["is_rep"] and not d["pending"]


def test_m5_rep_pick_once_and_override_only_without_big():
    assert "repShownOnce" in M5 and "위에서 대표 사진을 고르면 이 계정에도 같이 적용돼요" in M5
    assert "if ((r.fixes || []).indexOf('rep_image') >= 0 && repHasBig()) return false;" in M5
    assert "(repCands && !repHasBig() && !repCands.pending" in M5                    # 그래도 등록 = 큰 장이 없을 때만
    assert "post('/seller/collect/' + encodeURIComponent(itemId) + '/rep-image', {idx: repPick})" in M5
    assert "으로 바꿀까요?" in M5                                                     # 제안 한 번 · 바꾸는 건 유저


# ── ⑤ ────────────────────────────────────────────────────────────────────────

def test_share_draft_uses_read_taobao_id():
    from src.seller_console.upload_dispatcher import build_dispatch_payload
    it = {"id": "x", "url": "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=abc", "extra_json": json.dumps({"item_id_taobao": "744111222333"})}
    out = build_dispatch_payload({"title": "t", "url": "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=abc"}, it)
    assert out["sku"] == "744111222333" and out["url"] == "https://item.taobao.com/item.htm?id=744111222333"
    bare = build_dispatch_payload({"title": "t"}, {"id": "y", "url": "https://e.tb.cn/h.8Ic?tk=abc", "extra_json": "{}"})
    assert not bare.get("sku")                                                         # 번호가 없으면 지어내지 않는다


def test_manual_source_url_wins():
    from src.seller_console.upload_dispatcher import build_dispatch_payload
    it = {"id": "x", "url": "https://e.tb.cn/h.8Ic?tk=abc",
          "extra_json": json.dumps({"item_id_taobao": "111111", "source_url_manual": "https://item.taobao.com/item.htm?id=222222222"})}
    assert build_dispatch_payload({"title": "t"}, it)["sku"] == "222222222"


def test_precheck_holds_coupang_without_sku_not_smartstore():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title": "t", "images": ["https://img.example/a.jpg"], "price": "89", "_sku_probe": {"ok": False, "chosen": "https://e.tb.cn/h.x"}}
    h = UploadDispatcher.readiness_holds(pd, "coupang:gogane")
    src = [x for x in h if x["fix"] == "source_url"]
    assert src and src[0]["line"].startswith("원본 상품 주소가 없어 쿠팡 상품코드를 만들 수 없어요")
    assert not [x for x in UploadDispatcher.readiness_holds(pd, "smartstore") if x["fix"] == "source_url"]
    assert not [x for x in UploadDispatcher.readiness_holds(dict(pd, _sku_probe={"ok": True}), "coupang") if x["fix"] == "source_url"]


def test_source_url_route(client, item):
    bad = client.post(f"/seller/collect/{item}/source-url", json={"url": "https://e.tb.cn/h.abc?tk=x"})
    assert bad.status_code == 400 and "상품번호를 못 찾았어요" in bad.get_json()["error"]
    ok = client.post(f"/seller/collect/{item}/source-url", json={"url": "【淘宝】 https://item.taobao.com/item.htm?id=744111222333 「상품」"}).get_json()
    assert ok["ok"] and ok["sku"] == "744111222333"
    from src.seller_console import collect_history_store as S
    from src.seller_console.upload_dispatcher import build_dispatch_payload
    row = S.get(item, seller_id="default")
    assert build_dispatch_payload({"title": "t"}, row)["sku"] == "744111222333"


def test_m5_source_url_input_and_recheck():
    assert 'data-role="m5-source-url-in"' in M5 and "data-role=\"m5-source-url-save\"" in M5
    assert "post('/seller/collect/' + encodeURIComponent(itemId) + '/source-url', {url: u})" in M5


def test_uploader_failure_is_human_first(monkeypatch):
    """행동으로 잰다 — SKU가 비면 사람 말 먼저, 코드는 `coupang_sku_missing`."""
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader.__new__(CoupangUploader)
    up.account = None
    monkeypatch.setattr(CoupangUploader, "_missing_shipping_config", lambda self: [])
    monkeypatch.setattr(CoupangUploader, "resolve_delivery_company_code", lambda self: "CJGLS")
    r = up.upload_product({"title": "t", "sku": "", "url": "https://e.tb.cn/h.x"})
    assert r["success"] is False and r["held"] is True
    assert r["error_code"] == "coupang_sku_missing"
    assert r["error"].startswith("원본 상품 주소가 없어 쿠팡 상품코드를 만들 수 없어요")


def test_precheck_probes_sku_with_same_builder():
    """사전검증 준비가 등록과 **같은 빌더**를 부른다(구조 — AST)."""
    from tests._ast_probe import calls_in
    from src.seller_console import views
    import ast
    from tests._ast_probe import _tree_of
    aliases = {a.asname or a.name for n in ast.walk(_tree_of(views._pv_prepare)) if isinstance(n, ast.ImportFrom)
               for a in n.names if a.name == "build_dispatch_payload"}
    assert aliases and aliases & calls_in(views._pv_prepare)


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_both_scripts_parse():
    for path, a, b in (("src/seller_console/templates/_risk_block.html", "<script>", "</script>"),):
        s = Path(path).read_text(encoding="utf-8")
        js = s[s.index(a) + len(a):s.rindex(b)]
        r = subprocess.run(["node", "-e", "new Function(require('fs').readFileSync(0,'utf8'))"], input=js, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    i = M5.index("<script>\n(function () {")
    j = M5.index("})();\n</script>", i)
    js = re.sub(r"\{%[^%]*%\}", "", re.sub(r"\{\{[^}]*\}\}", "0", M5[i + 8:j + 5]))
    r = subprocess.run(["node", "-e", "new Function(require('fs').readFileSync(0,'utf8'))"], input=js, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
