"""F33 계약 — 텐센트가 어디까지인지 **숫자로** 남긴다.

## 축 다섯 (오너 PC 서랍 실측 2026-09-18 대조표)

  A 브랜드 보존 · B 관용 표현 · C 박스 맞춤 · D 영문 UI 보존 · E 타이포 일치

A·B·D는 `TransDetails`의 `SourceLineText`/`TargetLineText`로 **자동**,
C·E는 **사람이 장별 0/1**.

## 반례에 대한 답 — C는 왜 자동화하지 않는가

SDK 모델을 읽어 보니 `TransDetail`엔 `BoundingBox(X·Y·Width·Height)`·`LineHeight`·
`LinesCount`가 **실제로 있다**(`tencentcloud.tmt.v20180321.models` 원문 — 추측 아님).
반례가 말한 조건은 충족된다.

**그런데도 안 한다.** 그 박스의 주석은 「段落文本框位置」 = **원문 문단의 자리**다.
번역문이 **그려진** 자리가 아니다. 그걸로 「배경 도형 밖으로 넘쳤나」를 판정하면
재지 않은 것을 잰 척하는 것이다.

> ★ **있는 필드로 계산할 수 있는 것과, 그 필드가 뜻하는 것은 다르다.**

대신 참고 수치(박스 폭·길이비)로 올리고, 화면이 **「참고」라고 이름 붙인다.**

## 사람이 받는 것

5장 × 5축 × 2모드 = **50칸**이 채워지거나, 그 칸에 **「측정 불가」와 사유**가 적힌다.
빈칸은 없다.

**라이브 호출 0** — 공급사에 한 번도 안 나간다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
TITLE = "SPORTLINK 수행방패 3in1 다기능"


def _lines(*pairs, box=None):
    return [{"source": s, "target": t, "box": box or {"x": 1, "y": 2, "w": 300, "h": 40},
             "line_height": 20, "lines_count": 1} for s, t in pairs]


# ---------------------------------------------------------------------------
# ① 브랜드 사전 — 상품명에서 뽑는다(손으로 적지 않는다)
# ---------------------------------------------------------------------------

def test_brand_tokens_come_from_the_title():
    from src.services.image_bench_axes import brand_tokens
    assert "SPORTLINK" in brand_tokens(TITLE)


def test_units_and_common_abbreviations_are_not_brands():
    """`XL`·`USB`·`LED`를 브랜드로 보면 없는 실패가 쏟아진다."""
    from src.services.image_bench_axes import brand_tokens
    got = brand_tokens("USB LED XL 3D 케이스 ACME")
    assert "ACME" in got
    for junk in ("USB", "LED", "XL", "3D"):
        assert junk not in got


# ---------------------------------------------------------------------------
# ② A 브랜드 보존
# ---------------------------------------------------------------------------

def test_brand_kept_scores_one():
    from src.services.image_bench_axes import judge_brand
    out = judge_brand(_lines(("SPORTLINK 运动", "SPORTLINK 스포츠")), ["SPORTLINK"])
    assert out["score"] == 1


def test_brand_translated_scores_zero():
    """★ 로고가 번역되면 0 — 오너 대조표의 그 자리."""
    from src.services.image_bench_axes import judge_brand
    out = judge_brand(_lines(("SPORTLINK 运动", "스포츠링크 스포츠")), ["SPORTLINK"])
    assert out["score"] == 0
    assert "SPORTLINK" in out["reason"]


def test_a_page_without_the_brand_is_not_scored():
    """브랜드가 안 나온 장을 1로 세면 **없는 성공**을 만든다."""
    from src.services.image_bench_axes import judge_brand
    out = judge_brand(_lines(("防水", "방수")), ["SPORTLINK"])
    assert out["score"] is None
    assert "브랜드가 나오지 않" in out["reason"]


# ---------------------------------------------------------------------------
# ③ B 관용 표현 — 표에 있는 것만
# ---------------------------------------------------------------------------

def test_idiom_translated_well_scores_one():
    from src.services.image_bench_axes import judge_idiom
    assert judge_idiom(_lines(("三合一 设计", "3-in-1 디자인")))["score"] == 1


def test_a_literal_translation_scores_zero():
    """★ `삼합일` — 오너가 실제로 본 직역."""
    from src.services.image_bench_axes import judge_idiom
    out = judge_idiom(_lines(("三合一 设计", "삼합일 디자인")))
    assert out["score"] == 0 and "직역" in out["reason"]


def test_an_unknown_form_is_unmeasured_not_zero():
    """★★ 표에 없는 형태를 0으로 찍으면 **없는 실패**를 만든다 — 원문을 올려 표를 늘린다."""
    from src.services.image_bench_axes import judge_idiom
    out = judge_idiom(_lines(("三合一 设计", "세 가지 기능 디자인")))
    assert out["score"] is None
    assert "표를 늘려" in out["reason"]
    assert out["hits"][0]["target"] == "세 가지 기능 디자인"


def test_a_page_without_any_known_idiom_is_unmeasured():
    from src.services.image_bench_axes import judge_idiom
    assert judge_idiom(_lines(("防水", "방수")))["score"] is None


def test_the_idiom_table_only_holds_measured_entries():
    """실측된 것만 — 표를 상상으로 채우면 그때부터 채점이 소설이다.

    오너가 실측으로 준 원문만 들어간다. **목록을 못박지 않는다** — 그러면 표를 늘리는
    것 자체가 계약 위반이 되고, 이 표는 늘어나라고 있는 것이다. 대신 **형태**를 잰다.
    """
    from src.services.image_bench_axes import IDIOMS
    assert IDIOMS[0]["source"] == "三合一"           # 최초 실측(2026-09-18)
    for i in IDIOMS:
        assert i["source"] and i["good"], i
        assert "note" in i and i["note"], i           # 어디서 왔는지 없으면 실측이 아니다
        assert isinstance(i["bad"], tuple), i


def test_a_correct_line_is_never_marked_wrong_by_an_empty_bad_list():
    """★★ `bad`를 비워 둔 것은 **발명을 피한 것**이다(D3-4 ④).

    오너는 「오역이었다」고 알려 줬지 틀린 문장을 주지 않았다. 지어 넣으면 그 문장이
    안 나오는 **다른 오역**을 정답으로 통과시킨다. 그래서 정본이면 1, 아니면 **측정 불가**다.
    """
    from src.services.image_bench_axes import judge_idiom

    assert judge_idiom(_lines(("一放秒充", "올려놓기만 하면 충전")))["score"] == 1
    assert judge_idiom(_lines(("一放秒充", "한 번 놓으면 초충전입니다")))["score"] is None


# ---------------------------------------------------------------------------
# ④ D 영문 UI 보존
# ---------------------------------------------------------------------------

def test_english_ui_left_alone_scores_one():
    from src.services.image_bench_axes import judge_en_ui
    out = judge_en_ui(_lines(("Monday 1", "Monday 1"), ("Alarm 6:45AM", "Alarm 6:45AM")))
    assert out["score"] == 1


def test_touching_english_ui_scores_zero():
    """★ `Monday 1` → `월요일 1`이면 0."""
    from src.services.image_bench_axes import judge_en_ui
    out = judge_en_ui(_lines(("Monday 1", "월요일 1")))
    assert out["score"] == 0 and "Monday 1" in out["reason"]


def test_a_chinese_line_is_not_an_english_ui_line():
    from src.services.image_bench_axes import judge_en_ui
    assert judge_en_ui(_lines(("防水设计", "방수 설계")))["score"] is None


# ---------------------------------------------------------------------------
# ⑤ C·E — 사람 몫이고, 박스는 참고다
# ---------------------------------------------------------------------------

def test_c_and_e_are_human_axes():
    """D3-5 ② — F(배경 복원)가 **자동** 축으로 붙었다. 사람은 여전히 C·E만 찍는다."""
    from src.services.image_bench_axes import AUTO_AXES, HUMAN_AXES
    assert set(HUMAN_AXES) == {"C", "E"}
    assert set(AUTO_AXES) == {"A", "B", "D", "F"}


def test_box_data_is_offered_as_a_hint_not_a_score():
    """★★ **반례에 대한 답** — 박스는 원문 문단의 자리라 점수가 아니다."""
    from src.services import image_bench_axes as A
    hints = A.box_hints(_lines(("三合一 设计", "삼합일 디자인 어쩌고")))
    assert hints[0]["box_w"] == 300 and hints[0]["len_ratio"] > 1
    # 자동 축에 C가 없다 — 있으면 재지 않은 것을 잰 척하는 것이다.
    assert "C" not in A.auto_scores(_lines(("a", "b")), ["X"])


def test_the_screen_calls_the_box_a_hint():
    tpl = (ROOT / "src/seller_console/templates/image_translate_bench.html").read_text(
        encoding="utf-8")
    assert "박스(참고)" in tpl
    assert "번역문이 그려진 자리가 아니" in tpl


def test_the_sdk_really_has_those_fields():
    """필드 이름은 **실측 후에만** — SDK 모델에서 직접 확인한다(추측 금지)."""
    pytest.importorskip("tencentcloud.tmt.v20180321.models")
    import inspect
    import re
    from tencentcloud.tmt.v20180321 import models as M
    detail = re.findall(r"self\._(\w+) = None", inspect.getsource(M.TransDetail.__init__))
    for f in ("SourceLineText", "TargetLineText", "BoundingBox", "LineHeight", "LinesCount"):
        assert f in detail, f
    box = re.findall(r"self\._(\w+) = None", inspect.getsource(M.BoundingBox.__init__))
    assert box == ["X", "Y", "Width", "Height"], box


# ---------------------------------------------------------------------------
# ⑥ 표 — 빈칸이 없다
# ---------------------------------------------------------------------------

def _page(idx, lines):
    from src.services import image_bench_axes as A
    return {"idx": idx, "axes": A.auto_scores(lines, ["SPORTLINK"])}


def test_every_cell_is_either_a_score_or_a_reason():
    """★ 사람이 받는 것 — 장×축 칸이 **채워지거나 사유가 적힌다**. 빈칸 0.

    ※ 축 수를 박지 않는다 — D3-5에서 F가 붙어 5→6축이 됐다. 축은 `AXES`가 정본이다.
    """
    from src.services import image_bench_axes as A
    import src.seller_console.views as V
    results = [{"idx": i, "kind": "상품", "original": f"https://o/{i}.jpg",
                "url": f"/x/{i}", "status": "done", "ms": 900,
                "lines": _lines(("SPORTLINK 三合一", "SPORTLINK 3-in-1")),
                "axes": A.auto_scores(_lines(("SPORTLINK 三合一", "SPORTLINK 3-in-1")),
                                      ["SPORTLINK"]),
                "box_hints": []} for i in range(5)]
    grid = V._bench_grid({"results": results, "scores": {}, "mode": 0})
    assert len(grid["pages"]) == 5
    assert grid["cells_total"] == 5 * len(A.AXES)
    for p in grid["pages"]:
        for key, _l, _k, _h in A.AXES:
            cell = p["axes"][key]
            assert cell.get("score") in (0, 1) or cell.get("reason"), (p["idx"], key)


def test_human_cells_show_up_once_scored():
    import src.seller_console.views as V
    results = [{"idx": 0, "lines": [], "axes": {}, "box_hints": []}]
    grid = V._bench_grid({"results": results, "scores": {"cells": {"0:C": 1, "0:E": 0}},
                          "mode": 1})
    assert grid["pages"][0]["axes"]["C"]["score"] == 1
    assert grid["pages"][0]["axes"]["E"]["score"] == 0
    assert grid["mode"] == 1


def test_unmeasured_is_not_counted_as_zero():
    """★ 분모는 **잰 것만**이다 — 「측정 불가」를 0으로 세면 공급사를 없는 실패로 깎는다."""
    from src.services.image_bench_axes import summarize
    pages = [{"axes": {"A": {"score": 1}, "B": {"score": None}, "C": {"score": None},
                       "D": {"score": 0}, "E": {"score": None}}}]
    out = summarize(pages)
    assert out["A"] == {"ones": 1, "scored": 1, "unmeasured": 0}
    assert out["B"] == {"ones": 0, "scored": 0, "unmeasured": 1}
    assert out["D"] == {"ones": 0, "scored": 1, "unmeasured": 0}


# ---------------------------------------------------------------------------
# ⑦ 두 모드 — 같은 장을 두 번, 섞지 않는다
# ---------------------------------------------------------------------------

def test_mode_reaches_the_vendor_call():
    """★ Mode 0/1이 **실제 호출까지** 간다 — 화면에만 있으면 표가 거짓이 된다."""
    from src.services import image_translate_bench as bench
    seen = []
    bench.reset_for_tests()

    def _fake(url="", data=b"", mode=0, timeout_sec=None):
        seen.append(mode)
        return {"ok": True, "image_b64": "aGk=", "lines": [], "ms": 10, "vendor": "tencent",
                "target_text": "x"}

    fixtures = [{"item_no": "617129397971", "item_id": "i1", "title": TITLE,
                 "images": [{"url": "https://o/0.jpg", "kind": "상품"}]}]
    with patch("src.services.image_translate_tencent.translate_image", _fake), \
         patch("src.services.image_translate_store.store_translated",
               return_value={"url": "/x/0", "stored_by": "db", "bytes": 3, "note": ""}), \
         patch("src.db.image_translate_usage_pg.save_run", return_value=True), \
         patch("src.services.image_translate_store.record_usage", return_value=None):
        bench.start("run-lite", "u1", fixtures, mode=1, title=TITLE)
        for _ in range(200):
            if not bench.is_running():
                break
            import time
            time.sleep(0.01)
    assert seen == [1], seen
    bench.reset_for_tests()


def test_the_run_route_refuses_to_mix_modes_in_one_run():
    """한 실행은 한 모드다 — 섞으면 초당 한도도 표도 무너진다."""
    src = (ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
    import re
    fn = re.search(r"def image_translate_bench_run\(\):.*?\n(?=\n@bp\.)", src, re.S)
    assert fn
    body = "\n".join(l for l in fn.group(0).splitlines() if not l.strip().startswith("#"))
    assert 'mode = 1 if str(data.get("mode") or "0").strip() == "1" else 0' in body
    assert "bench.start(run_id, _seller_id(), rows, mode=mode" in body


def test_the_run_id_carries_the_mode():
    """실행 이름표에 모드가 들어간다 — 두 실행을 나중에 헷갈리지 않게.

    ※ 소스의 포맷 문자열을 찾던 계약이었는데, **그러면 코드를 조금만 고쳐도 터진다**
      (D3-3b가 접미어를 붙이자 그랬다). 이제 **낸 값**을 잰다.
    """
    from src.seller_console.views import bench_run_id
    assert bench_run_id(0).endswith("-m0")
    assert bench_run_id(1).endswith("-m1")
    # D3-3b: 같은 모드라도 **D3 실행은 이름이 다르다** — 표에서 짝이 갈리지 않게.
    assert bench_run_id(0, True).endswith("-m0-d3")
    assert bench_run_id(0) != bench_run_id(0, True)


# ---------------------------------------------------------------------------
# ⑧ 측정이지 렌더가 아니다
# ---------------------------------------------------------------------------

def test_we_never_redraw_the_vendor_response():
    """★ 이 트랙은 **측정**이다. 응답을 고쳐 그리는 코드가 있으면 안 된다."""
    body = (ROOT / "src/services/image_bench_axes.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    for banned in ("PIL", "Image.", "ImageDraw", "cv2", "inpaint"):
        assert banned not in code, banned


def test_no_live_call_escapes_this_file():
    import ast
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for net in ("requests", "http", "urllib", "socket", "httpx"):
        assert net not in imported, net
