from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_detect_language_basic():
    from src.cs_bot.classifier import detect_language

    assert detect_language("환불 문의") == "ko"
    assert detect_language("refund please") == "en"
    assert detect_language("返金できますか") == "ja"
    assert detect_language("可以退款吗") == "zh"


def test_classify_four_languages_and_priority():
    from src.cs_bot.classifier import classify

    assert classify("환불 가능한가요?")[0] == "refund"
    assert classify("where is my tracking number", "en")[0] == "shipping"
    assert classify("サイズはどうですか", "ja")[0] == "size"
    assert classify("库存还有吗", "zh")[0] == "stock"
    assert classify("안녕하세요")[0] == "general"
    assert classify("배송 48시간 지연됐어요", "ko")[1] == 2
