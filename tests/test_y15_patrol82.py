"""Y15 순찰 82(오너 2026-10-24) — 사전검증 네이버 옵션 검사에 「금지 문자」 항목이 없었다(df0f8a8c 통과 → 등록 400 쉼표).

- 금지 문자 표 `naver_options.FORBIDDEN_CHARS` — **실측만**(커머스API 문서엔 옵션값 금지 문자 목록이 없다).
- 사전검증 카드에 한 줄(보류 아님 — 보낼 땐 빈칸으로 바꿔 보낸다).
- 400 문구 「…항목에 X는 사용하실 수 없습니다」 → 그 문자를 이름 붙여 보이고, 표에 없으면 「새 금지 문자」.
"""
from tests.test_y15_patrol80 import _DF_KO, _DF_SRC

_MSG = "1번째 옵션의 옵션값 항목에 콤마(,)는 사용하실 수 없습니다."


def _product():
    return {"options": [{"name": "颜色分类", "values": _DF_SRC, "name_ko": "색상", "values_ko": _DF_KO}],
            "skus": [{"sku_id": str(i), "spec": [v], "stock": 5, "sell_price_krw": 883790} for i, v in enumerate(_DF_SRC)],
            "options_translated": True,
            "option_value_overrides": {_DF_SRC[0]: "성운백, 설화융 [방수 및 오염 방지]"}}


def test_table_is_measured_only_and_cleaner_uses_it():
    from src.uploaders import naver_options as N
    assert set(N.FORBIDDEN_CHARS) == {",", "，"}                     # 문서 목록 없음 — 지어낸 문자 0
    assert all(v[1] for v in N.FORBIDDEN_CHARS.values())             # 근거 칸 필수
    assert N.clean_value("성운백, 설화융") == "성운백 설화융"


def test_forbidden_found_lists_the_two_values_naver_rejected():
    from src.uploaders.naver_options import forbidden_found
    got = forbidden_found(_product())
    assert [g["before"] for g in got] == ["성운백, 설화융 [방수 및 오염 방지]", "다크 그레이, 스노우 벨벳 / 분리 세탁"]
    assert got[0]["after"] == "성운백 설화융 [방수 및 오염 방지]" and got[0]["chars"] == [","]


def test_prevalidate_card_shows_the_line_without_holding(monkeypatch):
    from src.seller_console.upload_dispatcher import PrevalidationResult, UploadDispatcher
    monkeypatch.setattr(UploadDispatcher, "_prevalidate_market",
                        lambda self, pd, base: PrevalidationResult(market=base, ok=True, message=""))
    out = UploadDispatcher().prevalidate(_product(), ["smartstore", "coupang"])
    rs = {r.market: r for r in (out if isinstance(out, list) else out.values())}
    det = " ".join(rs["smartstore"].details or [])
    assert "네이버 옵션값 금지 문자(,) 2개" in det and "「성운백 설화융 [방수 및 오염 방지]」" in det
    assert rs["smartstore"].ok is True                                # 보류 아님 — 보낼 땐 바꿔 보낸다
    assert "금지 문자" not in " ".join(rs["coupang"].details or [])   # 쿠팡은 같은 값을 받았다


def test_400_message_names_the_char_and_flags_new_ones():
    from src.uploaders.naver_invalid import row
    known = row("originProduct.detailAttribute.optionInfo.optionCombinations[0].optionName1", _MSG)
    assert "「,」" in known["line"] and "빈칸으로 바꿔" in known["line"]
    new = row("originProduct.detailAttribute.optionInfo.optionCombinations[1].optionName1",
              "2번째 옵션의 옵션값 항목에 세미콜론(;)는 사용하실 수 없습니다.")
    assert "「;」" in new["line"] and "새 금지 문자" in new["line"]
    plain = row("originProduct.salePrice", "최소 10원")
    assert plain["line"] == "originProduct.salePrice — 값 확인(최소 10원)"
