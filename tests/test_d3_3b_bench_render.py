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
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), (238, 234, 226))
    ImageDraw.Draw(img).rectangle([20, 20, 180, 60], fill=(25, 25, 25))
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
        def translate_product(self, src):
            calls["llm"] += 1
            return {"title_ko": "3-in-1 충전기"}

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
    import inspect
    src = inspect.getsource(B._run_d3_stage) + inspect.getsource(B._render_d3_for)
    assert "translate_image" not in src, "D3 단계가 공급사를 다시 부른다"


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

def test_the_d3_cells_are_namespaced_and_take_all_five_axes():
    """★★ 공급사 렌더본 점수와 **같은 자리에 섞으면** 무엇을 채점한 건지 갈린다."""
    import inspect

    from src.seller_console import views
    src = inspect.getsource(views.image_translate_bench_score)
    assert '"d3:"' in src or "'d3:'" in src
    # D3는 자동 축(A·B·D)도 사람이 찍는다 — 렌더가 달라지면 값도 달라지기 때문이다.
    assert "all_axes" in src


def test_the_grid_keeps_the_two_scores_apart():
    from src.seller_console.views import _bench_grid
    run = {"results": [{"idx": 0, "d3": {"drawn": 1}}],
           "scores": {"cells": {"0:C": 1, "d3:0:C": 0, "d3:0:A": 1}}}
    page = _bench_grid(run)["pages"][0]
    assert page["axes"]["C"]["score"] == 1        # 공급사
    assert page["d3_axes"]["C"]["score"] == 0     # 우리 — 다른 값이 따로 산다
    assert page["d3_axes"]["A"]["score"] == 1


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
