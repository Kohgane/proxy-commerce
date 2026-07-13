"""tests/test_v62_keyword_server.py — v62 STEP4: 키워드 서버 생성(클라 추출 폐지).

저장 시 서버가 생성: 제목 핵심 명사구·카테고리·옵션명·상세 빈출어 + 오염어('Chat history'류)·불용어 필터.
드로어 키워드 탭에 태그칩 렌더(편집 가능). 확장 수집 payload에서 서버가 keywords 채움.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
os.environ.setdefault("ADAPTER_DRY_RUN", "1")


def test_generate_keywords_priority_and_clean():
    from src.seller_console.keyword_gen import generate_keywords
    kw = generate_keywords(
        title="andobil [2026 Ultra-Thin] Magnetic Phone Grip Ring Holder Chat history",
        category="DIG", brand="andobil",
        options=[{"name": "색상", "values": ["블랙"]}, {"name": "사이즈", "values": ["S"]}],
        desc_text="MagSafe 그립 그립 폰그립 거치대 거치대 스탠드 스탠드 고가수집기")
    assert "andobil" in kw                                    # 브랜드 최우선
    assert "Magnetic" in kw and "Grip" in kw                  # 제목 명사구
    assert "그립" in kw or "거치대" in kw                     # 상세 빈출어(2회+)
    # 오염어 0 (Chat/history/고가수집기 필터)
    lows = [k.lower() for k in kw]
    assert "chat" not in lows and "history" not in lows
    assert not any("고가수집" in k for k in kw)
    assert 4 <= len(kw) <= 15


def test_generate_keywords_no_marketing_stopwords():
    from src.seller_console.keyword_gen import generate_keywords
    kw = generate_keywords(title="best premium 무료 배송 특가 가방", category="BAG")
    lows = [k.lower() for k in kw]
    for bad in ("best", "premium", "무료", "배송", "특가"):
        assert bad not in lows, f"불용어 미필터: {bad}"


def test_refine_keywords_noop_without_key(monkeypatch):
    from src.seller_console.keyword_gen import refine_keywords
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = ["andobil", "그립"]
    assert refine_keywords("andobil 폰그립", base) == base     # 키 없으면 그대로(가짜 생성 0)


def test_extension_collect_stores_server_keywords():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try:
        ch._in_memory.clear()
    except Exception:
        pass
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://www.amazon.com/dp/B0X",
                                        "title": "andobil Magnetic Phone Grip Chat history",
                                        "price": "12.99", "currency": "USD",
                                        "images": ["https://m/i.jpg"],
                                        "brand": "andobil",
                                        "options": [{"name": "색상", "values": ["블랙"]}]}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            it = ch.get(r.get_json()["item_id"], seller_ids={"u1"})
            ex = json.loads(it["extra_json"])
    kw = ex.get("keywords") or []
    assert kw, "서버 생성 키워드 없음"
    assert "andobil" in kw
    lows = [k.lower() for k in kw]
    assert "chat" not in lows and "history" not in lows      # 오염어 0


def test_drawer_renders_keyword_chips():
    tpl = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert 'data-etab="keywords"' in tpl and "keywordChips" in tpl
    assert "_EXTRA.keywords" in tpl                            # 서버 생성 키워드 렌더
