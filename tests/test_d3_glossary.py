"""D3 2단계 계약 — 용어집 번역. 브랜드는 지키고, UI는 건드리지 않는다.

## 이 트랙이 뭔가 (오너 승인 2026-09-20)

텐센트 **렌더본을 버리고** `TransDetails`를 「박스 + 원문」으로만 쓴 뒤,
**우리가 번역해서**(여기) 박스에 다시 그린다(3단계).
**골든 샘플 5축을 통과하기 전에는 파이프라인에 연결하지 않는다** — 지금 도는 텐센트 경로는 그대로다.

## 이 파일이 재는 것 — 규칙 셋

| 축 | 규칙 |
|---|---|
| **A** | 브랜드 토큰(대문자 영문) **보존** — 워드마크를 번역하면 다른 상품이다 |
| **B** | 관용 사전 우선 — `三合一` → `3-in-1`(직역 「삼합일」이 나왔던 실측) |
| **D** | 영문+숫자만인 줄 **미번역** — 제품 화면 UI에 없던 한국어를 만들지 않는다 |

> ★★ **생성이 쓰는 사전과 채점이 쓰는 사전이 같아야 한다.**
> 다르면 만들면서 틀리고 재면서 통과한다 → `image_bench_axes`를 그대로 쓴다(재구현 0).

번역기는 **주입**이다 — 라이브 호출 0.
"""
from __future__ import annotations

import pytest

from src.services import image_text_glossary as G


def _echo(s):
    """번역기 대역 — 들어온 걸 그대로 낸다(규칙만 잰다)."""
    return s


#: 이 모듈들이 D3 단계를 import하는 것은 **연결이 아니다** — 벤치(관리자 화면)와
#: 그 안의 3단계 렌더가 서로를 쓰는 자리다. 등록·번역 경로는 여기 없다.
BENCH_ONLY = {"image_translate_bench.py", "image_text_render.py"}


def _importers_of(module_name: str, *, allow=()) -> list:
    """`src/` 안에서 그 모듈을 **실제로 import 하는** 파일들 (글자 일치 아님).

    D3 트랙 공용 — 「아직 연결하지 않았다」를 지키는 잣대다. `allow`는 같은 트랙 안의
    모듈(3단계가 폰트 로더를 쓰는 것 같은 것)이고, **파이프라인 연결이 아니다.**
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    skip = {f"{module_name}.py", *allow}
    hits = []
    for p in (root / "src").rglob("*.py"):
        if p.name in skip:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [f"{node.module or ''}.{a.name}" for a in node.names]
            if any(module_name == n.rsplit(".", 1)[-1] or n.endswith(f".{module_name}")
                   for n in names):
                hits.append(str(p.relative_to(root)))
                break
    return sorted(set(hits))


# ---------------------------------------------------------------------------
# D) 영문·숫자만인 줄은 건드리지 않는다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("src", ["12:30", "START", "USB 3.0", "Model X-200", "88%"])
def test_an_english_ui_line_is_kept(src):
    """★★ 제품 화면에 **없던 한국어를 만들지 않는다**."""
    assert G.is_untranslatable(src) is True
    assert G.plan_line(src)["action"] == "keep"


@pytest.mark.parametrize("src", ["三合一 충전기", "휴대용 선풍기", "便携式 USB"])
def test_a_line_with_non_english_is_translated(src):
    assert G.is_untranslatable(src) is False
    assert G.plan_line(src)["action"] == "translate"


def test_an_empty_line_is_skipped():
    assert G.plan_line("   ")["action"] == "skip"


def test_a_kept_line_renders_the_source_verbatim():
    rows = G.translate_lines([{"source": "START"}], lambda s: "시작")
    assert rows[0]["render_text"] == "START"
    assert rows[0]["action"] == "keep"


# ---------------------------------------------------------------------------
# A) 브랜드는 번역기에 닿지 않는다
# ---------------------------------------------------------------------------

def test_a_brand_token_never_reaches_the_translator():
    """★★ 번역기에 원문 브랜드를 주면 음차한다(`PORTER` → 「포터」)."""
    seen = {}

    def _fn(s):
        seen["got"] = s
        return s

    G.translate_lines([{"source": "PORTER 정품 가방"}], _fn)
    assert "PORTER" not in seen["got"], seen


def test_the_brand_comes_back_unchanged():
    rows = G.translate_lines([{"source": "PORTER 正品包"}], _echo)
    assert "PORTER" in rows[0]["render_text"]
    assert rows[0]["protected"] == ["PORTER"]


def test_units_are_not_treated_as_brands():
    """★ `USB`·`XL`은 브랜드가 아니다 — 판정기와 같은 사전을 쓴다."""
    assert G.brand_tokens_in("USB XL 케이블") == []


def test_a_dropped_placeholder_falls_back_to_the_source():
    """★★ 번역기가 자리표시자를 **통째로 버리면 브랜드가 사라진다** — 그게 더 나쁘다.

    깨진 글자는 눈에 띄지만, 없어진 브랜드는 안 띈다. 이 계약이 그걸 잡았다.
    """
    rows = G.translate_lines([{"source": "PORTER 가방"}], lambda s: "가방입니다")
    assert rows[0]["render_text"] == "PORTER 가방"
    assert "되돌리지 못했습니다" in rows[0]["translate_error"]


def test_a_mangled_placeholder_also_falls_back():
    """제어문자가 남아도 **원문으로** 간다 — 상품 사진에 박히면 안 된다."""
    rows = G.translate_lines([{"source": "PORTER 가방"}],
                             lambda s: s.replace("\u2403", ""))   # 닫는 문자를 깬다
    assert rows[0]["render_text"] == "PORTER 가방"
    assert rows[0]["translate_error"]


def test_two_brands_round_trip():
    rows = G.translate_lines([{"source": "PORTER YOSHIDA 컬래버"}], _echo)
    assert rows[0]["render_text"].count("PORTER") == 1
    assert "YOSHIDA" in rows[0]["render_text"]


# ---------------------------------------------------------------------------
# B) 관용구는 사전이 이긴다
# ---------------------------------------------------------------------------

def test_a_literal_idiom_is_corrected():
    """★★ 실측된 오역 — `三合一`이 「삼합일」로 나왔다."""
    rows = G.translate_lines([{"source": "三合一 충전 케이블"}], lambda s: "삼합일 충전 케이블")
    assert "3-in-1" in rows[0]["render_text"]
    assert "삼합일" not in rows[0]["render_text"]


def test_a_good_translation_is_left_alone():
    rows = G.translate_lines([{"source": "三合一"}], lambda s: "3-in-1 충전기")
    assert rows[0]["render_text"] == "3-in-1 충전기"


def test_an_unknown_idiom_is_not_invented():
    """★ 사전에 없는 표현은 **건드리지 않는다** — 모르는 말을 고치는 건 발명이다."""
    rows = G.translate_lines([{"source": "五合一 케이블"}], lambda s: "오합일 케이블")
    assert rows[0]["render_text"] == "오합일 케이블"


def test_an_idiom_translated_by_meaning_is_not_overwritten():
    """원문에 관용구가 있어도, 번역기가 뜻을 옮겼으면 **덧붙이지 않는다**(판정은 벤치가)."""
    rows = G.translate_lines([{"source": "三合一"}], lambda s: "3가지 기능")
    assert rows[0]["render_text"] == "3가지 기능"


# ---------------------------------------------------------------------------
# 실패는 원문을 남긴다
# ---------------------------------------------------------------------------

def test_a_translator_error_keeps_the_source():
    """★★ 빈칸이나 지어낸 말로 덮지 않는다 — 그 줄은 「번역 안 됨」이고 그게 사실이다."""
    def _boom(s):
        raise RuntimeError("rate limited")

    rows = G.translate_lines([{"source": "휴대용 선풍기"}], _boom)
    assert rows[0]["render_text"] == "휴대용 선풍기"
    assert "RuntimeError" in rows[0]["translate_error"]


def test_an_empty_translation_keeps_the_source():
    rows = G.translate_lines([{"source": "휴대용 선풍기"}], lambda s: "   ")
    assert rows[0]["render_text"] == "휴대용 선풍기"
    assert "빈 문자열" in rows[0]["translate_error"]


def test_the_box_survives_untouched():
    """★ 박스는 1단계가 준 값이다 — 2단계가 손대지 않는다."""
    box = {"x": 10, "y": 20, "w": 100, "h": 30}
    rows = G.translate_lines([{"source": "선풍기", "box": box}], _echo)
    assert rows[0]["box"] == box


def test_the_summary_counts_only_what_it_measured():
    rows = G.translate_lines(
        [{"source": "三合一"}, {"source": "START"}, {"source": ""}], _echo)
    s = G.summarize(rows)
    assert s == {"total": 3, "translated": 1, "kept": 1, "failed": 0, "glossary": 0}


# ---------------------------------------------------------------------------
# ★★ D3-4 ④ 정본 용어집 + 문체 지시 (오너 실측 오역 2026-09-21)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source,ko", [
    ("一放秒充", "올려놓기만 하면 충전"),
    ("拒绝凌乱", "지저분함은 이제 그만"),
    ("轻松收纳", "간편 수납"),
])
def test_a_measured_mistranslation_is_answered_from_the_glossary(source, ko):
    """★★★ 오너가 **정본을 준 줄**은 번역기에 묻지 않는다 — 답을 아는데 또 틀릴 이유가 없다."""
    calls = []

    def _fn(s):
        calls.append(s)
        return "엉뚱한 번역입니다"

    rows = G.translate_lines([{"source": source}], _fn)
    assert rows[0]["render_text"] == ko
    assert rows[0]["glossary_hit"] == source
    assert calls == [], calls            # 전송 0회


def test_the_glossary_survives_spacing():
    """★ 공급사가 준 원문에 공백이 끼어도 같은 줄이다."""
    assert G.glossary_line(" 轻松 收纳 ") == "간편 수납"


def test_a_line_that_is_not_in_the_table_still_goes_to_the_translator():
    """★★ 표에 없는 줄까지 가로채면 **번역이 사라진다** — 표에 있는 것만 답한다."""
    rows = G.translate_lines([{"source": "超强吸力"}], _echo)
    assert not rows[0].get("glossary_hit")
    assert rows[0]["render_text"] == "超强吸力"


def test_the_summary_counts_the_glossary_lines():
    rows = G.translate_lines([{"source": "一放秒充"}, {"source": "超强吸力"}], _echo)
    assert G.summarize(rows)["glossary"] == 1


def test_the_style_instruction_bans_declarative_endings():
    """★★ 오너 지시 문구가 **실제 지시문에** 들어 있다 — 광고 카피체·평서형 종결 금지."""
    assert "광고 카피" in G.STYLE_INSTRUCTION
    assert "평서형 종결" in G.STYLE_INSTRUCTION
    for ending in ("입니다", "합니다"):
        assert ending in G.STYLE_INSTRUCTION, ending


# ---------------------------------------------------------------------------
# 같은 사전을 쓴다 · 아직 연결하지 않는다
# ---------------------------------------------------------------------------

def test_it_reuses_the_bench_dictionaries():
    """★★ 생성과 채점이 **같은 표**를 본다 — 두 벌이면 만들면서 틀리고 재면서 통과한다.

    ※ 소스 문자열이 아니라 **객체가 같은지**를 본다(메타 계약). 이름만 적어 두고
      다른 표를 들고 있으면 문자열 검사는 통과하지만 **표는 두 벌**이다.
    """
    from src.services import image_bench_axes as axes

    assert G.IDIOMS is axes.IDIOMS
    assert G._BRAND_TOKEN is axes._BRAND_TOKEN
    assert G._EN_UI is axes._EN_UI
    assert G._NOT_BRAND is axes._NOT_BRAND
    # 정본 용어집도 그 표에서 **파생**된다 — 손으로 적은 두 번째 표가 아니다.
    assert set(G.LINE_GLOSSARY.values()) == {i["ko"] for i in axes.IDIOMS if i.get("ko")}


def test_the_vendor_is_injected_not_chosen_here():
    """★ 공급사를 여기서 고르지 않는다 — 계약이 라이브 없이 규칙을 잰다.

    ※ **import 구조**로 잰다. 예전엔 소스 문자열에서 공급사 이름을 찾았는데,
      독스트링이 「LLM만 문체 지시를 따른다」를 설명하는 순간 헛것을 재게 된다.
    """
    from tests._ast_probe import calls_in, imports_in

    assert "translate_fn" in calls_in(G.translate_lines)
    joined = " ".join(imports_in(G)).lower()
    for vendor in ("tencent", "openai", "deepl", "papago", "translator"):
        assert vendor not in joined, vendor


def test_it_is_not_wired_into_the_pipeline_yet():
    """★★ 오너 지시 — **골든 샘플 5축 통과 전에는 연결하지 않는다.**

    지금 도는 텐센트 경로는 그대로다. 이 계약이 그 약속을 지킨다.

    ※ **글자가 아니라 `import`를 잰다.** 예전엔 파일 안에 이름이 보이기만 해도 실패였는데,
      3단계 모듈의 **독스트링이 2단계를 설명하면서** 이름을 적자 터졌다. 그건 연결이 아니다.
      계약이 주석을 읽으면 헛것을 재는 것이다.

    ※ **벤치는 파이프라인이 아니다**(D3-3b, 오너 2026-09-21). 관리자 화면이 오너 클릭으로
      한 장을 돌려 보는 자리이고, 결과는 벤치 저장소에만 간다. 여기서 막는 것은
      **등록·번역 경로가 이 모듈을 집어 가는 것**이다.
    """
    # F48-b(오너 2026-09-25): 쿠팡 **색상 속성값** 매핑은 「D3 용어집 재사용」이 지시다 —
    #   렌더를 잇는 게 아니라 표 한 장을 읽는다. 열어 주는 자리는 `coupang_options.py` 하나,
    #   가져가는 이름은 `glossary_line` 하나(`test_d3_3b_bench_render`가 그 좁힘을 잰다).
    assert _importers_of("image_text_glossary",
                         allow=set(BENCH_ONLY) | {"coupang_options.py"}) == []
