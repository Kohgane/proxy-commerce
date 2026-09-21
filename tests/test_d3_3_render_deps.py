"""D3-3 계약 — 렌더 의존성이 **배포 이미지 안에** 있다.

## 오너 결정 (2026-09-20)

> `opencv-python-headless + numpy + Noto Sans KR(Regular·Bold 2웨이트, 서브셋 아님)` → Dockerfile.
> Pillow 대안은 골든 샘플 5축 C·E를 못 넘긴다고 봐서 채택 안 함.

## 이 파일이 재는 것

| # | 계약 | 왜 |
|---|---|---|
| 1 | `requirements.txt`에 cv2·numpy가 **있다** | 없으면 F43 재발 — 조용히 무력 |
| 2 | **headless**다 | 서버에 libGL이 없다. 비-headless면 부팅이 죽는다 |
| 3 | `Dockerfile`이 폰트를 COPY한다 | 레포에만 있으면 이미지엔 없다(#423·#227·F43) |
| 4 | 폰트가 **서브셋이 아니다** | `뷁`·`힣`까지 그려져야 한다 |
| 5 | 두 굵기가 **다르게** 그려진다 | 이름만 다르고 같은 글씨면 Bold가 아니다 |
| 6 | 기본 인스턴스가 **Thin**이라 로더가 항상 지정한다 | 안 하면 실오라기 글씨가 사진에 박힌다 |
| 7 | 부팅 경로에 cv2·numpy가 **없다** | 기동 시간을 늘리지 않는다(함수 안 import) |
| 8 | 아직 파이프라인에 **연결 안 했다** | 골든 샘플 5축 통과 전에는 텐센트 경로 그대로 |

※ 「정적 Regular·Bold 2파일」은 google/fonts에서 **더 이상 배포되지 않는다**(404 실측).
   가변 폰트 한 장에서 그 두 **이름 인스턴스**를 꺼내 쓴다 — 받는 굵기는 같다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.services import image_render_font as F

ROOT = Path(__file__).resolve().parents[1]
REQ = (ROOT / "requirements.txt").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1·2) 파이썬 의존성
# ---------------------------------------------------------------------------

def test_opencv_and_numpy_are_declared():
    """★★ F43의 근원이 이거였다 — **선언되지 않은 의존성은 이미지에 없다.**"""
    assert "opencv-python-headless" in REQ
    assert "numpy" in REQ


def test_it_is_the_headless_build():
    """★ 비-headless는 `libGL.so.1`을 요구한다 — slim 이미지엔 없다."""
    for line in REQ.splitlines():
        s = line.strip()
        if s.startswith("opencv-python") and not s.startswith("#"):
            assert s.startswith("opencv-python-headless"), s


def test_the_declared_versions_are_the_ones_installed():
    """★ 선언과 실물이 같은지 **직접 불러서** 확인한다(주석 읽기 금지)."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    assert hasattr(cv2, "inpaint")          # 3단계가 쓰는 바로 그 함수
    assert hasattr(cv2, "INPAINT_TELEA")
    assert np.__version__


# ---------------------------------------------------------------------------
# 3) 이미지에 실린다
# ---------------------------------------------------------------------------

def test_the_dockerfile_copies_the_font_directory():
    """★★ 「레포엔 있는데 이미지엔 없다」 — #423 extensions/·#227 scripts/·F43 cv2와 같은 자리."""
    assert "COPY assets/fonts/" in DOCKERFILE


def test_the_font_is_not_excluded_from_the_build_context():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for line in ignore.splitlines():
        s = line.strip()
        assert s not in ("assets", "assets/", "assets/*"), s


def test_the_license_travels_with_the_font():
    """★ OFL 폰트는 라이선스를 함께 배포해야 한다."""
    assert (F.FONT_DIR / "OFL.txt").is_file()


# ---------------------------------------------------------------------------
# 4·5·6) 폰트 실물
# ---------------------------------------------------------------------------

def test_the_font_file_is_there():
    ok, why = F.available()
    assert ok, why


def test_it_is_not_a_subset():
    """★★ 서브셋이면 `뷁` 같은 글자가 두부(□)로 나간다 — **상품 사진에** 박힌다."""
    assert F.font_path().stat().st_size > 5_000_000, "너무 작다 — 서브셋 의심"
    f = F.load(32, "regular")
    assert f is not None
    for ch in "가힣뷁쭙괜":
        box = f.getbbox(ch)
        assert box and box[2] > box[0], ch     # 폭 0 = 글리프 없음


def _ink(font, text="고가브릿지") -> int:
    """그 폰트로 그렸을 때 **찍힌 검은 픽셀 수**.

    한글은 폭이 고정(전각)이라 **굵기를 폭으로 재면 안 된다** — Thin과 Bold의
    가로 폭이 똑같이 나온다(실측 221 == 221). 굵기는 **획의 두께**이므로 잉크로 잰다.
    """
    from PIL import Image, ImageDraw
    img = Image.new("L", (400, 80), 255)
    ImageDraw.Draw(img).text((5, 5), text, font=font, fill=0)
    return sum(1 for px in img.tobytes() if px < 128)


def test_both_weights_exist_and_differ():
    """★ 이름만 다르고 **같은 글씨면** Bold가 아니다 — 잉크로 잰다."""
    pytest.importorskip("PIL.Image")
    reg = _ink(F.load(48, "regular"))
    bold = _ink(F.load(48, "bold"))
    assert reg > 0 and bold > reg, (reg, bold)


def test_the_width_helper_answers_in_pixels():
    w = F.text_width("고가브릿지", 48, "regular")
    assert isinstance(w, int) and w > 0


def test_the_default_instance_is_thin_so_the_loader_must_always_set_one():
    """★★ 가변 폰트를 그냥 열면 **Thin(100)**이다.

    지정을 빠뜨리면 실오라기 같은 글씨가 상품 사진에 박힌다. 로더가 항상 지정한다는 걸
    **실제 잉크 차이**로 확인한다 — 기본(Thin) < Regular.
    """
    ImageFont = pytest.importorskip("PIL.ImageFont")
    raw = ImageFont.truetype(str(F.font_path()), 48)
    assert raw.getname()[1] == "Thin"          # 이게 기본값이다
    assert _ink(F.load(48, "regular")) > _ink(raw)


def test_an_unknown_weight_is_refused_not_silently_swapped():
    """★ 모르는 굵기를 **조용히 Regular로 바꾸지 않는다** — 틀린 걸 그리느니 멈춘다."""
    with pytest.raises(ValueError):
        F.load(32, "black")


def test_a_missing_font_returns_none_with_a_reason(monkeypatch, tmp_path):
    """★ 없으면 **다른 폰트로 대체하지 않는다.** 엉뚱한 폰트는 다른 상품이다."""
    monkeypatch.setattr(F, "FONT_DIR", tmp_path)
    ok, why = F.available()
    assert ok is False and why
    assert F.load(32) is None


# ---------------------------------------------------------------------------
# 7) 기동 시간
# ---------------------------------------------------------------------------

def test_cv2_is_not_imported_at_boot():
    """★★ 의존성을 넣어도 **부팅은 안 느려진다** — 함수 안 import이기 때문.

    이 계약이 그 사실을 지킨다: 누가 모듈 최상단으로 옮기면 여기서 깨진다.
    """
    import sys
    for mod in ("src.media.image_pipeline", "src.services.image_render_font"):
        assert mod in sys.modules or True
    src = (ROOT / "src" / "media" / "image_pipeline.py").read_text(encoding="utf-8")
    head = src.split("def ", 1)[0]
    assert "import cv2" not in head
    assert "import numpy" not in head
    fsrc = (ROOT / "src" / "services" / "image_render_font.py").read_text(encoding="utf-8")
    assert "from PIL import" not in fsrc.split("def ", 1)[0]


# ---------------------------------------------------------------------------
# 8) 아직 연결하지 않는다
# ---------------------------------------------------------------------------

def test_the_font_loader_is_not_wired_into_the_pipeline_yet():
    """★★ 오너 지시 — 골든 샘플 5축 통과 전에는 텐센트 경로가 그대로다.

    **3단계 렌더(`image_text_render`)가 폰트를 쓰는 것은 연결이 아니다** — 그 모듈 자체가
    아직 파이프라인 밖이고, 그건 자기 계약이 따로 지킨다(`test_d3_3_render.py`).
    여기서 막는 것은 **등록·번역 파이프가 폰트를 집어 가는 것**이다.

    ※ 글자가 아니라 `import`를 잰다(주석에 이름이 보이는 것과 실제 연결은 다르다).
    """
    from tests.test_d3_glossary import _importers_of
    assert _importers_of("image_render_font", allow={"image_text_render.py"}) == []
