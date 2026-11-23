"""ISBN1123 — 영어 상품명이 외국도서 리프(ISBN 필수, 경로가 「도서」로 안 잡힘)로 예측되면 쿠팡 등록이 그 카테고리를 쓰지 않는다."""
from src.uploaders.coupang_uploader import CoupangUploader

ISBN_META = {'attributes': [{'attributeTypeName': 'ISBN', 'required': 'MANDATORY'}]}
OK_META = {'attributes': [{'attributeTypeName': '색상', 'required': 'OPTIONAL'}]}


def _up(monkeypatch, pred, metas):
    up = CoupangUploader.__new__(CoupangUploader)
    up._predict_cache = {}
    monkeypatch.setattr(up, 'predict_category', lambda name, desc='': pred.get(name, ''), raising=False)
    monkeypatch.setattr(up, 'get_category_meta', lambda code: metas.get(str(code), {}), raising=False)
    return up


def test_isbn_leaf_rejected_and_korean_name_retried(monkeypatch):
    up = _up(monkeypatch, {'Garrett Leight DOTTIE SUN': '95348', '개럿 라이트 도티 선글라스': '69900'},
             {'95348': ISBN_META, '69900': OK_META})
    assert up.category_for({'title': 'Garrett Leight DOTTIE SUN', 'title_ko': '개럿 라이트 도티 선글라스'}) == ('69900', 'predict', '')


def test_isbn_leaf_without_alternative_is_not_used(monkeypatch):
    up = _up(monkeypatch, {'Boy Smells COCO CREAM': '98839'}, {'98839': ISBN_META})
    cid, src, why = up.category_for({'title': 'Boy Smells COCO CREAM', 'category_id': '98839'})
    assert cid == '' and src == '' and 'ISBN' in why


def test_real_book_keeps_isbn_leaf(monkeypatch):
    up = _up(monkeypatch, {'Kinfolk 매거진 Issue 50': '98839'}, {'98839': ISBN_META})
    assert up.category_for({'title': 'Kinfolk 매거진 Issue 50'})[0] == '98839'


def test_meta_failure_does_not_block(monkeypatch):
    up = _up(monkeypatch, {'Seletti Mug': '80530'}, {})
    assert up.category_for({'title': 'Seletti Mug'}) == ('80530', 'predict', '')
