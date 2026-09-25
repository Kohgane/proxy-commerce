"""D3-3b 계약 — 벤치 화면에서 **오너가 버튼으로** D3 렌더를 돌린다.

## 원칙 (오너 2026-09-21, 볼트 규칙으로 승격)

> **외부 키가 필요한 측정은 키가 있는 곳에서 돌린다.** CC 환경으로 키·상품 이미지를 옮기지 않는다.
> 로컬은 **계약(목)까지**, 실측은 **관리자 화면**.

그래서 이 파일엔 **라이브 호출이 0**이다. 텐센트도 LLM도 주입·목으로 갈음하고,
여기서 재는 것은 **배선과 화면**이다. 진짜 그림은 오너가 클릭해서 본다.

## 재는 것

| # | 계약 |
|---|---|
| 1 | 텐센트 호출은 **장당 한 번** — 두 렌더본이 같은 응답을 쓴다(과금이 두 배가 아니다) |
| 2 | D3 결과는 **벤치 저장소(`kind="d3"`)**에만 간다 — gallery/detail을 건드리지 않는다 |
| 3 | 한 장이 실패해도 **행 전체가 죽지 않는다**(사유만 남는다) |
| 4 | **토큰은 못 잰다고 말한다** — 추정치를 적지 않는다 |
| 5 | D3 칸은 **5축 전부 사람이** 찍고, 공급사 점수와 **섞이지 않는다** |
| 6 | 화면에 **세 장이 나란히** 뜬다(실브라우저) |
| 7 | 등록 파이프라인은 여전히 **이 값을 안 본다** |
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "src" / "seller_console" / "templates" / "image_translate_bench.html"

pytest.importorskip("cv2")
pytest.importorskip("PIL.Image")


def _jpeg(w=300, h=120) -> bytes:
    """원문 **글자**가 박힌 한 장.

    ※ 예전엔 검은 사각형을 그렸다. D3-4 ②로 마스크가 **글자 픽셀만** 잡게 된 뒤
      그건 「글자가 아니라 도형」으로 **정확히 거부된다** — 픽스처가 현실과 달랐던 것이다.
    """
    from PIL import Image, ImageDraw
    from src.services.image_render_font import load
    img = Image.new("RGB", (w, h), (238, 234, 226))
    ImageDraw.Draw(img).text((26, 26), "三合一", font=load(28, "bold"), fill=(25, 25, 25))
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


_LINES = [{"source": "三合一 充电器", "target": "三合一",
           "box": {"x": 20, "y": 20, "w": 160, "h": 40}}]


@pytest.fixture
def wired(monkeypatch):
    """텐센트·LLM·저장소를 전부 갈음하고 **호출 수를 센다**."""
    from src.services import image_translate_bench as B

    calls = {"tencent": 0, "llm": 0, "stored": []}

    def _fetch(url):
        return _jpeg(), ""

    monkeypatch.setattr("src.services.image_translate_tencent.fetch_image", _fetch)

    def _store(item_id, idx, b64, *, seller_id="", kind="gallery"):
        calls["stored"].append({"item_id": item_id, "idx": idx, "kind": kind,
                                "bytes": len(base64.b64decode(b64))})
        return {"url": f"/seller/admin/image-translate-bench/image/{item_id}/{idx}",
                "stored_by": "db", "note": ""}

    monkeypatch.setattr("src.services.image_translate_store.store_translated", _store)

    class _T:
        def translate_product(self, src, *, style=""):
            calls["llm"] += 1
            calls.setdefault("styles", []).append(style)
            # 지시를 따를 수 있는 단이 받았다고 **가정하지 않는다** — 목도 사실대로 답한다.
            return {"title_ko": "3-in-1 충전기", "provider": "openai",
                    "style": style, "style_applied": bool(style)}

    monkeypatch.setattr("src.seller_console.ai.translator.AITranslator", _T)
    return B, calls


# ---------------------------------------------------------------------------
# 1·2) 한 번 부르고, 벤치 저장소에만 둔다
# ---------------------------------------------------------------------------

def test_the_d3_render_reuses_the_single_tencent_response(wired):
    """★★★ **장당 과금이 두 배가 되지 않는다.**

    우리는 텐센트를 다시 부르지 않는다 — 이미 받은 `TransDetails`(박스+원문)를 다시 쓴다.
    이 계약은 D3 단계가 **공급사 호출을 하지 않음**을 함수 수준에서 못박는다.
    """
    B, calls = wired
    from tests._ast_probe import calls_in
    got = calls_in(B._run_d3_stage) | calls_in(B._render_d3_for)
    assert "translate_image" not in got, "D3 단계가 공급사를 다시 부른다"


def test_the_result_goes_to_the_bench_store_only(wired):
    """★★ `kind="d3"` — 등록이 보는 gallery/detail에 섞이면 **연결된 것처럼 보인다.**"""
    B, calls = wired
    out = B._run_d3_stage({"item_no": "X1", "item_id": "X1"}, 0,
                          {"url": "https://x.example/a.jpg"},
                          {"lines": _LINES}, "seller-1")
    assert out["ok"] is True, out
    assert calls["stored"] and calls["stored"][0]["kind"] == "d3"
    assert out["url"].startswith("/seller/admin/image-translate-bench/image/")


def test_the_glossary_rules_are_applied(wired):
    """★ 2단계가 실제로 낀다 — 직역(「삼합일」)이 아니라 사전 값이 그려진다."""
    B, calls = wired
    out = B._run_d3_stage({"item_no": "X1"}, 0, {"url": "u"}, {"lines": _LINES}, "s")
    assert calls["llm"] == 1
    assert out["drawn"] >= 1


# ---------------------------------------------------------------------------
# 3) 실패가 행을 죽이지 않는다
# ---------------------------------------------------------------------------

def test_no_lines_is_a_reason_not_a_crash(wired):
    B, _ = wired
    out = B._run_d3_stage({"item_no": "X"}, 0, {"url": "u"}, {"lines": []}, "s")
    assert out["ok"] is False and "줄" in out["error"]


def test_a_download_failure_is_a_reason(wired, monkeypatch):
    B, _ = wired
    monkeypatch.setattr("src.services.image_translate_tencent.fetch_image",
                        lambda url: (b"", "타임아웃"))
    out = B._run_d3_stage({"item_no": "X"}, 0, {"url": "u"}, {"lines": _LINES}, "s")
    assert out["ok"] is False and "타임아웃" in out["error"]


def test_a_store_failure_says_so(wired, monkeypatch):
    B, _ = wired
    monkeypatch.setattr("src.services.image_translate_store.store_translated",
                        lambda *a, **k: {"url": "", "stored_by": "", "note": "DB 없음"})
    out = B._run_d3_stage({"item_no": "X"}, 0, {"url": "u"}, {"lines": _LINES}, "s")
    assert out["ok"] is False and "DB 없음" in out["error"]


# ---------------------------------------------------------------------------
# 4) 토큰은 못 잰다고 말한다
# ---------------------------------------------------------------------------

def test_the_cost_counts_what_it_measured_and_says_what_it_could_not():
    """★★ **분모는 잰 것만.** 토큰을 추정해 적으면 그건 지어낸 숫자다."""
    from src.seller_console.views import _bench_grid
    run = {"results": [{"idx": 0, "d3": {"llm": {"calls": 3, "chars": 40, "errors": 0}}}]}
    grid = _bench_grid(run)
    cost = grid["d3_cost"]
    assert cost["tencent_calls"] == 1           # 장당 1콜
    assert cost["llm_calls"] == 3 and cost["llm_chars"] == 40
    assert cost["tokens"] is None
    assert "재지 못했습니다" in cost["tokens_note"]


def test_the_screen_says_tokens_were_not_measured():
    html = TPL.read_text(encoding="utf-8")
    assert "재지 못함" in html and "추정치를 적지 않습니다" in html


# ---------------------------------------------------------------------------
# 5) 채점 칸이 섞이지 않는다
# ---------------------------------------------------------------------------

def test_the_d3_cells_are_namespaced():
    """★★ 공급사 렌더본 점수와 **같은 자리에 섞으면** 무엇을 채점한 건지 갈린다.

    ※ 소스 문자열이 아니라 **라우트를 돌려** 확인한다(메타 계약).
    """
    from src.services.image_bench_axes import AUTO_AXES
    from tests._ast_probe import string_constants_in
    from src.seller_console import views

    consts = string_constants_in(views.image_translate_bench_score)
    assert "d3:" in consts, consts
    # D3-4 ⑤ — 자동 축은 **자동이 정본**이므로 사람 칸으로 받지 않는다. (D3-5 ②로 F 추가)
    assert AUTO_AXES == ("A", "B", "D", "F")


def test_the_grid_keeps_the_two_scores_apart():
    from src.seller_console.views import _bench_grid
    run = {"results": [{"idx": 0, "d3": {"drawn": 1}}],
           "scores": {"cells": {"0:C": 1, "d3:0:C": 0}}}
    page = _bench_grid(run)["pages"][0]
    assert page["axes"]["C"]["score"] == 1        # 공급사
    assert page["d3_axes"]["C"]["score"] == 0     # 우리 — 다른 값이 따로 산다


# ---------------------------------------------------------------------------
# ★★ D3-4 ⑤ — D3 열의 A·B·D는 **자동**(오너 브리프 2026-09-21)
# ---------------------------------------------------------------------------

def test_the_d3_column_is_auto_scored_by_the_same_judge(wired):
    """★★★ **판정 지점** — 우리 결과를 공급사와 **같은 판정기**로 잰다.

    다른 판정기를 쓰면 두 열의 숫자를 나란히 놓을 수 없다. 그게 비교의 전부다.
    """
    B, _ = wired
    out = B._run_d3_stage({"item_no": "X1"}, 0, {"url": "u"}, {"lines": _LINES}, "s",
                          ["SPORTLINK"])
    assert out["axes"]["B"]["score"] == 1, out["axes"]      # 三合一 → 3-in-1
    for key in ("A", "B", "D"):
        assert key in out["axes"], out["axes"]


def test_the_d3_judge_reads_our_text_not_the_vendors():
    """★★★ `target`이 **우리가 그린 글자**여야 한다 — 공급사 번역을 채점하면 남의 답안지다."""
    from src.services.image_translate_bench import d3_judgeable

    rows = [{"source": "三合一", "target": "삼합일", "render_text": "3-in-1"}]
    assert d3_judgeable(rows) == [{"source": "三合一", "target": "3-in-1"}]


def test_the_grid_shows_the_auto_scores_for_d3():
    """★★ 표가 그 값을 읽는다 — 계산만 하고 화면이 안 보면 채점이 아니다."""
    from src.seller_console.views import _bench_grid

    run = {"results": [{"idx": 0, "d3": {
        "drawn": 1, "axes": {"A": {"score": 1, "reason": "브랜드 원형 유지"},
                             "B": {"score": 0, "reason": "직역됨"},
                             "D": {"score": None, "reason": "영문 줄 없음"}}}}],
           "scores": {"cells": {}}}
    d3 = _bench_grid(run)["pages"][0]["d3_axes"]
    assert d3["A"]["score"] == 1 and d3["B"]["score"] == 0
    assert d3["D"]["score"] is None and d3["D"]["reason"]
    assert d3["C"]["reason"] == "사람이 아직 안 찍음"       # C·E는 여전히 사람


def test_a_human_cannot_overwrite_an_auto_axis_on_the_d3_row():
    """★ 자동 축을 사람이 덮으면 **두 열이 다른 자**로 재진다."""
    from src.seller_console.views import _bench_grid

    run = {"results": [{"idx": 0, "d3": {"drawn": 1,
                                         "axes": {"A": {"score": 0, "reason": "브랜드 소실"}}}}],
           "scores": {"cells": {"d3:0:A": 1}}}
    assert _bench_grid(run)["pages"][0]["d3_axes"]["A"]["score"] == 0


def test_the_style_instruction_is_passed_and_counted(wired):
    """★★ D3-4 ④ — 문체 지시를 **보냈고**, 따를 수 있는 단이 받았는지 **센다**."""
    from src.services.image_text_glossary import STYLE_INSTRUCTION

    B, calls = wired
    out = B._run_d3_stage({"item_no": "X1"}, 0, {"url": "u"}, {"lines": _LINES}, "s")
    assert calls["styles"] == [STYLE_INSTRUCTION]
    assert out["llm"]["styled"] == 1 and out["llm"]["unstyled"] == 0


def test_an_unstyled_provider_is_reported_not_hidden(wired, monkeypatch):
    """★★★ 사전형 MT가 받았으면 **따른 척하지 않는다** — 숫자로 남는다.

    이게 없으면 카피가 여전히 평서문일 때 **어디를 봐야 하는지** 모른다.
    """
    B, calls = wired

    class _Dict:
        def translate_product(self, src, *, style=""):
            # 문체 지시를 받긴 했지만 **따를 자리가 없다** — 평서문이 그대로 나온다.
            return {"title_ko": "이것은 3-in-1 충전기입니다", "provider": "mymemory",
                    "style_applied": False}

    monkeypatch.setattr("src.seller_console.ai.translator.AITranslator", _Dict)
    out = B._run_d3_stage({"item_no": "X1"}, 0, {"url": "u"}, {"lines": _LINES}, "s")
    assert out["llm"]["unstyled"] == 1 and out["llm"]["styled"] == 0
    assert out["llm"]["providers"] == {"mymemory": 1}


# ---------------------------------------------------------------------------
# 6) 화면 — 실브라우저
# ---------------------------------------------------------------------------

def _chrome_opts():
    """레포 규약 그대로(`test_f38…`와 동형 — 두 벌 금지)."""
    import glob
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return {"executable_path": hits[0]} if hits else {}


def test_three_images_stand_side_by_side_in_a_real_browser():
    """★★ **JS를 실행해서** 센다 — 마크업을 눈으로 읽고 「있겠지」 하지 않는다."""
    pw = pytest.importorskip("playwright.sync_api")
    html = TPL.read_text(encoding="utf-8")
    # 세 칸 블록을 **템플릿 원문에서** 잘라 온다 — 시작은 행, 끝은 번역본 이미지 줄.
    #   (손으로 마크업을 재조립하면 그건 우리가 만든 것을 재는 셈이다.)
    start = html.index('<div class="row g-2">')
    end = html.index('alt="번역본"', start)
    end = html.index("\n", end)
    block = html[start:end] + "\n{% endif %}</div></div>"

    from jinja2 import Environment
    out = Environment().from_string(block).render(
        r={"original": "o.jpg", "url": "t.jpg",
           "d3": {"url": "d.jpg", "erased": 1, "drawn": 1, "skipped": []}})

    with pw.sync_playwright() as p:
        browser = p.chromium.launch(**_chrome_opts())
        page = browser.new_page()
        page.set_content(out)
        assert page.locator("img").count() == 3, page.content()[:400]
        cols = page.evaluate(
            "() => Array.from(document.querySelectorAll('[class*=col-md-4]')).length")
        assert cols == 3, cols
        browser.close()


def test_four_images_stand_side_by_side_with_gen_remove():
    """★★ D3-5 ① — gen_remove가 붙으면 **네 장**이 한 줄에 선다(원본·telea·gen_remove·공급사).

    같은 방식으로 **템플릿 원문을 잘라** JS까지 돌려 센다.
    """
    pw = pytest.importorskip("playwright.sync_api")
    html = TPL.read_text(encoding="utf-8")
    start = html.index('<div class="row g-2">')
    end = html.index('alt="번역본"', start)
    end = html.index("\n", end)
    block = html[start:end] + "\n{% endif %}</div></div>"

    from jinja2 import Environment
    out = Environment().from_string(block).render(
        r={"original": "o.jpg", "url": "t.jpg",
           "d3": {"url": "d.jpg", "erased": 1, "drawn": 1, "skipped": []},
           "d3g": {"url": "g.jpg", "erased": 1, "drawn": 1, "inpainter": "gen_remove",
                   "cloud_tx": 51, "cloud_credits": 0.051,
                   "axes": {"F": {"score": 1, "reason": "지운 자리가 주변과 닮았습니다"}}},
           "pick": {"pick": "d3g"}})

    with pw.sync_playwright() as p:
        browser = p.chromium.launch(**_chrome_opts())
        page = browser.new_page()
        page.set_content(out)
        assert page.locator("img").count() == 4, page.content()[:400]
        cols = page.evaluate(
            "() => Array.from(document.querySelectorAll('[class*=col-md-3]')).length")
        assert cols == 4, cols
        body = page.inner_text("body")
        assert "51 tx" in body and "0.051 크레딧" in body         # 오너: 원가를 적어라
        assert "제안" in body                                        # 장별 제안 표지
        browser.close()


def test_a_fallback_is_named_telea_on_the_gen_remove_column():
    """★★★ 폴백을 숨기면 gen_remove 칸에 **telea 그림이 gen_remove 이름으로** 올라간다."""
    from jinja2 import Environment
    html = TPL.read_text(encoding="utf-8")
    start = html.index('<div class="row g-2">')
    end = html.index('alt="번역본"', start)
    end = html.index("\n", end)
    block = html[start:end] + "\n{% endif %}</div></div>"
    out = Environment().from_string(block).render(
        r={"original": "o.jpg", "url": "t.jpg",
           "d3": {"url": "d.jpg", "erased": 1, "drawn": 1, "skipped": []},
           "d3g": {"url": "g.jpg", "erased": 1, "drawn": 1, "inpainter": "telea",
                   "inpaint_fallback": "Cloudinary 자격 미설정", "cloud_tx": 0,
                   "cloud_credits": 0.0}})
    assert "telea로 폴백" in out and "Cloudinary 자격 미설정" in out


def test_the_run_button_sends_the_render_flag():
    html = TPL.read_text(encoding="utf-8")
    assert 'id="benchRenderD3"' in html
    assert "render:" in html and "benchRenderD3" in html


# ---------------------------------------------------------------------------
# 7) 파이프라인은 여전히 안 본다
# ---------------------------------------------------------------------------

def test_the_registration_pipeline_still_does_not_see_the_renderer():
    """★★★ **벤치는 파이프라인이 아니다.** 등록·번역 경로는 이 값을 쳐다보지 않는다."""
    from tests.test_d3_glossary import _importers_of
    allowed = {"image_translate_bench.py"}          # 벤치만
    assert _importers_of("image_text_render", allow=allowed) == []
    assert _importers_of("image_text_glossary", allow=allowed) == []
