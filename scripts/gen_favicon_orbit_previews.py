from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "src" / "seller_console" / "static" / "previews" / "phase165"
PREVIEWS_ROOT = OUT_DIR.parent

BG_START = (30, 27, 75, 255)   # #1e1b4b
BG_END = (29, 78, 216, 255)    # #1d4ed8
CYAN = (34, 211, 238, 255)     # #22d3ee
WHITE = (255, 255, 255, 255)
LIME = (163, 230, 53, 255)     # #a3e635
GOLD = (251, 191, 36, 255)     # #fbbf24


class Canvas:
    def __init__(self, size: int) -> None:
        self.w = size
        self.h = size
        self.data = bytearray(size * size * 4)

    def _idx(self, x: int, y: int) -> int:
        return (y * self.w + x) * 4

    def blend(self, x: int, y: int, color: tuple[int, int, int, int], alpha: float = 1.0) -> None:
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        if alpha <= 0:
            return
        idx = self._idx(x, y)
        src_a = (color[3] / 255.0) * clamp(alpha, 0.0, 1.0)
        if src_a <= 0:
            return
        dst_r, dst_g, dst_b, dst_a = self.data[idx:idx + 4]
        dst_a_f = dst_a / 255.0
        out_a = src_a + dst_a_f * (1 - src_a)
        if out_a <= 0:
            return
        out_r = (color[0] * src_a + dst_r * dst_a_f * (1 - src_a)) / out_a
        out_g = (color[1] * src_a + dst_g * dst_a_f * (1 - src_a)) / out_a
        out_b = (color[2] * src_a + dst_b * dst_a_f * (1 - src_a)) / out_a
        self.data[idx:idx + 4] = bytes((int(out_r), int(out_g), int(out_b), int(out_a * 255)))

    def draw_disc(self, cx: float, cy: float, radius: float, color: tuple[int, int, int, int], alpha: float = 1.0) -> None:
        r2 = radius * radius
        x0 = max(0, int(cx - radius - 1))
        x1 = min(self.w - 1, int(cx + radius + 1))
        y0 = max(0, int(cy - radius - 1))
        y1 = min(self.h - 1, int(cy + radius + 1))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                dx = x + 0.5 - cx
                dy = y + 0.5 - cy
                if dx * dx + dy * dy <= r2:
                    self.blend(x, y, color, alpha)

    def draw_line(self, x0: float, y0: float, x1: float, y1: float, thickness: float, color: tuple[int, int, int, int], alpha: float = 1.0) -> None:
        min_x = int(max(0, math.floor(min(x0, x1) - thickness - 1)))
        max_x = int(min(self.w - 1, math.ceil(max(x0, x1) + thickness + 1)))
        min_y = int(max(0, math.floor(min(y0, y1) - thickness - 1)))
        max_y = int(min(self.h - 1, math.ceil(max(y0, y1) + thickness + 1)))
        vx = x1 - x0
        vy = y1 - y0
        seg_len2 = vx * vx + vy * vy
        if seg_len2 == 0:
            self.draw_disc(x0, y0, thickness * 0.5, color, alpha)
            return
        half = thickness * 0.5
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                px = x + 0.5
                py = y + 0.5
                t = clamp(((px - x0) * vx + (py - y0) * vy) / seg_len2, 0.0, 1.0)
                qx = x0 + t * vx
                qy = y0 + t * vy
                dx = px - qx
                dy = py - qy
                if dx * dx + dy * dy <= half * half:
                    self.blend(x, y, color, alpha)

    def draw_polyline(self, points: list[tuple[float, float]], thickness: float, color: tuple[int, int, int, int], alpha: float = 1.0) -> None:
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            self.draw_line(x0, y0, x1, y1, thickness, color, alpha)

    def fill_polygon(self, points: list[tuple[float, float]], color: tuple[int, int, int, int], alpha: float = 1.0) -> None:
        if len(points) < 3:
            return
        min_y = max(0, int(math.floor(min(y for _, y in points))))
        max_y = min(self.h - 1, int(math.ceil(max(y for _, y in points))))
        for y in range(min_y, max_y + 1):
            scan_y = y + 0.5
            xs: list[float] = []
            for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
                if y1 == y2:
                    continue
                if (scan_y < min(y1, y2)) or (scan_y >= max(y1, y2)):
                    continue
                t = (scan_y - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for i in range(0, len(xs), 2):
                if i + 1 >= len(xs):
                    break
                x_start = max(0, int(math.floor(xs[i])))
                x_end = min(self.w - 1, int(math.ceil(xs[i + 1])))
                for x in range(x_start, x_end + 1):
                    self.blend(x, y, color, alpha)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: tuple[int, int, int, int], b: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
        int(a[3] + (b[3] - a[3]) * t),
    )


def in_rounded_rect(x: float, y: float, size: int, radius: float) -> bool:
    if x < 0 or y < 0 or x > size or y > size:
        return False
    if radius <= x <= size - radius:
        return True
    if radius <= y <= size - radius:
        return True
    corners = ((radius, radius), (size - radius, radius), (radius, size - radius), (size - radius, size - radius))
    for cx, cy in corners:
        dx = x - cx
        dy = y - cy
        if dx * dx + dy * dy <= radius * radius:
            return True
    return False


def draw_background(canvas: Canvas) -> None:
    size = canvas.w
    radius = size * 0.22
    for y in range(size):
        for x in range(size):
            if not in_rounded_rect(x + 0.5, y + 0.5, size, radius):
                continue
            t = (x + y) / (2 * (size - 1))
            canvas.blend(x, y, lerp(BG_START, BG_END, t), 1.0)


def arc_points(cx: float, cy: float, rx: float, ry: float, start_deg: float, end_deg: float, steps: int) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        ang = math.radians(start_deg + (end_deg - start_deg) * t)
        pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
    return pts


def draw_arrow_head(canvas: Canvas, tip: tuple[float, float], angle_deg: float, size: float, color: tuple[int, int, int, int]) -> None:
    ang = math.radians(angle_deg)
    back_x = tip[0] - size * math.cos(ang)
    back_y = tip[1] - size * math.sin(ang)
    left = (back_x + size * 0.58 * math.cos(ang + math.pi / 2), back_y + size * 0.58 * math.sin(ang + math.pi / 2))
    right = (back_x + size * 0.58 * math.cos(ang - math.pi / 2), back_y + size * 0.58 * math.sin(ang - math.pi / 2))
    canvas.fill_polygon([tip, left, right], color)


def draw_base_candidate_a(canvas: Canvas, simplified: bool = False) -> None:
    s = canvas.w
    c = s * 0.5
    thick = max(2, s * 0.065)
    orbit = arc_points(c, c, s * 0.30, s * 0.24, 220, 540, 120)
    canvas.draw_polyline(orbit, thick, CYAN)
    end = orbit[-1]
    prev = orbit[-3]
    ang = math.degrees(math.atan2(end[1] - prev[1], end[0] - prev[0]))
    draw_arrow_head(canvas, end, ang, s * 0.09, CYAN)

    canvas.draw_polyline(arc_points(c, c, s * 0.17, s * 0.17, 0, 360, 140), max(1, s * 0.032), WHITE, 0.95)
    canvas.draw_polyline(arc_points(c, c, s * 0.17, s * 0.08, 0, 360, 120), max(1, s * 0.022), WHITE, 0.86)
    canvas.draw_polyline(arc_points(c, c, s * 0.09, s * 0.17, 0, 360, 120), max(1, s * 0.022), WHITE, 0.75)


def draw_orbit_line(canvas: Canvas, orbit_color: tuple[int, int, int, int], simplified: bool = False) -> None:
    s = canvas.w
    c = s * 0.5
    if simplified:
        points = arc_points(c, c, s * 0.21, s * 0.11, 210, 400, 36)
        thick = max(1, s * 0.035)
    else:
        points = arc_points(c, c, s * 0.21, s * 0.11, 210, 930, 144)
        thick = max(2, s * 0.02)
    canvas.draw_polyline(points, thick, orbit_color, 0.95)
    sat = points[-1]
    canvas.draw_disc(sat[0], sat[1], max(1.0, s * 0.018), orbit_color, 1.0)


def draw_orbit_variant(canvas: Canvas, orbit_color: tuple[int, int, int, int], simplified: bool = False) -> None:
    draw_base_candidate_a(canvas, simplified=simplified)
    draw_orbit_line(canvas, orbit_color=orbit_color, simplified=simplified)


def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    length = struct.pack(">I", len(payload))
    body = chunk_type + payload
    crc = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    return length + body + crc


def write_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    rows = []
    stride = width * 4
    for y in range(height):
        rows.append(b"\x00" + rgba[y * stride:(y + 1) * stride])
    compressed = zlib.compress(b"".join(rows), level=9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", compressed) + png_chunk(b"IEND", b"")
    path.write_bytes(png)


def svg_template(inner: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
        "<stop offset='0%' stop-color='#1e1b4b'/><stop offset='100%' stop-color='#1d4ed8'/>"
        "</linearGradient></defs>"
        "<rect width='512' height='512' rx='112' fill='url(#g)'/>"
        f"{inner}</svg>"
    )


def orbit_svg(orbit_hex: str) -> str:
    return svg_template(
        "<g fill='none' stroke='#22d3ee' stroke-linecap='round' stroke-linejoin='round'>"
        "<path d='M 150 380 A 190 170 0 1 1 410 150' stroke-width='34'/>"
        "<path d='M 410 150 l -18 -48 l 54 16 z' fill='#22d3ee' stroke='none'/>"
        "</g>"
        "<g fill='none' stroke='#ffffff' stroke-opacity='0.9' stroke-width='15'>"
        "<circle cx='256' cy='266' r='84'/><ellipse cx='256' cy='266' rx='84' ry='40'/><ellipse cx='256' cy='266' rx='44' ry='84'/>"
        "</g>"
        f"<g fill='none' stroke='{orbit_hex}' stroke-linecap='round' stroke-linejoin='round'>"
        "<path d='M 140 310 A 110 56 28 1 1 366 245 A 110 56 28 1 1 140 310' stroke-width='12'/>"
        "</g>"
        f"<circle cx='366' cy='245' r='10' fill='{orbit_hex}'/>"
    )


def make_canvas(size: int, orbit_color: tuple[int, int, int, int], simplified: bool) -> Canvas:
    c = Canvas(size)
    draw_background(c)
    draw_orbit_variant(c, orbit_color, simplified=simplified)
    return c


def paste(dest: Canvas, src: Canvas, x: int, y: int) -> None:
    for j in range(src.h):
        for i in range(src.w):
            idx = (j * src.w + i) * 4
            rgba: tuple[int, int, int, int] = (
                src.data[idx],
                src.data[idx + 1],
                src.data[idx + 2],
                src.data[idx + 3],
            )
            dest.blend(x + i, y + j, rgba, 1.0)


def dark_bg(size: int, color: tuple[int, int, int, int]) -> Canvas:
    c = Canvas(size)
    for y in range(size):
        for x in range(size):
            c.blend(x, y, color, 1.0)
    return c


def write_svgs() -> None:
    (OUT_DIR / "orbit_lime.svg").write_text(orbit_svg("#a3e635"), encoding="utf-8")
    (OUT_DIR / "orbit_gold.svg").write_text(orbit_svg("#fbbf24"), encoding="utf-8")


def render_pngs() -> None:
    lime512 = make_canvas(512, orbit_color=LIME, simplified=False)
    lime32 = make_canvas(32, orbit_color=LIME, simplified=True)
    gold512 = make_canvas(512, orbit_color=GOLD, simplified=False)
    gold32 = make_canvas(32, orbit_color=GOLD, simplified=True)

    mapping = {
        "orbit_lime_512.png": lime512,
        "orbit_lime_32.png": lime32,
        "orbit_gold_512.png": gold512,
        "orbit_gold_32.png": gold32,
    }
    for name, canvas in mapping.items():
        write_png(OUT_DIR / name, canvas.w, canvas.h, bytes(canvas.data))

    contact = dark_bg(1200, (11, 16, 43, 255))
    paste(contact, lime512, 48, 48)
    paste(contact, gold512, 640, 48)
    paste(contact, lime32, 460, 640)
    paste(contact, gold32, 700, 640)
    write_png(OUT_DIR / "phase165_contact_sheet.png", contact.w, contact.h, bytes(contact.data))


def write_indexes() -> None:
    phase = """<!doctype html>
<html lang=\"ko\"><meta charset=\"utf-8\"><title>Phase 165 Orbit Favicon Previews</title>
<style>body{background:#0b102b;color:#e2e8f0;font-family:system-ui;margin:24px}h1{margin:0 0 12px}section{margin:18px 0}img{border-radius:16px;background:#0f172a;padding:8px}code{color:#67e8f9}</style>
<h1>Phase 165 Orbit Favicon Previews</h1>
<p>후보 A(딥 인디고 + 흰 지구본 + 시안 순환 화살표)에 공전 궤도선을 추가한 라임/골드 비교 미리보기입니다.</p>
<p>배포 후 URL: <code>/seller/static/previews/phase165/index.html</code></p>
<section><h2>Contact Sheet</h2><img src=\"phase165_contact_sheet.png\" width=\"640\" alt=\"phase165 contact sheet\"></section>
<section><h2>Orbit Lime (#a3e635)</h2><img src=\"orbit_lime_512.png\" width=\"220\" alt=\"orbit lime 512\"> <img src=\"orbit_lime_32.png\" width=\"64\" alt=\"orbit lime 32\"> <div><code>orbit_lime.svg</code></div></section>
<section><h2>Orbit Gold (#fbbf24)</h2><img src=\"orbit_gold_512.png\" width=\"220\" alt=\"orbit gold 512\"> <img src=\"orbit_gold_32.png\" width=\"64\" alt=\"orbit gold 32\"> <div><code>orbit_gold.svg</code></div></section>
</html>"""
    (OUT_DIR / "index.html").write_text(phase, encoding="utf-8")

    root_index = """<!doctype html>
<html lang=\"ko\"><meta charset=\"utf-8\"><title>Favicon Previews</title>
<body style=\"font-family:system-ui;background:#0b102b;color:#e2e8f0;padding:24px\">
<h1>Favicon Previews</h1>
<ul>
<li><a href=\"/seller/static/previews/phase164/index.html\" style=\"color:#67e8f9\">Phase 164 후보 보기</a></li>
<li><a href=\"/seller/static/previews/phase165/index.html\" style=\"color:#67e8f9\">Phase 165 orbit 라임/골드 미리보기</a></li>
</ul>
</body></html>"""
    (PREVIEWS_ROOT / "index.html").write_text(root_index, encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEWS_ROOT.mkdir(parents=True, exist_ok=True)
    write_svgs()
    render_pngs()
    write_indexes()
    print(f"Generated previews in: {OUT_DIR}")


if __name__ == "__main__":
    main()
