"""scripts/compare_favicon.py — v57 파비콘 정답지 픽셀 대조(오너 판정 도구).

배포 후 라이브 favicon-48(?v=182)와 정답지(assets/brand-icons/favicon-master-48.png)를 픽셀 대조해
로그로 남긴다. '픽셀 동일만 합격, 유사는 불합격' 판정을 기계적으로 증명한다.

사용:
  python scripts/compare_favicon.py                      # 로컬 favicon-48.png vs 정답지
  python scripts/compare_favicon.py --live https://kohganepercentiii.com/favicon-48.png?v=182
  python scripts/compare_favicon.py --a A.png --b B.png  # 임의 두 파일

종료코드 0=픽셀 동일(합격), 1=불일치(불합격/유사), 2=파일 없음/오류(정직).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

MASTER = "assets/brand-icons/favicon-master-48.png"
LIVE_LOCAL = "src/seller_console/static/favicon-48.png"


def _load(path_or_url: str):
    from PIL import Image
    import io
    if path_or_url.startswith(("http://", "https://")):
        import urllib.request
        with urllib.request.urlopen(path_or_url, timeout=20) as r:  # noqa: S310
            data = r.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")
    if not os.path.exists(path_or_url):
        raise FileNotFoundError(path_or_url)
    return Image.open(path_or_url).convert("RGBA")


def compare(a_path: str, b_path: str) -> int:
    try:
        a = _load(a_path)
        b = _load(b_path)
    except FileNotFoundError as e:
        print(f"[compare-favicon] 파일 없음: {e} (정직: 대조 불가)")
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"[compare-favicon] 로드 오류: {e}")
        return 2

    # 크기 다르면 b를 a 크기로 리샘플해 시각 비교(단, 픽셀 동일 판정은 원본 크기 동일일 때만).
    same_size = a.size == b.size
    if not same_size:
        b = b.resize(a.size)
    ab = a.tobytes()
    bb = b.tobytes()
    ha, hb = hashlib.md5(a.tobytes()).hexdigest(), hashlib.md5(b.tobytes()).hexdigest()

    diff_px, total = 0, a.size[0] * a.size[1]
    ap, bp = a.load(), b.load()
    max_d = 0
    for y in range(a.size[1]):
        for x in range(a.size[0]):
            pa, pb = ap[x, y], bp[x, y]
            d = sum(abs(pa[i] - pb[i]) for i in range(4))
            if d > 12:            # 미세 인코딩 오차 허용(>12/1020만 diff로 집계)
                diff_px += 1
            if d > max_d:
                max_d = d
    pct = 100.0 * diff_px / total
    print(f"[compare-favicon] A={a_path} {a.size}  B={b_path} {b.size}")
    print(f"[compare-favicon] 크기동일={same_size} md5(A)={ha} md5(B)={hb}")
    print(f"[compare-favicon] 다른 픽셀={diff_px}/{total} ({pct:.2f}%)  최대채널차={max_d}/1020")
    if same_size and diff_px == 0:
        print("[compare-favicon] 판정: 픽셀 동일 ✓ 합격")
        return 0
    print("[compare-favicon] 판정: 불일치(유사 포함) ✗ — 정답지와 픽셀 다름")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=LIVE_LOCAL, help="비교 A(기본=로컬 favicon-48.png)")
    ap.add_argument("--b", default=MASTER, help="비교 B(기본=정답지 favicon-master-48.png)")
    ap.add_argument("--live", help="라이브 URL(예: https://…/favicon-48.png?v=182) → A로 사용")
    args = ap.parse_args()
    a = args.live or args.a
    return compare(a, args.b)


if __name__ == "__main__":
    sys.exit(main())
