"""오너 지시 2026-10-27 22:20 ⑤ — 허가 품목은 차단 유지(「그렇게 하고」) · 차단 문구에 근거 법령 한 줄."""


def test_drug_block_stays_and_names_the_law():
    from src.services import risk_gate as R
    sc = R.scan({"title_ko": "가정용 의료기기 저주파 마사지기"})
    h = next(x for x in sc["hits"] if x["key"] == "cert:drug")
    assert h["grade"] == "block" and h["can_allow"] is False                    # 「그래도 등록」 없음
    assert "약사법 제44조" in h["why"] and "의료기기법 제17조" in h["why"]
    line = next(x for x in R.holds(sc) if x["code"] == "risk_block")
    assert "약사법 제44조" in line["line"]                                       # 보류 사유 줄(사전검증·등록 409)에도
