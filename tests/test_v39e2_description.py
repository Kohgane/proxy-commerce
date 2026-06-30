"""tests/test_v39e2_description.py — v39-E2 #3: 상세설명 실추출 + AI 초안 폴백 + 필러 제거.

1순위 실추출(본문 텍스트 + 스펙 표), 2순위 AI 초안(키 없으면 정직 구조화·가짜 0),
템플릿 한 줄 필러('가장 저렴한 가격으로 구매하세요') 제거.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("bs4")

from src.collectors.universal_scraper import extract_detail_description, is_filler_description


_DETAIL_HTML = """
<html><body>
  <div class="product-description">
    <p>이 소파는 데일리 사용에 맞춘 패브릭 3인용 모델입니다.</p>
    <table>
      <tr><th>소재</th><td>폴리에스터 패브릭</td></tr>
      <tr><th>사이즈</th><td>가로 200cm</td></tr>
    </table>
    <ul><li>탈착식 커버로 세탁이 쉽습니다.</li></ul>
  </div>
  <div class="reviews"><p>리뷰: 좋아요</p></div>
</body></html>
"""


def test_extract_detail_text_and_specs():
    d = extract_detail_description(_DETAIL_HTML, "https://temu.com/sofa")
    assert "패브릭 3인용" in d["text"]
    assert "탈착식 커버" in d["text"]
    specs = dict(d["specs"])
    assert specs.get("소재") == "폴리에스터 패브릭"
    assert specs.get("사이즈") == "가로 200cm"
    # 리뷰 영역 텍스트는 본문에서 제외
    assert "리뷰: 좋아요" not in d["text"]


def test_filler_line_detected_and_dropped():
    assert is_filler_description("Temu에서 가장 저렴한 가격으로 소파를 구매하세요.")
    assert is_filler_description("지금 쇼핑하세요")
    assert not is_filler_description("폴리에스터 패브릭 소재의 3인용 소파입니다.")


def test_extract_empty_when_no_detail_region():
    d = extract_detail_description("<html><body><p>x</p></body></html>", "https://x/p")
    assert d == {"text": "", "specs": []}


def test_ai_generate_stub_honest_no_fabrication(monkeypatch):
    # 키 없음/dry-run → provider 'stub', 확인된 정보(제목·스펙)만 — 없는 수치 날조 0
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.ai.translator import AITranslator
    res = AITranslator().generate_description({
        "title": "패브릭 3인용 소파", "category": "홈/가구",
        "specs": [("소재", "폴리에스터"), ("사이즈", "200cm")], "keywords": ["소파", "패브릭"],
    })
    assert res["provider"] == "stub" and res["is_draft"] is True
    assert "패브릭 3인용 소파" in res["text"]
    assert "소재: 폴리에스터" in res["text"]


def test_ai_generate_stub_empty_specs_asks_input(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.ai.translator import AITranslator
    res = AITranslator().generate_description({"title": "어떤 상품", "specs": []})
    assert "직접 입력" in res["text"]      # 없는 정보 지어내지 않고 입력 요청(정직)


def test_drawer_has_ai_draft_button_and_badge():
    tpl = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "AI 상세 초안 생성" in tpl and "aiDescribe" in tpl
    assert "AI 초안" in tpl and "aiDraftBadge" in tpl
    assert "/ai-description" in tpl


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_ai_description_route_honest_stub(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_get_owned_item", lambda iid: {
        "id": iid, "title": "패브릭 소파", "extra_json": '{"detail_specs": [["소재","패브릭"]]}'})
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.post("/seller/collect/preview/x1/ai-description", json={"title": "패브릭 소파"})
    d = r.get_json()
    assert d["ok"] and d["provider"] == "stub" and d["is_draft"] is True
    assert "패브릭 소파" in d["text"]
