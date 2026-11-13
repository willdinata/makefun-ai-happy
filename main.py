#!/usr/bin/env python3
"""Render a warm, storybook morning as a small, deterministic PNG."""

import math
import os
import struct
import zlib

SIZE = 512
SCALE = 2
WIDTH = SIZE * SCALE
HEIGHT = SIZE * SCALE


class Canvas:
    def __init__(self):
        self.pixels = bytearray(WIDTH * HEIGHT * 3)

    def _blend(self, x, y, color, alpha=1.0):
        if x < 0 or y < 0 or x >= WIDTH or y >= HEIGHT:
            return
        alpha = min(1.0, max(0.0, alpha))
        if alpha <= 0:
            return
        i = (y * WIDTH + x) * 3
        inv = 1.0 - alpha
        self.pixels[i] = int(self.pixels[i] * inv + color[0] * alpha)
        self.pixels[i + 1] = int(self.pixels[i + 1] * inv + color[1] * alpha)
        self.pixels[i + 2] = int(self.pixels[i + 2] * inv + color[2] * alpha)

    @staticmethod
    def _bounds(x0, y0, x1, y1):
        return (
            max(0, int(math.floor(x0 * SCALE))),
            max(0, int(math.floor(y0 * SCALE))),
            min(WIDTH, int(math.ceil(x1 * SCALE)) + 1),
            min(HEIGHT, int(math.ceil(y1 * SCALE)) + 1),
        )

    def background(self):
        stops = [
            (0.0, (255, 195, 176)),
            (0.34, (248, 151, 158)),
            (0.68, (249, 167, 127)),
            (1.0, (255, 219, 140)),
        ]
        glow_x, glow_y, glow_r = 75 * SCALE, 270 * SCALE, 250 * SCALE
        for y in range(HEIGHT):
            t = y / (HEIGHT - 1)
            for idx in range(len(stops) - 1):
                if stops[idx][0] <= t <= stops[idx + 1][0]:
                    start, c0 = stops[idx]
                    end, c1 = stops[idx + 1]
                    mix = (t - start) / (end - start)
                    base = tuple(int(a + (b - a) * mix) for a, b in zip(c0, c1))
                    break
            row = y * WIDTH * 3
            for x in range(WIDTH):
                dx, dy = x - glow_x, y - glow_y
                falloff = max(0.0, 1.0 - math.hypot(dx, dy) / glow_r)
                a = falloff * falloff * 0.30
                i = row + x * 3
                self.pixels[i] = int(base[0] * (1 - a) + 255 * a)
                self.pixels[i + 1] = int(base[1] * (1 - a) + 239 * a)
                self.pixels[i + 2] = int(base[2] * (1 - a) + 177 * a)

    def ellipse(self, cx, cy, rx, ry, color, alpha=1.0, angle=0.0):
        theta = math.radians(angle)
        co, si = math.cos(theta), math.sin(theta)
        ex = math.sqrt((rx * co) ** 2 + (ry * si) ** 2)
        ey = math.sqrt((rx * si) ** 2 + (ry * co) ** 2)
        x0, y0, x1, y1 = self._bounds(cx - ex - 1, cy - ey - 1, cx + ex + 1, cy + ey + 1)
        high_rx, high_ry = rx * SCALE, ry * SCALE
        for py in range(y0, y1):
            dy = (py + 0.5 - cy * SCALE)
            for px in range(x0, x1):
                dx = px + 0.5 - cx * SCALE
                u = co * dx + si * dy
                v = -si * dx + co * dy
                q = math.sqrt((u / high_rx) ** 2 + (v / high_ry) ** 2)
                dist = (q - 1.0) * min(high_rx, high_ry)
                coverage = min(1.0, max(0.0, 0.5 - dist))
                if coverage:
                    self._blend(px, py, color, alpha * coverage)

    def circle(self, cx, cy, radius, color, alpha=1.0):
        self.ellipse(cx, cy, radius, radius, color, alpha)

    def ring(self, cx, cy, radius, thickness, color, alpha=1.0):
        outer = radius + thickness / 2
        inner = max(0.0, radius - thickness / 2)
        x0, y0, x1, y1 = self._bounds(cx - outer - 1, cy - outer - 1, cx + outer + 1, cy + outer + 1)
        for py in range(y0, y1):
            dy = py + 0.5 - cy * SCALE
            for px in range(x0, x1):
                dx = px + 0.5 - cx * SCALE
                distance = math.hypot(dx, dy) / SCALE
                coverage = min(1.0, max(0.0, min(outer - distance, distance - inner) * SCALE + 0.5))
                if coverage:
                    self._blend(px, py, color, alpha * coverage)

    def round_rect(self, x0, y0, x1, y1, radius, color, alpha=1.0):
        bx0, by0, bx1, by1 = self._bounds(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
        radius *= SCALE
        left, top, right, bottom = x0 * SCALE, y0 * SCALE, x1 * SCALE, y1 * SCALE
        for py in range(by0, by1):
            y = py + 0.5
            for px in range(bx0, bx1):
                x = px + 0.5
                qx = abs(x - (left + right) / 2) - ((right - left) / 2 - radius)
                qy = abs(y - (top + bottom) / 2) - ((bottom - top) / 2 - radius)
                dist = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius
                coverage = min(1.0, max(0.0, 0.5 - dist))
                if coverage:
                    self._blend(px, py, color, alpha * coverage)

    def polygon(self, points, color, alpha=1.0):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x0, y0, x1, y1 = self._bounds(min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)
        pts = [(x * SCALE, y * SCALE) for x, y in points]
        for py in range(y0, y1):
            y = py + 0.5
            for px in range(x0, x1):
                x = px + 0.5
                inside = False
                j = len(pts) - 1
                for i in range(len(pts)):
                    xi, yi = pts[i]
                    xj, yj = pts[j]
                    if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                        inside = not inside
                    j = i
                if inside:
                    self._blend(px, py, color, alpha)

    def line(self, x0, y0, x1, y1, width, color, alpha=1.0):
        radius = width / 2
        ax, ay, bx, by = x0 * SCALE, y0 * SCALE, x1 * SCALE, y1 * SCALE
        vx, vy = bx - ax, by - ay
        length2 = vx * vx + vy * vy
        xlo, ylo, xhi, yhi = self._bounds(
            min(x0, x1) - radius - 1, min(y0, y1) - radius - 1,
            max(x0, x1) + radius + 1, max(y0, y1) + radius + 1,
        )
        r = radius * SCALE
        for py in range(ylo, yhi):
            y = py + 0.5
            for px in range(xlo, xhi):
                x = px + 0.5
                t = 0 if length2 == 0 else min(1.0, max(0.0, ((x - ax) * vx + (y - ay) * vy) / length2))
                distance = math.hypot(x - (ax + t * vx), y - (ay + t * vy))
                coverage = min(1.0, max(0.0, r + 0.5 - distance))
                if coverage:
                    self._blend(px, py, color, alpha * coverage)

    def polyline(self, points, width, color, alpha=1.0):
        for a, b in zip(points, points[1:]):
            self.line(a[0], a[1], b[0], b[1], width, color, alpha)

    def arc(self, cx, cy, rx, ry, start_deg, end_deg, width, color, alpha=1.0, steps=24):
        points = []
        for i in range(steps + 1):
            angle = math.radians(start_deg + (end_deg - start_deg) * i / steps)
            points.append((cx + rx * math.cos(angle), cy + ry * math.sin(angle)))
        self.polyline(points, width, color, alpha)


def heart_points(cx, cy, size):
    def bezier(p0, p1, p2, p3, count=10):
        points = []
        for i in range(1, count + 1):
            t = i / count
            u = 1 - t
            points.append((
                u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1],
            ))
        return points

    left = (cx - size * 0.5, cy - size * 0.08)
    top = (cx, cy - size * 0.28)
    right = (cx + size * 0.5, cy - size * 0.08)
    points = [(cx, cy + size * 0.55)]
    points += bezier((cx, cy + size * 0.55), (cx - size * 0.12, cy + size * 0.34), (cx - size * 0.9, cy - size * 0.22), left)
    points += bezier(left, (cx - size * 0.8, cy - size * 0.62), (cx - size * 0.22, cy - size * 0.52), top)
    points += bezier(top, (cx + size * 0.22, cy - size * 0.52), (cx + size * 0.8, cy - size * 0.62), right)
    points += bezier(right, (cx + size * 0.9, cy - size * 0.22), (cx + size * 0.12, cy + size * 0.34), (cx, cy + size * 0.55))
    return points


def draw_cloud(c, x, y, scale=1.0):
    cream = (255, 246, 230)
    c.ellipse(x, y + 5 * scale, 35 * scale, 10 * scale, cream, 0.88)
    c.circle(x - 19 * scale, y + 1 * scale, 12 * scale, cream, 0.92)
    c.circle(x - 3 * scale, y - 5 * scale, 17 * scale, cream, 0.94)
    c.circle(x + 16 * scale, y, 13 * scale, cream, 0.92)


def draw_bubble(c, x, y, radius, heart=False):
    c.circle(x, y, radius, (227, 250, 249), 0.20)
    c.ring(x, y, radius - 1.1, 1.6, (181, 244, 246), 0.82)
    c.arc(x, y, radius - 1, radius - 1, 205, 254, max(1.4, radius * 0.055), (255, 249, 239), 0.95)
    c.arc(x, y, radius - 2, radius - 2, 264, 303, 1.3, (255, 205, 218), 0.80)
    c.arc(x, y, radius - 2, radius - 2, 35, 83, 1.5, (255, 221, 163), 0.80)
    c.arc(x, y, radius - 1.8, radius - 1.8, 286, 323, max(1.0, radius * 0.035), (255, 220, 174), 0.84)
    c.arc(x, y, radius - 1.8, radius - 1.8, 326, 350, max(1.0, radius * 0.035), (255, 184, 209), 0.86)
    c.arc(x, y, radius - 1.8, radius - 1.8, 112, 151, max(1.0, radius * 0.035), (184, 237, 241), 0.84)
    c.arc(x, y, radius * 0.72, radius * 0.72, 218, 254, 1.0, (255, 255, 255), 0.62)
    c.ellipse(x - radius * 0.42, y - radius * 0.43, max(1.7, radius * 0.075), max(3.0, radius * 0.14), (255, 255, 255), 0.94, -25)
    if heart:
        c.circle(x, y, radius * 0.28, (255, 160, 193), 0.15)
        c.circle(x, y, radius * 0.18, (255, 157, 189), 0.19)
        c.polygon(heart_points(x, y, radius * 0.30), (255, 112, 157), 1.0)
        c.arc(x - 1, y - 1, radius * 0.07, radius * 0.07, 200, 300, 1.0, (255, 239, 238), 0.85)


def draw_robot(c):
    ink = (99, 91, 104)
    cream = (255, 246, 226)
    c.ellipse(164, 466, 67, 11, (83, 112, 79), 0.18)
    c.ellipse(142, 454, 18, 11, cream)
    c.ellipse(188, 454, 18, 11, cream)
    c.line(124, 399, 110, 413, 12, cream)
    c.circle(110, 413, 6, (252, 221, 199))
    c.line(201, 396, 215, 353, 13, cream)
    c.circle(215, 353, 6, (252, 221, 199))
    c.ellipse(164, 406, 46, 54, cream)
    c.ellipse(144, 386, 11, 22, (255, 252, 237), 0.56, -18)
    c.round_rect(139, 386, 189, 432, 12, (230, 126, 111))
    c.round_rect(145, 393, 183, 427, 9, (244, 151, 126))
    c.circle(164, 408, 9, (255, 217, 153), 0.95)
    c.circle(164, 408, 4, (255, 239, 190), 0.96)
    c.circle(147, 416, 2.1, (255, 221, 187), 0.9)
    c.circle(181, 416, 2.1, (255, 221, 187), 0.9)
    c.ellipse(164, 337, 47, 42, cream)
    c.ellipse(147, 318, 14, 8, (255, 255, 244), 0.62, -24)
    c.line(164, 296, 164, 286, 4, (236, 206, 166))
    c.circle(164, 280, 5, (255, 147, 165), 0.9)
    c.polygon(heart_points(164, 277, 7), (255, 119, 153))
    c.arc(150, 334, 7, 4, 205, 335, 2.4, ink)
    c.arc(178, 334, 7, 4, 205, 335, 2.4, ink)
    c.ellipse(164, 348, 5, 6.5, (119, 78, 92))
    c.ellipse(164, 351, 2.4, 2.2, (255, 137, 151))
    c.ellipse(142, 348, 7, 4, (246, 157, 159), 0.55)
    c.ellipse(186, 348, 7, 4, (246, 157, 159), 0.55)
    c.arc(137, 350, 8, 4, 205, 330, 1.2, (255, 255, 255), 0.48)
    c.arc(191, 350, 8, 4, 210, 335, 1.2, (255, 255, 255), 0.48)
    c.line(215, 353, 222, 332, 3.2, (134, 105, 104))
    c.ring(224, 324, 9, 2.5, (255, 246, 227), 1.0)
    c.arc(224, 324, 8, 8, 205, 270, 1.3, (255, 174, 154), 0.95)


def draw_fox(c):
    c.ellipse(91, 463, 33, 8, (69, 98, 70), 0.15)
    c.polygon([(100, 433), (67, 445), (39, 434), (51, 416), (77, 414), (104, 423)], (222, 119, 66))
    c.polygon([(47, 427), (39, 434), (49, 439), (58, 431), (55, 424)], (255, 245, 224))
    c.ellipse(91, 443, 25, 22, (222, 119, 66))
    c.ellipse(82, 449, 9, 13, (255, 242, 222))
    c.polygon([(67, 396), (70, 369), (88, 385)], (210, 101, 57))
    c.polygon([(91, 385), (108, 368), (109, 397)], (210, 101, 57))
    c.polygon([(72, 390), (74, 378), (83, 389)], (247, 177, 154))
    c.polygon([(96, 389), (105, 378), (103, 393)], (247, 177, 154))
    c.ellipse(88, 402, 25, 23, (235, 132, 72))
    c.ellipse(99, 410, 10, 7, (255, 241, 220))
    c.arc(81, 402, 5.2, 3.1, 205, 335, 2.1, (96, 69, 67))
    c.arc(97, 401, 5.2, 3.1, 205, 335, 2.1, (96, 69, 67))
    c.ellipse(103, 417, 3.2, 4, (112, 65, 69))
    c.ellipse(103, 419, 1.7, 1.6, (255, 151, 146))
    c.circle(108, 407, 2.0, (106, 76, 77))


def draw_rabbit(c):
    c.ellipse(258, 464, 27, 8, (69, 98, 70), 0.14)
    c.ellipse(258, 444, 20, 27, (255, 247, 226))
    c.ellipse(247, 455, 8, 10, (255, 247, 226))
    c.ellipse(269, 455, 8, 10, (255, 247, 226))
    c.ellipse(247, 382, 8, 28, (255, 247, 226), angle=-13)
    c.ellipse(247, 382, 3.4, 20, (246, 179, 177), angle=-13)
    c.ellipse(278, 389, 9, 24, (255, 247, 226), angle=61)
    c.ellipse(278, 389, 3.5, 16, (246, 179, 177), angle=61)
    c.ellipse(259, 415, 22, 21, (255, 247, 226))
    c.arc(252, 410, 4.2, 2.8, 205, 335, 1.9, (105, 90, 97))
    c.arc(265, 410, 4.2, 2.8, 205, 335, 1.9, (105, 90, 97))
    c.circle(259, 417, 1.4, (126, 79, 91))
    c.ellipse(259, 423, 3.8, 4.5, (126, 79, 91))
    c.ellipse(259, 425, 2.0, 1.8, (255, 154, 164))
    c.ellipse(244, 420, 4, 2.8, (246, 167, 169), 0.55)
    c.ellipse(274, 420, 4, 2.8, (246, 167, 169), 0.55)


def draw_bird(c):
    blue = (93, 171, 210)
    c.ellipse(434, 91, 18, 12, (74, 119, 143), 0.16)
    c.ellipse(433, 84, 18, 13, blue)
    c.ellipse(426, 77, 11, 10, (109, 190, 219))
    c.ellipse(438, 83, 7, 5, (174, 221, 224), 0.8, -30)
    c.polygon([(450, 78), (461, 82), (450, 86)], (246, 174, 105))
    c.circle(423, 76, 1.8, (67, 82, 105))
    c.arc(431, 82, 12, 9, 200, 300, 1.0, (227, 247, 239), 0.65)


def draw_sparkle(c, x, y, size, color):
    c.polygon([(x, y - size), (x + size * 0.22, y - size * 0.22),
               (x + size, y), (x + size * 0.22, y + size * 0.22),
               (x, y + size), (x - size * 0.22, y + size * 0.22),
               (x - size, y), (x - size * 0.22, y - size * 0.22)], color, 0.92)


def draw_scene(c):
    c.background()
    c.circle(75, 270, 34, (255, 216, 138), 0.82)
    c.circle(75, 270, 26, (255, 227, 157), 0.92)
    c.circle(66, 260, 8, (255, 244, 198), 0.28)

    draw_cloud(c, 177, 112, 0.90)
    draw_cloud(c, 335, 203, 0.67)
    draw_cloud(c, 410, 119, 0.62)

    far_hill = [(0, 342), (45, 326), (91, 328), (135, 344), (184, 338),
                (231, 316), (277, 307), (322, 317), (362, 338), (415, 333),
                (464, 311), (512, 318), (512, 512), (0, 512)]
    c.polygon(far_hill, (91, 153, 101))
    c.polyline(far_hill[:12], 2.2, (128, 180, 117), 0.67)
    near_hill = [(0, 392), (55, 371), (103, 370), (154, 382), (201, 380),
                 (251, 365), (298, 362), (343, 374), (389, 390), (439, 379),
                 (478, 360), (512, 364), (512, 512), (0, 512)]
    c.polygon(near_hill, (119, 190, 111))
    c.polyline(near_hill[:12], 2.5, (155, 209, 128), 0.76)
    c.ellipse(342, 440, 145, 68, (143, 204, 117), 0.18, -8)

    bubbles = [
        (251, 288, 16, False), (285, 247, 12, False), (304, 203, 19, False),
        (440, 225, 24, False), (456, 163, 16, False), (307, 151, 10, False),
        (487, 105, 11, False), (366, 145, 65, True),
    ]
    for bubble in bubbles:
        draw_bubble(c, *bubble)

    c.ellipse(90, 462, 53, 8, (69, 98, 70), 0.12)
    draw_fox(c)
    draw_rabbit(c)
    draw_robot(c)
    draw_bird(c)

    for x, y in [(290, 316), (420, 293), (491, 263), (321, 94), (468, 48)]:
        draw_sparkle(c, x, y, 4.5, (255, 249, 218))
    c.polygon(heart_points(276, 186, 8), (255, 174, 188), 0.83)
    c.polygon(heart_points(414, 68, 6), (255, 188, 193), 0.78)
    c.polygon(heart_points(337, 283, 5), (255, 185, 184), 0.72)

    flowers = [(28, 444), (53, 476), (323, 482), (365, 450), (410, 474), (486, 432)]
    for x, y in flowers:
        c.line(x, y + 4, x - 1, y + 13, 1.5, (62, 139, 87), 0.9)
        c.ellipse(x - 3, y + 10, 3, 1.3, (82, 160, 91), angle=-30)
        petal = (255, 229, 203) if x % 2 else (255, 202, 196)
        for dx, dy in [(0, -3), (3, 0), (0, 3), (-3, 0)]:
            c.circle(x + dx, y + dy, 1.8, petal, 0.95)
        c.circle(x, y, 1.6, (255, 209, 113), 1.0)


def downsample(canvas):
    output = bytearray(SIZE * SIZE * 3)
    for y in range(SIZE):
        for x in range(SIZE):
            src = ((y * SCALE) * WIDTH + x * SCALE) * 3
            dst = (y * SIZE + x) * 3
            for channel in range(3):
                total = 0
                for sy in range(SCALE):
                    row = src + sy * WIDTH * 3
                    for sx in range(SCALE):
                        total += canvas.pixels[row + sx * 3 + channel]
                output[dst + channel] = total // (SCALE * SCALE)
    return output


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(path, pixels):
    raw = bytearray()
    stride = SIZE * 3
    for y in range(SIZE):
        raw.append(0)
        raw.extend(pixels[y * stride:(y + 1) * stride])
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n"
    data += png_chunk(b"IHDR", header)
    data += png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += png_chunk(b"IEND", b"")
    with open(path, "wb") as image:
        image.write(data)


def main():
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not output_dir:
        raise SystemExit("MAKEFUN_OUTPUT_DIR must name the output directory")
    os.makedirs(output_dir, exist_ok=True)
    canvas = Canvas()
    draw_scene(canvas)
    write_png(os.path.join(output_dir, "entry.png"), downsample(canvas))


if __name__ == "__main__":
    main()
