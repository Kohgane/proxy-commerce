"""Y14-4(10-20 2호 후보 사전검증) — 리브러쉬 구강스프레이가 네이버 「패션잡화>패션소품>키링」으로 통과했다.
상품명 「… 3종 택1 (과일키링 증정) 올리브영」의 증정품 낱말이 상품명 사전에 잡혔다 → 카테고리 재료에서만 증정 묶음을 뺀다."""
from src.uploaders import naver_categories as NC

T = "리브러쉬 무알콜 과즙 구강스프레이 더블기획 15ml 3종 택1 (과일키링 증정) 올리브영"


def test_strip_gift_keeps_real_product_words():
    assert "키링" not in NC.strip_gift(T) and "구강스프레이" in NC.strip_gift(T)
    assert NC.strip_gift("곰돌이 키링") == "곰돌이 키링"                    # 키링이 상품이면 그대로
    assert NC.strip_gift("키링 세트 (사은품 증정)") == "키링 세트"
    assert NC.strip_gift("텀블러 + 빨대 증정 500ml") == "텀블러 + 500ml"


def test_pick_does_not_take_keyring_from_freebie(monkeypatch):
    monkeypatch.setattr(NC, "learned", lambda scope, title: "")
    monkeypatch.setattr(NC, "suggest", lambda p: {})
    assert NC.pick({"title": T})[0] != "50000570"
    assert NC.pick({"title": "곰돌이 아크릴 키링"})[0] == "50000570"


def test_coupang_prediction_input_drops_freebie():
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader.__new__(CoupangUploader)
    seen = []
    up.predict_category = lambda title, description="": seen.append(title) or "1"
    up.category_for({"title": T})
    assert "키링" not in seen[0] and "구강스프레이" in seen[0]
