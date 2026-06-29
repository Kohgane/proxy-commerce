"""v39 B: 소형 전용 고대비 브릿지 아이콘 생성(≤48px). 디테일 제거 — 굵은 청록 아치 + 주황 키스톤 점.

16/32px: 아치 + 키스톤 점만(데크/다리 생략). 48px: 짧은 다리(데크) 추가.
먹(#1A1714) 라운드 스퀘어 꽉 채움. 스트로크는 마스터 대비 굵게. 4x 슈퍼샘플.
"""
from PIL import Image, ImageDraw

INK = (26, 23, 20, 255)        # #1A1714
TEAL = (17, 154, 142, 255)     # #119A8E
ORANGE = (245, 130, 31, 255)   # #F5821F

OUT = "src/seller_console/static"


def draw_icon(size: int) -> Image.Image:
    SS = 8
    S = size * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # 라운드 스퀘어 배경(먹) — 여백 최소화
    m = int(S * 0.04)
    d.rounded_rectangle([m, m, S - m, S - m], radius=int(S * 0.24), fill=INK)

    legs = size >= 48                       # 16/32는 아치만, 48부터 다리
    stroke = int(S * (0.165 if size <= 32 else 0.13))   # 소형일수록 더 굵게
    cx = S / 2
    arch_w = S * (0.56 if size <= 32 else 0.52)
    x0, x1 = cx - arch_w / 2, cx + arch_w / 2
    top = S * (0.30 if size <= 32 else 0.30)
    # 아치(상단 반원, ∩) — 청록 굵은 스트로크
    bbox = [x0, top, x1, top + arch_w]
    d.arc(bbox, start=180, end=360, fill=TEAL, width=stroke)
    arch_mid_y = top + arch_w / 2           # 다리 시작 y
    if legs:
        leg_bottom = S * 0.74
        d.line([x0 + stroke / 2, arch_mid_y, x0 + stroke / 2, leg_bottom], fill=TEAL, width=stroke)
        d.line([x1 - stroke / 2, arch_mid_y, x1 - stroke / 2, leg_bottom], fill=TEAL, width=stroke)
        # 데크(다리 잇는 가로선)
        d.line([x0 - stroke * 0.2, leg_bottom, x1 + stroke * 0.2, leg_bottom], fill=TEAL, width=int(stroke * 0.7))
    # 주황 키스톤 점 — 유일한 포인트 컬러, 상대 크기 크게(아치 꼭대기)
    r = S * (0.13 if size <= 32 else 0.10)
    ky = top + (0 if size <= 32 else -S * 0.01)
    d.ellipse([cx - r, ky - r, cx + r, ky + r], fill=ORANGE)

    return im.resize((size, size), Image.LANCZOS)


def main():
    icons = {}
    for sz in (16, 32, 48):
        icon = draw_icon(sz)
        icon.save(f"{OUT}/favicon-{sz}.png")
        icons[sz] = icon
        print(f"wrote {OUT}/favicon-{sz}.png ({sz}x{sz})")
    # favicon.ico(멀티사이즈) — 브라우저가 .ico를 우선해도 고대비 소형 변형이 뜨도록.
    icons[48].save(f"{OUT}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"wrote {OUT}/favicon.ico (16/32/48)")
    # 미리보기(1:1 + 확대)
    prev = Image.new("RGB", (260, 90), (245, 239, 227))
    x = 14
    for sz in (16, 32, 48):
        ic = Image.open(f"{OUT}/favicon-{sz}.png").convert("RGBA")
        prev.paste(ic, (x, 14), ic)                       # 1:1
        big = ic.resize((64, 64), Image.NEAREST)
        prev.paste(big, (x, 14 + sz + 4) if sz < 48 else (x, 66), big)
        x += sz + 24
    prev.save("/tmp/small_icons_preview.png")


if __name__ == "__main__":
    main()
