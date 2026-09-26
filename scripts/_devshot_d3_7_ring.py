"""D3-7 캡처 — F축 링 영역 전/후(빨강=링). 테스트와 같은 합성 알약 이미지(tests/test_d3_7_f_ring_plate.py).

전: 글자 마스크를 16px 팽창한 링 — 알약 밖 흰 바탕까지 걸친다. 후: 판(알약) 안쪽만.
"""
import sys
import cv2
import numpy as np

sys.path.insert(0, ".")
from src.services import image_text_render as R          # noqa: E402
from tests.test_d3_7_f_ring_plate import BOX, _pill       # noqa: E402

src = _pill(True)
h, w = src.shape[:2]
rect = R._norm_box(BOX, w, h)
gm, _ = R._glyph_mask(cv2, np, src, rect, 2)
k = np.ones((R.F_RING_PX * 2 + 1, R.F_RING_PX * 2 + 1), np.uint8)
old = (cv2.dilate(gm, k) > 0) & (gm == 0)
new = old & (R._plate_interior(cv2, np, src, rect) > 0)


def paint(mask, label):
    img = src.copy()
    img[mask] = (0.45 * img[mask] + 0.55 * np.array([40, 40, 220])).astype(np.uint8)
    cv2.rectangle(img, (BOX["x"], BOX["y"]), (BOX["x"] + BOX["w"], BOX["y"] + BOX["h"]), (60, 60, 60), 1)
    cv2.putText(img, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (30, 30, 30), 1, cv2.LINE_AA)
    return img


out = np.vstack([paint(old, "before: dilate 16px - clean 0 / leftover 0"),
                 np.full((6, w, 3), 200, np.uint8),
                 paint(new, "after: inside plate - clean 1 / leftover 0")])
cv2.imwrite("docs/screens/d3_7/f-ring-before-after.png", cv2.resize(out, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
print("saved")
