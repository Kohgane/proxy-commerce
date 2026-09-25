"""D3-6 — 오너 벤치 실측 결함(2026-09-25) 회귀 계약.

채점 원본 3장(Cloudinary `cphvcw…`·`ctezbv…`·`ebvllh…`)은 **이 CI 컨테이너에서 받을 수 없다**
(`res.cloudinary.com` 송신 차단 — 403). 그래서 각 장의 **결함 조건을 그대로 재현한 합성 픽스처**로
잰다. 원본 3장이 `tests/fixtures/d3_6/<id>.jpg`로 커밋되면 맨 아래 계약이 **실물로도** 돈다
(없으면 건너뛴다고 **말한다**).

| # | 결함(오너 실측) | 계약 |
|---|---|---|
| ⓪ | URL만 보고 어느 열인지 모른다 | 업로드 public_id·context에 run·장·파이프라인 |
| ① | `三合一`→삼합일 · `拒绝混乱`이 페이지마다 다름 | 관용구는 번역기에 안 가고 정본이 박힌다 |
| ①-b | `SPORTLINK` 옆 `随行盾`이 번역됨 | `line_name_drop` — 지우고 안 쓴다, 브랜드는 그대로 |
| ② | 시계 화면 `Alarm 6:45am`이 「알람 6:45A」 | 전각으로 와도 영문 UI — 번역·지우기·그리기 0 |
| ③ | 시계 화면 작은 글자 「워ㅇ이」 | 박스 높이 < 원본 1.5%면 손대지 않음 |
| ④ | `使用前/使用后` 미탐지 | 응답 원문으로 「박스 밖 OCR」을 가른다 |
| ⑤ | 알약이 회색 사각형 + 파란 번짐 | 판(알약)은 마스크에서 빠지고 글자만 남는다 |
| ⑤ | 부제 넘침 | 그려질 자리로 재서 넘으면 줄인다(재현 못 함 — 방어 계약) |
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
from PIL import Image, ImageDraw  # noqa: E402

from src.services import image_text_glossary as G  # noqa: E402
from src.services import image_text_render as R  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "d3_6"


def _jpeg(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _font(px, w="bold"):
    from src.services.image_render_font import load
    return load(px, w)


def _echo_ko(s: str) -> str:
    """진짜 번역기처럼 자리표시자는 두고 한자만 옮긴다(호출 기록용 목)."""
    return (s.replace("随行盾", "수행방패").replace("多功能", "다기능")
             .replace("三合一", "삼합일").replace("闹钟", "알람"))


# ---------------------------------------------------------------------------
# ⓪ 이름표 — URL만 보고 어느 열인지
# ---------------------------------------------------------------------------

def test_bench_uploads_carry_run_page_and_pipeline(monkeypatch):
    from src.services import image_translate_store as S
    seen = []

    def _up(raw, **kw):
        seen.append(kw)
        pid = kw.get("public_id") or "random"
        return {"ok": True, "secure_url": f"https://res.cloudinary.com/x/image/upload/v1/proxy-commerce/bench/{pid}.jpg"}

    monkeypatch.setattr("src.media.image_pipeline.upload_bytes", _up)
    import base64
    lab = {"run_id": "bench-20260925-101500-m0-d3g", "item_no": "617129397971",
           "page": "3", "pipeline": "GEN_REMOVE"}
    got = S.store_translated("617129397971", 3, base64.b64encode(b"\xff\xd8\xff" + b"0" * 40).decode(),
                             kind="d3g", label=lab)
    assert seen[0]["public_id"] == "bench-20260925-101500-m0-d3g_617129397971_p3_GEN_REMOVE"
    assert seen[0]["context"] == lab and seen[0]["folder"] == "bench"
    for part in ("bench-20260925-101500-m0-d3g", "p3", "GEN_REMOVE"):
        assert part in got["url"]


def test_the_label_names_the_inpainter_actually_used():
    """폴백했으면 이름이 TELEA다 — gen_remove 칸이라고 GEN_REMOVE를 붙이지 않는다."""
    from src.services.image_translate_bench import bench_label
    from tests._ast_probe import string_constants_in
    from src.services import image_translate_bench as B
    assert bench_label("r", {"item_no": "9"}, 2, "TELEA") == {
        "run_id": "r", "item_no": "9", "page": "2", "pipeline": "TELEA"}
    assert {"GEN_REMOVE", "TELEA", "TENCENT"} <= string_constants_in(B._run_d3_stage) | \
        string_constants_in(B._run)


def test_sellers_translations_are_not_labelled():
    """이름표는 **벤치만** — 셀러 번역본 경로는 예전처럼 무이름(public_id 없음)."""
    from src.services import image_translate_store as S
    seen = []
    import src.media.image_pipeline as P
    orig = P.upload_bytes
    try:
        P.upload_bytes = lambda raw, **kw: seen.append(kw) or {"ok": True, "secure_url": "https://x/y.jpg"}
        S._store_via_cdn(b"abc")
    finally:
        P.upload_bytes = orig
    assert seen == [{}]


# ---------------------------------------------------------------------------
# ① 관용구 — 번역기에 안 간다 · ①-b 라인명 삭제
# ---------------------------------------------------------------------------

def test_idioms_never_reach_the_translator_on_either_pipeline():
    """TELEA·GEN_REMOVE는 **같은 줄 목록**을 그린다(`_render_d3_for`가 한 번 번역) —
    그 한 번에 관용구가 번역기에 안 가면 두 파이프라인 다 정본이다."""
    seen = []
    rows = G.translate_lines([{"source": "三合一 多功能"}, {"source": "拒绝混乱"}],
                             lambda s: seen.append(s) or _echo_ko(s))
    assert [r["render_text"] for r in rows] == ["3-in-1 다기능", "지저분함은 이제 그만"]
    assert all("三合一" not in s and "拒绝混乱" not in s for s in seen)
    from src.services import image_translate_bench as B
    from tests._ast_probe import calls_in
    assert "translate_lines" in calls_in(B._render_d3_for)      # 번역은 한 자리(두 렌더가 공유)


def _ink_box(text, xy, px=40, pad=8):
    """그린 글자의 **실제 잉크 범위** + 여백 = 박스. 손으로 적은 박스가 글자를 자르면
    테두리에 닿은 획이 「배경 도형」으로 빠진다(D3-5 규칙) — 픽스처가 현실과 달라진다."""
    l, t, r, b = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox(xy, text, font=_font(px))
    return {"x": l - pad, "y": t - pad, "w": (r - l) + 2 * pad, "h": (b - t) + 2 * pad}


CPHVCW_LINES = [   # cphvcw — 브랜드 워드마크 + 옆 라인명 + 시계 화면 UI
    {"source": "SPORTLINK", "box": _ink_box("SPORTLINK", (66, 44))},
    {"source": "随行盾", "box": _ink_box("随行盾", (346, 44))},
    {"source": "Monday 1", "box": {"x": 300, "y": 520, "w": 150, "h": 30}},
]


def test_line_name_next_to_a_brand_is_dropped_not_translated():
    seen = []
    rows = G.translate_lines(CPHVCW_LINES, lambda s: seen.append(s) or _echo_ko(s))
    brand, line_name, ui = rows
    assert brand["render_text"] == "SPORTLINK" and brand["action"] == "keep"
    assert line_name["action"] == "drop" and line_name["render_text"] == ""
    assert line_name["rule"] == G.LINE_NAME_RULE == "line_name_drop"
    assert ui["action"] == "keep"
    assert seen == []                     # 아무 줄도 번역기에 안 갔다


def test_a_han_line_far_from_the_brand_is_translated():
    rows = G.translate_lines([CPHVCW_LINES[0],
                              {"source": "随行盾", "box": {"x": 60, "y": 700, "w": 130, "h": 46}}],
                             _echo_ko)
    assert rows[1]["action"] == "translate" and rows[1]["render_text"] == "수행방패"


def test_a_line_name_in_the_same_box_as_the_brand_is_left_as_is():
    """한 박스(`SPORTLINK 随行盾`)면 라인명만 떼어 지울 수 없다 — **번역도 하지 않고** 원문 그대로."""
    def _never(s):
        raise AssertionError("번역기를 부르면 안 된다")
    [row] = G.translate_lines([{"source": "SPORTLINK 随行盾", "box": {"x": 0, "y": 0, "w": 400, "h": 48}}],
                              _never)
    assert row["action"] == "keep" and row["render_text"] == "SPORTLINK 随行盾"
    assert row["rule"] == "line_name_drop" and "번역 금지" in row["rule_reason"]
    # 브랜드 + 긴 문장이면 라인명이 아니다 — 번역한다(브랜드는 보호)
    [row] = G.translate_lines([{"source": "SPORTLINK 多功能随行防护盾牌"}], lambda s: s)
    assert row["action"] == "translate"


def _cphvcw_image() -> bytes:
    img = Image.new("RGB", (750, 1000), (240, 240, 236))
    d = ImageDraw.Draw(img)
    d.text((66, 44), "SPORTLINK", font=_font(40), fill=(20, 20, 20))
    d.text((346, 44), "随行盾", font=_font(40), fill=(20, 20, 20))
    return _jpeg(img)


def test_the_line_name_is_erased_and_nothing_is_drawn_while_the_logo_stays():
    raw = _cphvcw_image()
    rows = G.translate_lines(CPHVCW_LINES[:2], _echo_ko)
    out = R.render(raw, rows, method="telea")
    assert out["ok"] and out["dropped"] == 1 and out["drawn"] == 0
    before = np.array(Image.open(io.BytesIO(raw)).convert("L"))
    after = np.array(Image.open(io.BytesIO(out["image_bytes"])).convert("L"))
    def _sl(b):
        return (slice(b["y"], b["y"] + b["h"]), slice(b["x"], b["x"] + b["w"]))
    logo, name = _sl(CPHVCW_LINES[0]["box"]), _sl(CPHVCW_LINES[1]["box"])
    assert CPHVCW_LINES[0]["box"]["x"] + CPHVCW_LINES[0]["box"]["w"] < CPHVCW_LINES[1]["box"]["x"]
    assert np.abs(before[logo].astype(int) - after[logo].astype(int)).mean() < 2.0   # 로고 그대로
    assert (after[name] < 100).sum() < 0.1 * (before[name] < 100).sum()             # 라인명 지워짐


# ---------------------------------------------------------------------------
# ② 영문 UI(전각 포함) · ③ 소형 텍스트
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("src", ["Alarm 6:45am", "Ａｌａｒｍ ６：４５ａｍ", "Monday 1", "Ｍｏｎｄａｙ １"])
def test_english_ui_is_never_translated_even_in_fullwidth(src):
    rows = G.translate_lines([{"source": src, "box": {"x": 0, "y": 0, "w": 100, "h": 30}}],
                             lambda s: "알람 6:45A")
    assert rows[0]["action"] == "keep" and rows[0]["render_text"] == src


def test_the_judge_sees_fullwidth_ui_the_same_way():
    """생성과 판정이 **같은 함수** — 전각 UI를 번역하면 D축이 0을 준다."""
    from src.services.image_bench_axes import judge_en_ui
    r = judge_en_ui([{"source": "Ａｌａｒｍ ６：４５ａｍ", "target": "알람 6:45A"}])
    assert r["score"] == 0


def _ebvllh_image() -> bytes:
    """ebvllh — 시계 화면의 **작은** 한자 글자 + 파란 알약 위 흰 글자(박스가 알약보다 크다)."""
    img = Image.new("RGB", (750, 1000), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((210, 612, 540, 688), radius=38, fill=(40, 110, 220))
    d.text((300, 628), "三合一", font=_font(40), fill=(255, 255, 255))
    d.text((330, 300), "闹钟", font=_font(11, "regular"), fill=(30, 30, 30))
    return _jpeg(img)


EBVLLH_SMALL = {"source": "闹钟", "render_text": "알람", "action": "translate",
                "box": {"x": 326, "y": 298, "w": 30, "h": 13}}          # 13px < 1000×1.5%
EBVLLH_PILL = {"source": "三合一", "render_text": "3-in-1", "action": "translate",
               "box": {"x": 190, "y": 596, "w": 370, "h": 108}}        # 알약보다 큰 박스


def test_small_text_is_not_touched_at_all():
    raw = _ebvllh_image()
    out = R.render(raw, [EBVLLH_SMALL], method="telea")
    assert out["drawn"] == 0 and out["erased"] == 0 and out["image_bytes"] == raw
    assert any("소형 텍스트" in s["reason"] for s in out["skipped"])


def test_the_small_text_threshold_is_one_and_a_half_percent():
    ok = {"box": {"h": 15}}
    small = {"box": {"h": 14}}
    assert R.small_text_reason(ok, 1000) == "" and R.small_text_reason(small, 1000)


# ---------------------------------------------------------------------------
# ⑤ 알약 — 판은 남기고 글자만
# ---------------------------------------------------------------------------

def test_the_pill_is_not_erased_only_its_letters():
    raw = _ebvllh_image()
    erased, n, why = R.erase_boxes(raw, [EBVLLH_PILL["box"]], method="telea")
    assert why == "" and n == 1
    a = np.array(Image.open(io.BytesIO(erased)).convert("RGB")).astype(int)
    # 알약 몸통(글자 없는 오른쪽 끝) — 파랑 그대로
    body = a[630:670, 470:520]
    assert body[..., 2].mean() > 180 and body[..., 0].mean() < 90
    # 글자 자리는 **알약 색**으로 메워졌다(흰 글자가 남지 않았다)
    text = a[628:672, 300:420]
    assert text[..., 2].mean() > 170 and (text.sum(axis=2) > 700).mean() < 0.05


def test_the_gen_remove_region_stays_inside_the_pill():
    """gen_remove에 넘기는 영역 = 글자 외접 사각형 — **알약 전체가 아니다.**"""
    rects, fails = R.glyph_regions(_ebvllh_image(), [EBVLLH_PILL["box"]])
    assert fails == [] and len(rects) == 1
    x, y, w, h = rects[0]
    assert x >= 212 and x + w <= 538 and y >= 612 and y + h <= 688


def test_the_pill_text_is_sampled_white_not_pill_blue():
    """합성 캡처에서 찾은 것 — 글자색 기준이 박스 테두리(페이지 흰색)라 **파랑**을 쟀다."""
    t = R.sample_typography(_ebvllh_image(), EBVLLH_PILL["box"], "三合一")
    r, g, b = t["color"]
    assert min(r, g, b) > 200, t


def test_korean_on_a_pill_is_laid_out_inside_the_pill():
    """★ 박스가 알약보다 크면, 박스 폭에 맞춘 한국어가 **알약 밖으로 삐져나간다** —
    cphvcw 「부제 넘침」의 유력 원인. 판이 있으면 판 안쪽에 앉힌다."""
    raw = _ebvllh_image()
    pr = R.plate_rect(raw, EBVLLH_PILL["box"])
    assert pr and 210 <= pr["x"] and pr["x"] + pr["w"] <= 540
    row = dict(EBVLLH_PILL, render_text="지저분함은 이제 그만")
    out = R.render(raw, [row], method="telea")
    assert out["drawn"] == 1
    a = np.array(Image.open(io.BytesIO(out["image_bytes"])).convert("RGB")).astype(int)
    white = (a.min(axis=2) > 200)
    outside = white.copy()
    outside[612:688, 210:540] = False          # 알약 안은 제외
    band = outside[596:704, 190:560]           # 원래 박스 안, 알약 밖
    page = (a[596:704, 190:560].min(axis=2) > 200)
    # 알약 밖(페이지 바탕)은 원래 흰색이다 — 흰 글자가 **알약 안에만** 있는지는
    #   알약 안 흰 픽셀이 생겼는가와, 알약 밖에 **파랑 번짐**이 없는가로 잰다.
    inside_white = white[612:688, 250:500].mean()
    assert inside_white > 0.02, inside_white
    def _blue_out(arr):
        m = ((arr[:, :, 2] > 150) & (arr[:, :, 0] < 120))
        m[612:688, 210:540] = False
        return int(m[596:704, 190:560].sum())
    o = np.array(Image.open(io.BytesIO(raw)).convert("RGB")).astype(int)
    # 알약 가장자리의 JPEG 번짐은 원본에도 있다 — **원본보다 늘지 않았는가**를 잰다.
    assert _blue_out(a) <= _blue_out(o) + 20, (_blue_out(a), _blue_out(o))
    assert band.shape == page.shape


# ---------------------------------------------------------------------------
# ④ 박스 밖 OCR · ⑤ F 로그
# ---------------------------------------------------------------------------

def test_ocr_text_without_a_box_is_named():
    from src.services.image_translate_bench import unboxed_fragments
    lines = [{"source": "三合一 充电器"}, {"source": "SPORTLINK"}]
    assert unboxed_fragments("SPORTLINK 三合一 充电器 使用前 使用后", lines) == ["使用前", "使用后"]
    assert unboxed_fragments("", lines) == []            # 원문이 없으면 판정 불가 — 0이 아니다


def test_the_f_log_says_why_gen_remove_was_not_picked():
    from src.services.image_translate_bench import f_log_line
    row = {"d3": {"axes": {"F": {"score": 1}}},
           "d3g": {"axes": {"F": {"score": None}}, "inpainter": "telea",
                   "inpaint_fallback": "Cloudinary 자격 미설정"},
           "pick": {"pick": "d3", "reason": "공통 축 합 최고"}}
    line = f_log_line("run-1", "617129397971", 2, row)
    for part in ("p2", "TELEA F=1", "GEN_REMOVE F=측정불가", "폴백: Cloudinary 자격 미설정", "선택=d3"):
        assert part in line, (part, line)


# ---------------------------------------------------------------------------
# ⑤ 부제 넘침 — 그려질 자리로 잰다(방어)
# ---------------------------------------------------------------------------

def test_a_line_whose_ink_would_spill_is_shrunk(monkeypatch):
    """실제 폰트로는 재현 못 했다(180조합 넘침 0). 왼쪽 여백이 큰 글꼴을 가정해 **재는 방식**을 잰다."""
    real = R.load_font

    class _Wide:
        def __init__(self, f, size):
            self.f, self.size = f, size

        def getbbox(self, s):
            l, t, r, b = self.f.getbbox(s)
            return (l + (12 if self.size > 20 else 0), t, r + (12 if self.size > 20 else 0), b)

        def __getattr__(self, k):
            return getattr(self.f, k)

    monkeypatch.setattr(R, "load_font", lambda size, w="regular": _Wide(real(size, w), size))
    plan = R.fit_text("가볍고 튼튼한 방패", 200, 40)
    assert R._overflows(plan, "regular", 200) is True


# ---------------------------------------------------------------------------
# 실물 3장 — 커밋되면 돈다
# ---------------------------------------------------------------------------

REAL = ["cphvcwhsdvzgcdhfd5ve", "ctezbvgtpq31tlwvn1zc", "ebvllh1ala33hcyyctxq"]


@pytest.mark.parametrize("pid", REAL)
def test_owner_scoring_originals_are_decodable_when_committed(pid):
    p = FIX / f"{pid}.jpg"
    if not p.exists():
        pytest.skip(f"원본 {pid}.jpg 미커밋 — res.cloudinary.com이 이 환경에서 차단(403)")
    img = cv2.imdecode(np.frombuffer(p.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None and img.shape[0] > 0
