"""scripts/build_icons.py — 고가브릿지 브랜드 아이콘 v8을 코드로 생성(이미지 의존 0).

스펙(1024 캔버스, 중심 cx=512):
- 흰 배경 + 먹(#1A1714) 라운드 보더(radius 190, 두께 26)
- 게이트 아치(골드 #C9A24B, 중심선 반지름 165, 선폭 34, 중심 y=430, 상단 틈 반각 0.235rad,
  다리 2개가 x=중심±165로 데크 관통해 y=708)
- 키스톤(주황 #F5821F, 반지름 29, 틈 정중앙)
- 뾰족 타워 + 2단 받침대(x=252,772)
- 틸(#119A8E) 데크 2줄(y=612,664)
- 케이블(딥골드 #B28C3A, 폭 18): 오목 사이드스팬 + 타워탑(y=328) 사이 깊은 처짐(제어점 y=676)

산출: favicon.ico(16/32/48) + PNG 16/32/48/128/180/192/512/1024.
Pillow 필요(빌드타임 전용) — CI(collect-only)에서 import 안 되게 함수 내 지연 import.
"""
from __future__ import annotations

import math
import os

SIZE = 1024
S = 4  # supersample

INK = (0x1A, 0x17, 0x14)
GOLD = (0xC9, 0xA2, 0x4B)
ORANGE = (0xF5, 0x82, 0x1F)
TEAL = (0x11, 0x9A, 0x8E)
DEEPGOLD = (0xB2, 0x8C, 0x3A)
WHITE = (255, 255, 255)

CX = 512
ARCH_R = 165
ARCH_CY = 430
TOWER_X = (252, 772)
TOWER_TOP_Y = 328
DECK_Y = (612, 664)
DECK_X0, DECK_X1 = 150, 874


def _quad(p0, p1, p2, n=72):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return pts


def build_simple():
    """≤48px 소형 전용 고대비 변형 — 얇은 케이블/타워는 뭉개지므로 생략하고 굵은 게이트
    아치 + 큰 주황 키스톤 + 굵은 틸 데크만(색상 정체성 유지, 소형 가독). 흰 배경 통일."""
    from PIL import Image, ImageDraw
    W = SIZE * S
    img = Image.new("RGB", (W, W), WHITE)
    d = ImageDraw.Draw(img)

    def box(x0, y0, x1, y1):
        return [x0 * S, y0 * S, x1 * S, y1 * S]

    def P(pt):
        return (pt[0] * S, pt[1] * S)

    def dot(c, r, color):
        d.ellipse(box(c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=color)

    d.rounded_rectangle(box(38, 38, 986, 986), radius=int(190 * S), outline=INK, width=int(44 * S))
    # 굵은 골드 게이트 아치(전체 원 - 상단 틈) + 짧은 다리
    R, cy = 205, 470
    gap = math.degrees(0.235)
    d.arc(box(CX - R, cy - R, CX + R, cy + R), 270 + gap, 270 - gap + 360, fill=GOLD, width=int(76 * S))
    for lx in (CX - R, CX + R):
        d.line([P((lx, cy)), P((lx, 760))], fill=GOLD, width=int(76 * S))
    # 굵은 틸 데크 2줄(소형서 뭉개지지 않게 두껍게 — 16px서도 청록 생존)
    for dy in (622, 726):
        d.line([P((140, dy)), P((884, dy))], fill=TEAL, width=int(84 * S))
    # 큰 주황 키스톤
    dot((CX, cy - R), 70, ORANGE)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def build_master(simple=False):
    """1024 마스터 이미지를 코드로 렌더(4x 슈퍼샘플 후 축소). simple=True면 소형 고대비 변형."""
    if simple:
        return build_simple()
    from PIL import Image, ImageDraw
    W = SIZE * S
    img = Image.new("RGB", (W, W), WHITE)
    d = ImageDraw.Draw(img)

    def P(pt):
        return (pt[0] * S, pt[1] * S)

    def box(x0, y0, x1, y1):
        return [x0 * S, y0 * S, x1 * S, y1 * S]

    def tline(pts, color, w, joint="curve"):
        d.line([P(p) for p in pts], fill=color, width=int(round(w * S)), joint=joint)

    def dot(c, r, color):
        d.ellipse(box(c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=color)

    def leg(x, y0, y1, w, color):
        # 라운드 캡 세로 다리
        d.line([P((x, y0)), P((x, y1))], fill=color, width=int(w * S))
        r = w / 2.0
        dot((x, y0), r, color)
        dot((x, y1), r, color)

    # 1) 먹 라운드 보더
    d.rounded_rectangle(box(40, 40, 984, 984), radius=int(190 * S), outline=INK, width=int(26 * S))

    # 3) 케이블(딥골드) — 구조 뒤에 먼저
    TL, TR = (TOWER_X[0], TOWER_TOP_Y), (TOWER_X[1], TOWER_TOP_Y)
    tline(_quad(TL, (176, 522), (DECK_X0, DECK_Y[0])), DEEPGOLD, 18)   # 좌 사이드스팬(오목)
    tline(_quad(TR, (848, 522), (DECK_X1, DECK_Y[0])), DEEPGOLD, 18)   # 우 사이드스팬(오목)
    tline(_quad(TL, (CX, 676), TR), DEEPGOLD, 18)                       # 타워탑 사이 깊은 처짐

    # 4) 뾰족 타워 + 2단 받침대(x=252,772)
    for tx in TOWER_X:
        leg(tx, 356, 760, 20, GOLD)                                     # 샤프트
        d.polygon([P((tx, TOWER_TOP_Y)), P((tx - 15, 372)), P((tx + 15, 372))], fill=GOLD)  # 뾰족 top
        d.rectangle(box(tx - 34, 726, tx + 34, 750), fill=GOLD)         # 받침 1단
        d.rectangle(box(tx - 54, 750, tx + 54, 776), fill=GOLD)         # 받침 2단

    # 5) 게이트 아치(전체 원 - 상단 틈) + 다리
    gap = math.degrees(0.235)
    d.arc(box(CX - ARCH_R, ARCH_CY - ARCH_R, CX + ARCH_R, ARCH_CY + ARCH_R),
          270 + gap, 270 - gap + 360, fill=GOLD, width=int(34 * S))
    for lx in (CX - ARCH_R, CX + ARCH_R):                               # 347,677
        leg(lx, ARCH_CY, 708, 34, GOLD)

    # 6) 틸 데크 2줄(다리 앞)
    for dy in DECK_Y:
        d.line([P((DECK_X0, dy)), P((DECK_X1, dy))], fill=TEAL, width=int(20 * S))

    # 7) 키스톤(주황) — 최상단 틈 정중앙
    dot((CX, ARCH_CY - ARCH_R), 29, ORANGE)

    return img.resize((SIZE, SIZE), Image.LANCZOS)


def build_all(outdir):
    """마스터에서 전 사이즈 PNG + favicon.ico 파생(임의 디렉토리, 미리보기용)."""
    from PIL import Image
    os.makedirs(outdir, exist_ok=True)
    master = build_master()
    master.save(os.path.join(outdir, "icon-master-1024.png"))
    for s in [16, 32, 48, 128, 180, 192, 512, 1024]:
        master.resize((s, s), Image.LANCZOS).save(os.path.join(outdir, f"icon-{s}.png"))
    master.resize((48, 48), Image.LANCZOS).save(
        os.path.join(outdir, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    return master


def _rs(master, s):
    from PIL import Image
    return master.resize((s, s), Image.LANCZOS)


def deploy(root="."):
    """레포의 실제 아이콘 위치를 전부 v8로 교체(단일 소스=이 스크립트의 코드 지오메트리)."""
    import base64
    import io
    master = build_master(simple=False)
    small = build_master(simple=True)     # ≤48 고대비 변형(소형 가독)
    static = os.path.join(root, "src/seller_console/static")
    ext = os.path.join(root, "extensions/chrome-collector/icons")
    assets = os.path.join(root, "assets/brand-icons")
    for d in (static, ext, assets):
        os.makedirs(d, exist_ok=True)

    # 앱 static — 소형(16/32/48)은 고대비 변형, 대형은 풀 디테일
    _rs(small, 16).save(f"{static}/favicon-16.png")
    _rs(small, 32).save(f"{static}/favicon-32.png")
    _rs(small, 48).save(f"{static}/favicon-48.png")
    for s in (180, 192, 512, 1024):
        _rs(master, s).save(f"{static}/icon-{s}.png")
    _rs(master, 180).save(f"{static}/apple-touch-icon.png")
    _rs(small, 48).save(f"{static}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    # favicon.svg — 마스터 래스터(512) data-URI 임베드(스케일러블 선언 유지, 경량)
    buf = io.BytesIO()
    _rs(master, 512).save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
        'viewBox="0 0 512 512" role="img" aria-label="gogabridj bridge gateway mark">\n'
        f'  <image width="512" height="512" href="data:image/png;base64,{b64}"/>\n'
        '</svg>\n'
    )
    with open(f"{static}/favicon.svg", "w", encoding="utf-8") as f:
        f.write(svg)
    # 마스터 단일 소스 벤더링
    master.save(f"{assets}/icon-master-1024.png")

    # 확장 아이콘 — 16/32/48 고대비 변형, 128 풀
    for s in (16, 32, 48):
        _rs(small, s).save(f"{ext}/{s}.png")
    _rs(master, 128).save(f"{ext}/128.png")

    return master


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "deploy":
        deploy(".")
        print("deployed v8 icons → static + extension + assets")
    else:
        out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/icons_v8"
        build_all(out)
        print("built icons →", out)
