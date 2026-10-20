"""Y14 라운드 2 — 국내 쇼핑몰 배송·교환·적립 안내가 상세설명으로 들어오면 「비어 있음」(AI 초안으로 채움).

실측(10-20 사전검증): 리브러쉬 구강스프레이(올리브영) 상세 386자 = 배송비·도서산간·교환·반품·증정·등급 적립률 17줄,
상품 문장 0 → 네이버 사전검증 **통과** — 그대로 나갔으면 상품 상세가 올리브영 배송 정책이었다.
UI 판정(`detail_ui_junk.judge`)은 타오바오 가게 카드(5줄 이하·평점·발송 토큰)만 봤다.
"""
from pathlib import Path

from src.uploaders import detail_ui_junk as J

_OLIVE = (Path(__file__).parent / "fixtures" / "y14_oliveyoung_desc.txt").read_text(encoding="utf-8")


def test_oliveyoung_policy_block_is_empty_body():
    r = J.policy_judge(_OLIVE)
    assert r["junk"] and len(r["policy"]) == len(r["lines"]) == 17
    assert J.is_junk(_OLIVE)
    # 마켓 본문 정리(등록·사전검증 같은 함수)도 빈칸 → 상세 자동 초안
    from src.seller_console.upload_dispatcher import market_description
    assert market_description(_OLIVE) == ""


def test_card_line_says_shop_policy_not_shop_rating():
    line = J.note({"description": _OLIVE})
    assert "쇼핑몰 배송·교환·적립 안내" in line and "평점" not in line
    # 타오바오 가게 카드는 예전 문구 그대로
    assert "가게 이름·평점·발송·만족도" in J.note({"description": "沉默流浪汉\n4.5\n好评率84%\n平均2天内发货"})


def test_real_description_with_a_few_policy_lines_stays():
    real = ("천연 과즙 추출물로 만든 무알콜 구강 스프레이입니다.\n15ml 휴대용 사이즈로 언제 어디서나 사용할 수 있어요.\n"
            "· 배송비: 3,000원\n· 교환: 수령 후 7일 이내\n· 반품 (단순변심) 왕복 6,000원")
    assert not J.policy_judge(real)["junk"] and not J.is_junk(real)


def test_our_own_delivery_section_is_not_counted():
    """우리 고정 줄(「■ 배송·구매대행 안내」 아래 「교환·반품은…」)이 안내 줄로 세어져 초안이 쓰레기로 읽히면 안 된다."""
    from src.seller_console.ai.translator import _structured_draft
    stub = _structured_draft("무알콜 구강스프레이 15ml", "BTY", ["구강"], [], [], "")
    assert "■ 배송·구매대행 안내" in stub
    assert not J.is_junk(stub)
