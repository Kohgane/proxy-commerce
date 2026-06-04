from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "src" / "seller_console" / "static" / "previews" / "phase164"
PREVIEWS_ROOT = OUT_DIR.parent

BG_START = (30, 27, 75, 255)   # #1e1b4b
BG_END = (29, 78, 216, 255)    # #1d4ed8
CYAN = (34, 211, 238, 255)     # #22d3ee
WHITE = (255, 255, 255, 255)


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
        src_a = (color[3] / 255.0) * max(0.0, min(1.0, alpha))
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
                t = ((px - x0) * vx + (py - y0) * vy) / seg_len2
                t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
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


def lerp(a: tuple[int, int, int, int], b: tuple[int, int, int, int], t: float) -> tuple[int, int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


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


def draw_candidate_a(canvas: Canvas, simplified: bool = False) -> None:
    s = canvas.w
    c = s * 0.5
    thick = max(2, s * 0.065)
    orbit = arc_points(c, c, s * 0.30, s * 0.24, 220, 540, 120)
    canvas.draw_polyline(orbit, thick, CYAN)
    end = orbit[-1]
    prev = orbit[-3]
    ang = math.degrees(math.atan2(end[1] - prev[1], end[0] - prev[0]))
    draw_arrow_head(canvas, end, ang, s * 0.09, CYAN)
    if simplified:
        return
    canvas.draw_polyline(arc_points(c, c, s * 0.17, s * 0.17, 0, 360, 140), max(1, s * 0.032), WHITE, 0.95)
    canvas.draw_polyline(arc_points(c, c, s * 0.17, s * 0.08, 0, 360, 120), max(1, s * 0.022), WHITE, 0.86)
    canvas.draw_polyline(arc_points(c, c, s * 0.09, s * 0.17, 0, 360, 120), max(1, s * 0.022), WHITE, 0.75)


def draw_candidate_b(canvas: Canvas) -> None:
    s = canvas.w
    points: list[tuple[float, float]] = []
    for i in range(320):
        t = (i / 319) * 2 * math.pi
        x = 0.5 + 0.22 * math.sin(t)
        y = 0.5 + 0.14 * math.sin(t) * math.cos(t)
        points.append((x * s, y * s))
    canvas.draw_polyline(points, max(2, s * 0.065), CYAN)
    for idx in (80, 240):
        tip = points[idx]
        prev = points[idx - 3]
        ang = math.degrees(math.atan2(tip[1] - prev[1], tip[0] - prev[0]))
        draw_arrow_head(canvas, tip, ang, s * 0.085, CYAN)


def draw_candidate_c(canvas: Canvas) -> None:
    s = canvas.w
    arch = arc_points(s * 0.5, s * 0.63, s * 0.28, s * 0.24, 200, 340, 90)
    canvas.draw_polyline(arch, max(2, s * 0.07), CYAN)
    canvas.draw_line(s * 0.22, s * 0.70, s * 0.78, s * 0.70, s * 0.04, WHITE, 0.95)
    canvas.draw_line(s * 0.32, s * 0.70, s * 0.32, s * 0.84, s * 0.05, CYAN)
    canvas.draw_line(s * 0.68, s * 0.70, s * 0.68, s * 0.84, s * 0.05, CYAN)


def draw_candidate_d(canvas: Canvas) -> None:
    s = canvas.w
    p_top = (s * 0.5, s * 0.18)
    p_right = (s * 0.80, s * 0.42)
    p_bottom = (s * 0.5, s * 0.82)
    p_left = (s * 0.20, s * 0.42)
    outline = [p_top, p_right, p_bottom, p_left, p_top]
    canvas.draw_polyline(outline, max(2, s * 0.065), CYAN)
    center = (s * 0.5, s * 0.47)
    canvas.draw_line(*p_top, *center, s * 0.03, WHITE, 0.9)
    canvas.draw_line(*p_left, *center, s * 0.03, WHITE, 0.9)
    canvas.draw_line(*p_right, *center, s * 0.03, WHITE, 0.9)
    canvas.draw_line(*center, *p_bottom, s * 0.03, WHITE, 0.9)


def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)


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


def write_svgs() -> None:
    svgs = {
        "cand_a.svg": svg_template(
            "<g fill='none' stroke='#22d3ee' stroke-linecap='round' stroke-linejoin='round'>"
            "<ellipse cx='256' cy='256' rx='152' ry='122' stroke-width='34'/>"
            "<path d='M 150 380 A 190 170 0 1 1 410 150' stroke-width='34'/>"
            "<path d='M 410 150 l -18 -48 l 54 16 z' fill='#22d3ee' stroke='none'/>"
            "</g><g fill='none' stroke='#ffffff' stroke-opacity='0.9' stroke-width='15'>"
            "<circle cx='256' cy='266' r='84'/><ellipse cx='256' cy='266' rx='84' ry='40'/><ellipse cx='256' cy='266' rx='44' ry='84'/>"
            "</g>"
        ),
        "cand_b.svg": svg_template(
            "<g fill='none' stroke='#22d3ee' stroke-width='34' stroke-linecap='round' stroke-linejoin='round'>"
            "<path d='M 96 256 C 154 152 358 152 416 256 C 358 360 154 360 96 256 Z'/>"
            "<path d='M 170 220 l -40 20 l 40 20'/>"
            "<path d='M 342 292 l 40 -20 l -40 -20'/>"
            "</g>"
        ),
        "cand_c.svg": svg_template(
            "<g fill='none' stroke-linecap='round' stroke-linejoin='round'>"
            "<path d='M 98 356 A 158 132 0 0 1 414 356' stroke='#22d3ee' stroke-width='36'/>"
            "<path d='M 116 358 H 396' stroke='#ffffff' stroke-width='20' stroke-opacity='0.95'/>"
            "<path d='M 166 358 V 426 M 346 358 V 426' stroke='#22d3ee' stroke-width='26'/>"
            "</g>"
        ),
        "cand_d.svg": svg_template(
            "<g fill='none' stroke-linecap='round' stroke-linejoin='round'>"
            "<path d='M 256 90 L 416 216 L 256 422 L 96 216 Z' stroke='#22d3ee' stroke-width='34'/>"
            "<path d='M 256 90 L 256 240 L 96 216 M 256 240 L 416 216 M 256 240 L 256 422' stroke='#ffffff' stroke-width='16' stroke-opacity='0.9'/>"
            "</g>"
        ),
    }
    for name, content in svgs.items():
        (OUT_DIR / name).write_text(content, encoding="utf-8")


def make_canvas(size: int, painter) -> Canvas:
    c = Canvas(size)
    draw_background(c)
    painter(c)
    return c


def paste(dest: Canvas, src: Canvas, x: int, y: int) -> None:
    for j in range(src.h):
        for i in range(src.w):
            idx = (j * src.w + i) * 4
            rgba = tuple(src.data[idx:idx + 4])  # type: ignore[assignment]
            dest.blend(x + i, y + j, rgba, 1.0)


def dark_bg(size: int, color: tuple[int, int, int, int]) -> Canvas:
    c = Canvas(size)
    for y in range(size):
        for x in range(size):
            c.blend(x, y, color, 1.0)
    return c


def render_pngs() -> None:
    a512 = make_canvas(512, lambda c: draw_candidate_a(c, simplified=False))
    a32 = make_canvas(32, lambda c: draw_candidate_a(c, simplified=False))
    a32s = make_canvas(32, lambda c: draw_candidate_a(c, simplified=True))
    b512 = make_canvas(512, draw_candidate_b)
    b32 = make_canvas(32, draw_candidate_b)
    c512 = make_canvas(512, draw_candidate_c)
    c32 = make_canvas(32, draw_candidate_c)
    d512 = make_canvas(512, draw_candidate_d)
    d32 = make_canvas(32, draw_candidate_d)

    mapping = {
        "cand_a_512.png": a512,
        "cand_a_32.png": a32,
        "cand_a_32_simplified.png": a32s,
        "cand_b_512.png": b512,
        "cand_b_32.png": b32,
        "cand_c_512.png": c512,
        "cand_c_32.png": c32,
        "cand_d_512.png": d512,
        "cand_d_32.png": d32,
    }
    for name, canvas in mapping.items():
        write_png(OUT_DIR / name, canvas.w, canvas.h, bytes(canvas.data))

    contact = dark_bg(1184, (11, 16, 43, 255))
    paste(contact, a512, 32, 32)
    paste(contact, b512, 640, 32)
    paste(contact, c512, 32, 640)
    paste(contact, d512, 640, 640)
    thumbs = [a32, a32s, b32, c32, d32]
    x = 420
    for t in thumbs:
        paste(contact, t, x, 1112)
        x += 64
    write_png(OUT_DIR / "previews_contact_sheet.png", contact.w, contact.h, bytes(contact.data))


def write_indexes() -> None:
    phase = """<!doctype html>
<html lang="ko"><meta charset="utf-8"><title>Phase 164 Favicon Previews</title>
<style>body{background:#0b102b;color:#e2e8f0;font-family:system-ui;margin:24px}h1{margin:0 0 12px}section{margin:18px 0}img{border-radius:16px;background:#0f172a;padding:8px}code{color:#67e8f9}</style>
<h1>Phase 164 Favicon Previews</h1>
<p>딥 인디고 배경 + 일렉트릭 시안 심볼 후보 비교 (운영 favicon 미변경)</p>
<section><h2>Contact Sheet</h2><img src="previews_contact_sheet.png" width="592" alt="contact sheet"></section>
<section><h2>A (융합형)</h2><img src="cand_a_512.png" width="220" alt="A 512"> <img src="cand_a_32.png" width="64" alt="A 32"> <img src="cand_a_32_simplified.png" width="64" alt="A 32 simplified"> <div><code>cand_a.svg</code></div></section>
<section><h2>B (무한 순환)</h2><img src="cand_b_512.png" width="220" alt="B 512"> <img src="cand_b_32.png" width="64" alt="B 32"> <div><code>cand_b.svg</code></div></section>
<section><h2>C (브릿지)</h2><img src="cand_c_512.png" width="220" alt="C 512"> <img src="cand_c_32.png" width="64" alt="C 32"> <div><code>cand_c.svg</code></div></section>
<section><h2>D (원석)</h2><img src="cand_d_512.png" width="220" alt="D 512"> <img src="cand_d_32.png" width="64" alt="D 32"> <div><code>cand_d.svg</code></div></section>
</html>"""
    (OUT_DIR / "index.html").write_text(phase, encoding="utf-8")

    root_index = """<!doctype html>
<html lang="ko"><meta charset="utf-8"><title>Favicon Previews</title>
<body style="font-family:system-ui;background:#0b102b;color:#e2e8f0;padding:24px">
<h1>Favicon Previews</h1><p><a href="/seller/static/previews/phase164/index.html" style="color:#67e8f9">Phase 164 후보 보기</a></p>
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
