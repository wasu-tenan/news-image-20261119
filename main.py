#!/usr/bin/env python3
"""The world of Thursday 19 November 2026, in one picture.

Built for the make.fun news-image-20261119 bounty, second version.
The page is a broadsheet front page in the style the winning entries
of this bounty line use: a date masthead, a region bar, the day in
numbers, numbered and region-coded story cards with small drawn
scenes, a map of where it happened, an "also on Thursday" list, and a
date-check box. Twenty stories, every one of them reported on the
day itself (the reporting is summarised in NOTES.md).

The program is pure Python 3.13 standard library, fully offline and
deterministic: no clock, no randomness, no input. It paints into an
RGB buffer and encodes a PNG to $MAKEFUN_OUTPUT_DIR/entry.png
(default /output). Run it twice, get the same bytes twice.
"""

import math
import os
import struct
import zlib

PAGE = 1024

# ---------------------------------------------------------------- palette
PAPER = (247, 242, 230)
SHEET = (255, 253, 247)
INK = (22, 24, 28)
SOFT = (58, 62, 68)
FAINT = (110, 112, 108)
RULE = (203, 195, 175)
RED = (178, 40, 34)
GOLD = (198, 142, 32)
WHITE = (255, 255, 255)
SKY = (206, 226, 238)
SEA = (64, 110, 148)
SAND = (232, 214, 170)

# region colours, used for badges, kickers, the region bar and map pins
REGIONS = {
    "ASIA": (122, 62, 157),
    "MIDDLE EAST": (206, 118, 28),
    "EUROPE": (38, 92, 168),
    "AMERICAS": (186, 44, 44),
    "AFRICA": (46, 132, 74),
    "GLOBAL": (96, 100, 106),
}


# ---------------------------------------------------------------- painter
class Painter:
    """Flat RGB buffer plus the drawing verbs the page needs."""

    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(bytes(bg) * (w * h))

    def px(self, x, y, c):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(c)

    def box(self, x, y, w, h, c):
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(self.w, int(x + w)), min(self.h, int(y + h))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(c) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.buf[i:i + len(row)] = row

    def disc(self, cx, cy, r, c):
        r = int(r)
        cx, cy = int(cx), int(cy)
        for dy in range(-r, r + 1):
            half = int(math.sqrt(max(0, r * r - dy * dy)))
            self.box(cx - half, cy + dy, 2 * half + 1, 1, c)

    def line(self, x1, y1, x2, y2, thick, c):
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(dist / max(1.0, thick * 0.35)))
        for s in range(steps + 1):
            f = s / steps
            self.disc(x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, thick / 2.0, c)

    def lines(self, pts, thick, c, close=False):
        pts = list(pts)
        if close and pts:
            pts.append(pts[0])
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], thick, c)

    def fill(self, pts, c):
        lo = max(0, int(min(p[1] for p in pts)))
        hi = min(self.h - 1, int(max(p[1] for p in pts)))
        n = len(pts)
        for yy in range(lo, hi + 1):
            hits = []
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                if (ay <= yy < by) or (by <= yy < ay):
                    hits.append(ax + (yy - ay) * (bx - ax) / (by - ay))
            hits.sort()
            for i in range(0, len(hits) - 1, 2):
                self.box(int(hits[i]), yy, int(hits[i + 1]) - int(hits[i]) + 1, 1, c)

    def frame(self, x, y, w, h, c, t=1.5):
        self.box(x, y, w, t, c)
        self.box(x, y + h - t, w, t, c)
        self.box(x, y, t, h, c)
        self.box(x + w - t, y, t, h, c)


# ---------------------------------------------------------------- type
# A drawn typeface on a 6x9 grid. Each glyph is a tuple of strokes; a
# stroke is ("L", ((x, y), ...)) for a polyline, ("A", cx, cy, rx, ry,
# a0, a1) for an elliptical arc in degrees, or ("D", x, y) for a dot.
# Lowercase letters render as small caps, the newspaper way.
def _L(*pts):
    return ("L", tuple(pts))


def _A(cx, cy, rx, ry, a0, a1):
    return ("A", cx, cy, rx, ry, a0, a1)


def _D(x, y):
    return ("D", x, y)


GLYPHS = {
    "A": (_L((0, 9), (3, 0), (6, 9)), _L((1.2, 6), (4.8, 6))),
    "B": (_L((0, 0), (0, 9)), _L((0, 0), (3.4, 0), (5.2, 1.2), (5.2, 3.2), (3.4, 4.5), (0, 4.5)),
          _L((3.4, 4.5), (5.6, 5.8), (5.6, 7.8), (3.4, 9), (0, 9))),
    "C": (_L((5.6, 1.8), (4.2, 0.5), (1.8, 0.4), (0.3, 2.2), (0.3, 6.8), (1.8, 8.6), (4.2, 8.5), (5.6, 7.2)),),
    "D": (_L((0, 0), (0, 9)), _L((0, 0), (3.2, 0)), _A(3.2, 4.5, 2.6, 4.5, -90, 90), _L((3.2, 9), (0, 9))),
    "E": (_L((5.4, 0), (0, 0), (0, 9), (5.4, 9)), _L((0, 4.5), (4.2, 4.5))),
    "F": (_L((5.4, 0), (0, 0), (0, 9)), _L((0, 4.5), (4.2, 4.5))),
    "G": (_L((5.6, 1.8), (4.2, 0.5), (1.8, 0.4), (0.3, 2.2), (0.3, 6.8), (1.8, 8.6), (4.2, 8.5), (5.6, 7.2)),
          _L((3.4, 5.4), (6, 5.4), (6, 8.6))),
    "H": (_L((0, 0), (0, 9)), _L((6, 0), (6, 9)), _L((0, 4.5), (6, 4.5))),
    "I": (_L((3, 0), (3, 9)), _L((1.4, 0), (4.6, 0)), _L((1.4, 9), (4.6, 9))),
    "J": (_L((5.4, 0), (5.4, 6.6), (4, 8.8), (1.6, 8.8), (0.4, 7)),),
    "K": (_L((0, 0), (0, 9)), _L((5.6, 0), (0.8, 4.6)), _L((2, 3.6), (6, 9))),
    "L": (_L((0, 0), (0, 9), (5.4, 9)),),
    "M": (_L((0, 9), (0, 0), (3, 4), (6, 0), (6, 9)),),
    "N": (_L((0, 9), (0, 0), (6, 9), (6, 0)),),
    "O": (_A(3, 4.5, 2.9, 4.4, 0, 360),),
    "P": (_L((0, 9), (0, 0), (3.6, 0)), _A(3.6, 2.25, 2.3, 2.25, -90, 90), _L((3.6, 4.5), (0, 4.5))),
    "Q": (_A(3, 4.5, 2.9, 4.4, 0, 360), _L((3.8, 6.4), (6.2, 9.2))),
    "R": (_L((0, 9), (0, 0), (3.6, 0)), _A(3.6, 2.25, 2.3, 2.25, -90, 90), _L((3.6, 4.5), (0, 4.5)),
          _L((3.4, 4.5), (6, 9))),
    "S": (_L((5.4, 1.4), (3.8, 0.2), (1.6, 0.3), (0.3, 1.8), (1, 3.4), (3.2, 4.3), (5, 5.4), (5.3, 7.2),
             (3.8, 8.8), (1.4, 8.9), (0.3, 7.6)),),
    "T": (_L((0, 0), (6, 0)), _L((3, 0), (3, 9))),
    "U": (_L((0, 0), (0, 6.6), (1.5, 8.8), (4.5, 8.8), (6, 6.6), (6, 0)),),
    "V": (_L((0, 0), (3, 9), (6, 0)),),
    "W": (_L((0, 0), (1.3, 9), (3, 3.6), (4.7, 9), (6, 0)),),
    "X": (_L((0, 0), (6, 9)), _L((6, 0), (0, 9))),
    "Y": (_L((0, 0), (3, 4)), _L((6, 0), (3, 4), (3, 9))),
    "Z": (_L((0, 0), (6, 0), (0, 9), (6, 9)),),
    "0": (_A(3, 4.5, 2.5, 4.4, 0, 360),),
    "1": (_L((1.6, 2.2), (4, 0), (4, 9)), _L((1.4, 9), (5.4, 9))),
    "2": (_L((0.4, 2), (1.8, 0.4), (4.2, 0.3), (5.4, 1.8), (5, 3.6), (0.2, 9), (5.6, 9)),),
    "3": (_L((0.4, 1.2), (2.2, 0.2), (4.4, 0.5), (5, 2.2), (3.4, 4.3)),
          _L((3.4, 4.3), (5.2, 5.8), (5, 7.9), (3.2, 9), (0.4, 8.4))),
    "4": (_L((4.4, 9), (4.4, 0), (0, 6.4), (6, 6.4)),),
    "5": (_L((5.4, 0), (0.6, 0), (0.6, 3.6), (3.2, 3.4), (5.2, 5), (5.2, 7.4), (3.4, 9), (0.6, 8.2)),),
    "6": (_L((5, 1.6), (2.8, 0.3), (1, 2.2), (0.4, 5.8), (1.4, 8.4), (3.4, 8.9), (5.2, 7.6), (5.2, 5.4),
             (3.6, 4.1), (0.6, 5)),),
    "7": (_L((0, 0), (6, 0), (2.4, 9)),),
    "8": (_A(3, 2.2, 2.1, 2.2, 0, 360), _A(3, 6.7, 2.6, 2.3, 0, 360)),
    "9": (_L((0.8, 7.4), (2.8, 8.7), (5, 6.6), (5.6, 3.2), (4.6, 0.5), (2.6, 0.1), (0.6, 1.2), (0.6, 3.4),
             (2.2, 4.9), (5.4, 4)),),
    ".": (_D(3, 8.6),),
    ",": (_L((3.4, 8), (2.8, 9.6)),),
    ":": (_D(3, 2.6), _D(3, 7.6)),
    ";": (_D(3, 2.6), _L((3.4, 7.4), (2.8, 9.6))),
    "-": (_L((1, 4.5), (5, 4.5)),),
    "'": (_L((3, 0), (2.6, 2.2)),),
    '"': (_L((1.4, 0), (1.1, 2.2)), _L((4.2, 0), (3.9, 2.2))),
    "!": (_L((3, 0), (3, 6.2)), _D(3, 8.6)),
    "?": (_L((0.6, 1.8), (2, 0.3), (4.2, 0.4), (5.2, 2), (3, 4.6), (3, 6.6)), _D(3, 8.8)),
    "$": (_L((5.4, 1.4), (3.8, 0.2), (1.6, 0.3), (0.3, 1.8), (1, 3.4), (3.2, 4.3), (5, 5.4), (5.3, 7.2),
             (3.8, 8.8), (1.4, 8.9), (0.3, 7.6)), _L((3, -0.5), (3, 9.5))),
    "%": (_A(1.4, 1.8, 1.2, 1.5, 0, 360), _A(4.6, 7.2, 1.2, 1.5, 0, 360), _L((5.4, 0), (0.6, 9))),
    "+": (_L((3, 1.8), (3, 7.2)), _L((0.6, 4.5), (5.4, 4.5))),
    "/": (_L((1, 9.4), (5.2, -0.4)),),
    "(": (_A(4.2, 4.5, 2.4, 5, 100, 260),),
    ")": (_A(1.8, 4.5, 2.4, 5, -80, 80),),
    "&": (_L((5.2, 8.8), (1.4, 3.2), (0.8, 1.4), (2, 0.2), (3.8, 0.7), (3.4, 2.8), (0.6, 5.8), (0.8, 8),
             (2.8, 9), (4.6, 7.6), (5.8, 9.2)),),
    "*": (_L((3, 1), (3, 8)), _L((0.9, 2.8), (5.1, 6.2)), _L((5.1, 2.8), (0.9, 6.2))),
    "·": (_D(3, 4.5),),
}

ADV = 7.2      # advance per glyph, in grid units
SPACE = 4.0    # advance for a space
SMALL = 0.74   # lowercase -> small-cap scale


def _char_w(ch, size):
    if ch == " ":
        return SPACE * size / 9.0
    return ADV * size / 9.0


def text_w(s, size):
    return sum(_char_w(ch, size) for ch in s)


def draw(pg, s, x, y, size, colour, bold=False, align="left"):
    """Draw one line of text; returns the x just past the last glyph."""
    if align == "center":
        x -= text_w(s, size) / 2
    elif align == "right":
        x -= text_w(s, size)
    unit = size / 9.0
    thick = max(1.2, size * (0.165 if bold else 0.115))
    cx = x
    for ch in s:
        if ch == " ":
            cx += SPACE * unit
            continue
        glyph = GLYPHS.get(ch.upper())
        if glyph is None:
            cx += ADV * unit
            continue
        sc = SMALL if ch.islower() else 1.0
        for stroke in glyph:
            kind = stroke[0]
            if kind == "D":
                pg.disc(cx + stroke[1] * unit * sc + (1 - sc) * 0 * unit,
                        y + (9 - (9 - stroke[2]) * sc) * unit, max(1.0, thick * 0.62), colour)
            elif kind == "A":
                _, gx, gy, rx, ry, a0, a1 = stroke
                pts = []
                steps = 18
                for i in range(steps + 1):
                    ang = math.radians(a0 + (a1 - a0) * i / steps)
                    px_ = gx + rx * math.cos(ang)
                    py_ = gy + ry * math.sin(ang)
                    pts.append((cx + px_ * unit * sc, y + (9 - (9 - py_) * sc) * unit))
                pg.lines(pts, thick, colour)
            else:
                pts = [(cx + gx * unit * sc, y + (9 - (9 - gy) * sc) * unit) for gx, gy in stroke[1]]
                if len(pts) == 1:
                    pg.disc(pts[0][0], pts[0][1], max(1.0, thick * 0.62), colour)
                else:
                    pg.lines(pts, thick, colour)
        cx += ADV * unit
    return cx


def fit(pg, s, x, y, size, colour, max_w, bold=False, align="left"):
    while size > 8 and text_w(s, size) > max_w:
        size -= 0.5
    return draw(pg, s, x, y, size, colour, bold=bold, align=align)


def wrap(s, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = (cur + " " + word).strip()
        if text_w(trial, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def block(pg, s, x, y, size, colour, max_w, gap=1.42, bold=False, limit=None):
    lines = wrap(s, size, max_w)
    if limit:
        lines = lines[:limit]
    for i, line in enumerate(lines):
        draw(pg, line, x, y + i * size * gap, size, colour, bold=bold)
    return y + len(lines) * size * gap, len(lines)


# ---------------------------------------------------------------- scenes
# Small flat scenes drawn inside the card art strips. Each takes the
# strip's top-left corner and size; a dark caption banner is added by
# the card painter, not by the scenes.

def scene_summit(pg, x, y, w, h):
    pg.box(x, y, w, h, (24, 44, 74))
    flags = [(178, 40, 34), (196, 30, 40), (240, 240, 240)]
    marks = [(255, 255, 255), (250, 200, 40), (40, 80, 170)]
    for i in range(3):
        cx = x + w * (0.22 + 0.28 * i)
        pg.box(cx - 26, y + 8, 52, 30, flags[i])
        if i == 0:
            for sy in (14, 21, 28):
                pg.box(cx - 26, y + sy, 52, 3.4, (240, 240, 240))
            pg.box(cx - 26, y + 8, 24, 16, (40, 52, 120))
            for sx in range(3):
                for sy in range(2):
                    pg.disc(cx - 20 + sx * 7, y + 12 + sy * 6, 1.3, (240, 240, 240))
        elif i == 1:
            pg.disc(cx - 14, y + 16, 4, marks[1])
            for sx, sy in ((6, 10), (11, 13), (12, 19), (9, 24)):
                pg.disc(cx + sx - 16, y + sy, 1.6, marks[1])
        else:
            pg.box(cx - 26, y + 18, 52, 7, (40, 80, 170))
            pg.box(cx - 26, y + 30, 52, 8, (178, 40, 34))
        pg.disc(cx, y + h - 29, 10, (233, 198, 158))
        pg.fill([(cx - 17, y + h - 4), (cx - 12, y + h - 18), (cx + 12, y + h - 18),
                 (cx + 17, y + h - 4)], (30, 34, 44) if i != 1 else (120, 30, 34))
    pg.box(x + 8, y + h - 6, w - 16, 5, (96, 74, 48))


def scene_gulf(pg, x, y, w, h):
    pg.box(x, y, w, h, SKY)
    pg.disc(x + w - 26, y + 13, 8, GOLD)
    pg.box(x, y + h - 16, w, 16, SEA)
    # a tanker on the horizon
    pg.box(x + w * 0.52, y + h - 24, w * 0.3, 7, INK)
    pg.box(x + w * 0.60, y + h - 30, w * 0.08, 6, INK)
    # dashed missile arc over the water
    for t in range(13):
        f = t / 12
        mx = x + w * 0.06 + (w * 0.5) * f
        my = y + (h - 20) - (h - 16) * math.sin(math.pi * f)
        pg.disc(mx, my, 1.8, RED)
    pg.fill([(x + 8, y + h - 16), (x + 30, y + h - 34), (x + 52, y + h - 16)], (90, 84, 70))
    pg.box(x + 24, y + h - 40, 4, 8, INK)


def scene_court(pg, x, y, w, h):
    pg.box(x, y, w, h, (228, 222, 204))
    cx = x + w / 2
    pg.fill([(cx - 44, y + 16), (cx + 44, y + 16), (cx, y + 2)], (120, 96, 60))
    pg.box(cx - 46, y + 17, 92, 4, (120, 96, 60))
    for i in range(5):
        pg.box(cx - 38 + i * 19, y + 23, 6, h - 34, (250, 248, 240))
    pg.box(cx - 46, y + h - 10, 92, 5, (120, 96, 60))
    # scales of justice on the right
    sx = x + w - 34
    pg.line(sx, y + 10, sx, y + h - 16, 2.5, INK)
    pg.line(sx - 13, y + 14, sx + 13, y + 14, 2.5, INK)
    for dx in (-13, 13):
        pg.line(sx + dx, y + 14, sx + dx - 5, y + 24, 1.4, INK)
        pg.line(sx + dx, y + 14, sx + dx + 5, y + 24, 1.4, INK)
        pg.lines([(sx + dx - 6, y + 24), (sx + dx + 6, y + 24), (sx + dx, y + 29)], 1.8, INK)


def scene_bridge(pg, x, y, w, h):
    pg.box(x, y, w, h, SKY)
    pg.box(x, y + h - 10, w, 10, SEA)
    for tx in (x + w * 0.18, x + w * 0.78):
        pg.box(tx, y + 8, 5, h - 16, (52, 60, 70))
    pg.box(x, y + h - 22, w * 0.42, 5, INK)
    pg.fill([(x + w * 0.60, y + h - 22), (x + w, y + h - 22), (x + w * 0.94, y + h - 13),
             (x + w * 0.66, y + h - 16)], INK)
    pg.lines([(x + w * 0.18 + 2, y + 10), (x + w * 0.5, y + h - 20)], 1.4, (52, 60, 70))
    pg.lines([(x + w * 0.78 + 2, y + 10), (x + w * 0.62, y + h - 18)], 1.4, (52, 60, 70))


def scene_chart(pg, x, y, w, h):
    pg.box(x, y, w, h, (18, 40, 34))
    base = y + h - 8
    vals = (0.3, 0.45, 0.4, 0.62, 0.55, 0.8, 1.0)
    bw = w / (len(vals) * 1.6)
    for i, v in enumerate(vals):
        bx = x + 8 + i * bw * 1.6
        pg.box(bx, base - (h - 16) * v, bw, (h - 16) * v, (64, 178, 110))
    pts = [(x + 10 + i * bw * 1.6, base - (h - 14) * v - 3) for i, v in enumerate(vals)]
    pg.lines(pts, 2.4, (250, 200, 40))
    pg.fill([(pts[-1][0] + 8, pts[-1][1] - 2), (pts[-1][0] - 2, pts[-1][1] - 7),
             (pts[-1][0] - 1, pts[-1][1] + 4)], (250, 200, 40))


def scene_climate(pg, x, y, w, h):
    pg.box(x, y, w, h, (214, 232, 226))
    cx, cy = x + w * 0.34, y + h / 2
    pg.disc(cx, cy, h * 0.36, (84, 140, 190))
    pg.fill([(cx - 12, cy - 8), (cx - 2, cy - 13), (cx + 3, cy - 4), (cx - 6, cy + 1)], (70, 150, 90))
    pg.fill([(cx + 2, cy + 6), (cx + 13, cy + 3), (cx + 12, cy + 13), (cx + 3, cy + 12)], (70, 150, 90))
    tx = x + w * 0.60
    pg.box(tx, y + 6, 7, h - 16, WHITE)
    pg.frame(tx, y + 6, 7, h - 16, INK, 1.2)
    pg.disc(tx + 3.5, y + h - 9, 6.5, RED)
    pg.box(tx + 2, y + h - 24, 4, 16, RED)
    draw(pg, "1.5C", x + w - 4, y + 9, 12, RED, bold=True, align="right")


def scene_tents(pg, x, y, w, h):
    pg.box(x, y, w, h, (196, 208, 220))
    for i in range(9):
        rx = x + 6 + i * (w - 12) / 8
        pg.line(rx, y + 4, rx - 3, y + 15, 1.3, (90, 120, 160))
    for i, tx in enumerate((x + w * 0.16, x + w * 0.44, x + w * 0.72)):
        ty = y + h - 14
        pg.fill([(tx - 16, ty), (tx, ty - 15), (tx + 16, ty)], (226, 220, 204))
        pg.lines([(tx - 16, ty), (tx, ty - 15), (tx + 16, ty)], 1.6, (110, 100, 84))
    pg.box(x, y + h - 9, w, 9, SEA)
    pg.lines([(x + 4, y + h - 5), (x + w * 0.4, y + h - 6), (x + w * 0.7, y + h - 4),
              (x + w - 4, y + h - 6)], 1.4, WHITE)


def scene_vote(pg, x, y, w, h):
    pg.box(x, y, w, h, (232, 228, 214))
    cx = x + w / 2
    pg.fill([(cx - 30, y + 14), (cx + 30, y + 14), (cx + 22, y + 20), (cx - 22, y + 20)], (52, 60, 70))
    pg.disc(cx, y + 11, 5, (52, 60, 70))
    for i in range(4):
        pg.box(cx - 24 + i * 13, y + 21, 5, h - 30, (250, 248, 240))
    pg.lines([(x + 10, y + 12), (x + 20, y + 22), (x + 38, y + 4)], 4.5, RED)


def scene_missile(pg, x, y, w, h):
    pg.box(x, y, w, h, (30, 36, 52))
    for sx, sy in ((0.12, 0.3), (0.3, 0.62), (0.55, 0.2), (0.8, 0.5), (0.66, 0.75)):
        pg.disc(x + w * sx, y + h * sy, 1.4, WHITE)
    pg.fill([(x + w * 0.58, y + h * 0.62), (x + w * 0.78, y + h * 0.30), (x + w * 0.86, y + h * 0.38),
             (x + w * 0.66, y + h * 0.70)], (210, 214, 220))
    pg.fill([(x + w * 0.60, y + h * 0.64), (x + w * 0.50, y + h * 0.78), (x + w * 0.58, y + h * 0.80)],
            (244, 150, 44))
    # shield arc catching it
    pts = []
    for i in range(13):
        ang = math.radians(200 - i * 12)
        pts.append((x + w * 0.30 + 20 * math.cos(ang), y + h * 0.52 + 20 * math.sin(ang)))
    pg.lines(pts, 3, (84, 170, 220))
    pg.disc(x + w * 0.30, y + h * 0.52, 3, (84, 170, 220))


def scene_atom(pg, x, y, w, h):
    pg.box(x, y, w, h, (24, 30, 44))
    cx, cy = x + w / 2, y + h / 2
    for ang in (0, 60, 120):
        pts = []
        for i in range(25):
            t = math.radians(i * 360 / 24)
            ex, ey = 26 * math.cos(t), 10 * math.sin(t)
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            pts.append((cx + ex * ca - ey * sa, cy + ex * sa + ey * ca))
        pg.lines(pts, 1.6, (120, 190, 230), close=True)
    pg.disc(cx, cy, 5, (250, 200, 40))


def scene_star(pg, x, y, w, h):
    pg.box(x, y, w, h, WHITE)
    pg.box(x, y, w, 7, (52, 92, 168))
    pg.box(x, y + h - 7, w, 7, (52, 92, 168))
    cx, cy = x + w / 2, y + h / 2
    pts = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        r = 11 if i % 2 == 0 else 4.6
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    pg.fill(pts, (52, 92, 168))


def scene_voyager(pg, x, y, w, h):
    pg.box(x, y, w, h, (10, 12, 26))
    for sx, sy in ((0.08, 0.25), (0.2, 0.7), (0.45, 0.18), (0.7, 0.8), (0.88, 0.3), (0.6, 0.55)):
        pg.disc(x + w * sx, y + h * sy, 1.3, WHITE)
    cx, cy = x + w * 0.34, y + h * 0.5
    pg.disc(cx, cy, 9, (216, 220, 226))
    pg.disc(cx - 3, cy - 3, 3.4, (150, 156, 164))
    pg.line(cx + 6, cy + 4, cx + 26, cy + 12, 2, (216, 220, 226))
    pg.disc(cx + 28, cy + 13, 3, GOLD)
    for i in range(3):
        pts = []
        for k in range(9):
            ang = math.radians(-40 + k * 10)
            r = 16 + i * 7
            pts.append((x + w * 0.78 + r * math.cos(ang) * 0.5, y + h * 0.30 + r * math.sin(ang)))
        pg.lines(pts, 1.6, (120, 190, 230))


def scene_rain(pg, x, y, w, h):
    pg.box(x, y, w, h, (178, 196, 214))
    for cx, cy, r in ((x + w * 0.3, y + 12, 10), (x + w * 0.5, y + 9, 13), (x + w * 0.72, y + 12, 10)):
        pg.disc(cx, cy, r, (240, 244, 248))
    pg.box(x + w * 0.16, y + 10, w * 0.68, 9, (240, 244, 248))
    for i in range(8):
        rx = x + 8 + i * (w - 16) / 7
        pg.line(rx, y + 24, rx - 3, y + 33, 1.5, (52, 92, 168))
    pg.box(x, y + h - 8, w, 8, SEA)
    pg.lines([(x + 3, y + h - 5), (x + w * 0.35, y + h - 7), (x + w * 0.65, y + h - 4),
              (x + w - 3, y + h - 6)], 1.4, WHITE)


# ---------------------------------------------------------------- the map
# A dotted world: land is a set of soft blobs on a 56x26 grid, drawn as
# dots; numbered pins mark the card stories (positions approximate).
LAND = [
    # (centre col, centre row, radius col, radius row)
    (8, 4, 7.5, 3.6), (3, 2, 2.4, 1.4), (16, 2, 2.6, 1.5), (7, 9, 3.2, 1.8),
    (13, 15, 3.2, 3.2), (14, 20, 2.0, 2.8),
    (28, 4, 4.2, 2.4), (26, 3, 1.0, 1.0),
    (30, 11, 5.0, 4.0), (31, 16, 3.4, 2.8), (36, 16, 0.9, 1.8),
    (41, 4, 10.5, 3.4), (38, 10, 2.6, 2.6), (45, 10, 2.0, 2.0),
    (48, 17, 4.2, 2.4),
]
ISLANDS = [(43, 13), (45, 13), (47, 14), (49, 13), (51, 6), (50, 5), (52, 17), (53, 18)]
PINS = {  # story number -> (col, row) on the map grid
    1: (46, 8), 2: (38.5, 6.5), 3: (27.5, 3), 4: (32.5, 2.5), 5: (11, 5),
    6: (33.5, 5.5), 7: (36, 8.5), 8: (10, 6.5), 9: (40, 9.5), 10: (49, 5.5),
    11: (34.5, 7.5), 13: (3, 6),
}


def draw_map(pg, x, y, w, h):
    draw(pg, "WHERE IT HAPPENED", x, y, 12.5, INK, bold=True)
    gx, gy = x + 2, y + 22
    gw, gh = w - 4, h - 46
    cell_w, cell_h = gw / 56, gh / 26
    for row in range(26):
        for col in range(56):
            land = any(((col - c) / rc) ** 2 + ((row - r) / rr) ** 2 <= 1.0
                       for c, r, rc, rr in LAND) or (col, row) in ISLANDS
            if land:
                pg.disc(gx + col * cell_w + cell_w / 2, gy + row * cell_h + cell_h / 2,
                        min(cell_w, cell_h) * 0.44, (193, 182, 152))
    for num, (col, row) in PINS.items():
        region = STORIES[num - 1]["region"]
        cx = gx + col * cell_w + cell_w / 2
        cy = gy + row * cell_h + cell_h / 2
        pg.disc(cx, cy, 8, REGIONS[region])
        label = str(num)
        draw(pg, label, cx - text_w(label, 9.5) / 2, cy - 4.5, 9.5, WHITE, bold=True)
    deep = "12 · VOYAGER - OFF THE MAP, TO DEEP SPACE"
    draw(pg, deep, x + w - text_w(deep, 8.5), y + h - 25, 8.5, REGIONS["GLOBAL"], bold=True)
    draw(pg, "PINS: STORIES 1-13 · POSITIONS APPROXIMATE", x, y + h - 12, 8.5, FAINT)


# ---------------------------------------------------------------- cards
def badge(pg, cx, cy, num, region, r=10):
    pg.disc(cx, cy, r, REGIONS[region])
    label = str(num)
    size = 11 if num < 10 else 9
    draw(pg, label, cx - text_w(label, size) / 2, cy - size * 0.52, size, WHITE, bold=True)


def kicker(pg, x, y, story, w, small=False):
    r = 7.5 if small else 10
    badge(pg, x + r, y + r - 1, story["n"], story["region"], r)
    label = story["region"] + " · " + story["topic"]
    draw(pg, label, x + 2 * r + 5, y + 1, 8.6 if small else 11.5,
         REGIONS[story["region"]], bold=True)
    if not small:
        tag = story["tag"]
        draw(pg, tag, x + w - text_w(tag, 9), y + 2, 9, FAINT)


def card(pg, x, y, w, h, story, big=False):
    pg.box(x, y, w, h, SHEET)
    pg.frame(x, y, w, h, RULE, 1.2)
    art_h = 56 if big else 32
    story["scene"](pg, x + 5, y + 5, w - 10, art_h)
    cap = story["caption"]
    pg.box(x + 5, y + 5 + art_h - 13, w - 10, 13, (16, 20, 28))
    fit(pg, cap, x + 10, y + 5 + art_h - 10.5, 8.5, WHITE, w - 20, bold=True)
    ky = y + 5 + art_h + 6
    kicker(pg, x + 8, ky, story, w - 16, small=not big)
    ty = ky + (24 if big else 18)
    end, _ = block(pg, story["head"], x + 10, ty, 17.5 if big else 13.5, INK,
                   w - 20, gap=1.12, bold=True)
    block(pg, story["body"], x + 10, end + 3, 10.5 if big else 9.8, SOFT,
          w - 20, gap=1.38 if big else 1.32)


# ---------------------------------------------------------------- stories
# Thursday 19 November 2026. Every item below is from the day's own
# reporting as gathered and cross-checked in NOTES.md; nothing here is
# carried over from another day, and claims are attributed as claims.
STORIES = [
    dict(n=1, region="ASIA", topic="SUMMIT", tag="REUTERS · AP", scene=scene_summit,
         caption="SHENZHEN · APEC SIDELINES",
         head="Trump, Xi and Putin hold first three-way summit",
         body="The first US-China-Russia summit, on the APEC sidelines. Agenda: "
              "two wars, nuclear arms, trade and AI."),
    dict(n=2, region="MIDDLE EAST", topic="WAR", tag="AFP WIRES", scene=scene_gulf,
         caption="KUWAIT · BAHRAIN · HORMUZ",
         head="Iran strikes US bases in Kuwait and Bahrain",
         body="Retaliation for the US strike on Qeshm Island. A tanker was also "
              "struck near Oman, in Hormuz."),
    dict(n=3, region="GLOBAL", topic="JUSTICE", tag="UN NEWS", scene=scene_court,
         caption="THE HAGUE · THE UN COURT",
         head="World Court to rule on Myanmar genocide case",
         body="The UN court is to rule whether Myanmar's campaign against the "
              "Rohingya amounted to genocide."),
    dict(n=4, region="EUROPE", topic="WAR", tag="EN.H.UA", scene=scene_bridge,
         caption="KERCH STRAIT · THIRD HIT",
         head="Crimean Bridge hit a third time",
         body="Ukraine struck the bridge overnight; traffic halted. "
              "Aksyonov confirmed."),
    dict(n=5, region="AMERICAS", topic="MARKETS", tag="ONE TURN", scene=scene_chart,
         caption="WALL STREET · RECORD IPO",
         head="Anthropic's record $83 IPO",
         body="A record $83-a-share debut. AI worries drag stocks: FTSE "
              "-1.3%, Brent $89."),
    dict(n=6, region="GLOBAL", topic="CLIMATE", tag="AFP WIRES", scene=scene_climate,
         caption="ANTALYA · FINAL STRETCH",
         head="COP31 deadlocked in Antalya",
         body="The draft concedes 1.5C is gone; 144 items disputed. Talks "
              "close Friday."),
    dict(n=7, region="MIDDLE EAST", topic="AID", tag="PARIS EYE", scene=scene_tents,
         caption="GAZA · WINTER RAINS",
         head="Floods wreck 40,000 Gaza shelters",
         body="Winter rains damaged over 40,000 family shelters. 1.7M people "
              "displaced."),
    dict(n=8, region="AMERICAS", topic="POLITICS", tag="NDTV", scene=scene_vote,
         caption="WASHINGTON · THE HOUSE",
         head="Jeffries to lead the House",
         body="Democrats pick Hakeem Jeffries, set to be the first Black "
              "speaker."),
    dict(n=9, region="MIDDLE EAST", topic="WAR", tag="AFP WIRES", scene=scene_missile,
         caption="RIYADH · AIR DEFENCE",
         head="Saudi Arabia downs a Houthi missile",
         body="Cruise missile downed; jets bomb Yemen. Houthis say 17 died."),
    dict(n=10, region="ASIA", topic="NUCLEAR", tag="IAEA", scene=scene_atom,
         caption="VIENNA · THE WATCHDOG",
         head="North Korea expands uranium work",
         body="The IAEA says Pyongyang has expanded its uranium enrichment."),
    dict(n=11, region="MIDDLE EAST", topic="ISRAEL", tag="ONE TURN", scene=scene_star,
         caption="JERUSALEM · PRESIDENCY",
         head="Eisenkot tapped to form a government",
         body="President Herzog asks Eisenkot to form a government."),
    dict(n=12, region="GLOBAL", topic="SPACE", tag="ONE TURN", scene=scene_voyager,
         caption="DEEP SPACE · LIGHT-DAY",
         head="Voyager 1 reaches one light-day",
         body="The probe is now one light-day out from Earth."),
    dict(n=13, region="AMERICAS", topic="WEATHER", tag="ONE TURN", scene=scene_rain,
         caption="CALIFORNIA · RECORD RAIN",
         head="Record rain floods California",
         body="An atmospheric river drops record rain on California."),
]

ALSO = [  # (number, region, lead, text) — one line each
    (14, "ASIA", "Shenzhen", "Trump and Xi met one-to-one first, at Kylin Villa."),
    (15, "GLOBAL", "At sea", "Carrier Theodore Roosevelt redeploys to the region."),
    (16, "EUROPE", "Brussels", "EU governments approve the Indonesia trade deal."),
    (17, "EUROPE", "Brussels", "EU proposes a 45bn-euro loan for Ukraine."),
    (18, "GLOBAL", "Gaza aid", "Four nations demand Israel open access for aid."),
    (19, "AMERICAS", "Markets", "S&P 500 -0.23%; Hang Seng falls 2.78% on AI fears."),
    (20, "GLOBAL", "Arms talks", "New START, the nuclear pact, expired in February."),
]

KPIS = [
    ("3", "presidents at one table in Shenzhen", INK),
    ("$83", "Anthropic's record IPO price a share", INK),
    ("40,000+", "family shelters damaged in Gaza", RED),
    ("1.7M", "people displaced in Gaza", RED),
    ("144", "items still disputed at COP31", INK),
    ("-2.78%", "the Hang Seng's fall on the day", RED),
]

REGION_BAR = [("ASIA", 3), ("MIDDLE EAST", 4), ("EUROPE", 3), ("AMERICAS", 4), ("GLOBAL", 6)]


# ---------------------------------------------------------------- the page
MX = 36
CW = PAGE - 2 * MX  # 952


def paint():
    pg = Painter(PAGE, PAGE, PAPER)

    # utility line + masthead
    draw(pg, "THE WORLD IN ONE DAY", MX, 22, 12.5, RED, bold=True)
    right = "20 STORIES · 5 REGIONS · ALL FROM THIS ONE DAY"
    draw(pg, right, MX + CW - text_w(right, 12.5), 22, 12.5, FAINT, bold=True)
    fit(pg, "Thursday 19 November 2026", MX, 44, 54, INK, CW, bold=True)
    pg.box(MX, 112, CW, 3.2, INK)
    pg.box(MX, 118, CW, 1.2, INK)
    strap = ("Three leaders meet in Shenzhen · A World Court ruling on "
             "Myanmar · COP31 deadlocked in Antalya")
    fit(pg, strap, MX, 126, 13.5, RED, CW, bold=True)

    # region bar: segments sized by story count, the page's colour key
    bx = MX
    for name, count in REGION_BAR:
        wseg = CW * count / 20
        pg.box(bx, 148, wseg - 2, 19, REGIONS[name])
        label = name + " " + str(count)
        draw(pg, label, bx + (wseg - 2 - text_w(label, 10.5)) / 2, 152, 10.5, WHITE, bold=True)
        bx += wseg

    # the day in numbers
    pg.box(MX, 176, CW, 1.2, RULE)
    cell = CW / 6
    for i, (num, cap, colour) in enumerate(KPIS):
        cx = MX + i * cell
        if i:
            pg.box(cx, 180, 1.2, 40, RULE)
        fit(pg, num, cx + 8, 180, 26, colour, cell - 16, bold=True)
        block(pg, cap, cx + 8, 208, 9.3, SOFT, cell - 14, gap=1.26)
    pg.box(MX, 233, CW, 1.2, RULE)

    # three large cards
    y = 241
    w3 = (CW - 24) / 3
    for i in range(3):
        card(pg, MX + i * (w3 + 12), y, w3, 200, STORIES[i], big=True)
    # two rows of five smaller cards
    w5 = (CW - 42) / 5
    for row, yy in ((0, 449), (1, 619)):
        for i in range(5):
            card(pg, MX + i * (w5 + 10.5), yy, w5, 162, STORIES[3 + row * 5 + i])

    # map + also-on-Thursday
    draw_map(pg, MX, 793, 302, 146)
    ax = MX + 326
    draw(pg, "ALSO ON THURSDAY 19 NOVEMBER", ax, 793, 13, RED, bold=True)
    pg.box(ax, 813, PAGE - MX - ax, 1.2, RULE)
    for i, (num, region, lead, text) in enumerate(ALSO):
        iy = 823 + i * 16.5
        badge(pg, ax + 8, iy + 5, num, region, 7.5)
        end = draw(pg, lead + " — ", ax + 22, iy, 10.8, INK, bold=True)
        draw(pg, text, end, iy, 10.8, SOFT)

    # date check
    dy = 947
    pg.frame(MX, dy, CW, 46, RED, 1.6)
    draw(pg, "DATE CHECK", MX + 10, dy + 7, 11.5, RED, bold=True)
    note = ("Left out on purpose: the week's first two Crimean Bridge strikes, earlier in "
            "the week · COP31's close, due Friday 20 November · New START's expiry, back in "
            "February. All 20 stories happened, or were first reported, on Thursday "
            "19 November 2026; contested claims are attributed.")
    block(pg, note, MX + 104, dy + 6, 9.8, SOFT, CW - 118, gap=1.32)

    # footer
    draw(pg, "SOURCES: REUTERS · AP · AFP · BBC · CBS · UN", MX, 1006, 9.5, FAINT)
    tail = "ORIGINAL DRAWINGS, DRAWN IN CODE · 2026-11-19"
    draw(pg, tail, MX + CW - text_w(tail, 9.5), 1006, 9.5, FAINT)
    return pg


def encode_png(pg):
    raw = bytearray()
    stride = pg.w * 3
    for yy in range(pg.h):
        raw.append(0)
        raw += pg.buf[yy * stride:(yy + 1) * stride]
    payload = zlib.compress(bytes(raw), 9)

    def chunk(kind, data):
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", pg.w, pg.h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
            chunk(b"IDAT", payload) + chunk(b"IEND", b""))


def main():
    data = encode_png(paint())
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    try:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "entry.png")
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entry.png")
        with open(path, "wb") as fh:
            fh.write(data)
    print("wrote", path, len(data), "bytes")


if __name__ == "__main__":
    main()
