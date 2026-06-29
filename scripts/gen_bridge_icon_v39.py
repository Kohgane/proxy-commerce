"""v39 신규 브릿지 마크 — 흰 배경 + 검정 라운드 보더 + 금 게이트 링(아치) + 주황 키스톤 +
금 타워(기둥) 2 + 청록 데크(2줄 + 금 타이). 오너 확정 디자인 재현(첨부 이미지).

대형(>=180): 풀 디테일(타워+데크 2줄+타이). 소형(16/32/48): 단순화(타워 생략, 아치 굵게, 데크 2줄).
4x 슈퍼샘플. 산출: brand_icons_final 스타일 PNG 일습 + favicon.ico(16/32/48 멀티).
"""
import base64
import io

from PIL import Image, ImageDraw

WHITE = (255, 255, 255, 255)
BLACK = (17, 17, 17, 255)
GOLD = (201, 162, 75, 255)     # #C9A24B
ORANGE = (245, 130, 31, 255)   # #F5821F
TEAL = (17, 154, 142, 255)     # #119A8E


def draw(size: int, simple: bool) -> Image.Image:
    SS = 8
    S = size * SS
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def px(v):  # 정규화 → 픽셀
        return v * S

    # 배경: 흰 라운드 스퀘어 + 검정 라운드 보더
    m = px(0.045)
    border = max(2, int(px(0.05)))
    d.rounded_rectangle([m, m, S - m, S - m], radius=px(0.22), fill=WHITE,
                        outline=BLACK, width=border)

    cx = S / 2
    # 두께
    gw = px(0.085 if simple else 0.058)     # 금 아치/타워 스트로크(소형 더 굵게)
    tw = px(0.11 if simple else 0.05)        # 청록 데크 스트로크

    # 게이트 링(아치) — 금. 상단 키스톤이 얹히는 원형 아치. 소형은 더 크게.
    rr = px(0.20 if simple else 0.165)
    ay = px(0.40 if simple else 0.40)        # 링 중심 y
    d.ellipse([cx - rr, ay - rr, cx + rr, ay + rr], outline=GOLD, width=int(gw))

    deck_y1 = px(0.66 if simple else 0.66)
    deck_y2 = px(0.745 if simple else 0.735)

    if not simple:
        # 타워(기둥) 2 — 링 양옆, 데크에서 위로.
        tox = px(0.255)
        for sx in (cx - tox, cx + tox):
            d.line([sx, px(0.30), sx, deck_y1], fill=GOLD, width=int(px(0.045)))

    # 청록 데크 2줄 — 가로 바.
    dx0, dx1 = px(0.13), px(0.87)
    for dy in (deck_y1, deck_y2):
        d.line([dx0, dy, dx1, dy], fill=TEAL, width=int(tw), joint="curve")
        d.ellipse([dx0 - tw / 2, dy - tw / 2, dx0 + tw / 2, dy + tw / 2], fill=TEAL)
        d.ellipse([dx1 - tw / 2, dy - tw / 2, dx1 + tw / 2, dy + tw / 2], fill=TEAL)
    # 금 타이(데크 2줄 잇는 짧은 세로)
    n = 3 if simple else 5
    for i in range(n):
        x = dx0 + (dx1 - dx0) * (i + 0.5) / n
        d.line([x, deck_y1, x, deck_y2], fill=GOLD, width=int(px(0.035 if simple else 0.028)))

    # 주황 키스톤 점 — 아치 꼭대기(유일한 포인트 컬러), 소형은 크게.
    kr = px(0.085 if simple else 0.062)
    ky = ay - rr
    d.ellipse([cx - kr, ky - kr, cx + kr, ky + kr], fill=ORANGE)

    return im.resize((size, size), Image.LANCZOS)


def main():
    out = "src/seller_console/static"
    # 소형 단순(≤48) / 대형 풀(≥180)
    for sz in (16, 32, 48):
        draw(sz, simple=True).save(f"{out}/favicon-{sz}.png")
    for sz in (180, 192, 512, 1024):
        draw(sz, simple=False).save(f"{out}/icon-{sz}.png")
    draw(180, simple=False).save(f"{out}/apple-touch-icon.png")
    draw(48, simple=True).save(f"{out}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    # 마스터(OG 카드 등 파생 단일소스)
    draw(1024, simple=False).save("assets/brand-icons/icon-master-1024.png")
    # favicon.svg — 마스터 래스터(128px) data-URI 임베드(스케일러블 선언 유지, 경량)
    emb = draw(128, simple=False)
    buf = io.BytesIO(); emb.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" '
        'width="512" height="512" role="img" '
        'aria-label="gogabridj bridge gateway mark">\n'
        f'  <image width="512" height="512" href="data:image/png;base64,{b64}"/>\n'
        '</svg>\n'
    )
    with open(f"{out}/favicon.svg", "w", encoding="utf-8") as f:
        f.write(svg)
    # 크롬 확장 툴바 아이콘(16/32/48=단순, 128=풀)
    ext = "extensions/chrome-collector/icons"
    draw(16, simple=True).save(f"{ext}/16.png")
    draw(32, simple=True).save(f"{ext}/32.png")
    draw(48, simple=True).save(f"{ext}/48.png")
    draw(128, simple=False).save(f"{ext}/128.png")
    # 미리보기
    prev = Image.new("RGB", (560, 200), (235, 235, 235))
    x = 20
    for sz in (16, 32, 48):
        ic = Image.open(f"{out}/favicon-{sz}.png").convert("RGBA"); prev.paste(ic, (x, 30), ic)
        big = ic.resize((110, 110), Image.NEAREST); prev.paste(big, (x, 60), big); x += 140
    big512 = draw(150, simple=False); prev.paste(big512, (x, 25), big512)
    prev.save("/tmp/v39icon_preview.png")
    print("generated icons + /tmp/v39icon_preview.png")


if __name__ == "__main__":
    main()
