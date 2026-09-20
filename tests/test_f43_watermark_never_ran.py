"""F43 계약 — 워터마크 제거는 **라이브에서 돈 적이 없다**. 그걸 화면이 말하게 한다.

## 실측 (2026-09-20)

`cv2`가 `requirements.txt`·`Dockerfile` **어디에도 없었다**(grep 0). 프로덕션 이미지엔
OpenCV가 없었고 `src/media/image_pipeline.py`의 두 함수는 `ImportError`를
**`logger.debug`로 삼키고** `False`/원본을 돌려줬다. Render는 INFO 이상만 남기니
**아무 데도 안 보였다.**

결과 dict은 `watermark_detected: False`라고 말했다. 그건 거짓말은 아니지만
**「없다고 확인했다」로 읽힌다** — 실제로는 **재지 않았다.**

> 같은 유형 재발이다. `Pillow`도 requirements 미기재로 조용히 무력이었다(카나리 3차).
> 「함수 안 import + except로 삼키기」는 **기능이 죽어도 아무도 모르게** 만든다.

## 이 파일이 재는 것

| # | 계약 |
|---|---|
| 1 | 못 쟀으면 **사유가 나온다** — `watermark_checked=False` + `watermark_reason` |
| 2 | 쟀으면 `watermark_checked=True`이고 사유는 **비어 있다** |
| 3 | 못 잰 사유는 **WARNING**으로 운다 (debug 아님 = 라이브에서 보인다) |
| 4 | 통계 분모가 「잰 것」이다 — `watermark_checked` 카운트 |
| 5 | **cv2가 이미지에 들어와도 동작은 그대로다** — `IMAGE_INPAINT_ENABLED` 기본 off |

★ 5번이 이 트랙의 핵심이다. D3-3이 `opencv-python-headless`를 넣으면서 이 경로가
**처음으로 살아날 수 있게** 됐다. 검토 없이 살아나면 그건 회귀다(모서리 inpaint가
상품 사진을 건드린다). **지금까지 실제로 벌어진 일과 똑같이** 두고, 켜는 건 오너가 한다.
"""
from __future__ import annotations

import importlib
import logging
import re
from pathlib import Path

import pytest

from src.media import image_pipeline as P

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1·2) 「안 쟀다」와 「재고 없었다」가 다른 값이다
# ---------------------------------------------------------------------------

def test_a_missing_cv2_says_so_instead_of_answering_no(monkeypatch):
    """★★ cv2가 없으면 **「없다」가 아니라 「모른다」**로 나온다."""
    monkeypatch.setattr(P, "_load_cv2", lambda: (None, None, "OpenCV(cv2) 미설치 — 재지 못했습니다"))
    detected, reason = P._detect_watermark(b"\xff\xd8\xff")
    assert detected is False
    assert "미설치" in reason


def test_a_real_measurement_leaves_no_reason():
    """★ 사유가 **비어 있을 때만** 「쟀다」는 뜻이다."""
    cv2, np, why = P._load_cv2()
    if why:
        pytest.skip("이 환경에 cv2가 없다 — 실측 경로는 CI 이미지에서 잰다")
    # 1×1 흰 점 JPEG를 만들어 실제로 재게 한다(목 아님).
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (255, 255, 255)).save(buf, format="JPEG")
    detected, reason = P._detect_watermark(buf.getvalue())
    assert reason == "", reason
    assert isinstance(detected, bool)


def test_the_result_carries_both_the_answer_and_whether_it_was_measured():
    r = P.ImageProcessResult(original_url="u", processed_url="u")
    d = r.to_dict()
    assert "watermark_checked" in d
    assert "watermark_reason" in d
    assert d["watermark_checked"] is False   # 기본은 「안 쟀다」 — 안전한 쪽


def test_an_inpaint_failure_returns_the_original_and_says_why(monkeypatch):
    """★ 못 지웠는데 **지웠다고 말하지 않는다.**"""
    monkeypatch.setattr(P, "_load_cv2", lambda: (None, None, "cv2 없음"))
    out, removed, why = P._inpaint_watermark(b"ORIGINAL")
    assert out == b"ORIGINAL"
    assert removed is False
    assert why


# ---------------------------------------------------------------------------
# 3) 사유가 라이브에서 보인다
# ---------------------------------------------------------------------------

def test_the_missing_module_is_logged_at_warning_not_debug(monkeypatch, caplog):
    """★★ 이게 F43의 근원이다 — **debug는 Render 로그에 안 남는다.**"""
    monkeypatch.setattr(P, "_CV2_WARNED", False)
    real_import = __import__

    def _no_cv2(name, *a, **kw):
        if name == "cv2":
            raise ImportError("No module named 'cv2'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", _no_cv2)
    with caplog.at_level(logging.WARNING, logger=P.logger.name):
        _, _, reason = P._load_cv2()
    assert reason
    assert any(r.levelno >= logging.WARNING for r in caplog.records), caplog.text


def test_the_source_no_longer_swallows_importerror_into_debug():
    """★ 같은 유형 재발 방지 — 이 파일에 「debug로 삼키는 ImportError」가 없다."""
    lines = (ROOT / "src" / "media" / "image_pipeline.py").read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        if not re.match(r"\s*except ImportError\b", ln):
            continue
        for nxt in lines[i + 1:]:                 # 그 핸들러 본문만 — 다음 except에서 끊는다
            if re.match(r"\s*except\b", nxt):
                break
            assert "logger.debug" not in nxt, f"{i + 1}행 핸들러: {nxt}"


# ---------------------------------------------------------------------------
# 4) 분모는 잰 것만
# ---------------------------------------------------------------------------

def test_the_stats_count_what_was_actually_measured():
    """★ 「검출 0건」은 **0/0일 때 아무 뜻도 없다.**"""
    rows = [
        P.ImageProcessResult("a", "a", watermark_checked=True, watermark_detected=False),
        P.ImageProcessResult("b", "b", watermark_checked=False, watermark_reason="cv2 없음"),
    ]
    s = P.image_pipeline_stats(rows)
    assert s["watermark_checked"] == 1
    assert s["watermark_detected"] == 0


# ---------------------------------------------------------------------------
# 5) ★★ cv2가 들어와도 라이브 동작은 그대로다
# ---------------------------------------------------------------------------

def test_watermark_removal_stays_off_unless_someone_turns_it_on(monkeypatch):
    """★★ D3-3이 cv2를 이미지에 넣는다. **그것만으로 켜지면 회귀다.**

    이 기능은 지금껏 한 번도 돈 적이 없다 — 기본값을 **실제로 벌어진 일**에 맞춘다.
    """
    monkeypatch.delenv("IMAGE_INPAINT_ENABLED", raising=False)
    mod = importlib.reload(P)
    try:
        assert mod._INPAINT_ENABLED is False
    finally:
        importlib.reload(P)


def test_turning_it_on_is_one_env_var(monkeypatch):
    monkeypatch.setenv("IMAGE_INPAINT_ENABLED", "1")
    mod = importlib.reload(P)
    try:
        assert mod._INPAINT_ENABLED is True
    finally:
        monkeypatch.delenv("IMAGE_INPAINT_ENABLED", raising=False)
        importlib.reload(P)


def test_a_disabled_run_says_it_is_disabled_not_that_there_was_no_watermark(monkeypatch):
    """★★ 꺼져 있는 것과 없는 것도 **다른 값**이다."""
    monkeypatch.setattr(P, "_INPAINT_ENABLED", False)
    monkeypatch.setattr(P, "_resize_and_crop", lambda b, *a, **k: b)
    monkeypatch.setattr(P, "_convert_to_webp", lambda b: b)
    monkeypatch.setattr(P, "_upload_to_cdn", lambda *a, **k: None)

    class _Resp:
        def read(self):
            return b"BYTES"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    res = P.process_image("https://x.example/a.jpg")
    assert res.watermark_checked is False
    assert "꺼져" in res.watermark_reason


# ---------------------------------------------------------------------------
# 셀러 화면 — 개발 표기 없이 사실만
# ---------------------------------------------------------------------------

def test_the_seller_screen_distinguishes_unchecked_from_clean():
    """★ 라우트가 「확인하지 않았습니다」를 말한다 — 조용한 False가 아니라."""
    src = (ROOT / "src" / "seller_console" / "views.py").read_text(encoding="utf-8")
    i = src.index("def media_process_image")
    body = src[i:i + 2600]
    assert "watermark_checked" in body
    assert "확인하지 않았습니다" in body
    # 모듈명(cv2/OpenCV)은 **셀러 화면 문자열에 없다** — 로그로만.
    assert "OpenCV" not in body and "cv2" not in body
