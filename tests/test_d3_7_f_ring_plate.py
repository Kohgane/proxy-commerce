"""D3-7 — F축 링을 **판(알약) 안쪽**으로 제한 (오너 2026-09-26: 「박스 밖 픽셀 중 알약 내부」).

실측(PaddleOCR 스파이크 중 발견): 알약 위 글자는 링 16px이 알약 밖 **흰 바탕**까지 걸쳐, 잘 지운 장과
못 지운 장이 **둘 다 F=0**이었다 — 축이 아무것도 가르지 못했다.

| 장 | 전(링=팽창 16px) | 후(링=판 안쪽) |
|---|---|---|
| 알약 · 글자만 깨끗이 지움 | 0 (링이 흰 바탕과 섞임) | **1** |
| 알약 · 회색 찌꺼기 남김 | 0 | **0** |
| 판 없는 민 배경 | 기존과 같음 | 기존과 같음(`ring_scope=dilate`) |
"""
from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from src.services import image_text_render as R  # noqa: E402

BLUE = (200, 110, 30)          # BGR
BOX = {"x": 30, "y": 40, "w": 240, "h": 80}     # 텐센트 박스가 알약보다 크다(실측 모양)


def _png(img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _pill(text: bool, blob: bool = False):
    img = np.full((160, 300, 3), 255, np.uint8)
    cv2.rectangle(img, (70, 52), (230, 108), BLUE, -1)
    cv2.circle(img, (70, 80), 28, BLUE, -1)
    cv2.circle(img, (230, 80), 28, BLUE, -1)
    if text:
        cv2.putText(img, "ABC 123", (88, 92), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3, cv2.LINE_AA)
    if blob:
        cv2.rectangle(img, (88, 66), (212, 96), (170, 170, 170), -1)
    return img


def test_clean_erase_on_a_pill_passes():
    got = R.background_score(_png(_pill(False)), _png(_pill(True)), [BOX])
    assert got["score"] == 1, got
    assert got["hits"][0]["ring_scope"] == "plate"


def test_leftover_on_a_pill_still_fails():
    got = R.background_score(_png(_pill(False, blob=True)), _png(_pill(True)), [BOX])
    assert got["score"] == 0, got
    assert got["hits"][0]["ring_scope"] == "plate"


def test_no_plate_keeps_the_old_ring():
    img = np.full((160, 300, 3), 245, np.uint8)
    src = img.copy()
    cv2.putText(src, "ABC 123", (60, 92), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 20, 20), 3, cv2.LINE_AA)
    got = R.background_score(_png(img), _png(src), [BOX])
    assert got["score"] == 1 and got["hits"][0]["ring_scope"] == "dilate"
