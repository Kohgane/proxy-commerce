"""Y14 R2 — 쿠팡 예측이 「도서」인데 상품명에 책 낱말이 없으면 버린다(네이버 다리·쿠팡 등록 둘 다).

실측(10-20 17:00 UTC 재사전검증): 리브러쉬 무알콜 과즙 구강스프레이 → 쿠팡 예측 52046 「도서>국내도서>건강 취미>건강에세이/건강기타」
→ 네이버 후보 3개가 전부 도서 리프 → AI가 그중 「도서>건강/취미>건강>건강정보/이야기」를 골라 **통과**.
그리고 네이버 쪽 쿠팡 예측 입력(`_predict_input`)은 증정 문구를 안 걷어서 쿠팡 등록(`category_for`)과 재료가 달랐다.
"""
from src.uploaders import naver_categories as N

_LIB = "리브러쉬 무알콜 과즙 구강스프레이 더블기획 15ml 3종 택1 (과일키링 증정) 올리브영"


def test_book_guess_needs_a_book_word():
    path = "도서>국내도서>건강 취미>건강에세이/건강기타"
    assert N.is_book_guess(path, "건강에세이/건강기타", _LIB)
    assert not N.is_book_guess(path, "", "약사가 쓴 구강 건강 에세이 단행본")
    assert not N.is_book_guess(path, "", "어린이 그림책 세트")
    assert not N.is_book_guess("뷰티>구강용품>구강스프레이", "", _LIB)
    # 경로를 모르면 리프 이름에 「도서」가 든 경우만
    assert N.is_book_guess("", "도서 기타", _LIB) and not N.is_book_guess("", "구강스프레이", _LIB)


def test_naver_bridge_drops_book_prediction(monkeypatch):
    import src.channel_sync.coupang_uploader as CU
    import src.uploaders.coupang_categories as CC
    asked = []

    class _Up:
        access_key = secret_key = "k"

        def predict(self, name, desc):
            asked.append(name)
            return {"id": "52046", "name": "건강에세이/건강기타"}
    monkeypatch.setattr(CU, "make_uploader", lambda *a, **k: (_Up(), "gogane"))
    monkeypatch.setattr(CC, "path_of", lambda cid: "도서>국내도서>건강 취미>건강에세이/건강기타")
    g = N.coupang_guess({"title_ko": _LIB})
    assert g["id"] == "" and "책 낱말이 없어" in g["why"]
    # 쿠팡에 묻는 이름엔 증정 묶음이 없다(쿠팡 등록과 같은 재료)
    assert asked and "증정" not in asked[0] and "구강스프레이" in asked[0]


def test_coupang_register_drops_book_prediction(monkeypatch):
    from src.uploaders.coupang_uploader import CoupangUploader
    import src.uploaders.coupang_categories as CC
    up = CoupangUploader.__new__(CoupangUploader)
    up._predict_cache = {}

    def _predict(name, desc=""):
        up._predict_cache[(name.strip(), "")] = {"id": "52046", "name": "건강에세이/건강기타"}
        return {"id": "52046", "name": "건강에세이/건강기타"}
    monkeypatch.setattr(up, "predict", _predict, raising=False)
    monkeypatch.setattr(CC, "path_of", lambda cid: "도서>국내도서>건강 취미>건강에세이/건강기타")
    cid, src, why = up.category_for({"title": _LIB})
    assert cid == "" and src == "" and "책 낱말" in why
    # 진짜 책이면 예측 그대로
    cid, src, _ = up.category_for({"title": "약사가 쓴 구강 건강 에세이"})
    assert (cid, src) == ("52046", "predict")
