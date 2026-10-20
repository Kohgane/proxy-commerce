"""Y13-F W1(오너 2026-10-19) — 피샹리(회전 라운지 1인 소파)가 「소파>빈백」으로 올라갔다.

뿌리: 치환표가 懒人沙发(게으른 사람 소파 = 1인 휴식 소파의 통칭)를 「빈백 소파」로 바꿨고, 상품명의 「빈백」이 쿠팡 예측을
빈백 리프(77916)로 끌었다. 빈백은 **豆袋 · 懒人豆袋**(콩주머니)일 때만.
"""
from src.collectors import ko_polish as kp


def setup_function(_):
    kp.reset_cache()


def test_lazy_sofa_alone_is_one_seat_sofa():
    out = kp.preclean_cn("菲尚丽家用懒人沙发椅")
    assert "1인용 소파" in out and "빈백" not in out


def test_bean_bag_words_still_bean_bag():
    assert "빈백" in kp.preclean_cn("懒人豆袋沙发")
    assert "빈백" in kp.preclean_cn("豆袋懒人椅")


def test_literal_korean_lazy_sofa_is_one_seat():
    out = kp.polish_ko("게으른 사람 소파 의자 거실")
    assert "1인용 소파" in out and "빈백" not in out
