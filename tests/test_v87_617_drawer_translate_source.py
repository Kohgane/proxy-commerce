"""tests/test_v87_617_drawer_translate_source.py — 백로그 #617: 드로어 개별 [한국어로 번역] 원문 소스.

W11 item①은 재번역 **제목** 소스를 원본(title_en/title)으로 고쳤으나, **상세** 소스는
`extra.description or extra.description_ko`라 원본이 없으면 표시 번역본(description_ko, 한글)을
소스로 써 한글→한글 재번역(상용구 잔존·왜곡)이 됐다. 드로어 개별 [한국어로 번역] 버튼은
같은 `/seller/collect/bulk-translate` 엔드포인트를 단일 item_ids로 호출한다(collect_preview.html).

수리: 재번역 상세 소스도 **원본**(description)만 — description_ko는 소스에서 제외. 원본이 없으면
빈값(→ 기존 description_ko 보존, 빈값 클로버 금지).

계약: ① 소스에서 description_ko 제외(원본만) ② 실측 — 원본 있으면 원본에서 번역, 원본 없으면
표시 번역본을 소스로 보내지 않고 기존 번역본 보존 ③ 드로어 버튼이 같은 엔드포인트 사용.
"""
from __future__ import annotations

import json
from pathlib import Path

VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
DRAWER = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


def test_source_contract_excludes_translated_desc():
    # 상세 재번역 소스 = 원본(description)만. description_ko를 소스로 쓰지 않는다.
    assert 'desc = (extra.get("description") or "").strip()' in VIEWS
    assert 'desc = extra.get("description") or extra.get("description_ko")' not in VIEWS
    # 원본 없을 때 기존 번역본 보존(빈값 클로버 금지) 가드.
    assert 'if desc:\n                extra["description_ko"] = desc_ko' in VIEWS


def test_drawer_button_uses_bulk_translate_endpoint():
    # 드로어 개별 [한국어로 번역]이 같은 서버 경로를 단일 item_ids로 호출(원문 소스 로직 공유).
    assert "한국어로 번역" in DRAWER
    assert "/seller/collect/bulk-translate" in DRAWER
    assert "item_ids: [_ITEM_ID]" in DRAWER


def _setup(monkeypatch, extra, translator):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    import src.seller_console.views as V
    from src.seller_console import collect_history_store as ch
    ch._in_memory.clear()
    monkeypatch.setattr(V, "_seller_identities", lambda: {"u1"})
    monkeypatch.setattr(V, "_seller_id", lambda: "u1")
    import src.seller_console.ai.translator as _tr
    monkeypatch.setattr(_tr, "AITranslator", lambda: translator)
    iid = ch.append(source="extension", url="https://item.rakuten.co.jp/x/9/",
                    title="표시본(이미 번역)", price="1706", currency="JPY", seller_id="u1", extra=extra)
    return V, ch, iid


class _Spy:
    def __init__(self):
        self.seen = {}
    def translate_product(self, s):
        self.seen["title"] = s.get("title")
        self.seen["description"] = s.get("description")
        return {"title_ko": "제목KO", "description_ko": ("상세KO" if s.get("description") else ""),
                "provider": "papago", "attempts": [], "detected_lang": "ja"}
    def translate_options(self, o):
        return {"options": o, "provider": "none", "translated": False}


def test_retranslate_desc_uses_original_not_display(monkeypatch):
    t = _Spy()
    V, ch, iid = _setup(monkeypatch, {"title": "元", "title_en": "元",
                                      "description": "元の説明ＪＰ", "description_ko": "옛번역한글"}, t)
    from src.order_webhook import app
    with app.test_client() as c:
        c.post("/seller/collect/bulk-translate", json={"item_ids": [iid]})
    # 상세 소스 = 원본(表示 번역본 아님).
    assert t.seen["description"] == "元の説明ＪＰ"
    assert t.seen["description"] != "옛번역한글"
    ex = json.loads(ch.get(iid, seller_ids={"u1"}).get("extra_json") or "{}")
    assert ex["description_ko"] == "상세KO"          # 원본에서 새로 번역


def test_retranslate_without_original_preserves_ko(monkeypatch):
    """원본 상세가 없으면: 표시 번역본을 소스로 보내지 않고, 기존 description_ko를 보존(빈값 클로버 금지)."""
    t = _Spy()
    V, ch, iid = _setup(monkeypatch, {"title": "元", "title_en": "元",
                                      "description_ko": "보존되어야할한글설명"}, t)
    from src.order_webhook import app
    with app.test_client() as c:
        c.post("/seller/collect/bulk-translate", json={"item_ids": [iid]})
    # 소스로 한글 번역본을 보내지 않았다(빈 상세 → 한글→한글 재번역 방지).
    assert not t.seen["description"]
    # 기존 번역본 보존(빈값으로 덮어쓰지 않음).
    ex = json.loads(ch.get(iid, seller_ids={"u1"}).get("extra_json") or "{}")
    assert ex["description_ko"] == "보존되어야할한글설명"
