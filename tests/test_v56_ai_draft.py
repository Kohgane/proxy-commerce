"""tests/test_v56_ai_draft.py — v56 STEP3: AI 상세 초안 정직화.

'- k: v' 플레이스홀더 버그 수리(실키·실값·빈행 생략). 키없음=구조초안(특징·옵션표·안내 틀, 실데이터만).
키감지는 요청 시점 os.environ(부팅 캐시 아님). OPENAI_API_KEY 단일 명칭.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


@pytest.fixture(autouse=True)
def _clean_env():
    saved = os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("DEEPL_API_KEY", None)
    yield
    if saved is not None:
        os.environ["OPENAI_API_KEY"] = saved


def test_structured_draft_no_placeholder():
    from src.seller_console.ai.translator import _structured_draft
    t = _structured_draft("접이식 책상", "HOM", ["차량용", "접이식"],
                          [["소재", "ABS"], ["k", "v"], ["", ""], ["무게", "1.2kg"]],
                          [{"name": "색상", "values": ["블랙", "화이트"]}], "GOGA")
    assert "- k: v" not in t and "k: v" not in t          # 플레이스홀더 0
    assert "차량용" in t and "블랙, 화이트" in t and "ABS" in t and "1.2kg" in t   # 실데이터
    assert "■ 특징" in t and "■ 옵션·상세" in t and "■ 배송·구매대행 안내" in t   # 구조
    # 빈/1글자 행 생략
    assert "\n· k:" not in t


def test_stub_when_no_key():
    from src.seller_console.ai.translator import AITranslator
    r = AITranslator().generate_description({"title": "책상", "category": "HOM",
                                             "keywords": ["차량용"], "specs": [], "options": []})
    assert r["provider"] == "stub" and r["is_draft"] is True
    assert "책상" in r["text"] and "- k: v" not in r["text"]


def test_key_detection_request_time():
    # 부팅 시점이 아니라 매 요청(AITranslator())마다 os.environ을 읽는다(런타임에 키 설정 즉시 반영).
    from src.seller_console.ai.translator import AITranslator
    assert AITranslator().provider == "stub"          # 키 없음
    os.environ["OPENAI_API_KEY"] = "sk-test-runtime"
    try:
        assert AITranslator().provider == "openai"    # 같은 프로세스에서 키 설정 → 즉시 openai(요청시점 읽기)
    finally:
        os.environ.pop("OPENAI_API_KEY", None)
    assert AITranslator().provider == "stub"          # 제거 시 다시 stub


def test_openai_env_var_name_single():
    # 코드가 OPENAI_API_KEY 단일 명칭으로 읽는다(오타/이명 없음).
    import pathlib
    tr = pathlib.Path("src/seller_console/ai/translator.py").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" in tr
    assert "OPENAI_KEY" not in tr.replace("OPENAI_API_KEY", "") and "OPENAI_APIKEY" not in tr


def test_e2e_ai_description_endpoint():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    item = {"id": "x", "title": "책상", "url": "https://t/g-1", "price": "20605", "currency": "KRW",
            "extra_json": json.dumps({"title_ko": "접이식 책상", "category_code": "HOM",
                                      "keywords": ["차량용", "접이식"],
                                      "options": [{"name": "색상", "values": ["블랙"]}]})}
    with patch("src.seller_console.views._get_owned_item", return_value=item):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
            r = c.post("/seller/collect/preview/x/ai-description",
                       data=json.dumps({"title": "접이식 책상", "category": "HOM", "keywords": "차량용,접이식"}),
                       content_type="application/json")
            d = r.get_json()
            assert d["ok"] and d["provider"] == "stub" and d["is_draft"] is True
            assert "- k: v" not in d["text"] and "차량용" in d["text"] and "블랙" in d["text"]
