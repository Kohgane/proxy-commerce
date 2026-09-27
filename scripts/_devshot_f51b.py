"""F51-b 캡처 — 「쿠팡 필수 옵션」 블록, 수행방패 ICE SKU 10개.

★ 번역기 값(values_ko)은 **테스트 입력**(`tests/test_f51_coupang_multi_sku.FAKE_KO`)이다 — 이 샌드박스엔 번역 키가
  없다. 정본 10줄은 브리프에 실려 오지 않아 용어집 옵션 값 섹션은 비어 있다(그래서 전부 「번역기 값 — 확인」).
환율은 `FX_USE_LIVE=0`(오프라인)이라 앱 기본값(고정) — 표에 그대로 적힌다.
사용: python scripts/_devshot_f51b.py <before|after> <out_dir>
"""
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["FX_USE_LIVE"] = "0"
sys.argv = [sys.argv[0], TAG, OUT]
import scripts._devshot_f51 as base  # noqa: E402

FAKE_KO = {
    "三合一充电支架（白色）": "3-in-1 충전 거치대 화이트", "三合一充电支架（黑色）": "3-in-1 충전 거치대 블랙",
    "三合一充电支架（粉色）": "3-in-1 충전 거치대 핑크", "三合一充电支架（蓝色）": "3-in-1 충전 거치대 블루",
    "三合一充电支架（红色）": "3-in-1 충전 거치대 레드",
    "【三合一充电支架】带理线器（黑色）": "3-in-1 거치대+선정리 블랙", "【三合一充电支架】带理线器（白色）": "3-in-1 거치대+선정리 화이트",
    "【三合一充电支架】带理线器（蓝色）": "3-in-1 거치대+선정리 블루", "【三合一充电支架】带理线器（粉色）": "3-in-1 거치대+선정리 핑크",
    "【三合一充电支架】带理线器（红色）": "3-in-1 거치대+선정리 레드",
}
_orig = base._product


def _product():
    p = _orig()
    for o in p["options"]:
        o["values_ko"] = [FAKE_KO.get(v, v) for v in o["values"]]
    p["option_values_ko"] = dict(FAKE_KO)
    return p


base._product = _product
base.OUT = OUT
base.TAG = TAG
_shot = base.main


if __name__ == "__main__":
    import builtins
    _open = builtins.open
    _shot()
    # 파일 이름을 이 트랙 것으로
    import shutil
    shutil.move(f"{OUT}/f51-options-{TAG}.png", f"{OUT}/f51b-options-{TAG}.png")
    print(f"[{TAG}] → {OUT}/f51b-options-{TAG}.png")
