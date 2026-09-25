"""D3-5 계약 — 「쓰여지기 전 이미지」 복원 품질.

## 오너 브리프 (2026-09-25)

| # | 무엇 |
|---|---|
| ① | 인페인터 2단 — 글자 마스크 bbox를 **Cloudinary `e_gen_remove`**로 지우고 그 위에 렌더. telea는 폴백. 원가 줄에 크레딧 |
| ② | **F축 「배경 복원」** — 지운 영역과 주변 16px 링의 색·결 차이가 임계 이하면 1. 자동 |
| ③ | 장별 자동 선택 — [텐센트 / D3·telea / D3·gen_remove] 중 자동축 합 최고를 **제안**, 사람이 뒤집는다 |
| ④ | 폰트 결손(`绝·轻·纳·线·电`) — 원문 표시용 **Noto Sans SC 서브셋**, 렌더는 한글만이라 영향 없음을 계약으로 |

라이브 호출 0 — Cloudinary는 목이다(「키를 옮기지 말고 측정을 옮긴다」).
판정(수행방패 4장 재실행 → 표지 5축+F ≥5, 호환성 장에서 gen_remove F > telea F)은 **오너 벤치**다.
"""
from __future__ import annotations

import io
from unittest.mock import patch

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
pytest.importorskip("PIL.Image")

from src.services import image_bench_axes as A          # noqa: E402
from src.services import image_gen_remove as G          # noqa: E402
from src.services import image_text_render as R         # noqa: E402
from tests._ast_probe import calls_in                  # noqa: E402


# ---------------------------------------------------------------------------
# 픽스처 — 여기서 만든다(공급사 없이 실제 픽셀을 잰다)
# ---------------------------------------------------------------------------

W, H = 420, 220
#: 글자가 **박스 안에 다 들어가는** 크기로 잡는다. 삐져나가면 안 지워진 잉크가 링에 남아
#: F가 「결을 잃었다」가 아니라 **「잉크가 남았다」를 잰다** — 실제로 그렇게 헛것을 쟀었다
#: (60px를 70px 높이 박스에 넣었더니 11px 삐져나갔다). `_with_text`가 그걸 막는다.
BOX = {"x": 70, "y": 50, "w": 290, "h": 120}


def _bytes(a) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _flat():
    return np.full((H, W, 3), (240, 236, 228), np.uint8)


def _texture(seed=0):
    """결이 있는 배경 — 사진 위 글자(호환성 장)를 흉내 낸다."""
    rng = np.random.default_rng(seed)
    n = cv2.GaussianBlur(rng.normal(0, 1, (H, W, 3)).astype(np.float32), (0, 0), 2.0)
    n = n / (np.abs(n).max() + 1e-6)
    return np.clip(np.array([150, 120, 95], np.float32) + n * 55, 0, 255).astype(np.uint8)


def _with_text(a, size=60, text="原文文字"):
    """원문 글자를 **박스 안에** 그린다 — 삐져나가면 픽스처가 스스로 실패한다."""
    from PIL import Image, ImageDraw
    from src.services.image_render_font import load
    font = load(size, "bold")
    x, y = BOX["x"] + 10, BOX["y"] + 5
    bb = font.getbbox(text)
    assert (x + bb[0] >= BOX["x"] and y + bb[1] >= BOX["y"]
            and x + bb[2] <= BOX["x"] + BOX["w"] and y + bb[3] <= BOX["y"] + BOX["h"]), \
        f"픽스처 글자가 박스 밖으로 나간다 — F가 잉크를 재게 된다 ({size}px)"
    im = Image.fromarray(a.copy())
    ImageDraw.Draw(im).text((x, y), text, font=font, fill=(12, 12, 12))
    return np.array(im)


def _pill_with_text():
    """금색 알약 + 그 위의 글자 — 문단 박스가 도형까지 감싼 모양."""
    from PIL import Image, ImageDraw
    from src.services.image_render_font import load
    im = Image.new("RGB", (W, H), (245, 243, 236))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([40, 50, 380, 150], radius=48, fill=(201, 162, 75))
    d.text((120, 70), "一放秒充", font=load(50, "bold"), fill=(26, 23, 20))
    return _bytes(np.array(im)), {"x": 40, "y": 50, "w": 340, "h": 100}


LINE = {"source": "原文文字", "render_text": "원문 글자", "action": "translate", "box": BOX}


class _Resp:
    def __init__(self, status=200, content=b"", text=""):
        self.status_code, self.content, self.text = status, content, text
        self.headers = {}


# ---------------------------------------------------------------------------
# ① gen_remove — 문서에서 확인한 것만
# ---------------------------------------------------------------------------

def test_the_region_syntax_is_the_documented_one():
    """★ 레퍼런스 문법 `region_((x_…;y_…;w_…;h_…)[;…])` 그대로.

    문서 **예시** 문자열은 닫는 괄호가 잘려 있다 — 우리는 **형식 정의**를 따른다.
    """
    assert G.region_param([(300, 200, 750, 500)]) == "region_((x_300;y_200;w_750;h_500))"
    assert G.region_param([(1, 2, 3, 4), (5, 6, 7, 8)]) == \
        "region_((x_1;y_2;w_3;h_4);(x_5;y_6;w_7;h_8))"


def test_empty_or_degenerate_regions_are_not_sent():
    """★ 공급사가 뭐라 할지 모르는 값(0 폭)은 **만들지 않는다.**"""
    assert G.region_param([]) == ""
    assert G.region_param([(1, 1, 0, 5), (1, 1, 5, -1)]) == ""


def test_the_cost_comes_from_documented_constants():
    """★★ 오너: 「장당 Cloudinary 크레딧 소비를 원가 줄에 적어라.」

    50 tx(특수 카운트) + 1 tx(새 파생본) = 51 tx · 1 크레딧 = 1,000 tx — 둘 다 문서 값.
    """
    assert (G.TX_GEN_REMOVE, G.TX_BASE, G.TX_PER_CREDIT) == (50, 1, 1000)
    assert G.cost_of(1) == {"tx": 51, "credits": 0.051}
    assert G.cost_of(4) == {"tx": 204, "credits": 0.204}


def _uploaded(eager):
    return {"ok": True, "secure_url": "https://res.cloudinary.com/x/image/upload/src.jpg",
            "public_id": "src", "bytes": 10, "error": "", "keys": ["eager", "public_id"],
            "eager": eager}


def test_it_uploads_bytes_with_an_eager_effect_because_fetch_is_not_supported():
    """★★ 문서: gen_remove는 **fetch 이미지에 못 쓴다** → 업로드가 먼저, 효과는 eager로."""
    seen = {}

    def _up(image_bytes, *, prefer_webp=False, eager=None):
        seen.update(bytes=image_bytes, eager=eager)
        return _uploaded([{"secure_url": "https://res/derived.jpg"}])

    with patch("src.media.image_pipeline.upload_bytes", side_effect=_up), \
         patch("requests.get", return_value=_Resp(200, b"JPEGDATA")):
        got = G.gen_remove(b"SRC", [(1, 2, 3, 4)])
    assert seen["bytes"] == b"SRC"                                 # 주소가 아니라 바이트
    assert seen["eager"] == [{"effect": "gen_remove:region_((x_1;y_2;w_3;h_4))"}]
    assert got["ok"] is True and got["image_bytes"] == b"JPEGDATA"
    assert (got["tx"], got["credits"]) == (51, 0.051)


def test_an_upload_failure_is_not_charged():
    """★ 업로드부터 실패 = 파생본 **안 만들어졌다** — 청구 0은 추정이 아니라 사실이다."""
    with patch("src.media.image_pipeline.upload_bytes",
               return_value={"ok": False, "error": "Invalid api_key", "eager": []}):
        got = G.gen_remove(b"SRC", [(1, 2, 3, 4)])
    assert got["ok"] is False and got["tx"] == 0 and "Invalid api_key" in got["error"]


def test_an_empty_eager_result_is_unknown_cost_not_zero():
    """★★★ 업로드는 됐는데 eager가 비었다 — **만들어졌는지 모른다.**

    0으로 적으면 **쓴 돈을 안 쓴 것처럼** 보인다. 모르면 모른다(`None`).
    """
    with patch("src.media.image_pipeline.upload_bytes", return_value=_uploaded([])):
        got = G.gen_remove(b"SRC", [(1, 2, 3, 4)])
    assert got["ok"] is False and got["tx"] is None and got["credits"] is None
    assert "eager" in got["error"]


def test_a_pending_derivative_is_waited_on_then_reported(monkeypatch):
    """★ 문서: 생성 중이면 **423**(incoming이면 420). 짧게 기다리고, 끝내 안 되면 사유.

    그리고 **청구는 그대로 남는다** — 파생본 주소가 왔다는 건 만들어졌다는 뜻이다.
    """
    monkeypatch.setattr(G, "_PENDING_WAIT_SEC", 0)
    calls = []

    def _get(url, timeout=None):
        calls.append(url)
        return _Resp(423, b"", "Resource is being generated")

    with patch("src.media.image_pipeline.upload_bytes",
               return_value=_uploaded([{"url": "https://res/derived.jpg"}])), \
         patch("requests.get", side_effect=_get):
        got = G.gen_remove(b"SRC", [(1, 2, 3, 4)])
    assert len(calls) == G._PENDING_RETRIES
    assert got["ok"] is False and "423" in got["error"] and "준비" in got["error"]
    assert got["tx"] == 51                                         # 돈은 나갔다


def test_a_pending_derivative_that_becomes_ready_is_used(monkeypatch):
    monkeypatch.setattr(G, "_PENDING_WAIT_SEC", 0)
    seq = [_Resp(423), _Resp(200, b"READY")]
    with patch("src.media.image_pipeline.upload_bytes",
               return_value=_uploaded([{"secure_url": "https://res/d.jpg"}])), \
         patch("requests.get", side_effect=lambda *a, **k: seq.pop(0)):
        got = G.gen_remove(b"SRC", [(1, 2, 3, 4)])
    assert got["ok"] is True and got["image_bytes"] == b"READY"


def test_not_configured_says_which_gate(monkeypatch):
    for n in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        monkeypatch.delenv(n, raising=False)
    ok, why = G.configured()
    assert ok is False and "Cloudinary" in why


# ---------------------------------------------------------------------------
# ① render(method="gen_remove") — 폴백은 이름을 바꿔 적는다
# ---------------------------------------------------------------------------

@pytest.fixture
def cloud_on(monkeypatch):
    monkeypatch.setattr(G, "configured", lambda: (True, ""))
    return monkeypatch


def test_regions_are_glyph_bboxes_not_the_paragraph_box():
    """★★★ 오너: 영역 = **글자 마스크 bbox**. 문단 박스를 넘기면 **알약까지** 새로 그린다."""
    src, pill_box = _pill_with_text()
    rects, why = R.glyph_regions(src, [pill_box])
    assert rects and not why, why
    x, y, w, h = rects[0]
    assert x > pill_box["x"] and y > pill_box["y"], rects
    assert w * h < pill_box["w"] * pill_box["h"] * 0.6, (rects, pill_box)


def test_gen_remove_is_used_when_it_works(cloud_on):
    src = _bytes(_with_text(_flat()))
    seen = {}

    def _fake(image_bytes, rects):
        seen["rects"] = rects
        return {"ok": True, "image_bytes": _bytes(_flat()), "tx": 51, "credits": 0.051}

    cloud_on.setattr(G, "gen_remove", _fake)
    res = R.render(src, [LINE], method="gen_remove")
    assert res["ok"] is True and res["drawn"] == 1
    assert res["inpainter"] == "gen_remove" and res["inpaint_fallback"] == ""
    assert (res["cloud_tx"], res["cloud_credits"]) == (51, 0.051)
    assert seen["rects"]                                            # 글자 마스크 영역이 갔다


def test_not_configured_falls_back_to_telea_and_says_so(monkeypatch):
    """★★★ 폴백을 숨기면 gen_remove 칸에 **telea 그림이 gen_remove 이름으로** 올라간다."""
    monkeypatch.setattr(G, "configured", lambda: (False, "Cloudinary 자격 미설정"))
    res = R.render(_bytes(_with_text(_flat())), [LINE], method="gen_remove")
    assert res["ok"] is True
    assert res["inpainter"] == "telea"
    assert "Cloudinary 자격 미설정" in res["inpaint_fallback"]
    assert res["cloud_tx"] == 0


def test_a_failed_gen_remove_falls_back_but_keeps_the_charge(cloud_on):
    """★★ 지우기는 실패했어도 **돈은 나갔을 수 있다** — 폴백과 청구를 따로 적는다."""
    cloud_on.setattr(G, "gen_remove", lambda b, r: {
        "ok": False, "error": "파생본이 아직 준비되지 않았습니다(HTTP 423)",
        "tx": 51, "credits": 0.051})
    res = R.render(_bytes(_with_text(_flat())), [LINE], method="gen_remove")
    assert res["inpainter"] == "telea" and "423" in res["inpaint_fallback"]
    assert res["cloud_tx"] == 51                                    # 폴백해도 청구는 남는다


def test_the_erased_image_is_returned_for_f_and_not_stored():
    """★ F는 **지운 결과**를 잰다 — render가 넘기고, 벤치는 재고 나서 **버린다.**"""
    res = R.render(_bytes(_with_text(_flat())), [LINE], method="telea")
    assert res["erased_bytes"] and res["painted_boxes"] == [BOX]
    from src.services import image_translate_bench as B
    assert "pop" in calls_in(B._render_d3_for)


# ---------------------------------------------------------------------------
# ② F축 — 지운 자리가 주변과 닮았나
# ---------------------------------------------------------------------------

def test_f_is_an_auto_axis():
    assert "F" in A.AUTO_AXES and "F" not in A.HUMAN_AXES


def test_unerased_text_fails_f():
    """★★★ **판정 지점** — 글자를 안 지웠으면 F=0(색이 주변과 전혀 다르다)."""
    src = _bytes(_with_text(_flat()))
    got = R.background_score(src, src, [BOX])
    assert got["score"] == 0 and "색이 주변과 다릅니다" in got["reason"], got


def test_perfect_restoration_passes_f():
    """완벽 복원(글자만 사라진 배경) — 결 있는 배경에서도 1."""
    for base in (_flat(), _texture(0), _texture(1)):
        src = _bytes(_with_text(base))
        got = R.background_score(_bytes(base), src, [BOX])
        assert got["score"] == 1, got


def test_telea_that_loses_texture_fails_f():
    """★★★ 굵은 글자 + 결 있는 배경 — telea가 **결을 잃은** 자리를 F가 잡는다.

    교정 표(모듈 주석): telea 결 비 0.72~0.94, 완벽 복원 0.84~1.13.
    """
    src = _bytes(_with_text(_texture(0), size=60))
    erased, _n, why = R.erase_boxes(src, [BOX], method="telea")
    assert not why
    got = R.background_score(erased, src, [BOX])
    assert got["score"] == 0 and "결이 주변과 다릅니다" in got["reason"], got


def test_telea_on_a_flat_background_passes_f():
    """★★ F는 「telea면 0」이 아니다 — **결을 잃었으면 0**이다. 민 배경의 telea는 멀쩡하다."""
    src = _bytes(_with_text(_flat()))
    erased, _n, _w = R.erase_boxes(src, [BOX], method="telea")
    assert R.background_score(erased, src, [BOX])["score"] == 1


def test_a_resized_result_is_not_measured():
    """★ gen_remove는 6140px 넘으면 줄였다 키운다(문서) — 좌표가 어긋나면 **재지 않는다.**"""
    src = _bytes(_with_text(_flat()))
    from PIL import Image
    small = io.BytesIO()
    Image.new("RGB", (W // 2, H // 2), (240, 236, 228)).save(small, format="JPEG")
    got = R.background_score(small.getvalue(), src, [BOX])
    assert got["score"] is None and "크기" in got["reason"]


def test_tencent_f_is_unmeasurable_not_zero():
    """★★ 텐센트는 지운 중간본을 주지 않는다 — F를 **0으로 깎지 않는다.**"""
    assert "텐센트" in A.F_UNMEASURABLE_TENCENT
    from src.services import image_translate_bench as B
    from tests._ast_probe import names_in
    assert "F_UNMEASURABLE_TENCENT" in names_in(B._run)           # 벤치가 그 사유를 쓴다
    # 합계에서 **분모에 안 들어간다**(측정 불가는 0이 아니다)
    row = {"axes": A.auto_scores([], [])}
    row["axes"]["F"] = {"score": None, "reason": A.F_UNMEASURABLE_TENCENT}
    assert A.summarize([row])["F"]["unmeasured"] == 1


# ---------------------------------------------------------------------------
# ③ 장별 자동 선택
# ---------------------------------------------------------------------------

def _ax(a=1, b=1, d=1, f=None):
    s = lambda v: {"score": v, "reason": ""}                        # noqa: E731
    return {"A": s(a), "B": s(b), "D": s(d), "F": s(f)}


def test_only_axes_every_candidate_measured_are_summed():
    """★★★ 텐센트는 F를 못 잰다 — 잰 축만 더하면 D3가 **공짜로 1점** 먹는다. 공통 축만."""
    got = A.pick_best({"tencent": _ax(f=None), "d3": _ax(f=1)})
    assert got["common"] == ["A", "B", "D"]
    assert got["scores"] == {"tencent": 3, "d3": 3}


def test_the_higher_common_sum_wins():
    got = A.pick_best({"tencent": _ax(b=0), "d3": _ax(), "d3g": _ax(f=1)})
    assert got["pick"] in ("d3", "d3g") and got["scores"]["tencent"] == 2


def test_f_decides_between_the_two_d3s():
    """★★ 오너 판정 조건의 모양 — 같은 번역이면 **F가 가른다**(gen_remove가 결을 지키면 이긴다).

    D3 둘만 있으면 F는 **공통 축**이라 합에 들어간다.
    """
    got = A.pick_best({"d3": _ax(f=0), "d3g": _ax(f=1)})
    assert got["pick"] == "d3g" and "F" in got["common"]
    assert got["scores"] == {"d3": 3, "d3g": 4}


def test_f_breaks_the_tie_when_tencent_is_in_the_race():
    """텐센트가 끼면 F는 공통 축이 아니다 — 그땐 **동점 가르기**로만 쓴다(순서, 점수 아님)."""
    got = A.pick_best({"tencent": _ax(), "d3": _ax(f=0), "d3g": _ax(f=1)})
    assert got["common"] == ["A", "B", "D"]
    assert got["pick"] == "d3g" and "F로 갈랐" in got["reason"]


def test_a_known_good_background_beats_an_unmeasured_one():
    """F 순서: 통과 > 못 잼 > 실패 — 점수로 바꾸지 않고 **순서로만** 쓴다."""
    assert A.pick_best({"tencent": _ax(), "d3": _ax(f=1)})["pick"] == "d3"
    assert A.pick_best({"tencent": _ax(), "d3": _ax(f=0)})["pick"] == "tencent"


def test_a_full_tie_goes_to_the_cheapest():
    """동점이면 **돈이 덜 드는 쪽** — 텐센트(이미 냄) → telea(공짜) → gen_remove(크레딧)."""
    got = A.pick_best({"tencent": _ax(), "d3": _ax(), "d3g": _ax()})
    assert got["pick"] == "tencent"


def test_a_fallback_gen_remove_is_not_a_candidate():
    """★★ telea로 폴백한 gen_remove는 **telea 칸과 같은 그림**이다 — 두 번 세지 않는다."""
    from src.services.image_translate_bench import pick_candidates
    row = {"status": "done", "url": "t", "axes": _ax(),
           "d3": {"ok": True, "url": "d", "axes": _ax(f=1)},
           "d3g": {"ok": True, "url": "g", "axes": _ax(f=1), "inpainter": "telea"}}
    assert set(pick_candidates(row)) == {"tencent", "d3"}
    row["d3g"]["inpainter"] = "gen_remove"
    assert set(pick_candidates(row)) == {"tencent", "d3", "d3g"}


def test_a_failed_render_is_not_a_candidate():
    from src.services.image_translate_bench import pick_candidates
    row = {"status": "error", "url": "", "axes": _ax(),
           "d3": {"ok": False, "url": "", "axes": _ax()}}
    assert pick_candidates(row) == {}
    assert A.pick_best({})["pick"] == ""


def test_a_human_can_overturn_the_suggestion():
    """★★ 제안은 제안이다 — `pick:<장>` 칸에 사람이 고르면 **그게 등록본**이다."""
    from src.seller_console.views import _bench_grid
    run = {"results": [{"idx": 0, "status": "done", "url": "t", "axes": _ax(),
                        "d3": {"ok": True, "url": "d", "axes": _ax(f=1)}}],
           "scores": {"cells": {"pick:0": "tencent"}}}
    p = _bench_grid(run)["pages"][0]
    assert p["pick"]["suggested"] == "d3"
    assert p["pick"]["override"] == "tencent" and p["pick"]["chosen"] == "tencent"


def test_an_unknown_pick_value_is_ignored():
    from src.seller_console.views import _bench_grid
    run = {"results": [{"idx": 0, "status": "done", "url": "t", "axes": _ax()}],
           "scores": {"cells": {"pick:0": "whatever"}}}
    p = _bench_grid(run)["pages"][0]
    assert p["pick"]["override"] == "" and p["pick"]["chosen"] == "tencent"


def test_the_score_route_accepts_pick_and_d3g_cells():
    """저장 라우트가 새 칸 둘을 받는다 — `pick:`(문자열 후보명) · `d3g:`(C·E만)."""
    from src.seller_console import views
    from tests._ast_probe import string_constants_in
    consts = string_constants_in(views.image_translate_bench_score)
    assert "pick:" in consts and "d3g:" in consts


# ---------------------------------------------------------------------------
# 원가 줄 · 저장 자리
# ---------------------------------------------------------------------------

def test_the_cost_line_sums_known_charges_and_flags_unknown_ones():
    """★★ 모르는 장이 있으면 **합계를 단정하지 않는다** — 따로 센다."""
    from src.seller_console.views import _bench_grid
    res = [{"idx": i, "status": "done", "url": "t", "axes": _ax(),
            "d3": {"ok": True, "url": "d", "axes": _ax(), "llm": {}},
            "d3g": {"ok": True, "url": "g", "axes": _ax(), "inpainter": "gen_remove",
                    "cloud_tx": tx, "cloud_credits": None if tx is None else tx / 1000}}
           for i, tx in enumerate((51, 51, None))]
    cost = _bench_grid({"results": res, "scores": {}})["d3_cost"]
    assert cost["cloud_tx"] == 102 and cost["cloud_credits"] == 0.102
    assert cost["cloud_unknown"] == 1 and cost["gen_remove_pages"] == 3


def test_db_stored_bench_images_use_the_bench_route_with_their_kind(monkeypatch):
    """★★★ D3-5에서 찾은 구멍 — DB에 두면 저장소가 **셀러 경로**를 줬고, 그 라우트는
    `detail`이 아닌 kind를 **전부 gallery로** 읽었다(D3 칸에 텐센트 번역본이 떴다).
    """
    from src.services import image_translate_bench as B

    stored = []

    def _st(item_id, idx, b64, *, seller_id="", kind="gallery"):
        stored.append(kind)
        return {"url": f"/seller/collect/image-ko/{item_id}/{idx}?kind={kind}",
                "stored_by": "db", "note": ""}

    monkeypatch.setattr("src.services.image_translate_store.store_translated", _st)
    monkeypatch.setattr("src.services.image_translate_tencent.fetch_image",
                        lambda url: (_bytes(_with_text(_flat())), ""))
    monkeypatch.setattr(G, "configured", lambda: (True, ""))
    monkeypatch.setattr(G, "gen_remove", lambda b, r: {
        "ok": True, "image_bytes": _bytes(_flat()), "tx": 51, "credits": 0.051})

    class _T:
        def translate_product(self, src, *, style=""):
            return {"title_ko": "원문 글자", "provider": "openai", "style_applied": True}

    monkeypatch.setattr("src.seller_console.ai.translator.AITranslator", _T)
    lines = [{"source": "原文文字", "box": BOX}]
    out = B._run_d3_stage({"item_no": "X1"}, 0, {"url": "u"}, {"lines": lines}, "s",
                          gen_remove=True)
    assert stored == ["d3", "d3g"]
    assert out["url"] == "/seller/admin/image-translate-bench/image/X1/0?kind=d3"
    assert out["gen_remove"]["url"] == "/seller/admin/image-translate-bench/image/X1/0?kind=d3g"
    assert out["gen_remove"]["inpainter"] == "gen_remove"
    assert out["gen_remove"]["cloud_tx"] == 51
    assert "erased_bytes" not in out and "erased_bytes" not in out["gen_remove"]


def test_the_bench_image_route_opens_only_bench_kinds():
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"], s["email"], s["user_role"] = "o", "o@x", "admin"
        r = c.get("/seller/admin/image-translate-bench/image/X1/0?kind=gallery")
    assert r.status_code == 404                                    # 등록 자리는 안 연다


def test_gen_remove_is_opt_in_and_needs_d3():
    """★ 크레딧을 쓰므로 **따로 켠다** — 그리고 D3 없이 켜면 무시한다."""
    from src.seller_console.views import bench_run_id
    assert bench_run_id(0, True, True).endswith("-m0-d3g")
    assert bench_run_id(0, True, False).endswith("-m0-d3")
    assert bench_run_id(0, False, True).endswith("-m0")


# ---------------------------------------------------------------------------
# ④ 폰트 — 원문 기준선 전용, 렌더는 한글만
# ---------------------------------------------------------------------------

def test_the_source_font_draws_the_five_that_were_tofu():
    from src.services.image_render_font import supported, supported_source
    assert supported("绝轻纳线电") == ""                            # 렌더 폰트엔 여전히 없다
    assert supported_source("绝轻纳线电") == "绝轻纳线电"


def test_the_source_font_cannot_draw_korean():
    """★★ SC 서브셋엔 **한글이 없다** — 실수로 거기로 그리면 두부가 나온다. 그래서 막는다."""
    from src.services.image_render_font import supported_source
    assert supported_source("간편수납") == ""


def test_only_the_reference_render_opens_the_source_font():
    """★★★ 오너 계약 — **렌더는 한글만이라 영향 없음.** 원문 폰트는 기준선 자리 하나에서만 연다.

    ※ `_render_ref`는 로더를 **변수로 골라** 부른다(`loader = load_source_font if …`). 그래서
      「누가 부르나」가 아니라 **「누가 그 이름을 쥐나」**로 잰다 — 호출만 보면 아무도 안 부르는
      것처럼 보인다(실제로 처음엔 그렇게 헛것을 쟀다).
    """
    import inspect

    from tests._ast_probe import names_in
    holders = {name for name, fn in inspect.getmembers(R, inspect.isfunction)
               if fn.__module__ == R.__name__ and "load_source_font" in names_in(fn)}
    assert holders == {"_render_ref"}, holders
    for fn in (R.draw_lines, R.fit_text, R.render):
        assert "load_source_font" not in names_in(fn), fn.__name__


def test_korean_rendering_is_identical_without_the_source_font(monkeypatch):
    """★★★ 실행으로도 잰다 — SC 파일이 **없어도** 한국어 렌더 바이트는 똑같다."""
    from pathlib import Path

    from src.services import image_render_font as F
    src = _bytes(_flat())
    line = [{"render_text": "간편 수납", "box": BOX, "weight": "bold",
             "color": (20, 20, 20), "align": "center"}]
    before, n1, _ = R.draw_lines(src, line)
    monkeypatch.setattr(F, "source_font_path", lambda: Path("/nonexistent/sc.ttf"))
    after, n2, _ = R.draw_lines(src, line)
    assert n1 == n2 == 1 and before == after


def test_the_subset_is_gb2312_and_keeps_both_weights():
    """서브셋은 **손으로 고르지 않았다** — GB2312(간체 표준)를 코덱에서 열거했다.

    GB2312 한자 구간의 처음·끝·중간을 **코덱으로 뽑아** 잰다. 그리고 GB2312 **밖의** 글자는
    없어야 한다 — 있으면 서브셋이 아니라 원본 17MB가 들어온 것이다.
    """
    from src.services.image_render_font import load_source, source_font_path, supported_source
    assert source_font_path().is_file()
    assert load_source(40, "regular") is not None and load_source(40, "bold") is not None

    sample = "".join(bytes([hi, lo]).decode("gb2312")
                     for hi, lo in ((0xB0, 0xA1), (0xC8, 0xD0), (0xD7, 0xF9), (0xF7, 0xFE)))
    assert supported_source(sample) == sample, sample
    assert supported_source("龘") == ""                            # GB2312 밖 — 안 들어왔다


def test_when_no_axis_is_common_the_reason_says_f_decided():
    """★★ 흔한 경우 — 브랜드·관용구·영문 UI가 없는 장은 A·B·D가 **전부 측정 불가**다.

    그땐 F와 돈만으로 고른 것이다. 「합 0」을 점수처럼 보이게 쓰지 않는다.
    """
    none = {"score": None, "reason": ""}
    ax = lambda f: {"A": none, "B": none, "D": none, "F": {"score": f, "reason": ""}}  # noqa: E731
    got = A.pick_best({"tencent": ax(None), "d3": ax(0), "d3g": ax(1)})
    assert got["common"] == [] and got["pick"] == "d3g"
    assert "함께 잰 자동축이 없습니다" in got["reason"] and "F로 갈랐" in got["reason"]
    assert "합 0" not in got["reason"]
